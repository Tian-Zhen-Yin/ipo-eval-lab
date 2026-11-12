"""Fold 节点（设计 0005 §5；票 04）：Kleene 三值双规则折叠 → 套终态 → 三段板块结论。

层级链（§5）：leaf → clause(logic) → branch(AND，含 shared_clauses) → group(OR branches)
→ 段③(OR groups) → 板块 = AND(段①, 段②, 段③)。
双规则：AND 任一 not_met → not_met，否则任一 unknown → indeterminate，否则 met；
OR 任一 met → met，否则任一 unknown → indeterminate，否则 not_met。
needs_review 视同 unknown 参与折叠，但叶级态保留、套级带 needs_review 计数与
pending_judgments 清单（§5-P3 相容性）。
OR 落败支路被吸收（已满足条文真值已定，blockers 不含落败叶）——勘误 0001 §2.3
「同规则」表述不复刻（那会错杀甲公司现金流条文）。
facts 在 Fold 出口冻结（AR5）：本节点是最后一个可写 facts 的节点。
"""
from __future__ import annotations

from typing import Any, Iterable

from ipo_eval_lab.rulebook.models import Clause, Group

from .errors import EngineError

# 折叠三态（叶级 needs_review/indeterminate 归 unknown；出口再映 indeterminate）
MET = "met"
NOT_MET = "not_met"
UNKNOWN = "unknown"
NA = "not_applicable"   # ADR-0008：法定豁免，折叠前先剔除（ADR-0003 约定）

_SET_OUTCOME = {MET: "criteria_met", NOT_MET: "criteria_not_met", UNKNOWN: "indeterminate"}
_FROM_OUTCOME = {v: k for k, v in _SET_OUTCOME.items()}  # 板块反向映射（单一来源）


def _leaf_unit(check: dict[str, Any]) -> tuple[str, list[str]]:
    """叶 → (折叠态, blockers=item_refs)。met 无约束；not_met/unknown 以 item_ref 记名。

    豁免叶（not_applicable，ADR-0008）返回 NA——**不进折叠、不作约束、不记 blocker**。
    """
    state = check["state"]
    if state == MET:
        return MET, []
    if state == NOT_MET:
        return NOT_MET, [check["item_ref"]]
    if state == NA:
        return NA, []
    return UNKNOWN, [check["item_ref"]]  # indeterminate / needs_review 视同 unknown（§5）


def kleene_and(units: Iterable[tuple[str, list[str]]]) -> tuple[str, list[str]]:
    """AND：任一 not_met → not_met；否则任一 unknown → unknown；否则 met。

    豁免叶（NA）先剔除（ADR-0003「not_applicable 先剔除」）。**全被豁免的 AND
    子句视为 met（无约束）**——不是 not_met（那是「不达标」，语义相反），
    也不是 unknown（那是「判不了」）。空约束集上 AND 的恒等元是 met。
    """
    units = [u for u in units if u[0] != NA]
    for want in (NOT_MET, UNKNOWN):
        hit = [u for u in units if u[0] == want]
        if hit:
            return want, _merge(u[1] for u in hit)
    return MET, []


def kleene_or(units: Iterable[tuple[str, list[str]]]) -> tuple[str, list[str]]:
    """OR：任一 met → met（落败支路吸收）；否则任一 unknown → unknown；否则 not_met。

    豁免叶（NA）先剔除。**全被豁免的 OR 支路视为 not_met（该路径不成立）**——
    选一路径里没有可走的，等于走不通；恒等元取 not_met 而非 met，
    否则「全部豁免」会被读成「满足」。
    """
    units = [u for u in units if u[0] != NA]
    if any(u[0] == MET for u in units):
        return MET, []
    hit = [u for u in units if u[0] == UNKNOWN]
    if hit:
        return UNKNOWN, _merge(u[1] for u in hit)
    return NOT_MET, _merge(u[1] for u in units)


def _merge(blockers: Iterable[list[str]]) -> list[str]:
    out: list[str] = []
    for b in blockers:
        out.extend(x for x in b if x not in out)
    return out


def fold_clause(clause: Clause, checks: list[dict[str, Any]]) -> tuple[str, list[str]]:
    units = [_leaf_unit(c) for c in checks]
    return kleene_or(units) if clause.logic == "any" else kleene_and(units)


def fold_set(group: Group, checks: list[dict[str, Any]]) -> dict[str, Any]:
    """套条目：branch = AND(shared + 自有条款)；group = OR(branches)（§5 层级链）。"""
    by_clause: dict[str, list[dict[str, Any]]] = {}
    for c in checks:
        by_clause.setdefault(c["clause_id"], []).append(c)

    shared_units: list[tuple[str, list[str]]] = []
    shared_detail: list[dict[str, Any]] = []
    for clause in group.shared_clauses:
        state, blockers = fold_clause(clause, by_clause.get(clause.clause_id, []))
        shared_units.append((state, blockers))
        shared_detail.append({"clause_id": clause.clause_id, "state": state, "blockers": blockers})

    branches_detail: list[dict[str, Any]] = []
    branch_units: list[tuple[str, list[str]]] = []
    for branch in group.branches:
        clause_units = list(shared_units)  # 公共条文折进每个 branch（不变量 #6 的语义）
        clause_detail = list(shared_detail)
        for clause in branch.clauses:
            state, blockers = fold_clause(clause, by_clause.get(clause.clause_id, []))
            clause_units.append((state, blockers))
            clause_detail.append({"clause_id": clause.clause_id, "state": state, "blockers": blockers})
        b_state, b_blockers = kleene_and(clause_units)
        branch_units.append((b_state, b_blockers))
        branches_detail.append(
            {"set_id": branch.set_id, "state": b_state, "blockers": b_blockers, "clauses": clause_detail}
        )

    g_state, g_blockers = kleene_or(branch_units)
    nr_leaves = [c for c in checks if c["state"] == "needs_review"]

    return {
        "group_id": group.group_id,
        "display": group.display,
        "boards": list(group.boards),
        "outcome": _SET_OUTCOME[g_state],
        "blockers": g_blockers,
        "needs_review_count": len(nr_leaves),
        "pending_judgments": [
            {"leaf_id": c["leaf_id"], "item_ref": c["item_ref"], "reason": c["reason"]} for c in nr_leaves
        ],
        "shared_clauses": shared_detail,
        "branches": branches_detail,
    }


def fold_boards(set_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """段③(OR groups) → 板块 = AND(段①, 段②, 段③)。

    样板期段①（发行条件）/段②（板块定位）pass-through 占位（G-D 映射属 M1 全量），
    不阻塞结论；铺开后在此接入 issuance / positioning 组。
    """
    by_board: dict[str, list[dict[str, Any]]] = {}
    for entry in set_entries:
        for board in entry["boards"]:
            by_board.setdefault(board, []).append(entry)

    boards: list[dict[str, Any]] = []
    for board, entries in by_board.items():
        group3, blockers = kleene_or(
            (_FROM_OUTCOME[e["outcome"]], e["blockers"]) for e in entries
        )
        boards.append(
            {
                "board": board,
                "outcome": _SET_OUTCOME[group3],
                "blockers": blockers,
                "sets": [e["group_id"] for e in entries],
                "segments": {
                    "issuance": {"state": MET, "note": "pass-through 占位（随 M1 issuance 铺开）"},
                    "positioning": {"state": MET, "note": "pass-through 占位（G-D 逐套映射随 M1）"},
                    "listing_sets": {"state": group3, "blockers": blockers},
                },
            }
        )
    return boards


_FROM_OUTCOME = {"criteria_met": MET, "criteria_not_met": NOT_MET, "indeterminate": UNKNOWN}


def fold_checks(groups: list[Group], checks: list[dict[str, Any]]) -> dict[str, Any]:
    """checks → {sets: [...], boards: [...]}。折叠是纯函数：同 checks 必同输出。"""
    by_group: dict[str, list[dict[str, Any]]] = {}
    for c in checks:
        by_group.setdefault(c["group_id"], []).append(c)
    sets = [fold_set(g, by_group.get(g.group_id, [])) for g in groups]
    return {"sets": sets, "boards": fold_boards(sets)}
