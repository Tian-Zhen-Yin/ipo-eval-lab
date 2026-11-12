# -*- coding: utf-8 -*-
"""审核任务 B2/B3：结构完整性独立复核
方法与切分器不同源：
  1) 全文拼合校验（tiling）：YAML 全部条文 + 章节标题应无缝拼回清洗后全文流，
     条文间空隙只允许是章/节标题；凡有缺口 => 内容丢失。
  2) 原始定义候选扫描：独立正则扫描 PDF 全部行首"定义形态"条款号，与 YAML 条款号集合双向对账。
  3) 连续性：按前缀重推导尾号序列（跳号/重复/回退）。
  4) 章节归属：tiling 行走时跟踪当前章/节，与 YAML chapter/section 全量比对。
"""
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf

from common import LAWS, load_yaml, pdf_path_of, clean_page_lines

CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百]+章)\s*(.*)$")
SECTION_RE = re.compile(r"^(第[一二三四五六七八九十百]+节)\s*(.*)$")
DEF_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)[ \u3000]*([^\s].*)?$")


def full_clean_stream(pdf_path):
    """清洗后全文流（与切分器同口径）+ 原始行清单"""
    import pymupdf
    lines = []  # (page, line)
    with pymupdf.open(pdf_path) as doc:
        for i, page in enumerate(doc, start=1):
            for line in page.get_text().split("\n"):
                line = line.strip()
                if not line:
                    continue
                if re.match(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$", line):
                    continue
                if re.search(r"\.{4,}", line):
                    continue
                lines.append((i, line))
    stream = "".join(l for _, l in lines)
    return stream, lines


def raw_definition_candidates(lines):
    """独立扫描定义形态条款号：行首 id 且其后不是「条」字（含空行/文末）"""
    cands = []
    for page, line in lines:
        m = DEF_RE.match(line)
        if not m:
            continue
        rest = (m.group(2) or "")
        if rest.startswith("条"):
            continue  # 引用形态
        cands.append((page, m.group(1)))
    return cands


def looks_like_heading(gap: str) -> bool:
    """空隙应为若干完整章/节标题行的拼接"""
    parts = [p for p in re.split(r"(?<=[\u4e00-\u9fff）〕])", gap) if p]
    for p in parts:
        if not (CHAPTER_RE.match(p) or SECTION_RE.match(p)):
            return False
    return True


def audit_law(law):
    doc = load_yaml(law)
    arts = doc["articles"]
    stream, lines = full_clean_stream(pdf_path_of(law))
    res = {"law": law, "n_yaml": len(arts)}

    # ---- 1) tiling 全文拼合校验 + 章节归属 ----
    cursor = stream.find(arts[0]["text"][:12])
    if cursor < 0:
        res["tiling"] = "FATAL: 首条不在全文流中"
        return res
    front_matter_len = cursor
    mismatches, gaps_bad, attribution_bad = [], [], []
    cur_ch = cur_sec = None
    for k, a in enumerate(arts):
        t = a["text"]
        pos = stream.find(t, cursor)
        if pos != cursor:
            if pos < 0:
                mismatches.append({"article": a["article"], "why": "text 在游标之后找不到"})
                # 尝试全流搜索兜底
                pos2 = stream.find(t)
                mismatches[-1]["found_at"] = pos2
                continue
            gap = stream[cursor:pos]
            gaps_bad.append({"before": a["article"], "gap": gap[:120]})
        cursor = pos + len(t)
        # 章节归属：从空隙中提取标题，更新当前章/节
        gap = stream[max(cursor - len(t), 0):pos] if pos != cursor else ""
        # 重新扫描游标起点到 pos 之间的标题行——直接在 gap 上做
        seg = stream[cursor:pos + len(t)]
        # 归属校验：期望 YAML 记录的 chapter/section 与行走状态一致
        for p in re.split(r"(?<=[\u4e00-\u9fff）〕])", gap):
            m = CHAPTER_RE.match(p)
            if m:
                cur_ch = f"{m.group(1)} {m.group(2).strip()}".strip()
                cur_sec = None
                continue
            m = SECTION_RE.match(p)
            if m:
                cur_sec = f"{m.group(1)} {m.group(2).strip()}".strip()
        if (a.get("chapter") or None) != (cur_ch if cur_ch else a.get("chapter")) and a.get("chapter") != cur_ch:
            attribution_bad.append({"article": a["article"], "yaml": a.get("chapter"), "walk": cur_ch})
        if (a.get("section") or None) != (cur_sec if cur_sec else a.get("section")) and a.get("section") != cur_sec:
            attribution_bad.append({"article": a["article"], "field": "section", "yaml": a.get("section"), "walk": cur_sec})
    trailing = stream[cursor:]
    res["tiling"] = {"front_matter_chars": front_matter_len,
                     "gap_anomalies": gaps_bad,
                     "not_found": mismatches,
                     "trailing_chars": len(trailing),
                     "trailing_head": trailing[:150]}
    res["attribution_bad"] = attribution_bad

    # ---- 2) 原始定义候选 vs YAML 条款号 双向对账 ----
    cands = raw_definition_candidates(lines)
    cand_ids = [c[1] for c in cands]
    yaml_ids = [a["article"] for a in arts]
    res["def_scan"] = {
        "n_raw_candidates": len(cand_ids),
        "n_yaml": len(yaml_ids),
        "in_raw_not_yaml": [i for i in cand_ids if i not in set(yaml_ids)],
        "in_yaml_not_raw_order": None,
    }
    # 顺序对账（过滤引用误判后应逐一相等）
    if cand_ids == yaml_ids:
        res["def_scan"]["order_match"] = True
    else:
        res["def_scan"]["order_match"] = False
        # 找出第一个分歧点
        for i, (x, y) in enumerate(zip(cand_ids, yaml_ids)):
            if x != y:
                res["def_scan"]["first_divergence"] = {"pos": i, "raw": x, "yaml": y,
                                                       "raw_ctx": cands[max(0, i - 2):i + 3]}
                break

    # ---- 3) 连续性（按前缀独立重推导） ----
    seq_bad = []
    from collections import defaultdict, Counter
    by_prefix = defaultdict(list)
    for a in arts:
        parts = a["article"].split(".")
        by_prefix[".".join(parts[:-1])].append(int(parts[-1]))
    for pfx, tails in by_prefix.items():
        c = Counter(tails)
        dups = [t for t, n in c.items() if n > 1]
        expected = list(range(1, max(tails) + 1))
        missing = [t for t in expected if t not in c]
        if dups or missing:
            seq_bad.append({"prefix": pfx, "dups": dups, "missing": missing})
    res["continuity_bad"] = seq_bad

    # ---- 章节数对账（YAML 章集合 vs 清洗流中章标题序列） ----
    ch_in_stream = []
    for _, l in lines:
        m = CHAPTER_RE.match(l)
        if m:
            name = f"{m.group(1)} {m.group(2).strip()}".strip()
            if not ch_in_stream or ch_in_stream[-1] != name:
                ch_in_stream.append(name)
    ch_in_yaml = []
    for a in arts:
        if a.get("chapter") and (not ch_in_yaml or ch_in_yaml[-1] != a["chapter"]):
            ch_in_yaml.append(a["chapter"])
    res["chapters_stream_vs_yaml"] = {"stream": ch_in_stream, "yaml": ch_in_yaml,
                                      "match": ch_in_stream == ch_in_yaml}
    return res


def main():
    out = {}
    for law in LAWS:
        r = audit_law(law)
        out[law] = r
        t = r.get("tiling", {})
        print("=" * 8, law)
        print("  tiling: front=", t.get("front_matter_chars"), "gap_anomalies=", len(t.get("gap_anomalies", [])),
              "not_found=", len(t.get("not_found", [])), "trailing_chars=", t.get("trailing_chars"))
        for g in t.get("gap_anomalies", [])[:6]:
            print("    GAP before", g["before"], ":", repr(g["gap"]))
        for nf in t.get("not_found", [])[:6]:
            print("    NOTFOUND", nf)
        print("  trailing head:", repr(t.get("trailing_head")))
        d = r.get("def_scan", {})
        print("  def_scan: raw=", d.get("n_raw_candidates"), "yaml=", d.get("n_yaml"),
              "order_match=", d.get("order_match"),
              "raw_not_yaml=", d.get("in_raw_not_yaml")[:10])
        if d.get("first_divergence"):
            print("    first_divergence:", json.dumps(d["first_divergence"], ensure_ascii=False)[:400])
        print("  continuity_bad:", r["continuity_bad"][:8])
        print("  attribution_bad:", len(r["attribution_bad"]))
        for x in r["attribution_bad"][:8]:
            print("    ", json.dumps(x, ensure_ascii=False)[:200])
        print("  chapters match:", r["chapters_stream_vs_yaml"]["match"])
        if not r["chapters_stream_vs_yaml"]["match"]:
            print("    stream:", r["chapters_stream_vs_yaml"]["stream"])
            print("    yaml  :", r["chapters_stream_vs_yaml"]["yaml"])
    with io.open(Path(__file__).resolve().parent / "results_structure_audit.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print("saved -> results_structure_audit.json")


if __name__ == "__main__":
    main()
