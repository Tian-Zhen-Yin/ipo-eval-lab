"""
条文切分模块（设计 0009 §3.1）

职责：
- 正则/状态机切分条文（主干）
- 归一化条款号
- 计算 source_offset（页码 + 字符偏移）

依赖：
- parse.py（PDF → 文本）
- models.py（Article/SourceDoc）
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple
from datetime import datetime

from .parse import PDFParser
from .models import Article, SourceDoc, SourceOffset


class ArticleExtractor:
    """条文切分器（正则/状态机主干）"""

    # 正则模式（设计 0009 §2.3）
    PATTERNS = {
        "chapter": r"第[一二三四五六七八九十]+章",
        "section": r"第[一二三四五六七八九十]+节",
        "article": r"第[0-9]+条",
        "subsection": r"[（一二三四五六七八九十]+]",
    }

    def __init__(self, pdf_path: Path, law_id: str, title: str, effective_from: str):
        self.pdf_path = pdf_path
        self.law_id = law_id
        self.title = title
        self.effective_from = effective_from
        self.parser = PDFParser(pdf_path)

    def extract(self) -> SourceDoc:
        """
        提取条文列表

        Returns:
            SourceDoc: 包含元数据和条文列表
        """
        # 1. 解析 PDF 为文本
        pages = self.parser.parse_to_text()  # List[Tuple[page, text]]
        full_text = self.parser.get_full_text()

        # 2. 按章节目录定位起始 offset（简化版：直接全文切分）
        articles = self._extract_articles_from_text(full_text)

        # 3. 构建 SourceDoc
        source_doc = SourceDoc(
            law_id=self.law_id,
            title=self.title,
            source_type="exchange_rule",
            effective_from=self.effective_from,
            source_ref=str(self.pdf_path),
            downloaded_at=datetime.utcnow().strftime("%Y-%m-%d"),
            checksum=self.parser.checksum,
            articles=articles,
        )

        return source_doc

    def _extract_articles_from_text(self, text: str) -> List[Article]:
        """
        从全文中提取条文（正则切分）

        Args:
            text: 全文

        Returns:
            List[Article]: 条文列表
        """
        articles = []
        article_pattern = re.compile(self.PATTERNS["article"])

        # 按条文切分：用 "第X条" 作为分隔符
        # 注意：需要保留分隔符（条文号）在文本中
        parts = re.split(f"({self.PATTERNS['article']})", text)

        # parts 结构：[前文, "第1条", 条文1, "第2条", 条文2, ...]
        for i in range(1, len(parts), 2):
            if i + 1 >= len(parts):
                break

            article_id = parts[i].strip()  # "第1条"
            article_text = parts[i + 1].strip()  # 条文正文

            if not article_text:
                continue

            # 归一化条款号："第1条" → "1"，"2.1.2" → "2.1.2"
            normalized_id = self._normalize_article_id(article_id)

            # 计算 offset（简化版：按字符位置估算）
            # TODO: 实际应该用页码 offset（需要 parse.py 记录每页起始位置）
            offset = self._estimate_offset(text, article_id, article_text)

            article = Article(
                article=normalized_id,
                chapter=None,  # TODO: 从章节目录提取
                section=None,  # TODO: 从章节目录提取
                text=article_text,
                source_offset=offset,
                extracted_at=datetime.utcnow(),
                confidence="high",
                extraction_method="regex",
            )
            articles.append(article)

        return articles

    def _normalize_article_id(self, article_id: str) -> str:
        """
        归一化条款号

        Examples:
            "第1条" → "1"
            "2.1.2" → "2.1.2"
        """
        # 去除"第"和"条"
        normalized = article_id.replace("第", "").replace("条", "")
        return normalized.strip()

    def _estimate_offset(
        self, full_text: str, article_id: str, article_text: str
    ) -> SourceOffset:
        """
        估算条文在原文档中的位置（简化版）

        TODO: v2 用 parse.py 的页码信息精确计算
        """
        # 查找 article_id 在全文中的位置
        match = re.search(re.escape(article_id), full_text)
        if match:
            start = match.start()
            end = start + len(article_id) + len(article_text)
            # 简化：假设在第 1 页
            return SourceOffset(page=1, start=start, end=end)
        else:
            return SourceOffset(page=1, start=0, end=0)
