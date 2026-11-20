"""违例结构化与预填模板（ADR-0013 修订 1；工单 01）。

Violation 是 webui 分组渲染与预填标红的数据前提；CLI 行文经 __str__ 保持兼容。
预填闭环：错误格清空+批注 → 客户填回正确值重导 → ok。
"""
import json
from pathlib import Path

from openpyxl import load_workbook

from ipo_eval_lab.ingest.importer import Violation, import_profile
from ipo_eval_lab.ingest.prefill import build_prefill_template
from ipo_eval_lab.ingest.template import FIN_ROWS, build_sample_template

ROW = {r.key: r.row for r in FIN_ROWS}
FIN = "财务三年一期"


def _broken(tmp_path: Path, edits: dict[str, object]) -> Path:
    src = tmp_path / "s.xlsx"
    build_sample_template(src)
    wb = load_workbook(src)
    for coord, v in edits.items():
        wb[FIN][coord] = v
    out = tmp_path / "broken.xlsx"
    wb.save(out)
    return out


def test_cell_violations_structured_with_coord(tmp_path: Path) -> None:
    """格层违例是 Violation 实例：sheet/坐标/中文字段齐备，__str__ 兼容 CLI 行文。"""
    xlsx = _broken(tmp_path, {f"C{ROW['income.operating_revenues']}": None,
                              f"D{ROW['audit.status']}": "已审计过"})
    r = import_profile(xlsx, "acme_01", out_root=tmp_path / "out")

    assert r.status == "violations"
    assert all(isinstance(v, Violation) for v in r.violations)
    coords = {v.coord for v in r.violations}
    assert coords == {"C2", f"D{ROW['audit.status']}"}
    joined = "\n".join(str(v) for v in r.violations)
    assert "财务三年一期!C2 营业收入（元）：必填缺失" in joined
    assert "审计状态" in joined


def test_cross_check_violation_wrapped_no_coord(tmp_path: Path) -> None:
    """勾稽层违例包成 coord=None 的 Violation，reason 带勾稽号原文。"""
    xlsx = _broken(tmp_path, {f"B{ROW['balance.total_assets']}": 199_999_999})
    r = import_profile(xlsx, "acme_01", out_root=tmp_path / "out")

    assert r.status == "violations"
    v = next(v for v in r.violations if v.coord is None)
    assert v.sheet == FIN and "勾稽①" in v.reason
    assert str(v) == v.reason  # 无坐标无 label → 纯 reason，CLI 行文不变


def test_prefill_blanks_marks_keeps_valid_cells(tmp_path: Path) -> None:
    """预填：错误格清空+红底，原因落「校验批注」列（F 列，不依赖悬停批注）；正确格原样保留。"""
    xlsx = _broken(tmp_path, {f"C{ROW['income.operating_revenues']}": None,
                              f"D{ROW['audit.status']}": "已审计过"})
    r = import_profile(xlsx, "acme_01", out_root=tmp_path / "out")
    prefill = build_prefill_template(xlsx, r.violations, tmp_path / "prefill.xlsx")
    ws = load_workbook(prefill)[FIN]

    c2 = ws[f"C{ROW['income.operating_revenues']}"]
    assert c2.value is None and c2.fill.fill_type == "solid"
    assert "必填缺失" in ws[f"F{ROW['income.operating_revenues']}"].value  # 批注列同行可见
    d18 = ws[f"D{ROW['audit.status']}"]
    assert d18.value is None and "已审计" in ws[f"F{ROW['audit.status']}"].value
    assert ws["F1"].value.startswith("校验批注")

    src = load_workbook(xlsx)[FIN]  # 未涉错的格逐格保留
    assert ws[f"B{ROW['income.operating_revenues']}"].value == src["B2"].value
    assert ws[f"B{ROW['balance.total_assets']}"].value == src[f"B{ROW['balance.total_assets']}"].value


def test_prefill_roundtrip_closes_loop(tmp_path: Path) -> None:
    """闭环：预填件把错误格填回正确值 → 重导 ok（客户改完就能过）。"""
    xlsx = _broken(tmp_path, {f"C{ROW['income.operating_revenues']}": None,
                              f"D{ROW['audit.status']}": "已审计过"})
    r = import_profile(xlsx, "acme_01", out_root=tmp_path / "out")
    prefill = build_prefill_template(xlsx, r.violations, tmp_path / "prefill.xlsx")

    wb = load_workbook(prefill)
    ws = wb[FIN]
    ws[f"C{ROW['income.operating_revenues']}"] = 150_000_000
    ws[f"D{ROW['audit.status']}"] = "已审计"
    fixed = tmp_path / "fixed.xlsx"
    wb.save(fixed)

    r2 = import_profile(fixed, "acme_01", out_root=tmp_path / "out")
    assert r2.status == "ok", [str(v) for v in r2.violations]
    profile = json.loads((r2.company_dir / "profile.json").read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert profile["statements"][1]["income"]["operating_revenues"] == 150_000_000
