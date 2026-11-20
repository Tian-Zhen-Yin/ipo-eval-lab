"""企业数据接入·模板底稿测试（ADR-0013；工单 01）。

模板是 importer 与客户的单一事实源：坐标常量声明「哪个字段住在哪个格子」。
- build_sample_template：必填格必须有值（golden 对拍夹具的前提），申报口径 sheet
  填一半留一半（「留空合法」路径的夹具）；
- build_blank_template：发给客户的底稿，值区全空、表头与科目列齐全。
"""
from pathlib import Path

from openpyxl import load_workbook

from ipo_eval_lab.ingest.template import (
    DECL_ROWS,
    DECL_VALUE_COL,
    FIN_ROWS,
    HEADER_ROW,
    SHEET_DECLARED,
    SHEET_FIN,
    SHEET_SUBJECT,
    SUBJECT_ROWS,
    SUBJECT_VALUE_COL,
    YEAR_COLS,
    build_blank_template,
    build_sample_template,
)


def test_sample_template_required_cells_filled(tmp_path: Path) -> None:
    """样例模板：财务 sheet 每个必填科目 × 每个年度列都有值；主体信息必填项有值。"""
    p = tmp_path / "sample.xlsx"
    build_sample_template(p)

    ws = load_workbook(p)[SHEET_FIN]
    for row in FIN_ROWS:
        if not row.required:
            continue
        for col in YEAR_COLS:
            v = ws[f"{col}{row.row}"].value
            assert v not in (None, ""), f"{row.label}（{col}{row.row}）为必填格，样例不应为空"

    ws_sub = load_workbook(p)[SHEET_SUBJECT]
    for row in SUBJECT_ROWS:
        if not row.required:
            continue
        v = ws_sub[f"B{row.row}"].value
        assert v not in (None, ""), f"{row.label}（B{row.row}）为必填项，样例不应为空"


def test_sample_template_years_header_consecutive(tmp_path: Path) -> None:
    """年度表头：三个整数年份、升序且相邻（勾稽④的模板侧前置）。"""
    p = tmp_path / "sample.xlsx"
    build_sample_template(p)

    ws = load_workbook(p)[SHEET_FIN]
    years = [ws[f"{col}{HEADER_ROW}"].value for col in YEAR_COLS]
    assert all(isinstance(y, int) for y in years), f"表头年份应为整数，实际 {years}"
    assert years == sorted(years) and all(b - a == 1 for a, b in zip(years, years[1:])), (
        f"表头年份应连续递增，实际 {years}"
    )


def test_blank_template_value_area_empty(tmp_path: Path) -> None:
    """空白底稿：所有值区为空（客户填），但科目列与 sheet 结构必须齐全。"""
    p = tmp_path / "blank.xlsx"
    build_blank_template(p)
    wb = load_workbook(p)

    ws_fin, ws_sub, ws_dec = wb[SHEET_FIN], wb[SHEET_SUBJECT], wb[SHEET_DECLARED]
    for row in FIN_ROWS:
        assert ws_fin[f"A{row.row}"].value, f"科目列 A{row.row} 不应为空"
        for col in (*YEAR_COLS, "E"):
            assert ws_fin[f"{col}{row.row}"].value in (None, ""), (
                f"空白底稿 {col}{row.row} 应为空"
            )
    for row in SUBJECT_ROWS + DECL_ROWS:
        for sheet, vcol in ((ws_sub, SUBJECT_VALUE_COL), (ws_dec, DECL_VALUE_COL)):
            if sheet is ws_sub and row not in SUBJECT_ROWS:
                continue
            if sheet is ws_dec and row not in DECL_ROWS:
                continue
            assert sheet[f"A{row.row}"].value, f"项目列 A{row.row} 不应为空"
            assert sheet[f"{vcol}{row.row}"].value in (None, ""), (
                f"空白底稿 {sheet.title} {vcol}{row.row} 应为空"
            )


def test_sample_declared_partial_fill(tmp_path: Path) -> None:
    """申报口径夹具必须「填一半留一半」：留空合法（null → indeterminate）路径要有覆盖。"""
    p = tmp_path / "sample.xlsx"
    build_sample_template(p)
    ws = load_workbook(p)[SHEET_DECLARED]

    filled = [r for r in DECL_ROWS if ws[f"{DECL_VALUE_COL}{r.row}"].value not in (None, "")]
    empty = [r for r in DECL_ROWS if ws[f"{DECL_VALUE_COL}{r.row}"].value in (None, "")]
    assert len(filled) >= 5, "样例应填一部分，作为正向夹具"
    assert len(empty) >= 5, "样例应留一部分空，作为「留空合法」夹具"
