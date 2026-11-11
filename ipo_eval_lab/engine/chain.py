"""五节点责任链（设计 0005 §1；Fetch 先于 Calc——修 midas Init→Calc→Fetch 顺序病）。

T1：Init 实现，其余四节点占位直通；随 T2~T8 逐票点亮。
"""
from __future__ import annotations

from typing import Callable

from .context import RunContext

Node = Callable[[RunContext], None]


def fetch_node(ctx: RunContext) -> None:
    """Fetch（T2）：statements → facts（六驱动 + 七指标，两维 measures）。"""


def calc_node(ctx: RunContext) -> None:
    """Calc（T3）：窗口 token → 期间码 → 六量词 → 五态 + 差距三分列。"""


def fold_node(ctx: RunContext) -> None:
    """Fold（T4）：Kleene 双规则折叠 → 套终态 / 板块结论；facts 出口冻结（AR5）。"""


def result_node(ctx: RunContext) -> None:
    """Result（T5~T8）：进度/覆盖率、层①②③、result.json 组装。"""


def run_chain(ctx: RunContext, init: Node) -> RunContext:
    """按序执行五节点；init 由 runner 以闭包注入（携带坐标与加载产物）。"""
    for node in (init, fetch_node, calc_node, fold_node, result_node):
        node(ctx)
    return ctx
