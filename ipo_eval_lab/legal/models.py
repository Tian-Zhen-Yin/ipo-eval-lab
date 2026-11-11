"""
上市法规原文库数据契约（设计 0009 §5.2）

Pydantic 模型定义原文库的 YAML 格式：
- SourceDoc: 单个法规文档（元数据 + 条文列表）
- Article: 单条条文（条款号 + 逐字正文 + 来源偏移 + 提取元信息）
- SourceOffset: 条文在原文档中的位置（页码/字符偏移）
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class SourceOffset(BaseModel):
    """条文在原文档中的位置，用于追溯回原文"""
    page: int = Field(..., description="PDF 页码（1-based）")
    start: int = Field(..., description="字符起始偏移（从页首开始）")
    end: int = Field(..., description="字符结束偏移")


class Article(BaseModel):
    """单条条文（条款级）"""
    article: str = Field(..., description="条款号，如 '2.1.2' 或 '1'")
    chapter: Optional[str] = Field(None, description="所属章节，如 '第二章 首次公开发行股票并上市'")
    section: Optional[str] = Field(None, description="所属节，如 '第一节 上市条件'")
    text: str = Field(..., description="逐字正文（保留原始格式，除页眉页脚外不清洗）")
    source_offset: SourceOffset = Field(..., description="条文在原文档中的位置")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="提取时间戳")
    confidence: str = Field(default="high", description="置信度：high/medium/low")
    extraction_method: str = Field(default="regex", description="提取方法：regex/vector/manual")


class SourceDoc(BaseModel):
    """单个法规文档（元数据 + 条文列表）"""
    law_id: str = Field(..., description="法规唯一标识，如 'sse_star_2026'")
    title: str = Field(..., description="法规标题")
    source_type: str = Field(default="exchange_rule", description="来源类型：exchange_rule / other")
    effective_from: str = Field(..., description="生效日期，YYYY-MM-DD")
    source_ref: str = Field(..., description="归档文件路径，如 'raw/legal_docs_20261111/sse_star_2026.pdf'")
    downloaded_at: str = Field(..., description="下载时间，YYYY-MM-DD")
    checksum: str = Field(..., description="文件哈希（sha256），防篡改")
    articles: List[Article] = Field(default_factory=list, description="条文列表")


class SourceTextsMeta(BaseModel):
    """原文库元数据（_meta.yaml）"""
    rulebook_version: str = Field(..., description="规则库版本，如 'rb-2026.11'")
    source_docs_version: str = Field(..., description="原文库版本，对应下载日期 YYYY-MM-DD")
    version_mapping: dict = Field(default_factory=dict, description="版本映射：law_id → 元数据")
    extraction_config: dict = Field(default_factory=dict, description="切分配置：正则模式、向量阈值等")
