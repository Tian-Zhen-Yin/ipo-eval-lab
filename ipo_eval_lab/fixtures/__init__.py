"""M3 企业数据契约（设计 0006）：CompanyProfile 模型 + 加载期勾稽断言。

AR4：坏数据起不了 run——本 loader 由引擎 Init 节点与测试共用同一实现（F1）。
"""
from .loader import (
    FixtureDataError,
    LoadedCompany,
    Range,
    SanityBounds,
    check_profile,
    load_company,
    load_profile,
    load_sanity,
)
from .models import CompanyProfile

__all__ = [
    "CompanyProfile",
    "FixtureDataError",
    "LoadedCompany",
    "Range",
    "SanityBounds",
    "check_profile",
    "load_company",
    "load_profile",
    "load_sanity",
]
