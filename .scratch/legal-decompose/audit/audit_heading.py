# -*- coding: utf-8 -*-
"""章/节标题字段全量校验：
1) 用 TOC(前6页) 收集权威章/节标题清单，与 YAML 全部 chapter/section 字段对账
2) 穷举 PDF 中所有形似章/节标题的行，用上下文启发式（上一行是否句末收尾/本行是否含句号）
   区分真标题与正文断行伪标题
3) 对已确认的伪标题事件，量化丢失文本
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
DOTS = re.compile(r"\.{4,}")
PAGENUM = re.compile(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$")
SENT_END = tuple("。：；！？”")


def get_raw_lines(pdf_path):
    with pymupdf.open(pdf_path) as doc:
        pages = [p.get_text() for p in doc]
    lines = []  # (page_1based, idx_in_page, line)
    for i, t in enumerate(pages, start=1):
        for j, l in enumerate(t.split("\n")):
            ls = l.strip()
            if not ls or PAGENUM.match(ls):
                continue
            lines.append((i, j, ls))
    return lines, pages


def toc_titles(pages, toc_page_count=6):
    """从目录区收集权威标题：带引导点的行取点前文本；裸 第X章/节 行取下一行作标题"""
    titles = []
    for i, t in enumerate(pages[:toc_page_count], start=1):
        ls = [l.strip() for l in t.split("\n")]
        for k, l in enumerate(ls):
            if not l or PAGENUM.match(l):
                continue
            if DOTS.search(l):
                title = DOTS.split(l)[0].strip(" .")
                title = re.sub(r"\s*\d+\s*$", "", title).strip()
                if title:
                    titles.append(title)
            elif CH.match(l) or SEC.match(l):
                m = CH.match(l) or SEC.match(l)
                head = m.group(1)
                rest = m.group(2).strip()
                if rest:
                    titles.append(f"{head} {rest}")
                else:
                    # 标题在下一行（bse 形态），跳过页码行后取下一非空行
                    for nxt in ls[k + 1:]:
                        if not nxt or PAGENUM.match(nxt):
                            continue
                        titles.append(f"{head} {nxt}")
                        break
    # 去重保序
    seen, out = set(), []
    for t in titles:
        key = re.sub(r"\s+", "", t)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


def main():
    report = {}
    for law in LAWS:
        doc = load_yaml(law)
        lines, pages = get_raw_lines(pdf_path_of(law))
        # 正文起始页 = 首条 article 的页
        body_start_page = doc["articles"][0]["source_offset"]["page"]
        toc = toc_titles(pages)
        toc_norm = {re.sub(r"\s+", "", t): t for t in toc}

        # ---- 1) YAML 章/节字段对账 ----
        field_anomalies = []
        for a in doc["articles"]:
            for fld in ("chapter", "section"):
                v = a.get(fld)
                if not v:
                    continue
                key = re.sub(r"\s+", "", v)
                if key not in toc_norm:
                    field_anomalies.append({"article": a["article"], "field": fld, "value": v})

        # ---- 2) 伪标题穷举（正文区） ----
        false_heading_candidates = []
        for idx, (p, j, l) in enumerate(lines):
            if p < body_start_page - 1:
                continue
            m = CH.match(l) or SEC.match(l)
            if not m:
                continue
            reasons = []
            if "。" in l or "；" in l:
                reasons.append("行内含句读（真标题不含）")
            # 上一行是否句末收尾
            if idx > 0:
                prev = lines[idx - 1][2]
                prev_is_heading = bool(CH.match(prev) or SEC.match(prev))
                prev_ends_sentence = prev.rstrip().endswith(SENT_END)
                if not prev_is_heading and not prev_ends_sentence:
                    reasons.append(f"上一行未句末收尾: …{prev[-18:]!r}")
            if reasons:
                false_heading_candidates.append({"page": p, "line": l, "reasons": reasons})

        # ---- 3) 已确认事件的丢失量化（sse_main 5.2.14 / sse_star 12.7.1 及类似） ----
        losses = []
        art_by_id = {a["article"]: a for a in doc["articles"]}
        ids = [a["article"] for a in doc["articles"]]
        for k, aid in enumerate(ids):
            a = art_by_id[aid]
            # 条文结尾若是明显未完句（不以句末标点收尾且不以款项结构收尾）=> 可疑截断
            t = a["text"].rstrip()
            if t and not t.endswith(SENT_END + ("。", "；", "：", "）", "”")) and k + 1 < len(ids):
                nxt = art_by_id[ids[k + 1]]
                if nxt["chapter"] == a["chapter"] and nxt["section"] == a["section"]:
                    losses.append({"article": aid, "page": a["source_offset"]["page"],
                                   "tail": t[-40:]})

        report[law] = {
            "n_toc_titles": len(toc),
            "field_anomalies": field_anomalies,
            "false_heading_candidates": false_heading_candidates,
            "suspicious_unterminated_articles": losses,
        }
        print("=" * 10, law)
        print(f"  TOC titles: {len(toc)} | 字段异常: {len(field_anomalies)}")
        seen_field = set()
        for x in field_anomalies:
            key = (x["field"], x["value"])
            if key not in seen_field:
                seen_field.add(key)
                print(f"    [{x['field']}] {x['value']!r}  (如 {x['article']})")
        print(f"  伪标题候选: {len(false_heading_candidates)}")
        for x in false_heading_candidates:
            print(f"    p{x['page']} {x['line'][:44]!r} | {'; '.join(x['reasons'])}")
        print(f"  可疑未完句条文: {len(losses)}")
        for x in losses[:10]:
            print(f"    {x['article']} (p{x['page']}) 尾部: …{x['tail']!r}")

    with io.open(Path(__file__).resolve().parent / "results_heading_audit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
