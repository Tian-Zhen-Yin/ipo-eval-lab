"""进度与覆盖率（E9 / ADR-0007，设计 0005 §5.2）。

每套给进度 progress（0~100）+ 覆盖率 coverage（0~100），**必须成对出现**：
- progress = min 折叠的叶分数 × 100，与 AND 判定同源（progress = 100 ⟺ 套 met，无未定义叶时）
- coverage = 可判叶数 / 适用叶总数 × 100
- 未定义叶（indeterminate / needs_review）**不进进度聚合，只进覆盖分母**（midas null→0 病灶的对照）
- 进度不参与判定，≥100 时 binding/next 为 null（无卡点）
- 卡点 binding_clause_id = 进度最小的子句；次弱 next_binding_clause_id = 第2小（平序按子句出现顺序）

叶分数：met→1；not_met 有 gap_ratio→1−gap_ratio；thr=0 或布尔/动作叶→0；undefined→None。
子句得分：all→min（任一 undefined→子句 undefined）；any→max（定义叶，全 undefined→子句 undefined）。
套得分：min(定义子句得分)。

共享子句（shared_clauses）折进每个 branch，checks 行里会重复出现，聚合前按 clause_id 去重。
"""
from __future__ import annotations

from ipo_eval_lab.rulebook.models import Group


def _leaf_score(check: dict) -> float | None:
    """单叶得分 0~1；未定义 → None（不进聚合，不是 0）。"""
    state = check["state"]
    if state == "met":
        return 1.0
    if state == "not_met":
        thr = check["threshold"]["value"]
        if thr == 0:
            return 0.0  # gap_ratio 无定义（三年均为正等），不造无穷大
        g = check.get("gap_ratio")
        return (1.0 - g) if g is not None else 0.0
    return None  # indeterminate / needs_review：不进聚合


def compute_progress_coverage(
    groups: list[Group], checks: list[dict]
) -> dict[str, dict]:
    """返回 {group_id: {progress, coverage, binding_clause_id, next_binding_clause_id}}。"""
    by_group: dict[str, list[dict]] = {}
    for c in checks:
        by_group.setdefault(c["group_id"], []).append(c)

    out: dict[str, dict] = {}
    for group in groups:
        g_checks = by_group.get(group.group_id, [])
        total_leaves = len(g_checks)
        defined_leaves = [c for c in g_checks if c["state"] in ("met", "not_met")]
        coverage = round(len(defined_leaves) / total_leaves * 100) if total_leaves else 100

        # 按 clause_id 聚合（shared clause 会在多个 branch 中重复出现，去重后再算子句得分）
        clauses: dict[str, dict] = {}
        order: list[str] = []
        for c in g_checks:
            cid = c["clause_id"]
            if cid not in clauses:
                clauses[cid] = {"logic": c["clause_logic"], "leaves": []}
                order.append(cid)
            clauses[cid]["leaves"].append(c)

        clause_score: dict[str, float | None] = {}
        for cid in order:
            cd = clauses[cid]
            scores = [_leaf_score(c) for c in cd["leaves"]]
            defined = [s for s in scores if s is not None]
            if cd["logic"] == "any":
                clause_score[cid] = max(defined) if defined else None
            else:  # all：任一 undefined → 子句 undefined
                clause_score[cid] = (
                    min(defined) if (len(defined) == len(scores)) else None
                )

        defined_clauses = [(cid, s) for cid, s in clause_score.items() if s is not None]
        progress = round(min(s for _, s in defined_clauses) * 100) if defined_clauses else 0

        if progress >= 100:
            binding = next_binding = None
        else:
            ordered = sorted(defined_clauses, key=lambda t: t[1])  # 稳定，平序按子句出现顺序
            binding = ordered[0][0]
            next_binding = ordered[1][0] if len(ordered) > 1 else None

        out[group.group_id] = {
            "progress": progress,
            "coverage": coverage,
            "binding_clause_id": binding,
            "next_binding_clause_id": next_binding,
        }
    return out
