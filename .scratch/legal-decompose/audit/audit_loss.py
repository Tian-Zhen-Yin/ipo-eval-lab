# -*- coding: utf-8 -*-
"""严格拼合校验（最终版）：全流 = 前置区 + Σ[间隙 + 条款号 + 条文文本] + 尾部。
每个间隙必须可解释：标题行(CH/SEC) + 标题换行续行(短、无句末标点) + 条款号前缀。
否则 => 正文丢失候选，逐条量化。
"""
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

from common import LAWS, load_yaml, pdf_path_of

CH = re.compile(r"^(第[一二三四五六七八九十百]+章)\s*(.*)$")
SEC = re.compile(r"^(第[一二三四五六七八九十百]+节)\s*(.*)$")
PAGENUM = re.compile(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$")
DOTS = re.compile(r"\.{4,}")
SENT_END = tuple("。；：！？”")


def clean_lines(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        pages = [p.get_text() for p in doc]
    out = []
    for i, t in enumerate(pages, start=1):
        for l in t.split("\n"):
            ls = l.strip()
            if not ls or PAGENUM.match(ls) or DOTS.search(ls):
                continue
            out.append((i, ls))
    return out, pages


HEAD_START = re.compile(r"第[一二三四五六七八九十百]+[章节]")
ID_TAIL = re.compile(r"(\d+\.\d+(?:\.\d+)?)\s*$")
PUNCT = "。；：，！？"


def classify_gap(gap: str):
    """间隙解释器 v2：剥尾部条款号 → 按标题起点切分 → 每段标题后随文本
    若含句读或超长 → 正文内容（丢失候选）。"""
    g = ID_TAIL.sub("", gap.rstrip())
    if not g:
        return ("OK", None)
    # 按标题起点切分：每段 = 标记 + 后随文本（到下一标记）
    marks = list(HEAD_START.finditer(g))
    if not marks:
        # 无标记的间隙：只允许是纯标题续行（短、无句读）
        if len(g) <= 25 and not any(c in g for c in PUNCT):
            return ("OK", None)
        return ("BODY_LOSS", g)
    # 首个标记前的前置文本
    pre = g[: marks[0].start()]
    if pre and (len(pre) > 25 or any(c in pre for c in PUNCT)):
        return ("BODY_LOSS", g)
    for k, m in enumerate(marks):
        seg_end = marks[k + 1].start() if k + 1 < len(marks) else len(g)
        following = g[m.end():seg_end]
        if following and (len(following) > 30 or any(c in following for c in PUNCT)):
            return ("BODY_LOSS", g)
    return ("OK", None)


def main():
    report = {}
    for law in LAWS:
        doc = load_yaml(law)
        arts = doc["articles"]
        lines, _pages = clean_lines(pdf_path_of(law))
        stream = "".join(l for _, l in lines)
        losses = []
        cursor = 0
        for a in arts:
            aid, t = a["article"], a["text"]
            pos = stream.find(t, cursor)
            if pos < 0:
                losses.append({"kind": "NOT_FOUND", "article": aid})
                # 尝试从全流重新定位
                pos2 = stream.find(t)
                if pos2 < 0:
                    continue
                pos = pos2
            gap = stream[cursor:pos]
            if gap:
                kind, bad = classify_gap(gap)
                if kind == "BODY_LOSS":
                    losses.append({"kind": "GAP_BODY_LOSS", "article": aid, "gap": gap})
            cursor = pos + len(t)
        trailing = stream[cursor:]
        if trailing:
            kind, bad = classify_gap(trailing)
            if kind == "BODY_LOSS":
                losses.append({"kind": "TRAILING_LOSS", "gap": trailing})
            else:
                losses.append({"kind": "TRAILING_HEADINGLIKE", "gap": trailing})
        report[law] = losses
        print("=" * 10, law, f"损失候选 {len(losses)}")
        for x in losses:
            g = x.get("gap", "")
            print(f"  [{x['kind']}] before {x.get('article')}: {g[:160]!r}")
    with io.open(Path(__file__).resolve().parent / "results_loss_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
