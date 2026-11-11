"""
M1 校准管线置信度合成（设计 0003 §9）

不用模型自报置信度，由可验证事实合成：
- g4 = L0✓ ∧ 锚点全覆盖 ∧ 回译 yes ∧ 快照 exact → 自动入候选库
- g3 = 前三项 ✓ ∧ 快照 value/structure_diff → 候选库 + 人工必检标记
- g2 = 覆盖率警告 / partial → 人工队列
- g1 = 任一拦截 → 人工队列（evidence pack）
"""

from typing import Any

from .models import (
    GateName, GateStatus, GateResult, GateFailure, ConfidenceTier,
    ConfidenceSynthesis, CandidateRule, EvidencePack, SourceClauseRef
)


def synthesize_confidence(
    candidate: CandidateRule,
    gate_results: dict[GateName, GateResult],
) -> ConfidenceSynthesis:
    """
    合成单条候选规则的置信度档位
    
    Args:
        candidate: 候选规则
        gate_results: gate_name -> GateResult
    
    Returns:
        ConfidenceSynthesis: tier + 各 gate 状态 + 自动判定
    """
    # 收集各闸门状态
    l0 = gate_results.get(GateName.L0)
    l1b = gate_results.get(GateName.L1B)
    l2 = gate_results.get(GateName.L2)
    l3 = gate_results.get(GateName.L3)
    
    # 状态映射
    basis = {
        "L0": l0.status if l0 else GateStatus.FAIL,
        "L1b": l1b.status if l1b else GateStatus.FAIL,
        "L2": l2.status if l2 else GateStatus.FAIL,
        "L3": l3.status if l3 else GateStatus.FAIL,
    }
    
    # 1) L0 拦截 → g1
    if l0 and l0.status == GateStatus.FAIL:
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id,
            tier=ConfidenceTier.G1,
            basis=basis,
            gate_results=[r for r in gate_results.values() if r],
            auto_decision="review_queue",
        )
    
    # 2) L1b 拦截 → g1
    if l1b and l1b.status == GateStatus.FAIL:
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id,
            tier=ConfidenceTier.G1,
            basis=basis,
            gate_results=[r for r in gate_results.values() if r],
            auto_decision="review_queue",
        )
    
    # 3) L1b 有覆盖率警告 → g2
    if l1b and l1b.payload and l1b.payload.get("warnings"):
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id,
            tier=ConfidenceTier.G2,
            basis=basis,
            gate_results=[r for r in gate_results.values() if r],
            auto_decision="review_queue",
        )
    
    # 4) L2 拦截 → g1
    if l2 and l2.status == GateStatus.FAIL:
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id,
            tier=ConfidenceTier.G1,
            basis=basis,
            gate_results=[r for r in gate_results.values() if r],
            auto_decision="review_queue",
        )
    
    # 5) L2 partial → g2（如果有 partial 状态）
    if l2 and l2.payload:
        judgment = l2.payload.get("judgment", {})
        if judgment.get("equivalent") == "partial":
            return ConfidenceSynthesis(
                clause_id=candidate.clause_id,
                tier=ConfidenceTier.G2,
                basis=basis,
                gate_results=[r for r in gate_results.values() if r],
                auto_decision="review_queue",
            )
    
    # 6) L3 判定
    if l3 and l3.status == GateStatus.PASS:
        category = l3.payload.get("diff_category", "")
        if category == "exact":
            # 全绿 → g4
            return ConfidenceSynthesis(
                clause_id=candidate.clause_id,
                tier=ConfidenceTier.G4,
                basis=basis,
                gate_results=[r for r in gate_results.values() if r],
                auto_decision="candidates",
            )
        elif category == "source_only":
            # 新规，记录但不降级 → g4
            return ConfidenceSynthesis(
                clause_id=candidate.clause_id,
                tier=ConfidenceTier.G4,
                basis=basis,
                gate_results=[r for r in gate_results.values() if r],
                auto_decision="candidates",
            )
    elif l3 and l3.status == GateStatus.FAIL:
        # L3 value_diff / structure_diff → g3（入库但必检）
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id,
            tier=ConfidenceTier.G3,
            basis=basis,
            gate_results=[r for r in gate_results.values() if r],
            auto_decision="candidates",  # 候选库 + 人工必检标记
        )
    
    # 兜底：g2
    return ConfidenceSynthesis(
        clause_id=candidate.clause_id,
        tier=ConfidenceTier.G2,
        basis=basis,
        gate_results=[r for r in gate_results.values() if r],
        auto_decision="review_queue",
    )


def build_evidence_pack(
    candidate: CandidateRule,
    gate_results: dict[GateName, GateResult],
    synthesis: ConfidenceSynthesis,
) -> EvidencePack:
    """构建人工队列 evidence pack"""
    return EvidencePack(
        clause_id=candidate.clause_id,
        source=SourceClauseRef(
            law_id=candidate.evidence.get("law_id", ""),
            article=candidate.evidence.get("article", ""),
            chapter=candidate.source.chapter,
            section=candidate.source.section,
            text=candidate.source.text,
        ),
        candidate=candidate.candidate,
        gates=gate_results,
        suggested_action="manual_review",
    )


__all__ = ["synthesize_confidence", "build_evidence_pack"]