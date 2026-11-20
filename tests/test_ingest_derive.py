"""企业数据导入·推导规则测试（ADR-0013；工单 02）。

对样例模板改格后重导，锁定三条推导规则：
- 中间年期初 = 上年期末（可推导，非必填）；
- 分红/增资双缺 → 残差归分红、增资记 0（derived 披露）；
- 首年期初缺 → 拒绝（无上年期末可链，事实必填；工单 03 升级为收集式违例）。
"""
import json
from pathlib import Path

from openpyxl import load_workbook

from ipo_eval_lab.ingest.importer import import_profile
from ipo_eval_lab.ingest.template import FIN_ROWS, build_sample_template

ROW = {r.key: r.row for r in FIN_ROWS}


def _blank_cells(src: Path, dst: Path, coords: list[str]) -> Path:
    """复制样例模板并清空指定格（坐标如 "C15"）。"""
    wb = load_workbook(src)
    ws = wb["财务三年一期"]
    for c in coords:
        ws[c] = None
    wb.save(dst)
    return dst


def test_derive_opening_from_prev_closing(tmp_path: Path) -> None:
    """中间年期初留空 → 由上年期末推导，值与显式填写一致。"""
    src = tmp_path / "s.xlsx"
    build_sample_template(src)
    xlsx = _blank_cells(
        src, tmp_path / "blank_opening.xlsx",
        [f"C{ROW['equity_roll.opening_attrib_parent']}", f"D{ROW['equity_roll.opening_attrib_parent']}"],
    )

    result = import_profile(xlsx, "sample_co_01", out_root=tmp_path)
    profile = json.loads((result.company_dir / "profile.json").read_text(encoding="utf-8"))  # type: ignore[union-attr]
    assert [s["equity_roll"]["opening_attrib_parent"] for s in profile["statements"]] == [
        92_000_000, 105_000_000, 125_000_000,
    ]
    assert "equity_roll.opening_attrib_parent" in result.derived_fields


def test_derive_dividends_residual_injection_zero(tmp_path: Path) -> None:
    """分红/增资双缺 → 分红 = 期初+净利−期末，增资 = 0，双双入 derived。"""
    src = tmp_path / "s.xlsx"
    build_sample_template(src)
    xlsx = _blank_cells(
        src, tmp_path / "blank_dvd.xlsx",
        [f"{c}{ROW['equity_roll.dividends']}" for c in "BCD"]
        + [f"{c}{ROW['equity_roll.capital_injection']}" for c in "BCD"],
    )

    result = import_profile(xlsx, "sample_co_01", out_root=tmp_path)
    profile = json.loads((result.company_dir / "profile.json").read_text(encoding="utf-8"))  # type: ignore[union-attr]
    rolls = [s["equity_roll"] for s in profile["statements"]]
    # 2023: 92+15−105=2；2024: 105+18−125=−2（增资年，残差为负即净增资>净利留存）
    assert [r["dividends"] for r in rolls] == [2_000_000, -2_000_000, 2_000_000]
    assert [r["capital_injection"] for r in rolls] == [0, 0, 0]
    assert {"equity_roll.dividends", "equity_roll.capital_injection"} <= set(result.derived_fields)


def test_first_year_opening_missing_is_violation(tmp_path: Path) -> None:
    """首年期初缺 → 无上年期末可链：收集式违例（工单 03），带坐标，不落盘。"""
    src = tmp_path / "s.xlsx"
    build_sample_template(src)
    xlsx = _blank_cells(src, tmp_path / "no_opening.xlsx", [f"B{ROW['equity_roll.opening_attrib_parent']}"])

    result = import_profile(xlsx, "sample_co_01", out_root=tmp_path / "out")
    assert result.status == "violations"
    assert result.company_dir is None
    assert any("期初归母所有者权益" in str(v) for v in result.violations), [str(v) for v in result.violations]
    assert not list(tmp_path.glob("out/sample_co_01_*")), "违例时不应留下半成品目录"
