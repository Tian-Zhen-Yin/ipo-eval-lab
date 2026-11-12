# -*- coding: utf-8 -*-
"""审核任务 A：核心上市标准条文全量精审（子串比对 + 数值逐款项对照 + checksum）"""
import difflib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from common import (LAWS, article_index, normalized_window_text, numbers_in,
                    pdf_path_of, sha256_of, split_clauses, load_yaml)

CORE = {
    "sse_main_2026": ["3.1.1", "3.1.2", "3.1.3"],
    "sse_star_2026": ["2.1.1", "2.1.2", "2.1.3"],
    "szse_main_2026": ["3.1.1", "3.1.2"],
    "szse_chinext_2026": ["2.1.1", "2.1.2", "2.1.3", "2.1.4"],
    "bse_2026": ["2.1.1", "2.1.2", "2.1.3", "2.1.4"],
}


def diff_snippet(yaml_text: str, page_text: str) -> str:
    """定位 YAML 文本相对 PDF 页文本的第一个差异区（容错：容忍空白差异）"""
    strip = lambda s: s.replace(" ", "").replace("\u3000", "")
    ys, ps = strip(yaml_text), strip(page_text)
    sm = difflib.SequenceMatcher(None, ys, ps, autojunk=False)
    diffs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete", "insert"):
            ctx = ys[max(0, i1 - 15):i1]
            diffs.append(f"[{tag}] YAML「{ctx}【{ys[i1:i2]}】{ys[i2:i2+15]}」 vs PDF「{ps[max(0,j1-15):j1]}【{ps[j1:j2]}】{ps[j2:j2+15]}」")
        if len(diffs) >= 8:
            break
    return " | ".join(diffs) if diffs else "(空白差异级别，无实质差异)"


def main():
    report = {"checksum": {}, "articles": []}
    ok_all = True
    for law in LAWS:
        doc = load_yaml(law)
        pdf = pdf_path_of(law)
        actual = sha256_of(pdf)
        declared = doc.get("checksum", "")
        match = declared == actual
        report["checksum"][law] = {"declared": declared[:24] + "...", "actual": actual[:24] + "...", "match": match}
        if not match:
            ok_all = False
        idx = article_index(doc)
        win = {}  # 页窗口文本缓存
        for aid in CORE.get(law, []):
            a = idx.get(aid)
            if a is None:
                report["articles"].append({"law": law, "article": aid, "status": "MISSING"})
                ok_all = False
                continue
            page = a["source_offset"]["page"]
            for r in (1, 2, 3):
                key = (page, r)
                if key not in win:
                    win[key] = normalized_window_text(pdf, page, r)
                pt = win[key]
                if a["text"] in pt:
                    st = {"law": law, "article": aid, "page": page, "status": f"SUBSTRING_OK(r={r})",
                          "len": len(a["text"])}
                    # 数值逐款项对照：定位 PDF 中的对应片段，逐款项比对数值序列
                    start = pt.index(a["text"][:20])
                    region = pt[start:start + len(a["text"]) + 200]
                    clause_issues = []
                    yc = split_clauses(a["text"])
                    yn = [numbers_in(t) for _, t in yc]
                    ynums_flat = [n for seq in yn for n in seq]
                    if ynums_flat != numbers_in(a["text"]):
                        clause_issues.append("款项数值序列与全文数值序列不一致(内部检查)")
                    st["clause_count_yaml"] = len(yc) - (1 if yc and yc[0][0] == "HEAD" else 0)
                    st["clause_marks"] = [m for m, _ in yc if m != "HEAD"]
                    st["numbers"] = ynums_flat
                    st["issues"] = clause_issues
                    report["articles"].append(st)
                    if clause_issues:
                        ok_all = False
                    break
            else:
                # 子串失败：给差异定位
                pt = win[(page, 1)]
                report["articles"].append({"law": law, "article": aid, "page": page,
                                           "status": "SUBSTRING_FAIL",
                                           "diff": diff_snippet(a["text"], pt)})
                ok_all = False

    out = Path(__file__).resolve().parent / "results_core_audit.json"
    with io.open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    for c in report["checksum"].items():
        print("checksum", c[0], "match=", c[1]["match"])
    for a in report["articles"]:
        line = f"{a['law']:20s} {a['article']:6s} p{a.get('page','-')} {a['status']:18s} len={a.get('len','-')} clauses={a.get('clause_count_yaml','-')}"
        print(line)
        if a["status"] == "SUBSTRING_FAIL":
            print("   DIFF:", a.get("diff"))
        if a.get("issues"):
            print("   NUM-ISSUE:", a["issues"])
    print("OVERALL:", "PASS" if ok_all else "FAIL")
    print("saved ->", out)


if __name__ == "__main__":
    main()
