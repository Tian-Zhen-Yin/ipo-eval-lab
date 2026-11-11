"""层②③：帕累托路径 + 归因枚举（设计 0005 §7；票 07）。

帕累托前沿在**全部适用套**上计算（四轴，越小越好，design 0001 §5.1）：
  1. not_met 叶数
  2. max gap_ratio（数值叶）
  3. years_high（情景进入年所需值；暂缺按 +∞）
  4. data_uncertainty（indeterminate + needs_review **计数**，G6——度量数据完整度，
     不表征审核通过概率）
推荐三重闸（票 07 拍板「甲公司推荐空」的实现语义）：
  - 过闸：套内无 not_met 的定量/documentary 硬叶（judgment 项不构成 hard gate，P3）；
  - 无数据缺口：blocker 归因格位落 missing_data / pending_worksheet / pending_audit 的套
    不推荐——企业自估缺数据挡推荐，「宁可说清差在哪，不硬推一个套」；
  - judgment 型不确定（pending_judgment）**不挡**（0001 §5.1：推荐可以带 uncertainty），
    这类套进 alternatives。
excluded[] 分 reason：hard_leaf_not_met（硬叶未满足）/ indeterminate_data_gap（数据缺口，
票 07 措辞）/ dominated（被支配，附被谁支配）。
禁「最优」表述：输出任何位置不合成单值排序（E1~E4）。

层③归因：逐 blocker 出 (verifiability × substantive_obstacle) 格位 + 一句话依据，
只计数不合成标量，不编造治理建议。blocker 集合对齐 Fold 的 sets[].blockers
（OR 落败支路已被吸收，不进格位——与套终态的 blocker 概念同源）。
verifiability：verified / missing_data / pending_worksheet / pending_judgment / pending_audit
substantive_obstacle：none / numeric_gap / boolean_gap
（「缺 2022 年数据」= missing_data × none；「净利差 0.6 亿」= verified × numeric_gap）
"""
from __future__ import annotations

from ipo_eval_lab.rulebook.models import Group

# 数据缺口型格位：落进这些格位的套不推荐（票 07「indeterminate 数据缺口」挡推荐）
_DATA_GAP_CELLS = {"missing_data", "pending_worksheet", "pending_audit"}


def _axes(g_checks: list[dict]) -> tuple[float, float, float, float]:
    """四轴（越小越好）。years_high 暂缺按 +∞，随情景接入层②后替换。"""
    not_met = [c for c in g_checks if c["state"] == "not_met"]
    gaps = [c["gap_ratio"] for c in not_met if c.get("gap_ratio") is not None]
    uncertainty = sum(
        1 for c in g_checks if c["state"] in ("indeterminate", "needs_review")
    )
    return (float(len(not_met)), max(gaps, default=0.0), float("inf"), float(uncertainty))


def _dominates(a: tuple, b: tuple) -> bool:
    """a 支配 b：a ≤ b 所有轴且至少一轴严格小。"""
    return all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b))


def _classify_blocker(check: dict) -> tuple[str, str]:
    """单条 blocker → (verifiability, substantive_obstacle)。"""
    state = check["state"]
    if state == "indeterminate":
        # 缺年/缺口径（T3 reason 里带「缺」），或非标意见
        reason = check.get("reason") or ""
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


def _basis(check: dict, vf: str, so: str) -> str:
    """一句话依据——只复述 check 字段，不编造治理建议。"""
    if so == "numeric_gap":
        gap = check.get("gap_ratio")
        pct = f"{gap:.0%}" if gap is not None else "n/a"
        return (
            f"{check['item_ref']}：差 {check.get('diff')}（gap {pct}）"
            f"——有实测有阈值，实质差距而非数据问题"
        )
    if so == "boolean_gap":
        return f"{check['item_ref']}：布尔/动作叶未达成（无比例语义）"
    if vf == "missing_data":
        return f"{check['item_ref']}：{check.get('reason') or '数据缺口'}——缺实测不可比，可验证性降档"
    if vf == "pending_worksheet":
        return f"{check['item_ref']}：底稿未填，缺申报方输入"
    if vf == "pending_audit":
        return f"{check['item_ref']}：{check.get('reason') or '审计意见存疑'}，数据可信度待核查"
    if vf == "pending_judgment":
        return f"{check['item_ref']}：需专业意见，引擎无权代判（P3：不挡 gate 与推荐）"
    return f"{check['item_ref']}：未定义"


def compute_layers23(
    rulebook, groups: list[Group], facts: dict
) -> dict:
    """返回 {hard_gate, pareto_frontier, recommendation, alternatives, excluded, attribution}。"""
    checks = facts.get("checks", [])
    items_by_id = {i.item_id: i for i in rulebook.items}
    sets_by_id = {s["group_id"]: s for s in facts.get("sets", [])}
    checks_by_group: dict[str, list[dict]] = {}
    for c in checks:
        checks_by_group.setdefault(c["group_id"], []).append(c)

    passing: list[str] = []
    hard_fails: dict[str, list[dict]] = {}
    data_gap_gids: set[str] = set()
    attribution_cells: list[dict] = []
    axes: dict[str, tuple[float, float, float, float]] = {}

    for group in groups:
        gid = group.group_id
        g_checks = checks_by_group.get(gid, [])
        axes[gid] = _axes(g_checks)

        # blocker 集合对齐 Fold 的 sets[].blockers（OR 落败支路已吸收——否则会出现
        # 「条文经择一支路 met、套终态 criteria_met，却因落败叶过不了 gate」的矛盾）
        blocker_refs = set(sets_by_id.get(gid, {}).get("blockers", []))

        # ① hard gate：not_met 的定量/documentary 硬叶（judgment 项不挡，P3）
        fails = [
            c
            for c in g_checks
            if c["state"] == "not_met"
            and c["item_ref"] in blocker_refs
            and (item := items_by_id.get(c["item_ref"])) is not None
            and item.nature != "judgment"
        ]
        hard_fails[gid] = fails
        if not fails:
            passing.append(gid)

        # ③ 层③归因：blocker 概念与 gate / 套终态同源
        seen_items: set[str] = set()
        for c in g_checks:
            if c["state"] == "met" or c["item_ref"] not in blocker_refs:
                continue
            if c["item_ref"] in seen_items:
                continue  # 同一 blocker item 多叶（如 OR 支路）只记一格
            seen_items.add(c["item_ref"])
            vf, so = _classify_blocker(c)
            attribution_cells.append(
                {
                    "group_id": gid,
                    "leaf_id": c["leaf_id"],
                    "item_ref": c["item_ref"],
                    "verifiability": vf,
                    "substantive_obstacle": so,
                    "basis": _basis(c, vf, so),
                }
            )
            if vf in _DATA_GAP_CELLS:
                data_gap_gids.add(gid)

    # ② 帕累托前沿（全部适用套，含未过闸套——四轴保有区分度，E6）
    frontier_ids: list[str] = [
        g.group_id
        for g in groups
        if not any(
            o.group_id != g.group_id and _dominates(axes[o.group_id], axes[g.group_id])
            for o in groups
        )
    ]

    # 推荐三重闸（票 07 语义）：recommendation = 前沿 ∩ 过闸 ∩ 无任何缺口；
    # 仅 judgment 型缺口（pending_judgment）的过闸套进 alternatives（P3：不挡，作为
    # 带 uncertainty 的备选呈现）；数据缺口型（missing_data 等）→ excluded。
    frontier_set = set(frontier_ids)
    judgment_only_gids = {
        cell["group_id"]
        for cell in attribution_cells
        if cell["verifiability"] == "pending_judgment"
    }
    recommended = [
        gid
        for gid in frontier_ids
        if gid in passing
        and gid not in data_gap_gids
        and gid not in judgment_only_gids
    ]
    alternatives = [
        gid
        for gid in frontier_ids
        if gid in passing
        and gid not in data_gap_gids
        and gid in judgment_only_gids
    ]

    # ④ excluded + reason（票 07 词表：hard_leaf_not_met / indeterminate_data_gap / dominated）
    dominated_by: dict[str, list[str]] = {}
    for g in groups:
        gid = g.group_id
        if gid in recommended or gid in alternatives:
            continue
        dom = [
            o.group_id
            for o in groups
            if o.group_id != gid and _dominates(axes[o.group_id], axes[gid])
        ]
        if dom:
            dominated_by[gid] = dom

    excluded: list[dict] = []
    for g in groups:
        gid = g.group_id
        if gid in recommended or gid in alternatives:
            continue
        if hard_fails.get(gid):
            reason = "hard_leaf_not_met"
        elif gid in data_gap_gids:
            reason = "indeterminate_data_gap"
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

    counts: dict[str, int] = {}
    for cell in attribution_cells:
        key = f"{cell['verifiability']} × {cell['substantive_obstacle']}"
        counts[key] = counts.get(key, 0) + 1

    return {
        "hard_gate": {
            "passing": passing,
            "failing": sorted(gid for gid, f in hard_fails.items() if f),
            "note": "judgment/needs_review 不挡；不挡不等于 met（indeterminate 套可过闸但 coverage < 100）",
        },
        "pareto_frontier": frontier_ids,
        "recommendation": recommended,
        "alternatives": alternatives,
        "excluded": excluded,
        "attribution": {"cells": attribution_cells, "counts": counts},
        "note": "四轴与归因只计数不合成标量；recommendation 为空时以层①差距画像为主体；跨套比较走四轴，不合成单值排序",
    }
