"""进度与覆盖率（E9 / ADR-0007，设计 0005 §5.2）。

每套给进度 progress（0~100）+ 覆盖率 coverage（0~100），**必须成对出现**：
- progress = min 折叠的叶分数 × 100，与 AND 判定同源（progress = 100 ⟺ 套 met，无未定义叶时）
- coverage = 可判叶数 / 适用叶总数 × 100
- 未定义叶（indeterminate / needs_review）**不进进度聚合，只进覆盖分母**（midas null→0 病灶的对照）
- 进度不参与判定，≥100 时 binding/next 为 null（无卡点）
- 卡点 binding_clause_id = 子句分数最小的子句（ADR-0007「达成最小叶分数的 clause」）
- 次弱 next_binding_clause_id 回答「补完卡点后下一个是谁」：只看**有差距语义**的叶，按 gap_ratio
  降序取 binding 之后的第一个——OR 支路不构成约束（design 0005 §5.2 边界规则，Kleene OR 下
  支路不是独立约束）；thr=0 / 布尔叶 gap 分母为 0、无比例可言；无 gap（None）的叶不可排序。
  甲公司算例：候选仅剩 c2（gap −0.07，距 2 亿门槛仅 7% 富余）→ 次弱 = cn_main_g1_c2，
  与 golden / 设计 0006 §契约算例逐字一致

coverage < 100% 的套由 coverage_forbidden_claims 生成追加禁令（禁「可达标 / 预计能过」，
进度限定「已评估部分」），随 T8 汇编进 narrative_handoff.forbidden_claims。

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
        # 豁免叶（not_applicable，ADR-0008）既不进 coverage 分母、也不进 progress 聚合：
        # 它有确定结论「法律上不约束」——既非数据缺口（不该拉低 coverage、误触
        # 「禁可达标」禁令），也非未定义叶（不该拖低 progress）。
        g_checks = [c for c in by_group.get(group.group_id, [])
                    if c["state"] != "not_applicable"]
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
        if not defined_clauses:
            # 无可判子句：两种成因须分开——
            #   (a) 全被豁免（ADR-0008）：无约束 → progress=100（空约束集的恒等元）
            #   (b) 全为未定义叶（indeterminate/needs_review）：判不了 → progress=0
            # 混为一谈会把「依法不受约束」误读成「进展为零」。
            all_exempt = bool(by_group.get(group.group_id)) and not g_checks
            progress = 100 if all_exempt else 0
        else:
            progress = round(min(s for _, s in defined_clauses) * 100)

        if progress >= 100:
            binding = next_binding = None  # ≥100 无卡点（设计 0005 §5.2）
        elif not defined_clauses:
            binding = next_binding = None  # 无可判子句（无叶 / 全未定义）：无卡点可言
        else:
            ordered = sorted(defined_clauses, key=lambda t: t[1])  # 稳定；binding = 分数最小的子句
            binding = ordered[0][0]
            # 次弱：在「有差距语义」的叶里按 gap_ratio 降序取 binding 之后的第一个（弱者在前）。
            # 排除三类：binding 自身子句；any 逻辑子句的支路叶（Kleene OR 下不构成约束）；
            # 无 gap 的叶（thr=0 / 布尔叶 gap_ratio 无定义，二值无「差多少」）。
            candidates = [
                c
                for c in g_checks
                if c["clause_id"] != binding
                and c["clause_logic"] != "any"
                and c["state"] in ("met", "not_met")
                and c.get("gap_ratio") is not None
            ]
            candidates.sort(key=lambda c: c["gap_ratio"], reverse=True)
            next_binding = candidates[0]["clause_id"] if candidates else None

        out[group.group_id] = {
            "progress": progress,
            "coverage": coverage,
            "binding_clause_id": binding,
            "next_binding_clause_id": next_binding,
        }
    return out


def coverage_forbidden_claims(progress_coverage: dict[str, dict]) -> list[str]:
    """coverage < 100% 的套生成追加禁令（E9 / ADR-0007；随 T8 汇编进 narrative_handoff）。

    覆盖不满时进度只代表「已评估部分」，禁「可达标 / 预计能过」式表述——
    禁止把未评估叶当隐形加分项。coverage = 100% 的套不产生禁令。
    """
    claims: list[str] = []
    for gid, pc in progress_coverage.items():
        if pc["coverage"] < 100:
            claims.append(
                f"套 {gid} coverage={pc['coverage']}%<100%：禁「可达标 / 预计能过」表述，"
                f"进度仅代表已评估部分（{100 - pc['coverage']}% 叶因数据缺口未判定）"
            )
    return claims
