"""原文库数据查看：rulebook/source_texts/*.yaml → results/source_texts_view.xlsx

临时工具（.scratch），产物落 results/（不入 git）。
"""
import sys
from pathlib import Path

import yaml
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "rulebook" / "source_texts"
OUT = ROOT / "results" / "source_texts_view.xlsx"

BOARD_LABEL = {
    "sse_main_2026": "上交所主板",
    "sse_star_2026": "科创板",
    "szse_main_2026": "深交所主板",
    "szse_chinext_2026": "创业板",
    "bse_2026": "北交所",
}

wb = Workbook()

# ---- Sheet 1: 总览 ----
ws = wb.active
ws.title = "总览"
ws.append(["板块", "law_id", "条文数", "章节数", "现行版", "生效日(修订月)"])
header_fill = PatternFill("solid", fgColor="D9E2F3")
for c in ws[1]:
    c.font = Font(bold=True)
    c.fill = header_fill

for f in sorted(SRC.glob("*.yaml")):
    if f.name.startswith("_"):
        continue
    data = yaml.safe_load(f.read_text(encoding="utf-8"))
    arts = data["articles"]
    chapters = {a["chapter"] for a in arts if a.get("chapter")}
    ws.append([
        BOARD_LABEL.get(data["law_id"], data["law_id"]),
        data["law_id"],
        len(arts),
        len(chapters),
        "2026年4月修订",
        data["effective_from"],
    ])
for col, w in zip("ABCDEF", (14, 20, 10, 10, 16, 18)):
    ws.column_dimensions[col].width = w

# ---- Sheet 2~6: 每板块一个 sheet，全文可查 ----
for f in sorted(SRC.glob("*.yaml")):
    if f.name.startswith("_"):
        continue
    data = yaml.safe_load(f.read_text(encoding="utf-8"))
    label = BOARD_LABEL.get(data["law_id"], data["law_id"])
    ws = wb.create_sheet(label[:28])
    ws.append(["条款号", "章", "节", "页", "字数", "正文（规范化连续文本）"])
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = header_fill
    for a in data["articles"]:
        ws.append([
            a["article"],
            a.get("chapter") or "",
            a.get("section") or "",
            a["source_offset"]["page"],
            len(a["text"]),
            a["text"],
        ])
    widths = (9, 26, 30, 6, 7, 110)
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=6):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")

OUT.parent.mkdir(exist_ok=True)
wb.save(OUT)
print(f"已生成: {OUT}")
