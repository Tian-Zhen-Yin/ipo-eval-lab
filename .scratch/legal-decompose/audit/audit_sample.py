# -*- coding: utf-8 -*-
"""审核任务 B1：非核心条文抽样审核（每文件 10 条，跨章节，含跨页条文）
子串比对窗口 ±2 页；同时统计全库跨页条文比例。
"""
import io
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

from common import LAWS, load_yaml, pdf_path_of, clean_page_lines

PAGENUM = re.compile(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$")
DOTS = re.compile(r"\.{4,}")

CORE = set()
for ids in [
    ["3.1.1", "3.1.2", "3.1.3"], ["2.1.1", "2.1.2", "2.1.3"], ["3.1.1", "3.1.2"],
    ["2.1.1", "2.1.2", "2.1.3", "2.1.4"], ["2.1.1", "2.1.2", "2.1.3", "2.1.4"],
]:
    CORE.update(ids)


def page_texts(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        pages = [p.get_text() for p in doc]
    cleaned = ["".join(clean_page_lines(t)) for t in pages]
    return cleaned


def main():
    report = {}
    rng = random.Random(42)
    for law in LAWS:
        doc = load_yaml(law)
        arts = doc["articles"]
        pages = page_texts(pdf_path_of(law))
        n = len(pages)
        cache = {}

        def window(center, radius):
            key = (center, radius)
            if key not in cache:
                lo, hi = max(1, center - radius), min(n, center + radius)
                cache[key] = "".join(pages[lo - 1:hi])
            return cache[key]

        # 跨页统计：条文文本不在自身页单独文本中 => 跨页（起于该页、止于后页）
        crosspage = []
        for a in arts:
            p = a["source_offset"]["page"]
            if a["text"] not in pages[p - 1] and a["text"] in window(p, 2):
                crosspage.append(a["article"])

        # 抽样：非核心、按章均匀、保证含跨页
        sample = []
        chapters = []
        for a in arts:
            if a["article"] not in CORE and a["article"] not in {s[0] for s in sample}:
                chapters.append(a)
        # 每章取至多 1-2 条，凑满 10
        by_ch = {}
        for a in chapters:
            by_ch.setdefault((a.get("chapter") or "?").split(" ")[0], []).append(a)
        keys = sorted(by_ch)
        pool = []
        i = 0
        while len(pool) < 14 and i < 60:  # 轮转各章取候选
            k = keys[i % len(keys)]
            lst = by_ch[k]
            if lst:
                pool.append(lst.pop(rng.randrange(len(lst))))
            i += 1
        # 优先纳入跨页条文 2 条
        cp_in = [a for a in pool if a["article"] in set(crosspage)][:2]
        rest = [a for a in pool if a not in cp_in]
        chosen = (cp_in + rest)[:10]

        results = []
        for a in chosen:
            p = a["source_offset"]["page"]
            found_r = None
            for r in (0, 1, 2):
                if a["text"] in (pages[p - 1] if r == 0 else window(p, r)):
                    found_r = r
                    break
            results.append({"article": a["article"], "page": p, "chapter": a.get("chapter"),
                            "section": a.get("section"), "len": len(a["text"]),
                            "status": f"OK(r={found_r})" if found_r is not None else "SUBSTRING_FAIL"})
            if found_r is None:
                pt = window(p, 2)
                idx = pt.find(a["text"][:20])
                results[-1]["ctx"] = pt[max(0, idx - 50):idx + len(a["text"]) + 50] if idx >= 0 else "(找不到开头)"
        report[law] = {"n_articles": len(arts), "n_crosspage": len(crosspage),
                       "crosspage_ids": crosspage[:15], "sample": results}
        fails = [r for r in results if r["status"] == "SUBSTRING_FAIL"]
        print(f"== {law}: 抽样 {len(results)} 条, 跨页条文全库 {len(crosspage)} 条")
        for r in results:
            mark = "跨页" if r["article"] in set(crosspage) else ""
            print(f"   {r['article']:8s} p{r['page']:<4d} {r['status']:10s} len={r['len']:<5d} {mark} {r.get('chapter','')[:18]}")
        for f in fails:
            print("   FAIL ctx:", f.get("ctx", "")[:120])

    with io.open(Path(__file__).resolve().parent / "results_sample_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
