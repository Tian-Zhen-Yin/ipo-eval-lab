"""
上市法规原文库模块（设计 0009）

职责：
- 浏览器半自动下载官方文档（fetch.py）
- PDF → 文本解析（parse.py）
- 正则/状态机切分条文（extract.py）
- 向量相似度兜底（vector.py）

输出：rulebook/source_texts/*.yaml（逐字条文库）
"""

from .models import Article, SourceDoc, SourceOffset, SourceTextsMeta

__all__ = ["Article", "SourceDoc", "SourceOffset", "SourceTextsMeta"]
