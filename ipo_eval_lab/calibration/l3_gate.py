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
    """
    套级对拍：对齐键 (board, company_type, group_no)（设计 0003 §6）。
    候选按套聚合并集（shared + 各支路）后与快照条目逐 item_ref 比对——
    clause 级单打会产生系统性误报（同套兄弟条款互相算「缺失」）。
    每个候选条文继承其所属套的判定结果。
    """
    snapshot = load_midas_snapshot(snapshot_path)
    items = load_items(rulebook_dir) if rulebook_dir else {}

    def canon(item_ref: str) -> str:
        """item_ref 归并键：rules 里 l3_group 相同的条目在 midas 存量里无法区分措辞
        （如 self_developed_tech / _full 同为一条定性行），对拍时按组归并。"""
        return (items.get(item_ref) or {}).get("l3_group") or item_ref

    # 按套聚合（保持输入顺序）
    set_order: list[tuple] = []
    set_rules: dict[tuple, list[CandidateRule]] = {}
    for r in rules:
        gkey = (r.context.board, r.context.company_type, r.context.group_no)
        if gkey not in set_rules:
            set_rules[gkey] = []
            set_order.append(gkey)
        set_rules[gkey].append(r)

    set_results: dict[tuple, GateResult] = {}
    all_diffs: list[L3Diff] = []

    for gkey in set_order:
        group = set_rules[gkey]
        board, ctype, gno = gkey
        first = group[0]
        key = build_snapshot_key(board, ctype, gno)
        snap_entry = snapshot.get(key)

        if not snap_entry:
            all_diffs.append(L3Diff(
                clause_id=first.clause_id,
                category=L3DiffCategory.SOURCE_ONLY,
                detail=f"快照无对齐键 {key}（可能为新规或快照漏收）",
            ))
            set_results[gkey] = GateResult(
                clause_id=first.clause_id, gate=GateName.L3, status=GateStatus.PASS,
                payload={"diff_category": L3DiffCategory.SOURCE_ONLY.value,
                         "snapshot_key": key},
            )
            continue

        # 候选并集：canon(item_ref) -> {(op, threshold)} 签名集合
        cand_sigs: dict[str, set] = {}
        for r in group:
            for lf in r.clause.leaves:
                cand_sigs.setdefault(canon(lf.item_ref), set()).add((lf.op, lf.threshold))

        snap_leaves: dict[str, list[dict]] = {}
        for lf in snap_entry.get("leaves", []):
            snap_leaves.setdefault(canon(lf.get("item_ref")), []).append(lf)

        def _numeric(leaves: list[dict]) -> list[dict]:
            """只留有量值阈值的叶：qualitative 叶（行业对比路径等）无数值可比，
            参与签名比对只会把「op 差」报成含 None 的噪声。"""
            return [l for l in leaves if l.get("threshold") is not None]

        def _fmt(sigs) -> str:
            return "、".join(f"({op},{thr})" for op, thr in
                             sorted(sigs, key=lambda s: (str(s[0]), str(s[1]))))

        leaf_diffs: list[L3Diff] = []
        for item_ref, snaps in snap_leaves.items():
            numeric_snaps = _numeric(snaps)
            cand_set = cand_sigs.get(item_ref)
            if cand_set is None:
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.SNAPSHOT_ONLY,
                    detail=f"快照有 item {item_ref}、候选未提取（套 {key}）",
                ))
                continue
            if not numeric_snaps:
                # 快照该条为定性条件（无量值）/ 无对应数值可比 → 不作数值判定
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.EXACT,
                    detail="快照为定性条件，无数值可比",
                ))
                continue
            snap_sigs = {(sl.get("op"), sl.get("threshold")) for sl in numeric_snaps}
            if snap_sigs & cand_set:
                # 至少一个签名命中即 exact：多支路多阈值取并集，命中即可
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.EXACT, detail="一致",
                ))
                continue
            snap_ops = {op for op, _ in snap_sigs}
            cand_ops = {op for op, _ in cand_set}
            if snap_ops & cand_ops:
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.VALUE_DIFF,
                    candidate_value={"sigs": _fmt(cand_set)},
                    snapshot_value={"sigs": _fmt(snap_sigs)},
                    detail=f"item {item_ref} 阈值不同：候选 {_fmt(cand_set)} vs 快照 {_fmt(snap_sigs)}（套 {key}）",
                ))
            else:
                same_thr = ({t for _, t in cand_set} & {t for _, t in snap_sigs})
                note = "（同阈值、op 不同：边界含否）" if same_thr else ""
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.STRUCTURE_DIFF,
                    candidate_value={"sigs": _fmt(cand_set)},
                    snapshot_value={"sigs": _fmt(snap_sigs)},
                    detail=(f"item {item_ref} op 不同{note}：候选 {_fmt(cand_set)} "
                            f"vs 快照 {_fmt(snap_sigs)}（套 {key}）"),
                ))

        # source_only：候选有、快照没有
        for item_ref in cand_sigs:
            if item_ref not in snap_leaves:
                leaf_diffs.append(L3Diff(
                    clause_id=first.clause_id, item_ref=item_ref,
                    category=L3DiffCategory.SOURCE_ONLY,
                    detail=f"快照无 item {item_ref}（套 {key}）",
                ))

        all_diffs.extend(d for d in leaf_diffs if d.category != L3DiffCategory.EXACT)

        cats = {d.category for d in leaf_diffs}
        if L3DiffCategory.VALUE_DIFF in cats or L3DiffCategory.STRUCTURE_DIFF in cats:
            category = (L3DiffCategory.VALUE_DIFF if L3DiffCategory.VALUE_DIFF in cats
                        else L3DiffCategory.STRUCTURE_DIFF)
            set_results[gkey] = GateResult(
                clause_id=first.clause_id, gate=GateName.L3, status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L3, check_code=f"l3-{category.value}",
                    reason=f"快照差异：{category.value}（人工必检，套 {key}）",
                    details={"clause_id": first.clause_id,
                             "diffs": [d.model_dump() for d in leaf_diffs
                                       if d.category != L3DiffCategory.EXACT]},
                ),
            )
        else:
            payload_cat = (L3DiffCategory.SNAPSHOT_ONLY.value
                           if L3DiffCategory.SNAPSHOT_ONLY in cats
                           else L3DiffCategory.EXACT.value)
            set_results[gkey] = GateResult(
                clause_id=first.clause_id, gate=GateName.L3, status=GateStatus.PASS,
                payload={"diff_category": payload_cat, "snapshot_key": key},
            )

    # 每个候选条文继承其套的判定
    results = [set_results[(r.context.board, r.context.company_type, r.context.group_no)]
               for r in rules]
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
