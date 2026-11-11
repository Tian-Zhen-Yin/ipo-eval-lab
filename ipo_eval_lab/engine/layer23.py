"""层②③：帕累托路径 + 归因枚举（设计 0005 §7；票 07）。

帕累托前沿在**全部适用套**上计算（四轴，越小越好）：
  1. not_met 叶数
  2. max gap_ratio（定量 leaf 中最大差距比例）
  3. years_high（情景进入年所需值；暂缺按 +∞）
  4. data_uncertainty（未定义叶占比）
recommendation = 前沿 ∩ 过闸套；过闸 = 套内无 not_met 的定量/documentary 硬叶
（judgment / needs_review 不挡，P3）。
excluded[] 分 reason：
  - hard_leaf_not_met：含未满足的定量/documentary 硬叶
  - dominated：被支配，附被谁支配
备选方案只在过闸套上算前沿会导致轴 1 恒为 0 而退化——已推翻 0001 已拍板的四轴，不取。

层③归因：逐 blocker 出 (verifiability × substantive_obstacle) 格位，**只计数不合成标量**。
verifiability：verified / missing_data / pending_worksheet / pending_judgment / pending_audit
substantive_obstacle：none / numeric_gap / boolean_gap
（如「缺 2022 年数据」= missing_data × none；「净利差 0.6 亿」= verified × numeric_gap）
"""
from __future__ import annotations

from ipo_eval_lab.rulebook.models import Group


def _axes(group_entry: dict) -> tuple[float, float, float, float]:
    """四轴（越小越好）。years_high 暂缺按 +∞，随层①情景落实替换。"""
    blockers = group_entry.get("blockers", []) or []
    not_met_count = len(blockers)
    max_gap = 0.0
    for b in blockers:
        g = b.get("gap_ratio") if isinstance(b, dict) else None
        if g is not None and g > max_gap:
            max_gap = g
    years_high = float("inf")  # 暂缺；层① window_roll 落实后替换
    coverage = group_entry.get("coverage", 100) / 100.0
    uncertainty = 1.0 - coverage
    return (not_met_count, max_gap, years_high, uncertainty)


def _dominates(a: tuple, b: tuple) -> bool:
    """a 支配 b：a ≤ b 所有轴且至少一轴严格小。"""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _classify_blocker(check: dict) -> tuple[str, str]:
    """单条 blocker → (verifiability, substantive_obstacle)。"""
    state = check["state"]
    if state == "indeterminate":
        # 缺年/缺口径（T3 reason 里带 "缺"），或非标意见
        reason = (check.get("reason") or "").lower()
        if "未审计" in reason or "非标意见" in reason:
            return ("pending_audit", "none")
        return ("missing_data", "none")
    if state == "needs_review":
        return ("pending_judgment", "none")
    # state == not_met：diff 三分列已定性
    fmt = check["threshold"]["format"]
    if fmt == "boolean":
        return ("verified", "boolean_gap")
    return ("verified", "numeric_gap")


def compute_layers23(
    rulebook, groups: list[Group], facts: dict, progress_coverage: dict
) -> dict:
    """返回 {hard_gate, pareto_frontier, recommendation, alternatives, excluded}。"""
    checks_by_leaf: dict[str, list[dict]] = {}
    for c in facts.get("checks", []):
        checks_by_leaf.setdefault(c["leaf_id"], []).append(c)

    entries = list(progress_coverage.values())  # {group_id, progress, coverage, blockers, ...}
    group_by_id = {g.group_id: g for g in groups}

    # ① hard gate：套内无 not_met 的定量/documentary 硬叶
    passing: list[str] = []
    hard_fails: dict[str, list[dict]] = {}
    items_by_id = {i.item_id: i for i in rulebook.items}
    for entry in entries:
        gid = entry["group_id"]
        leaf_fails: list[dict] = []
        for c in facts.get("checks", []):
            if c["group_id"] != gid:
                continue
            item = items_by_id.get(c["item_ref"])
            if item is None or item.nature == "judgment":
                continue
            if c["state"] == "not_met":
                leaf_fails.append(c)
        if leaf_fails:
            hard_fails[gid] = leaf_fails
        else:
            passing.append(gid)

    # ② 帕累托前沿（全部适用套）
    axes = {e["group_id"]: _axes(e) for e in entries}
    frontier_ids: list[str] = []
    for e in entries:
        gid = e["group_id"]
        if not any(_dominates(axes[other], axes[gid]) and other != gid for other in entries):
            frontier_ids.append(gid)

    # ③ recommendation = 前沿 ∩ 过闸
    frontier_set = set(frontier_ids)
    passing_set = set(passing)
    recommended = [gid for gid in frontier_ids if gid in passing_set]

    # ④ excluded + dominated-by
    dominated_by: dict[str, list[str]] = {}
    for e in entries:
        gid = e["group_id"]
        if gid in recommended:
            continue
        dom = [o for o in entries if o["group_id"] != gid and _dominates(axes[o["group_id"]], axes[gid])]
        if dom:
            dominated_by[gid] = [o["group_id"] for o in dom]

    excluded: list[dict] = []
    for e in entries:
        gid = e["group_id"]
        if gid in recommended:
            continue
        if gid in hard_fails:
            reason = "hard_leaf_not_met"
        elif gid in dominated_by:
            reason = "dominated"
        else:
            reason = "not_on_frontier"
        excluded.append(
            {
                "group_id": gid,
                "reason": reason,
                "dominated_by": dominated_by.get(gid, []),
                "hard_leaves": [
                    {"leaf_id": c["leaf_id"], "item_ref": c["item_ref"], "diff": c.get("diff")}
                    for c in hard_fails.get(gid, [])
                ],
            }
        )

    # ⑤ 层③归因：逐 blocker 格位（只计数）
    attribution: dict[tuple[str, str], int] = {}
    for gid, fails in hard_fails.items():
        for c in fails:
            vf, so = _classify_blocker(c)
            attribution[(vf, so)] = attribution.get((vf, so), 0) + 1

    return {
        "hard_gate": {
            "passing": passing,
            "failing": sorted(hard_fails),
            "note": "judgment/needs_review 不挡；不挡不等于 met（indeterminate 套可过闸但 coverage < 100）",
        },
        "pareto_frontier": frontier_ids,
        "recommendation": recommended,
        "alternatives": [gid for gid in frontier_ids if gid not in passing_set],
        "excluded": excluded,
        "attribution": {f"{vf} × {so}": n for (vf, so), n in sorted(attribution.items())},
        "note": "轴与归因只计数不合成标量；recommendation 为空时以层①差距画像为主体",
    }
