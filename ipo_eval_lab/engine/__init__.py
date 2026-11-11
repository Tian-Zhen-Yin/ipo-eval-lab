"""M4 测评引擎（设计 0004 §2 在线域 / 设计 0005 五节点责任链）。

T1（Init）：run 坐标装配 + as_of 生效过滤（关闭 #9-V6）+ 适用性判定 + CLI。
Fetch/Calc/Fold/Result 为占位直通，随 T2~T8 逐票点亮。
"""
from .applicability import ApplicabilityResult, judge_applicability
from .asof import AsOfFilter, filter_by_as_of
from .context import RunContext, RunTarget, Selection
from .errors import EngineError
from .runner import run_eval

__all__ = [
    "ApplicabilityResult",
    "AsOfFilter",
    "EngineError",
    "RunContext",
    "RunTarget",
    "Selection",
    "filter_by_as_of",
    "judge_applicability",
    "run_eval",
]
