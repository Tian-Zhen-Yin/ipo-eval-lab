"""
M1 校准管线 L3 快照闸门（设计 0003 §6）

与 midas 现值 diff，五分类：exact / value_diff / structure_diff / snapshot_only / source_only
"""

from pathlib import Path
from typing import Any, Optional
import yaml

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L3DiffCategory, L3Diff,
    CandidateRule, CandidateLeaf
)


def load_midas_snapshot(path: Path) -> dict[str, dict]:
    """加载 midas 快照（对齐键：(board, company_type, group_no)）"""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("snapshot", {})


def build_snapshot_key(board: str, company_type: str, group_no: str) -> str:
    """构造对齐键"""
    return f"{board}:{company_type}:{group_no}"


def compare_leaf(candidate_leaf: CandidateLeaf, snapshot_leaf: dict) -> L3Diff:
    """逐 leaf 比对"""
    # 数值比对
    cand_val = candidate_leaf.threshold
    snap_val = snapshot_leaf.get("threshold")
    
    if snap_val is not None and abs(cand_val - float(snap_val)) > 1e-6:
        return L3Diff(
            leaf_id=candidate_leaf.leaf_id,
            category=L3DiffCategory.VALUE_DIFF,
            candidate_value={"threshold": cand_val},
            snapshot_value={"threshold": snap_val},
            detail=f"阈值不同：候选 {cand_val} vs 快照 {snap_val}"
        )
    
    # 结构比对（op / quantifier / window）
    cand_struct = {
        "op": candidate_leaf.op,
        "quantifier": candidate_leaf.quantifier,
        "window": candidate_leaf.window,
    }
    snap_struct = {
        "op": snapshot_leaf.get("op"),
        "quantifier": snapshot_leaf.get("quantifier"),
        "window": snapshot_leaf.get("window"),
    }
    
    if snap_struct.get("op") and cand_struct["op"] != snap_struct["op"]:
        return L3Diff(
            leaf_id=candidate_leaf.leaf_id,
            category=L3DiffCategory.STRUCTURE_DIFF,
            candidate_value=cand_struct,
            snapshot_value=snap_struct,
            detail=f"op 不同：{cand_struct['op']} vs {snap_struct['op']}"
        )
    
    if snap_struct.get("quantifier") and cand_struct["quantifier"] != snap_struct["quantifier"]:
        return L3Diff(
            leaf_id=candidate_leaf.leaf_id,
            category=L3DiffCategory.STRUCTURE_DIFF,
            candidate_value=cand_struct,
            snapshot_value=snap_struct,
            detail=f"quantifier 不同：{cand_struct['quantifier']} vs {snap_struct['quantifier']}"
        )
    
    if snap_struct.get("window") and cand_struct["window"] != snap_struct["window"]:
        return L3Diff(
            leaf_id=candidate_leaf.leaf_id,
            category=L3DiffCategory.STRUCTURE_DIFF,
            candidate_value=cand_struct,
            snapshot_value=snap_struct,
            detail=f"window 不同：{cand_struct['window']} vs {snap_struct['window']}"
        )
    
    return L3Diff(
        leaf_id=candidate_leaf.leaf_id,
        category=L3DiffCategory.EXACT,
        candidate_value=cand_struct,
        snapshot_value=snap_struct,
        detail="完全一致"
    )


def run_l3_gate(
    candidates: list[CandidateRule],
    snapshot_path: Path,
) -> tuple[list[GateResult], list[L3Diff]]:
    """
    L3 快照闸门主函数
    - 返回：(GateResult 列表, 差异清单)
    - 差异清单是副产品，直接服务 midas 数据治理
    """
    snapshot = load_midas_snapshot(snapshot_path)
    results: list[GateResult] = []
    all_diffs: list[L3Diff] = []
    
    for c in candidates:
        # 从 candidate 提取对齐键信息
        evidence = c.evidence
        board = evidence.get("board", "")
        company_type = evidence.get("company_type", "")
        group_no = evidence.get("group_no", "")
        
        key = build_snapshot_key(board, company_type, group_no)
        snap_entry = snapshot.get(key)
        
        if not snap_entry:
            # 快照无此条 → source_only
            all_diffs.append(L3Diff(
                leaf_id=c.candidate.clause_id,
                category=L3DiffCategory.SOURCE_ONLY,
                detail=f"快照无对齐键 {key}，可能为新规或漏收"
            ))
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L3,
                status=GateStatus.PASS,
                payload={"diff_category": L3DiffCategory.SOURCE_ONLY.value,
                         "snapshot_key": key}
            ))
            continue
        
        # 逐 leaf 比对
        snap_leaves = {lf.get("leaf_id", ""): lf for lf in snap_entry.get("leaves", [])}
        leaf_diffs = []
        has_value_diff = False
        has_structure_diff = False
        
        for cand_leaf in c.candidate.leaves:
            snap_leaf = snap_leaves.get(cand_leaf.leaf_id)
            if not snap_leaf:
                leaf_diffs.append(L3Diff(
                    leaf_id=cand_leaf.leaf_id,
                    category=L3DiffCategory.SOURCE_ONLY,
                    detail=f"快照无 leaf {cand_leaf.leaf_id}"
                ))
                continue
            
            diff = compare_leaf(cand_leaf, snap_leaf)
            leaf_diffs.append(diff)
            if diff.category == L3DiffCategory.VALUE_DIFF:
                has_value_diff = True
            if diff.category == L3DiffCategory.STRUCTURE_DIFF:
                has_structure_diff = True
        
        all_diffs.extend(leaf_diffs)
        
        # 汇总：value_diff / structure_diff → 人工必检；exact → 加分
        if has_value_diff or has_structure_diff:
            category = L3DiffCategory.VALUE_DIFF if has_value_diff else L3DiffCategory.STRUCTURE_DIFF
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L3,
                status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L3, check_code=f"l3-{category.value}",
                    reason=f"快照差异：{category.value}",
                    details={"diffs": [d.model_dump() for d in leaf_diffs]}
                )
            ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L3,
                status=GateStatus.PASS,
                payload={"diff_category": L3DiffCategory.EXACT.value,
                         "snapshot_key": key}
            ))
    
    return results, all_diffs


def generate_midas_diff_report(diffs: list[L3Diff]) -> str:
    """生成 midas 差异清单报告（副产品）"""
    lines = ["# midas 存量差异清单", ""]
    lines.append(f"总计 {len(diffs)} 条差异")
    lines.append("")
    
    by_category = {}
    for d in diffs:
        by_category.setdefault(d.category, []).append(d)
    
    for cat in [L3DiffCategory.VALUE_DIFF, L3DiffCategory.STRUCTURE_DIFF,
                L3DiffCategory.SNAPSHOT_ONLY, L3DiffCategory.SOURCE_ONLY,
                L3DiffCategory.EXACT]:
        items = by_category.get(cat, [])
        if not items:
            continue
        lines.append(f"## {cat.value}（{len(items)} 条）")
        lines.append("")
        for d in items:
            lines.append(f"- `{d.leaf_id}`：{d.detail}")
        lines.append("")
    
    return "\n".join(lines)


__all__ = [
    "run_l3_gate", "compare_leaf", "load_midas_snapshot",
    "build_snapshot_key", "generate_midas_diff_report",
]