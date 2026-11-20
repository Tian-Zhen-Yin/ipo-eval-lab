"""Result 出口组装（契约 v0.2；设计 0004 §6 / 票 08）。

四段：run / facts / layers / narrative_handoff——单文件自包含，外部叙述 agent
只需要这一个 JSON（设计 0004 §6：agent 不需要读规则库或 fixtures）。

- facts 与 Fold 出口冻结对象同源（AR5）：直接引用 ctx.facts，不拷贝不改写。
- 每个数字带 refs（不变量 5）：key_checks / window_roll 行带 law_ref；
  citation_index 提供阈值判定 → item → metric → law_ref（law_id#article）直达法条。
- narrative_handoff：固定 disclaimers（段①抽样核查 / 甜区声明 / 市值自估）+ 动态边界
  （审计状态与规则版本 / judgment 未核查清单 / 资格认定）；forbidden_claims 固定条目
  + coverage<100 追加禁令（E9 / ADR-0007）+ scenario is_forecast 标注义务。
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from ipo_eval_lab.rulebook.models import Group, Rulebook

# ── 固定措辞（设计 0001 §5.2 / 票 08） ─────────────────────────

_FIXED_DISCLAIMERS = [
    "段①抽样核查：发行条件部分只覆盖保荐人核查清单的子集（募集资金运用等节零覆盖），「指标层面满足」≠ 尽调通过",
    "甜区声明：64 套中 40 套为特殊画像套（红筹/表决权差异），定性条文密集、needs_review 必然集中；工具的有效区是一般企业套（24 套）+ 定位叠加",
    "预计市值依赖自估：所有市值类结论一律带「企业自估」限定",
]
_DISCLAIMER_ELIGIBILITY = "上市资格由交易所/证监会认定，本工具输出为指标层面参照"

_FIXED_FORBIDDEN = [
    "禁「符合发行条件」——只能说「指标层面满足/不满足 X 套的 Y 条件」",
    "禁「能够上市 / 即将上市 / 保证过会」",
    "禁「不符合上市条件」——只能说「指标层面不满足 X 套的 Y 条件」",
    "禁「预计 N 年达标」——除非逐字转述 scenario 且带 is_forecast 标注",
    "禁「本报告可替代专业意见」",
]
_FORBIDDEN_SCENARIO = "情景数字（window_roll/growth）仅可逐字转述并必须保留 is_forecast=true 标注，不得写成预测结论"


def _json_safe(obj: Any) -> Any:
    """date/datetime → isoformat；其余原样（契约要求整个文件可 json.dumps）。"""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


def _clause_law_refs(rulebook: Rulebook) -> dict[str, str]:
    """clause_id → law_ref（shared_clauses 与 branch clauses 合并，同 id 同文）。"""
    out: dict[str, str] = {}
    for group in rulebook.groups:
        for clause in group.shared_clauses:
            out[clause.clause_id] = clause.law_ref
        for branch in group.branches:
            for clause in branch.clauses:
                out[clause.clause_id] = clause.law_ref
    return out


def _check_rows_by_clause(facts: dict, clause_id: str) -> list[dict]:
    return [c for c in facts.get("checks", []) if c["clause_id"] == clause_id]


def _leaf_rows(facts: dict, clause_id: str, law_refs: dict[str, str]) -> list[dict]:
    """卡点/次弱 clause 的叶级行：{leaf_id, item_ref, state, diff?, refs}。"""
    rows = []
    for c in _check_rows_by_clause(facts, clause_id):
        row: dict[str, Any] = {
            "leaf_id": c["leaf_id"],
            "item_ref": c["item_ref"],
            "state": c["state"],
            "refs": [law_refs.get(c["clause_id"], c["clause_id"])],
        }
        if c.get("diff") is not None:
            row["diff"] = c["diff"]
        rows.append(row)
    return rows


def _key_checks(
    rulebook: Rulebook, facts: dict, progress_coverage: dict, law_refs: dict[str, str]
) -> list[dict]:
    """关键检查（设计 0006 §6 golden 口径）：卡点叶 + 次弱叶 + any 条文折叠行（Kleene 活例）。"""
    rows: list[dict] = []
    emitted_clauses: set[str] = set()
    for group in rulebook.groups:
        gid = group.group_id
        pc = progress_coverage.get(gid, {})
        # 卡点 → 次弱的顺序（golden：np_latest 叶、OR 条文、np_3y_sum 叶）
        for cid in (pc.get("binding_clause_id"), pc.get("next_binding_clause_id")):
            if cid and cid not in emitted_clauses:
                rows.extend(_leaf_rows(facts, cid, law_refs))
                emitted_clauses.add(cid)
        # any 条文折叠行（clause 级 met/not_met——Kleene OR 活例）
        for sset in facts.get("sets", []):
            if sset["group_id"] != gid:
                continue
            for branch in sset.get("branches", []):
                for cd in branch.get("clauses", []):
                    clause = _find_clause(rulebook, cd["clause_id"])
                    if clause is not None and clause.logic == "any" and cd["clause_id"] not in emitted_clauses:
                        rows.append(
                            {
                                "clause_id": cd["clause_id"],
                                "state": cd["state"],
                                "refs": [law_refs.get(cd["clause_id"], cd["clause_id"])],
                            }
                        )
                        emitted_clauses.add(cd["clause_id"])
    return rows


def _find_clause(rulebook: Rulebook, clause_id: str):
    for group in rulebook.groups:
        for clause in group.shared_clauses:
            if clause.clause_id == clause_id:
                return clause
        for branch in group.branches:
            for clause in branch.clauses:
                if clause.clause_id == clause_id:
                    return clause
    return None


def _window_roll_rows(
    rulebook: Rulebook, facts: dict, scenario: dict, law_refs: dict[str, str]
) -> list[dict]:
    """层① window_roll → 契约行：{leaf_id, item_ref, required, rolled_state, assumption, risk, refs}（golden 口径字段）。"""
    rows = []
    for e in scenario.get("window_roll", []):
        rows.append(
            {
                "leaf_id": e["leaf_id"],
                "item_ref": e["item_ref"],
                "required": e["required_entering_year_value"],
                "rolled_state": e.get("rolled_state"),
                "assumption": e.get("assumption", "zero_growth"),
                "risk": e["risk"],
                "k": e["k"],
                "recent_actual": e["recent_actual"],
                "refs": [law_refs.get(_leaf_clause(facts, e["leaf_id"]), e["leaf_id"])],
            }
        )
    return rows


def _leaf_clause(facts: dict, leaf_id: str) -> str:
    for c in facts.get("checks", []):
        if c["leaf_id"] == leaf_id:
            return c["clause_id"]
    return leaf_id


def _citation_index(rulebook: Rulebook, facts: dict, law_refs: dict[str, str]) -> list[dict]:
    """阈值判定 → item → metric → law_ref（law_id#article）直达法条（不变量 5 的链路补全）。"""
    items_by_id = {i.item_id: i for i in rulebook.items}
    seen: set[str] = set()
    rows: list[dict] = []
    for c in facts.get("checks", []):
        if c["leaf_id"] in seen:
            continue
        seen.add(c["leaf_id"])
        item = items_by_id.get(c["item_ref"])
        rows.append(
            {
                "leaf_id": c["leaf_id"],
                "clause_id": c["clause_id"],
                "item_ref": c["item_ref"],
                "metric_ref": getattr(item, "metric_ref", None),
                "law_ref": law_refs.get(c["clause_id"], c["clause_id"]),
                "op": c["op"],
                "threshold": c["threshold"],
                "data_refs": c.get("refs", []),
            }
        )
    return rows


def _narrative_handoff(
    rulebook: Rulebook, facts: dict, layers: dict, progress_coverage: dict
) -> dict:
    """叙述交接（自包含）：units（复述数字，必带 refs）+ citation_index + disclaimers + forbidden_claims。

    进度不进 narrative 素材（E9 禁令）——units 只复述终态/blockers/情景，不出现分数叙述。
    """
    law_refs = _clause_law_refs(rulebook)
    units: list[dict] = []

    for sset in facts.get("sets", []):
        gid = sset["group_id"]
        pc = progress_coverage.get(gid, {})
        line = f"{gid}：基于所提供数据与 as_of 规则版本，指标层面{sset['outcome']}"
        if pc.get("binding_clause_id"):
            line += f"；卡点条款 {pc['binding_clause_id']}"
            if pc.get("next_binding_clause_id"):
                line += f"，次弱 {pc['next_binding_clause_id']}"
        if sset.get("blockers"):
            line += f"；blockers={'、'.join(sset['blockers'])}"
        units.append(
            {
                "unit_id": f"set:{gid}",
                "kind": "set_outcome",
                "text": line + "。",
                "refs": [law_refs.get(cid, cid) for cid in _group_clause_ids(rulebook, gid)][:1],
            }
        )
        path = layers.get("path", {})
        for e in path.get("excluded", []):
            if e["group_id"] == gid:
                units.append(
                    {
                        "unit_id": f"excl:{gid}",
                        "kind": "path_excluded",
                        "text": f"{gid} 未进推荐：{e['reason']}（依据层② gate 与四轴比较，不合成单值排序）。",
                        "refs": [law_refs.get(cid, cid) for cid in _group_clause_ids(rulebook, gid)][:1],
                    }
                )

    for row in layers.get("gap", {}).get("window_roll", []):
        rolled = row.get("rolled_state")
        verdict = ""
        if rolled == "met":
            verdict = "零增长假设（进入年值=最近一年实际）下推迟申报：指标层面仍满足。"
        elif rolled == "not_met":
            verdict = "零增长假设（进入年值=最近一年实际）下推迟申报：指标层面不满足。"
        units.append(
            {
                "unit_id": f"roll:{row['leaf_id']}",
                "kind": "window_roll",
                "text": (
                    f"{row['leaf_id']}：报告期窗口滚动一年，进入年需 {row['required']:g}"
                    f"（vs 最近年实际 {row['recent_actual']:g}，滚动风险 {row['risk']}）。{verdict}"
                ),
                "refs": row["refs"],
            }
        )

    for row in layers.get("gap", {}).get("growth_rows", []):
        units.append(
            {
                "unit_id": f"growth:{row['leaf_id']}",
                "kind": "growth_scenario",
                "text": (
                    f"{row['leaf_id']}：两点情景（r=0 与历史 CAGR {row['hist_cagr']:.1%}）"
                    f"下进入年值区间 [{row['years_low']:g}, {row['years_high']:g}]，is_forecast=true。"
                ),
                "refs": row["refs"],
            }
        )

    run = layers["run_ref"]
    disclaimers = list(_FIXED_DISCLAIMERS)
    disclaimers.append(
        f"数据与口径：规则库 {rulebook.meta.rulebook_version}@as_of {run['as_of_date']}；"
        f"报告期审计状态 {run['report_period']['audit_status']}/{run['report_period']['audit_opinion']}"
    )
    pending = [j for s in facts.get("sets", []) for j in s.get("pending_judgments", [])]
    if pending:
        names = "、".join(j["item_ref"] if isinstance(j, dict) else str(j) for j in pending)
        disclaimers.append(f"judgment 项未核查 {len(pending)} 项：{names}（引擎无权代判）")
    disclaimers.append(_DISCLAIMER_ELIGIBILITY)

    forbidden = list(_FIXED_FORBIDDEN) + [_FORBIDDEN_SCENARIO]
    forbidden.extend(_coverage_claims(progress_coverage))

    return {
        "units": units,
        "citation_index": layers["citation_index"],
        "disclaimers": disclaimers,
        "forbidden_claims": forbidden,
    }


def _coverage_claims(progress_coverage: dict) -> list[str]:
    """coverage < 100% 的追加禁令（E9；实现在 progress.coverage_forbidden_claims）。"""
    from .progress import coverage_forbidden_claims

    return coverage_forbidden_claims(progress_coverage)


def _group_clause_ids(rulebook: Rulebook, group_id: str) -> list[str]:
    for group in rulebook.groups:
        if group.group_id == group_id:
            ids = [c.clause_id for c in group.shared_clauses]
            for branch in group.branches:
                ids.extend(c.clause_id for c in branch.clauses)
            return ids
    return []


def assemble_result(
    ctx,
    progress_coverage: dict,
    scenario: dict,
    layers23: dict,
) -> dict:
    """契约 v0.2 四段组装。facts 引用冻结对象（AR5）；整体 JSON-safe。"""
    rulebook: Rulebook = ctx.inputs["rulebook"]
    facts = ctx.facts  # AR5：同一对象，不拷贝
    law_refs = _clause_law_refs(rulebook)

    # 层① gap
    pc_by_gid = progress_coverage
    gap_sets = []
    for sset in facts.get("sets", []):
        gid = sset["group_id"]
        pc = pc_by_gid.get(gid, {})
        gap_sets.append(
            {
                "group_id": gid,
                "display": sset.get("display"),
                "boards": sset.get("boards", []),
                "outcome": sset["outcome"],
                "blockers": sset.get("blockers", []),
                "needs_review_count": sset.get("needs_review_count", 0),
                "progress": pc.get("progress"),
                "coverage": pc.get("coverage"),
                "binding_clause_id": pc.get("binding_clause_id"),
                "next_binding_clause_id": pc.get("next_binding_clause_id"),
            }
        )

    growth_rows = [
        {k: v for k, v in e.items() if k != "note"}
        for e in scenario.get("growth", [])
    ]
    for row in growth_rows:
        row["refs"] = [law_refs.get(_leaf_clause(facts, row["leaf_id"]), row["leaf_id"])]

    layers = {
        "run_ref": ctx.run,
        "citation_index": _citation_index(rulebook, facts, law_refs),
        "gap": {
            "sets": gap_sets,
            "key_checks": _key_checks(rulebook, facts, progress_coverage, law_refs),
            "window_roll": _window_roll_rows(rulebook, facts, scenario, law_refs),
            "growth_rows": growth_rows,
        },
        "path": {
            "hard_gate": layers23["hard_gate"],
            "pareto_frontier": layers23["pareto_frontier"],
            "recommendation": layers23["recommendation"],
            "alternatives": layers23["alternatives"],
            "excluded": layers23["excluded"],
        },
        "attribution": layers23["attribution"],
    }

    handoff = _narrative_handoff(rulebook, facts, layers, progress_coverage)

    result = {
        "run": ctx.run,
        "facts": facts,  # AR5：与 Fold 出口冻结对象同源（同一引用，不拷贝不改写）
        "layers": {k: v for k, v in layers.items() if k not in ("run_ref", "citation_index")},
        "narrative_handoff": {
            "units": handoff["units"],
            "citation_index": handoff["citation_index"],
            "disclaimers": handoff["disclaimers"],
            "forbidden_claims": handoff["forbidden_claims"],
        },
    }
    # facts 保持同一引用（AR5）；其余段经 _json_safe（无日期对象，防御性转换）
    result["run"] = _json_safe(result["run"])
    result["layers"] = _json_safe(result["layers"])
    result["narrative_handoff"] = _json_safe(result["narrative_handoff"])
    return result


def state_counts(facts: dict) -> Counter:
    """检查叶五态计数（终端摘要用；not_applicable 叶不生成行，显式补零）。"""
    counts = Counter(c["state"] for c in facts.get("checks", []))
    for s in ("met", "not_met", "indeterminate", "needs_review", "not_applicable"):
        counts.setdefault(s, 0)
    return counts
