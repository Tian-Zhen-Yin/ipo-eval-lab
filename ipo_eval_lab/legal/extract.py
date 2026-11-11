"""
条文切分模块（设计 0009 §3.1，v2：按 2026-11-11 实测 PDF 形态重写）

实测形态（raw/legal_docs_20261111 五份 PDF 侦察结论）：
- 条款号统一为点分式：``2.1.1`` / ``3.1.2``（科创板紧贴正文无空格，其余有空格）
- 页码在每页首行：``11 `` / ``— 11 —`` / ``- 11 -``
- 目录行含半角引导点：``第三章股票上市和交易.......``（正文无此形态，整行丢弃）
- 章节标题：``第二章 股票上市与交易`` / ``第一节 首次公开发行股票的上市``
- 条文正文硬换行 + 跨页拼接（北交所 2.4.1 实测跨页）

逐字保真的口径（设计决策，见 0009 §3.4）：
PDF 提取的"原始格式"含断行噪音，原文库 ``text`` 存**规范化连续文本**
（合并硬换行、去页码行、去目录行）。下游 R9 逐字引文校验的锚点 = 原文库
text 本身（L1 的 quote 从 text 摘抄），不是 PDF 原始字节——substring 语义不变。
"""

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .models import Article, SourceDoc, SourceOffset
from .parse import PDFParser


class ArticleExtractor:
    """条文切分器（正则/状态机主干，行扫描 + 章节上下文）"""

    # 条款号：行首点分式（两段或三段数字），后跟零个或多个空格
    ARTICLE_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)[ \u3000]*")
    # 引用形态：条款号后紧跟"条"字（如 "4.2.8 条第一款..."，正文断行把"第"切到上行末），
    # 这是正文引用不是新条文定义（定义形态条款号后直接跟正文，无"条"字）
    ARTICLE_REF_RE = re.compile(r"^(\d+\.\d+(?:\.\d+)?)[ \u3000]*条")
    # 页码行：'11 ' / '— 11 —' / '- 11 -'（实测页码不总在首行，需全行过滤）
    PAGE_NUM_RE = re.compile(r"^[—\-\s]*\d{1,3}\s*[—\-\s]*$")
    # 目录行：含 4 个及以上半角引导点（正文无此形态）
    TOC_LINE_RE = re.compile(r"\.{4,}")
    # 章标题：'第二章 股票上市与交易'
    CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百]+章)\s*(.*)$")
    # 节标题：'第一节 首次公开发行股票的上市'
    SECTION_RE = re.compile(r"^(第[一二三四五六七八九十百]+节)\s*(.*)$")

    def __init__(self, pdf_path: Path, law_id: str, title: str, effective_from: str):
        self.pdf_path = pdf_path
        self.law_id = law_id
        self.title = title
        self.effective_from = effective_from
        self.parser = PDFParser(pdf_path)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def extract(self) -> Tuple[SourceDoc, List[str]]:
        """提取条文，返回 (SourceDoc, 完整性告警列表)"""
        pages_text = self._load_clean_pages()

        articles: List[Article] = []
        warnings: List[str] = []
        cur_chapter: Optional[str] = None
        cur_section: Optional[str] = None
        cur: Optional[dict] = None  # {id, lines, page, char_start}

        for page_no, line in self._iter_lines(pages_text):
            m_chap = self.CHAPTER_RE.match(line)
            m_sec = self.SECTION_RE.match(line)
            m_art = self.ARTICLE_RE.match(line)
            is_ref = m_art is not None and self.ARTICLE_REF_RE.match(line) is not None

            if m_chap:
                if cur:
                    articles.append(self._build_article(cur))
                    cur = None
                cur_chapter = f"{m_chap.group(1)} {m_chap.group(2).strip()}".strip()
                cur_section = None
                continue
            if m_sec:
                if cur:
                    articles.append(self._build_article(cur))
                    cur = None
                cur_section = f"{m_sec.group(1)} {m_sec.group(2).strip()}".strip()
                continue
            if m_art and not is_ref:
                if cur:
                    articles.append(self._build_article(cur))
                cur = {
                    "id": m_art.group(1),
                    "lines": [line[m_art.end():]],
                    "page": page_no,
                    "chapter": cur_chapter,
                    "section": cur_section,
                }
                continue
            if cur is not None:
                cur["lines"].append(line)

        if cur:
            articles.append(self._build_article(cur))

        # 完整性校验：条款号连续性（设计 0009 §3.3）
        warnings = self._check_continuity(articles)

        source_doc = SourceDoc(
            law_id=self.law_id,
            title=self.title,
            source_type="exchange_rule",
            effective_from=self.effective_from,
            source_ref=str(self.pdf_path).replace("\\", "/"),
            downloaded_at=datetime.utcnow().strftime("%Y-%m-%d"),
            checksum=self.parser.checksum,
            articles=articles,
        )
        return source_doc, warnings

    # ------------------------------------------------------------------
    # 内部步骤
    # ------------------------------------------------------------------

    def _load_clean_pages(self) -> List[Tuple[int, str]]:
        """逐页提取并清洗：去页码行、去目录行、去空行"""
        import pymupdf

        pages: List[Tuple[int, str]] = []
        with pymupdf.open(self.pdf_path) as doc:
            for i, page in enumerate(doc, start=1):
                lines = [l.strip() for l in page.get_text().split("\n")]
                cleaned = []
                for line in lines:
                    if not line:
                        continue
                    if self.PAGE_NUM_RE.match(line):
                        continue  # 页码行（实测不总在首行，全行过滤）
                    if self.TOC_LINE_RE.search(line):
                        continue  # 目录行
                    cleaned.append(line)
                if cleaned:
                    pages.append((i, "\n".join(cleaned)))
        return pages

    def _iter_lines(self, pages: List[Tuple[int, str]]):
        """产出 (页号, 行) 序列"""
        for page_no, text in pages:
            for line in text.split("\n"):
                yield page_no, line

    def _build_article(self, cur: dict) -> Article:
        """规范化条文：合并硬换行（中文直接拼接）"""
        text = "".join(part for part in cur["lines"] if part)
        return Article(
            article=cur["id"],
            chapter=cur.get("chapter"),
            section=cur.get("section"),
            text=text,
            source_offset=SourceOffset(page=cur["page"], start=0, end=0),
            extracted_at=datetime.utcnow(),
            confidence="high",
            extraction_method="regex",
        )

    def _check_continuity(self, articles: List[Article]) -> List[str]:
        """条款号连续性校验：同章内 X.Y.Z 序号应递增连续，跳号即告警"""
        warnings: List[str] = []
        prev_prefix: Optional[Tuple[str, ...]] = None
        prev_tail = 0
        for art in articles:
            parts = tuple(art.article.split("."))
            tail = int(parts[-1])
            prefix = parts[:-1]
            if prev_prefix is not None and prefix == prev_prefix:
                if tail != prev_tail + 1:
                    warnings.append(
                        f"条款号跳号: {prev_prefix} {prev_tail} -> {art.article}"
                    )
            prev_prefix, prev_tail = prefix, tail
        return warnings
