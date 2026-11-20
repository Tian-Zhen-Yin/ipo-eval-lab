"""企业数据导入·违例收集式校验（ADR-0013；工单 03）。

风格对齐 fixtures/loader 的 FixtureDataError：一次收集全部违例再报（逐条带
sheet/坐标/中文字段/勾稽号）；status="violations" 时**不落盘**。
勾稽⑥（增长率区间）是 mock 生成器卫生参数——企业数据不查（ADR-0013 分流）。
"""
import json
from pathlib import Path

from openpyxl import load_workbook

from ipo_eval_lab.ingest.importer import import_profile
from ipo_eval_lab.ingest.template import FIN_ROWS, build_sample_template

ROW = {r.key: r.row for r in FIN_ROWS}
FIN_SHEET = "财务三年一期"


def _sample_with_edits(dst: Path, edits: dict[str, object]) -> Path:
    """复制样例模板并写入指定格（坐标 → 新值；None = 清空）。"""
    src = dst.parent / "s.xlsx"
    build_sample_template(src)
    wb = load_workbook(src)
    for coord, v in edits.items():
        wb[FIN_SHEET][coord] = v
    wb.save(dst)
    return dst


def _import(xlsx: Path, tmp_path: Path):
    return import_profile(xlsx, "sample_co_01", out_root=tmp_path / "out")


def test_missing_required_reported_with_location(tmp_path: Path) -> None:
    """缺必填格：违例带 sheet/坐标/中文字段；不落盘、无半成品目录。"""
    xlsx = _sample_with_edits(tmp_path / "v.xlsx", {f"C{ROW['income.operating_revenues']}": None})

    r = _import(xlsx, tmp_path)
    assert r.status == "violations"
    assert r.company_dir is None
    assert any("C2" in str(v) and "营业收入" in str(v) for v in r.violations), [str(v) for v in r.violations]
    assert not list((tmp_path / "out").glob("sample_co_01_*")) if (tmp_path / "out").exists() else True


def test_all_violations_collected_at_once(tmp_path: Path) -> None:
    """多类错并存（缺必填 / 枚举非法 / 表头年份非整数）：一次报全。"""
    xlsx = _sample_with_edits(
        tmp_path / "v.xlsx",
        {
            f"C{ROW['income.operating_revenues']}": None,                # 缺必填
            f"D{ROW['audit.status']}": "已审计过",                        # 枚举非法
        },
    )
    # 表头年份改坏：B1 写成文本
    wb = load_workbook(xlsx)
    wb[FIN_SHEET]["B1"] = "二〇二三年"
    wb.save(xlsx)

    r = _import(xlsx, tmp_path)
    assert r.status == "violations"
    joined = "\n".join(str(v) for v in r.violations)
    assert "营业收入" in joined and "审计状态" in joined and "表头年份" in joined, r.violations


def test_cross_check_violations_from_loader(tmp_path: Path) -> None:
    """勾稽层违例（①资产≠负债+权益 / ④年份断档）：复用 loader 检查，带勾稽号。"""
    xlsx = _sample_with_edits(
        tmp_path / "v.xlsx",
        {
            f"B{ROW['balance.total_assets']}": 199_999_999,  # ① 破坏恒等式
            "D1": 2026,  # ④ 2024 → 2026 断档
        },
    )

    r = _import(xlsx, tmp_path)
    assert r.status == "violations"
    joined = "\n".join(str(v) for v in r.violations)
    assert "勾稽①" in joined, r.violations
    assert "勾稽④" in joined, r.violations


def test_growth_bound_not_checked_for_enterprise(tmp_path: Path) -> None:
    """勾稽⑥不查企业数据：净利 −95% 下滑不产生「增长率」违例（推导自动保②③）。"""
    xlsx = _sample_with_edits(tmp_path / "v.xlsx", {f"D{ROW['income.net_profit_total']}": 1_000_000})

    r = _import(xlsx, tmp_path)
    assert r.status == "ok", r.violations  # ①~⑤ 全过（roll/调节项按推导自洽）
    assert not any("增长率" in str(v) for v in r.violations)
