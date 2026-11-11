"""
M1 校准管线 L3 快照闸门（设计 0003 §6）

与 midas 现值 diff，五分类：exact / value_diff / structure_diff / snapshot_only / source_only
对齐键 (board, company_type, group_no)，逐 leaf 比 {op, threshold 归一, quantifier, window}。
"""

from pathlib import Path
from typing import Optional
import yaml

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L3DiffCategory, L3Diff,
    CandidateRule, CandidateLeaf,
)
from .rulebook_refs import load_items


def load_midas_snapshot(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("snapshot", {}) or {}


def build_snapshot_key(board: str, company_type: str, group_no: Optional[int]) -> str:
    return f"{board}:{company_type}:{group_no}"


def _numbers_equal(a, b) -> bool:
    if a is None or b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= max(1e-6, abs(float(b)) * 1e-9)
    except (TypeError, ValueError):
        return str(a) == str(b)


def compare_leaf(
    leaf: CandidateLeaf, snapshot_leaf: dict, item: Optional[dict] = None,
) -> L3Diff:
    """逐 leaf 比对：先数值，再结构（op / quantifier / window）"""
    cand_struct = {
        "op": leaf.op,
        "threshold": leaf.threshold,
        "quantifier": (item or {}).get("quantifier"),
        "window": (item or {}).get("window"),
    }
    snap_struct = {
        "op": snapshot_leaf.get("op"),
        "threshold": snapshot_leaf.get("threshold"),
        "quantifier": snapshot_leaf.get("quantifier"),
        "window": snapshot_leaf.get("window"),
    }

    if snapshot_leaf.get("threshold") is not None and not _numbers_equal(
        leaf.threshold, snapshot_leaf.get("threshold")
    ):
        return L3Diff(
            clause_id=leaf.leaf_id, item_ref=leaf.item_ref,
            category=L3DiffCategory.VALUE_DIFF,
            candidate_value={"threshold": leaf.threshold},
            snapshot_value={"threshold": snapshot_leaf.get("threshold")},
            detail=f"阈值不同：候选 {leaf.threshold} vs 快照 {snapshot_leaf.get('threshold')}",
        )

    for field in ("op", "quantifier", "window"):
        snap_value = snapshot_leaf.get(field)
        if snap_value is None:
            continue
        cand_value = cand_struct.get(field)
        snap_norm = snap_value
        cand_norm = cand_value
        if field == "window" and isinstance(snap_value, dict):
            snap_norm = (snap_value.get("kind"), snap_value.get("n"))
            cand_norm = (cand_value.get("kind"), cand_value.get("n")) if isinstance(cand_value, dict) else cand_value
        if cand_norm != snap_norm:
            return L3Diff(
                clause_id=leaf.leaf_id, item_ref=leaf.item_ref,
                category=L3DiffCategory.STRUCTURE_DIFF,
                candidate_value=cand_struct,
                snapshot_value=snap_struct,
                detail=f"{field} 不同：候选 {cand_norm} vs 快照 {snap_norm}",
            )

    return L3Diff(
        clause_id=leaf.leaf_id, item_ref=leaf.item_ref,
        category=L3DiffCategory.EXACT,
        candidate_value=cand_struct, snapshot_value=snap_struct,
        detail="完全一致",
    )


def run_l3_gate(
    rules: list[CandidateRule],
    snapshot_path: Path,
    rulebook_dir: Optional[Path] = None,
) -> tuple[list[GateResult], list[L3Diff]]:
    snapshot = load_midas_snapshot(snapshot_path)
    items = load_items(rulebook_dir) if rulebook_dir else {}
    results: list[GateResult] = []
    all_diffs: list[L3Diff] = []

    for r in rules:
        key = build_snapshot_key(r.context.board, r.context.company_type, r.context.group_no)
        snap_entry = snapshot.get(key)

        if not snap_entry:
            all_diffs.append(L3Diff(
                clause_id=r.clause_id,
                category=L3DiffCategory.SOURCE_ONLY,
                detail=f"快照无对齐键 {key}（可能为新规或快照漏收）",
            ))
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L3, status=GateStatus.PASS,
                payload={"diff_category": L3DiffCategory.SOURCE_ONLY.value,
                         "snapshot_key": key},
            ))
            continue

        # 快照逐叶（按 item_ref 对齐，leaf_id 命名可不同）
        snap_leaves = {lf.get("item_ref") or lf.get("leaf_id"): lf
                       for lf in snap_entry.get("leaves", [])}
        leaf_diffs: list[L3Diff] = []
        for cand_leaf in r.clause.leaves:
            snap_leaf = snap_leaves.get(cand_leaf.item_ref)
            if not snap_leaf:
                leaf_diffs.append(L3Diff(
                    clause_id=r.clause_id, item_ref=cand_leaf.item_ref,
                    category=L3DiffCategory.SOURCE_ONLY,
                    detail=f"快照无 item {cand_leaf.item_ref}",
                ))
                continue
            leaf_diffs.append(compare_leaf(cand_leaf, snap_leaf, items.get(cand_leaf.item_ref)))

        # snapshot_only：快照有、候选没有
        cand_items = {lf.item_ref for lf in r.clause.leaves}
        for snap_item_ref in snap_leaves:
            if snap_item_ref not in cand_items:
                leaf_diffs.append(L3Diff(
                    clause_id=r.clause_id, item_ref=snap_item_ref,
                    category=L3DiffCategory.SNAPSHOT_ONLY,
                    detail=f"快照有 item {snap_item_ref}、候选未提取",
                ))

        all_diffs.extend(leaf_diffs)

        cats = {d.category for d in leaf_diffs}
        if L3DiffCategory.VALUE_DIFF in cats or L3DiffCategory.STRUCTURE_DIFF in cats:
            category = (L3DiffCategory.VALUE_DIFF if L3DiffCategory.VALUE_DIFF in cats
                        else L3DiffCategory.STRUCTURE_DIFF)
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L3, status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L3, check_code=f"l3-{category.value}",
                    reason=f"快照差异：{category.value}（人工必检）",
                    details={"clause_id": r.clause_id,
                             "diffs": [d.model_dump() for d in leaf_diffs]},
                ),
            ))
        else:
            payload_cat = (L3DiffCategory.SNAPSHOT_ONLY.value
                           if L3DiffCategory.SNAPSHOT_ONLY in cats
                           else L3DiffCategory.EXACT.value)
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L3, status=GateStatus.PASS,
                payload={"diff_category": payload_cat, "snapshot_key": key},
            ))

    return results, all_diffs


def generate_midas_diff_report(diffs: list[L3Diff], as_of: str = "") -> str:
    """《midas 存量数据差异清单》——L3 副产品，直接服务 midas 侧数据治理"""
    lines = ["# midas 存量差异清单", ""]
    if as_of:
        lines.append(f"- as_of：{as_of}")
    lines.append(f"- 差异条数：{len(diffs)}")
    lines.append("")

    for cat in (L3DiffCategory.VALUE_DIFF, L3DiffCategory.STRUCTURE_DIFF,
                L3DiffCategory.SNAPSHOT_ONLY, L3DiffCategory.SOURCE_ONLY,
                L3DiffCategory.EXACT):
        items = [d for d in diffs if d.category == cat]
        if not items:
            continue
        lines.append(f"## {cat.value}（{len(items)} 条）")
        lines.append("")
        for d in items:
            ref = f"{d.clause_id} · {d.item_ref}" if d.item_ref else d.clause_id
            lines.append(f"- `{ref}`：{d.detail}")
        lines.append("")
    return "\n".join(lines)


__all__ = [
    "run_l3_gate", "compare_leaf", "load_midas_snapshot",
    "build_snapshot_key", "generate_midas_diff_report",
]
