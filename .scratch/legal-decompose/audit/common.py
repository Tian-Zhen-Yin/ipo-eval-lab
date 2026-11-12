# -*- coding: utf-8 -*-
"""审核公共库：复刻 extract.py 的规范化口径（独立实现，不 import 项目代码）"""
import hashlib
import io
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT / "rulebook" / "source_texts"
PDF_DIR = ROOT / "raw" / "legal_docs_20261111"

LAWS = ["sse_main_2026", "sse_star_2026", "szse_main_2026", "szse_chinext_2026", "bse_2026"]

# 与 ipo_eval_lab/legal/extract.py 相同口径的过滤规则（独立重写，用于交叉验证）
PAGE_NUM_RE = re.compile(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$")
TOC_LINE_RE = re.compile(r"\.{4,}")


def load_yaml(law_id: str) -> dict:
    with io.open(SRC_DIR / f"{law_id}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean_page_lines(raw_page_text: str):
    """与 extract.py _load_clean_pages 相同的行清洗：strip、去空行/页码行/目录行"""
    out = []
    for line in raw_page_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if PAGE_NUM_RE.match(line):
            continue
        if TOC_LINE_RE.search(line):
            continue
        out.append(line)
    return out


def normalized_page_text(pdf_path: Path, page_no_1based: int) -> str:
    """单页规范化连续文本（模拟 _build_article 的 ''.join 合并）"""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        raw = doc[page_no_1based - 1].get_text()
    return "".join(clean_page_lines(raw))


def normalized_window_text(pdf_path: Path, center_page: int, radius: int = 1) -> str:
    """center_page±radius 页规范化文本直接拼接（跨页条文）"""
    import pymupdf

    parts = []
    with pymupdf.open(pdf_path) as doc:
        n = doc.page_count
        for p in range(max(1, center_page - radius), min(n, center_page + radius) + 1):
            raw = doc[p - 1].get_text()
            parts.append("".join(clean_page_lines(raw)))
    return "".join(parts)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def article_index(doc: dict) -> dict:
    return {a["article"]: a for a in doc["articles"]}


def pdf_path_of(law_id: str) -> Path:
    return PDF_DIR / f"{law_id}.pdf"


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str):
    """抽取数值序列（金额/百分比/天数/年限的数字本体）"""
    return NUM_RE.findall(text)


CLAUSE_SPLIT_RE = re.compile(r"（[一二三四五六七八九十]+）")


def split_clauses(text: str):
    """按（一）（二）切款项，返回 [(标号, 片段)]"""
    marks = CLAUSE_SPLIT_RE.findall(text)
    parts = CLAUSE_SPLIT_RE.split(text)
    head = parts[0]  # 款项前导语
    out = [("HEAD", head)] if head.strip() else []
    for m, p in zip(marks, parts[1:]):
        out.append((m, p))
    return out
