"""
M1 校准管线置信度合成（设计 0003 §9）

不用模型自报置信度，由可验证事实合成：
- g4 = L0✓ ∧ 锚点全覆盖 ∧ 回译 yes ∧ 快照 exact/新规 → 自动入候选库
- g3 = 前三项 ✓ ∧ 快照 value/structure_diff → 候选库 + 人工必检
- g2 = 覆盖率警告 / partial → 人工队列
- g1 = 任一硬拦截 → 人工队列（evidence pack）
"""

from .models import (
    GateName, GateStatus, GateResult, ConfidenceTier,
    ConfidenceSynthesis, CandidateRule, EvidencePack, SourceClauseRef,
)


def synthesize_confidence(
    candidate: CandidateRule,
    gate_results: dict[GateName, GateResult],
) -> ConfidenceSynthesis:
    basis = {
        g.value: (r.status.value if r else "missing")
        for g, r in gate_results.items()
    }
    ordered = [gate_results[g] for g in
               (GateName.L0, GateName.L1B, GateName.L2, GateName.L3)
               if g in gate_results]

    l0, l1b, l2, l3 = (gate_results.get(g) for g in
                       (GateName.L0, GateName.L1B, GateName.L2, GateName.L3))

    def out(tier: ConfidenceTier, to_queue: bool) -> ConfidenceSynthesis:
        return ConfidenceSynthesis(
            clause_id=candidate.clause_id, tier=tier, basis=basis,
            gate_results=ordered,
            auto_decision="review_queue" if to_queue else "candidates",
        )

    # g1：任一硬拦截；L2 partial 例外 → g2（设计 0003 §9）
    if l0 is not None and l0.status == GateStatus.FAIL:
        return out(ConfidenceTier.G1, True)
    if l1b is not None and l1b.status == GateStatus.FAIL:
        return out(ConfidenceTier.G1, True)
    if l2 is not None and l2.status == GateStatus.FAIL:
        details = l2.failure.details if l2.failure else {}
        if details.get("equivalent") == "partial":
            return out(ConfidenceTier.G2, True)
        return out(ConfidenceTier.G1, True)

    # g2：覆盖率警告
    if l1b and l1b.payload and l1b.payload.get("warnings"):
        return out(ConfidenceTier.G2, True)

    # 前三级全绿后看 L3
    if l3 is not None and l3.status == GateStatus.FAIL:
        return out(ConfidenceTier.G3, False)   # 候选库 + 人工必检标记

    if l3 is None:
        return out(ConfidenceTier.G2, True)    # L3 未执行 → 不进候选库

    return out(ConfidenceTier.G4, False)


def build_evidence_pack(
    candidate: CandidateRule,
    gate_results: dict[GateName, GateResult],
    synthesis: ConfidenceSynthesis,
) -> EvidencePack:
    """人工队列 evidence pack：原文引文 + 候选结构 + 哪道闸为什么红"""
    return EvidencePack(
        clause_id=candidate.clause_id,
        board=candidate.context.board,
        source=SourceClauseRef(
            law_id=candidate.source.law_id,
            article=candidate.source.article,
            chapter=candidate.source.chapter,
            section=candidate.source.section,
            text=candidate.source.text,
        ),
        candidate=candidate.clause,
        gates={g.value: r for g, r in gate_results.items()},
        suggested_action="manual_review",
    )


__all__ = ["synthesize_confidence", "build_evidence_pack"]
