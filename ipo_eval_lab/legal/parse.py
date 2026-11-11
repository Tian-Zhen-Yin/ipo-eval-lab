"""
PDF 解析模块（设计 0009 §3.1）

职责：
- PDF → 文本解析
- 保留页码和字符偏移（用于 source_offset）
- 清理页眉/页脚、格式化标记

依赖：
- pdfplumber（优先，保留布局）
- PyMuPDF（备选，处理扫描版）
"""

from pathlib import Path
from typing import List, Tuple
import hashlib


class PDFParser:
    """PDF 解析器"""

    def __init__(self, pdf_path: Path):
        self.pdf_path = pdf_path
        self.checksum = self._compute_checksum()

    def _compute_checksum(self) -> str:
        """计算文件 SHA256 哈希"""
        sha256 = hashlib.sha256()
        with open(self.pdf_path, "rb") as f:
            sha256.update(f.read())
        return f"sha256:{sha256.hexdigest()}"

    def parse_to_text(self) -> List[Tuple[int, str]]:
        """
        解析 PDF 为文本列表（每页一个字符串）

        Returns:
            List[Tuple[page_number, text]]: 页码（1-based）和文本
        """
        try:
            import pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber not installed. Install with: pip install pdfplumber"
            )

        pages_text = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    # 清理：去除多余空行
                    cleaned = "\n".join(
                        line for line in text.split("\n") if line.strip()
                    )
                    pages_text.append((i, cleaned))

        return pages_text

    def get_full_text(self) -> str:
        """获取全文（所有页拼接）"""
        pages = self.parse_to_text()
        return "\n\n".join(text for _, text in pages)
