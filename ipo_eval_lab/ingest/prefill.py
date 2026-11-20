"""预填模板（ADR-0013 修订 1；工单 01）：客户只改错格，不必从头填。

复制客户上传的原件：违例格**清空 + 红底**，并在该行的「校验批注」列写明原因——
不用单元格批注（VML 旧部件，钉钉/企微/在线表格等 JS 预览器普遍炸），原因直接可见；
无坐标的勾稽层违例不指涉单格，汇总落在批注列表尾。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from .importer import Violation

_ERR_FILL = PatternFill(start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid")

# 各 sheet 的校验批注列 = 模板既有网格之外的第一空列（importer 按坐标常量读格，不读这些列）
_NOTE_COL = {"主体信息": "C", "财务三年一期": "F", "申报口径": "D"}


def build_prefill_template(
    src_xlsx: Path | str, violations: Iterable[Violation], out_path: Path | str
) -> Path:
    """错误格清空标红、原因落批注列、正确值原样保留；返回落盘路径。"""
    wb = load_workbook(Path(src_xlsx))
    by_sheet: dict[str, list[Violation]] = {}
    for v in violations:
        by_sheet.setdefault(v.sheet, []).append(v)

    for sheet, vs in by_sheet.items():
        if sheet not in wb.sheetnames or sheet not in _NOTE_COL:
            continue
        ws = wb[sheet]
        col = _NOTE_COL[sheet]
        head = ws[f"{col}1"]
        head.value = "校验批注（改完红底格后重新上传）"
        head.font = Font(bold=True)
        ws.column_dimensions[col].width = 34
        tail = ws.max_row + 2  # 无坐标（勾稽层）违例的表尾汇总区
        for v in vs:
            if v.coord is None:
                ws[f"{col}{tail}"] = f"⚠ {v.reason}"
                tail += 1
                continue
            cell = ws[v.coord]
            cell.value = None
            cell.fill = _ERR_FILL
            row = "".join(ch for ch in v.coord if ch.isdigit())
            ws[f"{col}{row}"] = f"⚠ {v.reason}"

    p = Path(out_path)
    wb.save(p)
    return p
