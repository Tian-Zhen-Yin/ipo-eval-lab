"""测试期生成器族（设计 0006 §7；F5/F6）：±ε 边界族 + knockout 缺数族。

两族动态生成、不落盘：读规则库阈值，阈值变则变体自动跟随（F5），
不存在「边界文件过期」问题。变体是 JSON 级 dict（未过模型），
测试侧用与引擎 Init 同一条路复核（CompanyProfile.model_validate + check_profile）。

±ε 边界族只对「单值可翻转」的叶生效，跳过规则全部显式列出：
- judgment：恒 needs_review，无 met/not_met 可翻（P3）
- thr = 0：±1 元翻转要求负年值，与 ⑥ 净利下界（−90%）不相容；E9 已另有二值规则
- quantifier ∉ {latest, sum}：all_periods/avg/cagr/ratio 无「单值 ±ε」语义
- 非直写指标（roe 派生 / 净资产：v1 样板套无此类叶）：无字段级写入口
- documentary 仅 mktcap（v1 唯一有样板叶的直写底稿指标）

数值改动沿勾稽网络传播（_set_metric_value / _reroll_equity_from）：
改净利 → 权益滚动③ + 资产负债表① + 调节表②联动改写，变体保持可加载。
latest 量词的变体对全部年度等比缩放（保同比轨迹 → ⑥ 不破），末年精确落 thr±1；
sum 量词只改末年，其余年原值（窗口合计 = thr±1）。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterator

from ..rulebook.models import Item, Leaf, Nature, Op, Quantifier, Rulebook

# Fetch 取数面的逆：指标 → 字段级写入口（v1 覆盖样板规则库全部数值叶）
# 键为 rulebook metric_id（注意 net_cash_flow_from_oper 是指标 id，对应字段
# net_cash_flow_from_operating——两者只差词尾，勿混）
_WRITABLE_METRICS = frozenset(
    {"operating_revenues", "net_profit_attrib_parent", "net_cash_flow_from_oper", "rd_investment_total"}
)
_FLIP_OPS = frozenset({Op.ge, Op.gt, Op.le, Op.lt})


@dataclass
class Variant:
    """一个测试变体：profile dict + 人读说明 + （±ε 族）目标叶期望。"""

    name: str
    profile: dict[str, Any]
    note: str
    leaf_id: str | None = None
    item_id: str | None = None
    expected_state: str | None = None  # ±ε 族：thr±1 在 op 下的期望态（E8 无 ε，整数精确翻转）
    expected_value: int | None = None  # ±ε 族：目标叶聚合值应精确等于 thr ± 1


# ── profile 取值（Fetch 语义的数据侧子集：直写指标 × latest/sum）──


def _fy_end(profile: dict[str, Any]) -> int:
    return max(s["fiscal_year"] for s in profile["statements"])


def _stmt(profile: dict[str, Any], year: int) -> dict[str, Any] | None:
    return next((s for s in profile["statements"] if s["fiscal_year"] == year), None)


def _metric_year_value(profile: dict[str, Any], year: int, metric: str) -> int | None:
    """单年指标值；缺年 / 缺口径 → None（E3 无静默回退：null 不顶替、不进比较）。"""
    s = _stmt(profile, year)
    if s is None:
        return None
    inc = s["income"]
    if metric == "operating_revenues":
        return inc["operating_revenues"]
    if metric == "net_profit_attrib_parent":
        np_ = inc["net_profit_attrib_parent"]
        if np_["excl_nonrecurring"] is None:
            return None  # 扣非缺 → 逐年孰低无值（不顶替）
        return min(np_["as_reported"], np_["excl_nonrecurring"])
    if metric == "net_cash_flow_from_oper":
        return s["cash_flow"]["net_cash_flow_from_operating"]
    if metric == "rd_investment_total":
        if inc["rd_expensed"] is None or inc["rd_capitalized"] is None:
            return None  # 任一源缺 → 该年缺值
        return inc["rd_expensed"] + inc["rd_capitalized"]
    return None


def quantified_value(profile: dict[str, Any], item: Item, fy_end: int | None = None) -> int | None:
    """按 E2 窗口解析 + E4 量词（latest/sum 子集）从 profile 复算叶值。

    窗口缺年 / 缺口径 → None（= 该叶未定义的数据前置）。仅供边界族测试断言
    「变体精确落在 thr±1 两侧」；引擎判定语义在 M4/M5 单点实现，此处不复刻五态。
    """
    fy = fy_end or _fy_end(profile)
    w = item.window
    assert w is not None
    if w.kind == "latest":
        years = [fy]
    elif w.kind == "last_n_years":
        years = list(range(fy - w.n + 1, fy + 1))
    else:  # nth_year
        years = [fy - w.n + 1]
    vals = [_metric_year_value(profile, y, item.metric_ref) for y in years]
    if any(v is None for v in vals):
        return None
    if item.quantifier is Quantifier.latest:
        return vals[-1]
    if item.quantifier is Quantifier.sum:
        return sum(vals)
    return None


# ── 勾稽传播写入 ──


def _set_metric_value(profile: dict[str, Any], year: int, metric: str, value: int) -> None:
    """写单年指标值并沿勾稽网络传播：改净利 → ③滚动→①资产负债表→②调节表联动。"""
    s = _stmt(profile, year)
    assert s is not None
    if metric == "operating_revenues":
        s["income"]["operating_revenues"] = value  # 无勾稽耦合，仅受 ⑥ 约束
    elif metric == "net_cash_flow_from_oper":
        s["cash_flow"]["net_cash_flow_from_operating"] = value
        s["reconciliation"]["net_cash_flow_from_operating"] = value
        s["reconciliation"]["adjustments"] = value - s["reconciliation"]["net_profit_total"]
    elif metric == "net_profit_attrib_parent":
        np_ = s["income"]["net_profit_attrib_parent"]
        np_["as_reported"] = np_["excl_nonrecurring"] = value  # 孰低两维同步 = 目标值
        s["income"]["net_profit_total"] = value  # 少数损益恒 0 → 总额随归母同改（V9 口径）
        _reroll_equity_from(profile, year)
    elif metric == "rd_investment_total":
        cap = s["income"]["rd_capitalized"]
        assert cap is not None  # 任一源缺则该年缺值，调用方已保证两源齐全
        s["income"]["rd_expensed"] = value - cap
    else:  # pragma: no cover - _WRITABLE_METRICS 守卫在前
        raise NotImplementedError(metric)


def _reroll_equity_from(profile: dict[str, Any], year: int) -> None:
    """从 year 起重放权益滚动（③ 链连续）并联动资产负债表（①）与调节表（②）。"""
    stmts = profile["statements"]
    idx = next(i for i, s in enumerate(stmts) if s["fiscal_year"] == year)
    for j in range(idx, len(stmts)):
        s = stmts[j]
        e = s["equity_roll"]
        e["net_profit_attrib_parent"] = s["income"]["net_profit_attrib_parent"]["as_reported"]
        e["closing_attrib_parent"] = (
            e["opening_attrib_parent"] + e["net_profit_attrib_parent"] - e["dividends"] + e["capital_injection"]
        )
        b = s["balance"]
        b["total_equity_attrib_to_parent"] = e["closing_attrib_parent"]
        b["total_equity"] = e["closing_attrib_parent"] + b["minority_interests"]
        b["total_assets"] = b["total_liabilities"] + b["total_equity"]
        r = s["reconciliation"]
        r["net_profit_total"] = s["income"]["net_profit_total"]
        r["adjustments"] = s["cash_flow"]["net_cash_flow_from_operating"] - r["net_profit_total"]
        if j + 1 < len(stmts):
            stmts[j + 1]["equity_roll"]["opening_attrib_parent"] = e["closing_attrib_parent"]


# ── ±ε 边界族（F5）──


def _iter_leaves(rb: Rulebook) -> Iterator[tuple[Leaf, Item]]:
    items = {i.item_id: i for i in rb.items}
    for g in rb.groups:
        for clause in [*g.shared_clauses, *(c for b in g.branches for c in b.clauses)]:
            for leaf in clause.leaves:
                yield leaf, items[leaf.item_ref]


def _flip_state(op: Op, delta: int) -> str:
    """thr±1 元在 op 下的期望态（E8：整数比较无 ε，两侧各只差 1 元必翻转）。"""
    if delta > 0:  # v = thr + 1
        return "met" if op in (Op.ge, Op.gt) else "not_met"
    return "not_met" if op in (Op.ge, Op.gt) else "met"


def boundary_variants(rb: Rulebook, base: dict[str, Any]) -> list[Variant]:
    """每个可翻轂数值叶生成 thr+1 / thr−1 两变体（读规则库阈值，动态跟随）。"""
    fy = _fy_end(base)
    out: list[Variant] = []
    for leaf, item in _iter_leaves(rb):
        for sign, delta in (("plus", 1), ("minus", -1)):
            v = _boundary_variant(leaf, item, base, fy, sign, delta)
            if v is not None:
                out.append(v)
    return out


def _boundary_variant(
    leaf: Leaf, item: Item, base: dict[str, Any], fy: int, sign: str, delta: int
) -> Variant | None:
    thr = leaf.threshold.value
    if isinstance(thr, bool) or not isinstance(thr, int) or thr == 0:
        return None  # 布尔阈值 / thr=0：无 ±ε 元翻转语义（见模块 docstring）
    if leaf.op not in _FLIP_OPS:
        return None  # eq/ne 的 thr±1 两侧同为 not_met，不成对翻转
    target = thr + delta
    name = f"{leaf.leaf_id}__{sign}"

    if item.nature is Nature.documentary:
        if item.metric_ref != "mktcap":
            return None
        p = copy.deepcopy(base)
        p["documentary"]["mktcap_self_estimate"] = {"value": target, "note": "±ε 边界族生成（F5）"}
        return Variant(
            name, p, f"{item.display}：底稿自估值 = {target:,}（阈值 {thr:,} {'+' if delta > 0 else '−'}1 元）",
            leaf_id=leaf.leaf_id, item_id=item.item_id,
            expected_state=_flip_state(leaf.op, delta), expected_value=target,
        )

    if item.nature is not Nature.quantitative:
        return None  # judgment 恒 needs_review（P3）
    if item.quantifier not in (Quantifier.latest, Quantifier.sum):
        return None
    metric = item.metric_ref
    if metric not in _WRITABLE_METRICS:
        return None

    p = copy.deepcopy(base)
    if item.quantifier is Quantifier.sum:
        years = list(range(fy - item.window.n + 1, fy + 1))
        if fy not in years:
            return None
        others = [_metric_year_value(base, y, metric) for y in years if y != fy]
        if any(v is None for v in others):
            return None  # 其余年已缺值：叶本身未定义，边界族无意义
        value = target - sum(others)
        if value < 0:
            return None  # 负的营收/净利年破坏 ⑥ 基年语义
        _set_metric_value(p, fy, metric, value)
        note = f"{item.display}：{fy} 年改 {value:,} → 窗口合计精确 = {target:,}"
    else:  # latest：全部年等比缩放（同比轨迹保持 → ⑥ 不破），末年精确落 target
        cur = _metric_year_value(base, fy, metric)
        if cur is None or cur <= 0 or target <= 0:
            return None
        scale = target / cur
        for s in p["statements"]:  # 缩放需全序列有值；中途发现缺值则丢弃整个 p
            y = s["fiscal_year"]
            v0 = _metric_year_value(base, y, metric)
            if v0 is None:
                return None
            v = target if y == fy else round(v0 * scale)
            if v < 0:
                return None
            _set_metric_value(p, y, metric, v)
        note = f"{item.display}：全部年等比缩放（保同比轨迹），{fy} 年精确 = {target:,}"

    return Variant(
        name, p, note,
        leaf_id=leaf.leaf_id, item_id=item.item_id,
        expected_state=_flip_state(leaf.op, delta), expected_value=target,
    )


# ── knockout 缺数族（F6；§7 四变体，测 E3 三原则的数据前置）──


def knockout_variants(base: dict[str, Any]) -> list[Variant]:
    """对 base 定稿表做删项：删首年 / 置空次年扣非 / 置空市值（G-C）/ 次年意见改 qualified。

    年份按 base 结构推导（首年 = statements[0]，次年 = 倒数第二年），基准样本
    即 2022 / 2023——若未来 base 年份变化，变体自动跟随。
    """
    years = sorted(s["fiscal_year"] for s in base["statements"])
    first, second_last = years[0], years[-2]
    out: list[Variant] = []

    p = copy.deepcopy(base)
    p["statements"] = [s for s in p["statements"] if s["fiscal_year"] != first]
    out.append(Variant(
        f"drop_{first}", p,
        f"删 {first} 整年：三年窗口叶缺年（E2-1 前置）；两年/最新窗口不受影响（E3-1 叶级隔离前置）",
    ))

    p = copy.deepcopy(base)
    _stmt(p, second_last)["income"]["net_profit_attrib_parent"]["excl_nonrecurring"] = None
    out.append(Variant(
        f"null_excl_{second_last}", p,
        f"{second_last} 扣非置空：含该年的净利叶整叶无值（E3-2 不顶替）；np_latest 照常",
    ))

    p = copy.deepcopy(base)
    p["documentary"]["mktcap_self_estimate"] = None
    out.append(Variant(
        "null_mktcap", p,
        "市值自估置空：mktcap 叶无值（G-C 落点；base 即此形态，变体保形供引擎回归对照）",
    ))

    p = copy.deepcopy(base)
    _stmt(p, second_last)["audit"]["opinion"] = "qualified"
    out.append(Variant(
        f"qualified_{second_last}", p,
        f"{second_last} 意见改 qualified：涉该年涉财叶 needs_review（E3-3 审计覆盖降级）",
    ))

    return out
