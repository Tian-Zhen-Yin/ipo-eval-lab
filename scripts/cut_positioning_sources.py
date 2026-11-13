"""段② 法律源 PDF/docx → 原文库（rulebook/source_texts/*.yaml）

G4a（底稿 0003）：把 raw/legal_docs_20261113/ 的 4 份新法规机械切分入原文库，
随后 scripts/build_legal_library.py 重生成法条库（L6 锚点依赖）。

切分规则（设计 0009「混合·结构优先」的最小实现）：
- 条文式（交易所规定/审核规则）：`第X条` 状态机（X = 中文数字）
- 序号式（证监会指引）：`一、` `二、` 状态机
- PDF 用 pymupdf，docx 用 zipfile 直读 document.xml（去标签）

产物与既有 source_texts 同 schema（article/chapter/section/text + 抽取元数据）。
生成物入 git；checksum 记录源文件哈希（可复算）。

用法：
    python scripts/cut_positioning_sources.py            # 生成
    python scripts/cut_positioning_sources.py --check    # 只校验（CI 用）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "raw" / "legal_docs_20261113"
OUT = REPO / "rulebook" / "source_texts"

# law_id → (文件, 标题, source_type, effective_from, 切分模式)
DOCS = {
    "csrc_kechuang_attr": (
        "csrc_kechuang_attr_2024.pdf",
        "科创属性评价指引（试行）",
        "law",                        # 证监会规范性文件——Literal 三值中最接近的一档
        "2024-04-30",
        "csrc_numbered",              # 一、二、三、四
    ),
    "sse_star_recommend": (
        "sse_star_recommend_2024.docx",
        "上海证券交易所科创板企业发行上市申报及推荐暂行规定（2024年4月修订）",
        "exchange_rule",
        "2024-04-30",
        "article",
    ),
    "szse_chinext_recommend": (
        "szse_chinext_recommend_2024.pdf",
        "深圳证券交易所创业板企业发行上市申报及推荐暂行规定（2024年修订）",
        "exchange_rule",
        "2024-04-30",
        "article",
    ),
    "cn_audit_rule": (
        None,                          # 沪深两份同文，source_ref 列两个
        "股票发行上市审核规则（沪深同文，2024年4月修订）",
        "exchange_rule",
        "2024-04-30",
        "article",
    ),
}
CN_AUDIT_FILES = ["sse_audit_rule_2024.docx", "szse_audit_rule_2024.pdf"]

CN_NUM = "一二三四五六七八九十"


def read_pdf(path: Path) -> str:
    import pymupdf

    doc = pymupdf.open(path)
    return "\n".join(p.get_text() for p in doc)


def read_docx(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    # 段落边界 → 换行，再去标签
    xml = xml.replace("</w:p>", "\n")
    return re.sub(r"<[^>]+>", "", xml)


def read_text(path: Path) -> str:
    return read_pdf(path) if path.suffix == ".pdf" else read_docx(path)


def split_articles(text: str, mode: str) -> list[dict]:
    """条文切分。返回 [{article, chapter, section, text}]。"""
    flat = re.sub(r"[ \t\u3000]+", "", text.replace("\n", ""))
    if mode == "article":
        heads = list(re.finditer(rf"第[{CN_NUM}]+条", flat))
    else:  # csrc_numbered：指引的一、二、三、四（顶格序号）
        heads = list(re.finditer(rf"[（(]?[{CN_NUM}]+[）)]?、", flat))

    articles = []
    for i, m in enumerate(heads):
        label = m.group(0).strip("（()）")
        end = heads[i + 1].start() if i + 1 < len(heads) else len(flat)
        body = flat[m.end():end].strip()
        # 尾部页码噪声（PDF 页脚「— 2 —」/纯数字行）
        body = re.sub(r"(—\s*\d+\s*—|\d{1,3})$", "", body).strip()
        if len(body) < 10:
            continue   # 目录行/引用行（如「第七条规定的…进行相应的信息披露」片断）
        articles.append({
            "article": label,   # article 模式保留「第X条」全称（与五部规则一致）；指引保留「一、」
            "chapter": None, "section": None, "text": body,
        })
    return articles


def normalize_article_labels(articles: list[dict], mode: str) -> list[dict]:
    if mode != "article":
        return articles
    out = []
    for a in articles:
        m = re.match(rf"第[{CN_NUM}]+条", a["article"])
        out.append({**a, "article": m.group(0) if m else a["article"]})
    return out


def sha256_of(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in paths:
        h.update(p.read_bytes())
    return "sha256:" + h.hexdigest()


CN_ORDER = {c: i for i, c in enumerate("零一二三四五六七八九")}


def _cn_key(label: str) -> int:
    """中文序号 → 排序键（十一=11、二十=20、二十一=21）。"""
    res, cur = 0, 0
    for ch in label:
        if ch == "十":
            res += (cur or 1) * 10
            cur = 0
        elif ch in CN_ORDER:
            cur = CN_ORDER[ch]
    return res + cur


def dedupe(articles: list[dict]) -> list[dict]:
    """同 article 标签去重，保留 text 最长的一条，按序号排序。

    重复来源：docx/pdf 把「修订说明/附件参考格式」拼在正文后（引用条文片段），
    或沪深同文两份拼接（cn_audit_rule）。正文条款完整长于引用片段，取最长即正文。
    """
    best: dict[str, dict] = {}
    for a in articles:
        cur = best.get(a["article"])
        if cur is None or len(a["text"]) > len(cur["text"]):
            best[a["article"]] = a
    return sorted(best.values(), key=lambda a: _cn_key(a["article"]))


def build() -> dict[str, dict]:
    laws: dict[str, dict] = {}
    for law_id, (fname, title, stype, eff, mode) in DOCS.items():
        files = ([SRC / fname] if fname else [SRC / f for f in CN_AUDIT_FILES])
        text = "\n".join(read_text(p) for p in files)
        if law_id == "csrc_kechuang_attr":
            # 同一 PDF 含「修改决定」+「重公布全文」两段同形序号——修改决定条款以
            # 「将第X条修改为」开头，丢弃；只留重公布全文（现行文本，锚点用它）。
            articles = [a for a in split_articles(text, mode)
                        if not a["text"].startswith("将第")]
        else:
            articles = split_articles(text, mode)
        articles = dedupe(normalize_article_labels(articles, mode))
        if not articles:
            raise SystemExit(f"{law_id}: 切分结果为空——切分模式 {mode} 需人工核查")
        laws[law_id] = {
            "law_id": law_id,
            "title": title,
            "source_type": stype,
            "effective_from": eff,
            "source_ref": json.dumps([str(p.relative_to(REPO)) for p in files], ensure_ascii=False),
            "downloaded_at": "2026-11-13",
            "checksum": sha256_of(files),
            "articles": [
                {**a, "source_offset": None, "extracted_at": date.today().isoformat(),
                 "confidence": "high", "extraction_method": "regex"}
                for a in articles
            ],
        }
    return laws


HEADER = """# 原文库（由 scripts/cut_positioning_sources.py 机械切分，勿手工编辑）
# 来源：raw/legal_docs_20261113/（官方源直下，G1 采购；底稿 0003）
"""


def render(law: dict) -> str:
    # 顶层 = dict（与既有五部 source_texts 一致——build_legal_library 按单 dict 读）
    body = yaml.safe_dump(law, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return HEADER + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    laws = build()
    stale = []
    for law_id, law in sorted(laws.items()):
        path = OUT / f"{law_id}.yaml"
        text = render(law)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(law_id)
            continue
        path.write_text(text, encoding="utf-8")
        print(f"写入 {path.relative_to(REPO)}（{len(law['articles'])} 条文）")

    if args.check:
        if stale:
            print(f"原文库不是最新：{stale}（跑 scripts/cut_positioning_sources.py）", file=sys.stderr)
            return 1
        print("段② 原文库与源文件一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
