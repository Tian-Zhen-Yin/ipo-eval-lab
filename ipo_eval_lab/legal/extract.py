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
    # 句读字符（真标题行内不含；审核 0006 §2-P0 零误报集合）
    PUNCT_IN_TITLE = ("。", "；")
    # 句末收尾字符（正文行应以此收尾）
    SENT_END_CHARS = ("。", "；", "：", "）", "”", "…", "!")
    # 标题续行拼接上限（标题文字一般 <30 字；款项正文行不会紧跟真标题出现）
    TITLE_TAIL_MAX = 30

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
        # 展平为 (page, line) 流——标题续行拼接需要 peek/消费下一行
        stream = [(p, l) for p, t in pages_text for l in t.split("\n")]

        articles: List[Article] = []
        cur_chapter: Optional[str] = None
        cur_section: Optional[str] = None
        cur: Optional[dict] = None
        prev_line: Optional[str] = None

        i = 0
        while i < len(stream):
            page_no, line = stream[i]
            i += 1
            m_chap = self.CHAPTER_RE.match(line)
            m_sec = self.SECTION_RE.match(line)
            m_art = self.ARTICLE_RE.match(line)
            is_ref = m_art is not None and self.ARTICLE_REF_RE.match(line) is not None

            # 章/节命中先做伪标题判别（审核 0006 P0 根因：
            # 正文断行恰好落在「第X章/节」之后，如「…根据本章第二节、第四节、⏎第五节的规定…」）
            if (m_chap or m_sec) and self._is_false_heading(line, prev_line):
                if cur is not None:
                    cur["lines"].append(line)  # 拼回正文
                prev_line = line
                continue

            if m_chap:
                if cur:
                    articles.append(self._build_article(cur))
                    cur = None
                tail, i = self._consume_title_tail(stream, i)
                cur_chapter = f"{m_chap.group(1)} {m_chap.group(2).strip()}{tail}".strip()
                cur_section = None
                prev_line = line
                continue
            if m_sec:
                if cur:
                    articles.append(self._build_article(cur))
                    cur = None
                tail, i = self._consume_title_tail(stream, i)
                cur_section = f"{m_sec.group(1)} {m_sec.group(2).strip()}{tail}".strip()
                prev_line = line
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
            elif cur is not None:
                cur["lines"].append(line)
            prev_line = line

        if cur:
            articles.append(self._build_article(cur))

        # 完整性校验（设计 0009 §3.3 + 审核 0006 P3-4）
        warnings = self._check_continuity(articles) + self._check_unterminated(articles)

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

    def _is_false_heading(self, line: str, prev_line: Optional[str]) -> bool:
        """伪标题判别（审核 0006 P3-2 双启发式，正文区零误报）：
        1. 行内含句读（。；）→ 正文断行（真标题不含句读）
        2. 上一行未句末收尾（且上一行不是标题）→ 正文续行
        """
        if any(c in line for c in self.PUNCT_IN_TITLE):
            return True
        if prev_line is not None:
            prev_is_heading = bool(
                self.CHAPTER_RE.match(prev_line) or self.SECTION_RE.match(prev_line)
            )
            if not prev_is_heading and not prev_line.rstrip().endswith(self.SENT_END_CHARS):
                return True
        return False

    def _consume_title_tail(self, stream, i: int) -> Tuple[str, int]:
        """真标题的标题文字分离拼接（审核 0006 P2）：
        深主板「第一章总」+「则」、北交所「第一章」+「总」+「则」（可跨多行）、
        创业板「第一节」+「股票交易异常波动和澄清」。
        续行须：非条款号/非章节行、无句读、长度 ≤ TITLE_TAIL_MAX；满足则循环拼接。
        """
        tail = ""
        while i < len(stream):
            nxt = stream[i][1]
            if (
                nxt
                and not self.ARTICLE_RE.match(nxt)
                and not self.CHAPTER_RE.match(nxt)
                and not self.SECTION_RE.match(nxt)
                and not any(c in nxt for c in self.PUNCT_IN_TITLE)
                and len(nxt) <= self.TITLE_TAIL_MAX
            ):
                tail += nxt
                i += 1
            else:
                break
        return tail, i

    def _check_unterminated(self, articles: List[Article]) -> List[str]:
        """未完句自检（审核 0006 P3-4）：条文不以句末标点收尾即告警。
        4 处 P0 正文丢失全部命中该特征，可零成本拦截同类回归。"""
        warnings: List[str] = []
        for art in articles:
            t = art.text.rstrip()
            if t and not t.endswith(self.SENT_END_CHARS):
                warnings.append(f"条文未完句收尾: {art.article} …{t[-20:]!r}")
        return warnings

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
