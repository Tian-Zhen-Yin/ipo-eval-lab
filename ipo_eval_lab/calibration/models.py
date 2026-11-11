"""
M1 校准管线数据契约（设计 0003）

Pydantic 模型定义：
- CandidateRule: AI 提取产出的候选规则（L1a 输出）
- EvidencePack: 人工队列输入包
- GateResult: 每道闸门的判定结果
- ConfidenceTier: g1~g4 置信度档位
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Literal, Any
from enum import Enum


class GateName(str, Enum):
    L0 = "L0"
    L1A = "L1a"
    L1B = "L1b"
    L2 = "L2"
    L3 = "L3"


class GateStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class ConfidenceTier(str, Enum):
    G4 = "g4"  # 自动入候选库
    G3 = "g3"  # 入库但必检
    G2 = "g2"  # 人工队列
    G1 = "g1"  # 人工队列（被拦截）


class L0CheckCode(str, Enum):
    SCHEMA_VALID = "0-1"           # Schema 合法
    UNIT_CONSISTENT = "0-2"        # 量纲一致
    UNIQUENESS = "0-3"             # 唯一性
    REF_INTEGRITY = "0-4"          # 引用完整
    WINDOW_ENUM = "0-5"            # 窗口不重述
    STRUCT_COMPLETE = "0-6"        # 结构完整
    COMBINATION_COVERAGE = "0-7"   # 组合覆盖
    VERSION_ALIGN = "0-8"          # 版本对齐


class L1bCheckCode(str, Enum):
    QUOTE_VERBATIM = "1b-1"        # 引文逐字命中
    NUMERIC_ANCHOR = "1b-2"        # 数值锚点在归一化集合内
    COVERAGE_SCAN = "1b-3"         # 覆盖率扫描（抓漏条件）


class L3DiffCategory(str, Enum):
    EXACT = "exact"
    VALUE_DIFF = "value_diff"
    STRUCTURE_DIFF = "structure_diff"
    SNAPSHOT_ONLY = "snapshot_only"
    SOURCE_ONLY = "source_only"


class EquivalenceJudgment(str, Enum):
    YES = "yes"
    NO = "no"
    PARTIAL = "partial"


# ── 核心数据结构 ──

class SourceClauseRef(BaseModel):
    """原文条文引用（用于 evidence pack）"""
    law_id: str
    article: str
    chapter: Optional[str] = None
    section: Optional[str] = None
    text: str  # 逐字正文


class CandidateLeaf(BaseModel):
    """候选叶子节点（对应 rulebook Leaf）"""
    leaf_id: str
    item_ref: str
    quantifier: str
    window: str
    op: str
    threshold: float
    threshold_format: str  # 原文形态，如 "2亿元"、"15%"、"五十亿"
    quote: str  # 必须逐字摘抄原文


class CandidateClause(BaseModel):
    """候选条文"""
    clause_id: str
    law_ref: str  # 格式 law_id#article（如 sse_main_2026#3.1.2）
    logic: Literal["all", "any"]  # 对应 rulebook Clause.logic
    leaves: List[CandidateLeaf] = Field(min_length=1)


class CandidateRule(BaseModel):
    """候选规则（L1a 产出，L1b/L2/L3 消费）"""
    clause_id: str
    source: SourceClauseRef
    candidate: CandidateClause
    evidence: dict = Field(default_factory=dict)  # source_doc, version 等
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    model_provider: str
    model_name: str


class GateFailure(BaseModel):
    """单条闸门失败详情"""
    gate: GateName
    check_code: str  # L0CheckCode / L1bCheckCode 等
    reason: str
    details: dict = Field(default_factory=dict)


class GateResult(BaseModel):
    """单条目在某道闸门的判定结果"""
    clause_id: str
    gate: GateName
    status: GateStatus
    payload: Optional[dict] = None  # pass 时：候选结构 / 判定结果
    failure: Optional[GateFailure] = None  # fail 时：给 evidence pack 的原因


class L2Judgment(BaseModel):
    """L2 回译判定结果"""
    equivalent: EquivalenceJudgment
    differences: List[str] = Field(default_factory=list)
    rendered_text: str  # 确定性渲染器产出的中文文本


class L3Diff(BaseModel):
    """L3 快照差异"""
    leaf_id: str
    category: L3DiffCategory
    candidate_value: Optional[dict] = None
    snapshot_value: Optional[dict] = None
    detail: str = ""


class EvidencePack(BaseModel):
    """人工队列输入包（单条）"""
    clause_id: str
    source: SourceClauseRef
    candidate: CandidateClause
    gates: dict[str, GateResult]  # gate_name -> GateResult
    suggested_action: Literal["manual_review", "accept_as_is", "reject"] = "manual_review"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConfidenceSynthesis(BaseModel):
    """置信度合成结果"""
    clause_id: str
    tier: ConfidenceTier
    basis: dict[str, GateStatus]  # L0/L1b/L2/L3 的通过情况
    gate_results: List[GateResult]
    auto_decision: Literal["candidates", "review_queue"]


class CalibrationReport(BaseModel):
    """校准批次报告"""
    batch_id: str
    as_of_date: str
    source_version: str
    total_clauses: int
    passed_l0: int
    passed_l1b: int
    passed_l2: int
    passed_l3: int
    tier_counts: dict[ConfidenceTier, int]
    candidates_written: int
    review_queue_written: int
    midas_diff_summary: dict[L3DiffCategory, int]
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── 配置模型 ──

class L1aModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 2048
    system_prompt: Optional[str] = None


class L2ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024


class CalibrationConfig(BaseModel):
    """校准管线配置（YAML 可外部化）"""
    l1a: L1aModelConfig
    l2: L2ModelConfig
    source_dir: str = "rulebook/source_texts"
    output_dir: str = "calibration_output"
    metric_whitelist_path: str = "rulebook/metrics.yaml"  # 26 项 metric 白名单
    anchor_normalization_path: str = "config/anchor_normalization.yaml"  # R10
    snapshot_path: str = "calibration/midas_snapshot.yaml"  # L3 对比基线


__all__ = [
    "GateName", "GateStatus", "ConfidenceTier",
    "L0CheckCode", "L1bCheckCode", "L3DiffCategory", "EquivalenceJudgment",
    "SourceClauseRef", "CandidateLeaf", "CandidateClause", "CandidateRule",
    "GateFailure", "GateResult", "L2Judgment", "L3Diff",
    "EvidencePack", "ConfidenceSynthesis", "CalibrationReport",
    "L1aModelConfig", "L2ModelConfig", "CalibrationConfig",
]