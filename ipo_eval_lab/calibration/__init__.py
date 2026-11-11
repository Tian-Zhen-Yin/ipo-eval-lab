"""
M1 校准管线模块（设计 0003）

职责：
- L0 确定性闸门（8 项 lint，零 AI）
- L1b 锚点核对（引文防编造 / 数值锚点 / 覆盖率扫描）
- L2 回译闸门（确定性渲染 + 异构模型判断，judge 由外部注入）
- L3 快照闸门（midas diff 五分类）
- 置信度合成（g1~g4）+ evidence pack

边界（AR2 / D3）：本模块零 AI 依赖——不 import 任何模型 SDK。
L1a 提取与 L2 判断由外部 agent 会话执行，结果以 JSONL 落盘后由本管线消费。
"""

from .models import (
    GateName, GateStatus, ConfidenceTier,
    CandidateRule, CandidateClause, CandidateLeaf, CandidateContext, SourceClauseRef,
    GateResult, GateFailure, EvidencePack, CalibrationReport, L2Judgment, L3Diff,
)
from .l0_gate import run_l0_gate
from .l1b_gate import run_l1b_gate
from .l2_gate import (
    run_l2_gate_agent, run_l2_gate_offline,
    render_leaf, render_clause, render_candidate, build_l2_prompt, parse_l2_response,
)
from .l3_gate import run_l3_gate, generate_midas_diff_report
from .confidence import synthesize_confidence, build_evidence_pack
from .pipeline import calibrate_run, load_source_clauses, load_candidates, load_l2_judgments

__all__ = [
    "GateName", "GateStatus", "ConfidenceTier",
    "CandidateRule", "CandidateClause", "CandidateLeaf", "CandidateContext", "SourceClauseRef",
    "GateResult", "GateFailure", "EvidencePack", "CalibrationReport", "L2Judgment", "L3Diff",
    "run_l0_gate", "run_l1b_gate",
    "run_l2_gate_agent", "run_l2_gate_offline",
    "render_leaf", "render_clause", "render_candidate", "build_l2_prompt", "parse_l2_response",
    "run_l3_gate", "generate_midas_diff_report",
    "synthesize_confidence", "build_evidence_pack",
    "calibrate_run", "load_source_clauses", "load_candidates", "load_l2_judgments",
]
