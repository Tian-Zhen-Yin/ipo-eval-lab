"""五节点责任链（设计 0005 §1；Fetch 先于 Calc——修 midas Init→Calc→Fetch 顺序病）。

T1：Init 实现，其余四节点占位直通；随 T2~T8 逐票点亮。
"""
from __future__ import annotations

from typing import Callable

from .calc import evaluate_leaves
from .context import RunContext
from .fetch import build_facts
from .fold import fold_checks

Node = Callable[[RunContext], None]


def fetch_node(ctx: RunContext) -> None:
    """Fetch（票 02）：statements → facts（六驱动 + 七指标，两维 measures）。"""
    ctx.facts = build_facts(ctx.inputs["rulebook"], ctx.inputs["profile"])


def calc_node(ctx: RunContext) -> None:
    """Calc（票 03）：窗口 token → 期间码 → 六量词 → 五态 + 差距三分列。"""
    ctx.facts["checks"] = evaluate_leaves(
        ctx.inputs["rulebook"], ctx.facts, ctx.selection.applicable
    )


def fold_node(ctx: RunContext) -> None:
    """Fold（票 04）：Kleene 双规则折叠 → 套终态 / 三段板块结论；出口冻结 facts（AR5）。"""
    folded = fold_checks(ctx.selection.applicable, ctx.facts["checks"])
    ctx.facts["sets"] = folded["sets"]
    ctx.facts["boards"] = folded["boards"]
    ctx.freeze_facts()


def result_node(ctx: RunContext) -> None:
    """Result（票 05~08）：进度/覆盖率、层①②③、result.json 组装——facts 只读（AR5）。"""


def run_chain(ctx: RunContext, init: Node) -> RunContext:
    """按序执行五节点；init 由 runner 以闭包注入（携带坐标与加载产物）。"""
    for node in (init, fetch_node, calc_node, fold_node, result_node):
        node(ctx)
    return ctx
