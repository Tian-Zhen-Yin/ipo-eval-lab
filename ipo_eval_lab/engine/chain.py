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
    """Calc（票 03）：窗口 token → 期间码 → 六量词 → 五态 + 差距三分列。

    profile 传入是为豁免判定（ADR-0008）：命中豁免的叶在取数前即判 not_applicable。
    """
    ctx.facts["checks"] = evaluate_leaves(
        ctx.inputs["rulebook"], ctx.facts, ctx.selection.applicable,
        profile=ctx.inputs.get("profile"),
    )


def fold_node(ctx: RunContext) -> None:
    """Fold（票 04）：Kleene 双规则折叠 → 套终态 / 三段板块结论；出口冻结 facts（AR5）。"""
    folded = fold_checks(ctx.selection.applicable, ctx.facts["checks"])
    ctx.facts["sets"] = folded["sets"]
    ctx.facts["boards"] = folded["boards"]
    ctx.freeze_facts()


def result_node(ctx: RunContext) -> None:
    """Result（票 05~08）：进度/覆盖率、层①②③、契约 v0.2 组装——facts 只读（AR5）。

    层①②③在本节点统一接线：progress（T5）→ scenario（T6）/layers23（T7）→
    assemble_result（票 08）；facts 在 Fold 出口已冻结，这里只读。
    """
    from .layer1 import compute_scenario
    from .layer23 import compute_layers23
    from .progress import compute_progress_coverage
    from .result import assemble_result

    rulebook = ctx.inputs["rulebook"]
    groups = ctx.selection.applicable
    progress_coverage = compute_progress_coverage(groups, ctx.facts["checks"])
    scenario = compute_scenario(rulebook, groups, ctx.facts)
    layers23 = compute_layers23(rulebook, groups, ctx.facts)
    ctx.result = assemble_result(
        ctx, progress_coverage=progress_coverage, scenario=scenario, layers23=layers23
    )
    # layers 段同时挂 ctx（供终端摘要等消费；契约全量在 ctx.result）
    ctx.layers = ctx.result["layers"]


def run_chain(ctx: RunContext, init: Node) -> RunContext:
    """按序执行五节点；init 由 runner 以闭包注入（携带坐标与加载产物）。"""
    for node in (init, fetch_node, calc_node, fold_node, result_node):
        node(ctx)
    return ctx
