"""Calc 节点（设计 0005 §3/§4；票 03）：窗口解析 + 六量词 + 五态 + 差距三分列。

窗口单点（§3）：锚 = fiscal_years 最后一个完整会计年度 FY_end；窗口不足/断年 →
indeterminate（**不缩窗、不外推、不补零**）；stub 永不进窗口。
判定矩阵（§4.1）+ 审计覆盖（§4.4-3）：非标意见年涉叶 → needs_review；未审计年涉叶
→ indeterminate——均叶级、随后按普通状态参与折叠（T4）。涉财叶的闸门**读规则库**
metric.measures.audit（AR3 数据驱动：校准给任何指标加 audit measure，行为自动跟随）。
缺数三原则（§4.4）：叶级隔离 / 无静默回退（**null 永不进比较**，修 midas
`ResultEvalServiceImpl.java:149` 的 null→0）/ 审计覆盖降级。

差距三分列（§4.3）：数值叶 diff + gap_ratio（thr=0 只报 diff 不造无穷大）；
计数叶 required_delta；布尔/动作叶 required_action（文案引自条文配置，不自由发挥）。
CAGR 用勘误后方向 (末/首)^(1/(n−1))−1（评审 0004 P0 病灶是分子分母颠倒）。
"""
from __future__ import annotations

from typing import Any, Callable

from ipo_eval_lab.rulebook.models import Group, Item, Leaf, Metric, Rulebook, Window

from .errors import EngineError

MET = "met"
NOT_MET = "not_met"
INDET = "indeterminate"
NEEDS_REVIEW = "needs_review"
NON_STANDARD = ("qualified", "disclaimer", "adverse")  # 非标意见 → needs_review（§4.1）


class _MissingValue(Exception):
    """窗口内某年缺值/缺年——转 indeterminate + 显式原因（无静默回退）。专用异常，不与 ValueError 混用。"""


# op 语义单点：比较与差距方向同一张表（§4.2 判定 + §4.3 diff 公式）
_OPS: dict[str, tuple[Callable[[Any, Any], bool], Callable[[Any, Any], Any]]] = {
    "eq": (lambda v, t: v == t, lambda v, t: abs(v - t)),
    "ne": (lambda v, t: v != t, lambda v, t: None),  # ne 无差距概念
    "gt": (lambda v, t: v > t, lambda v, t: t - v),
    "ge": (lambda v, t: v >= t, lambda v, t: t - v),
    "lt": (lambda v, t: v < t, lambda v, t: v - t),
    "le": (lambda v, t: v <= t, lambda v, t: v - t),
}
_CMP = {op: fns[0] for op, fns in _OPS.items()}  # 测试可读入口


def resolve_window(window: Window, fiscal_years: list[int]) -> tuple[list[int] | None, list[int]]:
    """窗口 token → (期间码或 None, 需求年列表)。不可满足 → (None, want)——want 供原因组装，单点不重算。"""
    fy_end = fiscal_years[-1]
    if window.kind == "latest":
        want = [fy_end]
    elif window.kind == "last_n_years":
        want = list(range(fy_end - window.n + 1, fy_end + 1))
    elif window.kind == "nth_year":
        want = [fy_end - window.n + 1]
    else:
        raise EngineError(f"未知窗口 kind：{window.kind}")
    have = set(fiscal_years)
    ok = want and all(y in have for y in want)
    return (want if ok else None), want


def cagr(values: list[float]) -> float | None:
    """(x[末]/x[首])^(1/(n−1)) − 1，n = 窗口年数。

    无定义 → None：n < 2；首年 ≤ 0（设计 §4.2）；末年 < 0（防御性——负/正的分数幂
    得复数，设计未列此边界，宁可 indeterminate 不许复数下沉比较）。
    """
    n = len(values)
    if n < 2 or values[0] <= 0 or values[-1] < 0:
        return None
    return (values[-1] / values[0]) ** (1 / (n - 1)) - 1


def _decision_node(metric_node: dict[str, Any], metric: Metric) -> dict[str, Any]:
    """指标节点 → 判定用序列（decision_measure 优先；documentary 单值原样）。"""
    if metric.decision_measure == "lower_of_both":
        return metric_node["lower_of_both"]
    if "series" in metric_node:
        return metric_node["series"]
    return metric_node


def _window_values(metric_node: dict[str, Any], metric: Metric, periods: list[int]) -> tuple[list[float], list[str]]:
    """取窗口内各年判定值 + refs（去重保序）；缺年/缺值 → _MissingValue(原因)。"""
    node = _decision_node(metric_node, metric)
    vals: list[float] = []
    refs: list[str] = []
    for y in periods:
        entry = node.get(y)
        if entry is None:
            raise _MissingValue(f"{y} 年无实测（序列缺年）")
        if entry["value"] is None:
            raise _MissingValue(f"{y} 年缺值：{entry.get('reason') or '原因未注明'}")
        vals.append(entry["value"])
        refs.extend(r for r in entry["refs"] if r not in refs)
    return vals, refs


def _audit_gate(
    metric: Metric, periods: list[int], facts: dict[str, Any]
) -> tuple[str, str] | None:
    """审计覆盖降级闸门（§4.4-3，叶级）。返回 (state, reason) 或 None（放行）。

    闸门读规则库：metrics.yaml 声明 measures.audit 含 "audited" 的指标才受降级
    （当前仅净利——校准铺开后任何指标加声明即自动跟随，AR3）。
    """
    if not (metric.measures and "audited" in metric.measures.audit):
        return None
    for y in periods:
        audit = facts["audit"].get(y, {})
        if audit.get("status") != "audited":
            return INDET, f"{y} 年未审计（窗口年不可用，measures.audit=[audited]）"
        if audit.get("opinion") in NON_STANDARD:
            return NEEDS_REVIEW, f"{y} 年非标意见（{audit['opinion']}）→ 人工核查"
    return None


def _base_check(leaf: Leaf) -> dict[str, Any]:
    return {
        "leaf_id": leaf.leaf_id,
        "item_ref": leaf.item_ref,
        "op": leaf.op.value,
        "threshold": {"value": leaf.threshold.value, "format": leaf.threshold.format.value},
        "state": None,
        "value": None,
        "diff": None,
        "gap_ratio": None,
        "reason": None,
        "refs": [],
    }


def _fill_gap(check: dict[str, Any], v: float, leaf: Leaf) -> dict[str, Any]:
    """差距三分列（§4.3）。数值 diff+gap_ratio / 计数 required_delta / 布尔 required_action。"""
    thr, op, fmt = leaf.threshold.value, leaf.op.value, leaf.threshold.format.value
    if fmt in ("number", "percent"):
        d = _OPS[op][1](v, thr)
        check["diff"] = d
        if d is not None and thr != 0:
            check["gap_ratio"] = d / abs(thr)
    elif fmt == "integer":
        check["required_delta"] = int(thr - v)
    elif fmt == "boolean":
        # 文案引自条文配置（leaf.note / 校准 evidence 回填），引擎不自由发挥
        check["required_action"] = leaf.note
    return check


def _eval_quantified(
    check: dict[str, Any], leaf: Leaf, item: Item, metric: Metric,
    facts: dict[str, Any], metrics_by_id: dict[str, Metric], metric_nodes: dict[str, Any],
) -> dict[str, Any]:
    """quantitative × calc 主路径：窗口 → 审计闸门 → 六量词 → 比较 + 差距。"""
    thr, op = leaf.threshold.value, leaf.op.value

    # 窗口（§3）：不足/断年 → indeterminate，不缩窗不外推不补零
    fiscal_years = sorted(facts["audit"].keys())
    periods, want = resolve_window(item.window, fiscal_years)
    if periods is None:
        check.update(
            state=INDET,
            reason=f"窗口需 {want}，实有 {fiscal_years}（不缩窗、不外推、不补零）",
        )
        return check

    # 审计闸门（§4.4-3）
    gate = _audit_gate(metric, periods, facts)
    if gate is not None:
        check.update(state=gate[0], reason=gate[1])
        return check

    # 六量词（§4.2）
    try:
        if item.quantifier == "ratio":
            num_metric, den_metric = metrics_by_id[item.numerator], metrics_by_id[item.denominator]  # type: ignore[index]
            num_vals, refs_n = _window_values(metric_nodes[num_metric.metric_id], num_metric, periods)
            den_vals, refs_d = _window_values(metric_nodes[den_metric.metric_id], den_metric, periods)
            den_sum = sum(den_vals)
            if den_sum == 0:
                check.update(state=INDET, reason="ratio 分母合计 = 0（无定义）")
                return check
            check["refs"] = refs_n + [r for r in refs_d if r not in refs_n]
            v: float = sum(num_vals) / den_sum
        else:
            vals, check["refs"] = _window_values(metric_nodes[metric.metric_id], metric, periods)
            if item.quantifier == "latest":
                v = vals[-1]
            elif item.quantifier == "sum":
                v = sum(vals)
            elif item.quantifier == "avg":
                v = sum(vals) / len(vals)
            elif item.quantifier == "cagr":
                c = cagr(vals)
                if c is None:
                    check.update(state=INDET, reason=f"CAGR 无定义（首年 {vals[0]} ≤ 0 / 末年 < 0 / 窗口 < 2 年）")
                    return check
                v = c
            elif item.quantifier == "all_periods":
                bad = [y for y, val in zip(periods, vals) if not _CMP[op](val, thr)]
                check.update(
                    state=MET if not bad else NOT_MET,
                    value=min(vals),
                    reason=None if not bad else f"窗口内不满足年：{bad}",
                )
                return check  # 全称量词叶级二值（ADR-0007），无单一 diff
            else:
                raise EngineError(f"未知量词：{item.quantifier}")
    except _MissingValue as e:  # 缺年/缺值 → indeterminate + 显式原因（无静默回退）
        check.update(state=INDET, reason=str(e))
        return check

    check["value"] = v
    check["state"] = MET if _CMP[op](v, thr) else NOT_MET
    return _fill_gap(check, v, leaf)


def evaluate_leaf(
    leaf: Leaf,
    item: Item,
    metric: Metric | None,
    facts: dict[str, Any],
    metrics_by_id: dict[str, Metric],
    metric_nodes: dict[str, Any],
) -> dict[str, Any]:
    """单叶五态判定 + 差距三分列。产出是 checks[] 的行（契约 §3.2 形态，T8 汇编）。"""
    check = _base_check(leaf)

    # judgment × declared：恒 needs_review，永不 met（§4.1）
    if item.nature == "judgment":
        check.update(
            state=NEEDS_REVIEW,
            pending_evidence=list(item.pending_evidence),
            reason="judgment × declared：需专业意见，永不 met（declared 值只作证据）",
        )
        return check

    if metric is None:
        raise EngineError(f"item {item.item_id} 非 judgment 却无 metric_ref")
    thr, op = leaf.threshold.value, leaf.op.value

    # documentary × worksheet：无窗口量词，按底稿值判；无值 indeterminate（§4.1）
    if item.quantifier is None or item.window is None:
        node = _decision_node(metric_nodes[metric.metric_id], metric)
        check["refs"] = list(node["refs"])
        if node["value"] is None:
            check.update(state=INDET, reason=node.get("reason") or "底稿值缺（documentary）")
            return check
        check["value"] = node["value"]
        check["state"] = MET if _CMP[op](node["value"], thr) else NOT_MET
        return _fill_gap(check, node["value"], leaf)

    return _eval_quantified(check, leaf, item, metric, facts, metrics_by_id, metric_nodes)


def evaluate_leaves(rulebook: Rulebook, facts: dict[str, Any], groups: list[Group]) -> list[dict[str, Any]]:
    """对适用套的全部叶求判定（叶级隔离：缺数只杀含该年的叶）。折叠归 T4。"""
    items_by_id = {i.item_id: i for i in rulebook.items}
    metrics_by_id = {m.metric_id: m for m in rulebook.metrics}
    metric_nodes = facts["metrics"]
    checks: list[dict[str, Any]] = []
    for group in groups:
        clauses = [(c, None) for c in group.shared_clauses]
        for branch in group.branches:
            clauses.extend((c, branch) for c in branch.clauses)
        for clause, branch in clauses:
            for leaf in clause.leaves:
                item = items_by_id.get(leaf.item_ref)
                if item is None:
                    raise EngineError(f"叶 {leaf.leaf_id} 引用未知 item：{leaf.item_ref}")
                metric = metrics_by_id.get(item.metric_ref) if item.metric_ref else None
                check = evaluate_leaf(leaf, item, metric, facts, metrics_by_id, metric_nodes)
                check.update(
                    group_id=group.group_id,
                    clause_id=clause.clause_id,
                    clause_logic=clause.logic,
                    set_id=branch.set_id if branch else None,
                )
                checks.append(check)
    return checks
