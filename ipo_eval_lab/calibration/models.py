"""
M1 校准管线数据契约（设计 0003）

与规则库 schema（设计 0002 / rulebook/models.py）对齐：
- CandidateLeaf = 规则库 Leaf + quote（逐字引文）+ threshold_text（原文数值形态）
- CandidateClause = 规则库 Clause
- CandidateContext = 归属坐标（board / company_type / group_no / set_id / role / scope）
- CandidateRule = 一条 clause 级流动单元（R7）

差异只在「证据层」：候选人自带 quote 与原文数值形态；正式库 YAML 不带（证据由
calibration 产出物承担）。
"""

from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional, List, Literal, Any, Union
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
    G4 = "g4"
    G3 = "g3"
    G2 = "g2"
    G1 = "g1"


class L0CheckCode(str, Enum):
    SCHEMA_VALID = "0-1"
    UNIT_CONSISTENT = "0-2"
    UNIQUENESS = "0-3"
    REF_INTEGRITY = "0-4"
    WINDOW_ENUM = "0-5"
    STRUCT_COMPLETE = "0-6"
    COMBINATION_COVERAGE = "0-7"
    VERSION_ALIGN = "0-8"


class L1bCheckCode(str, Enum):
    QUOTE_VERBATIM = "1b-1"
    NUMERIC_ANCHOR = "1b-2"
    COVERAGE_SCAN = "1b-3"


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


# ── 原文与候选结构 ──

class SourceClauseRef(BaseModel):
    """原文条文引用（evidence pack 的「原文引文」段）"""
    law_id: str
    article: str
    chapter: Optional[str] = None
    section: Optional[str] = None
    text: str


class CandidateLeaf(BaseModel):
    """候选叶（规则库 Leaf 形状 + 两项证据字段）"""
    leaf_id: str
    item_ref: str
    op: Literal["eq", "ne", "gt", "ge", "lt", "le"]
    threshold: Union[bool, int, float]
    threshold_format: Literal["number", "percent", "integer", "boolean"]
    threshold_text: str   # 原文数值形态，如 "2 亿元" / "25%"
    quote: str            # 支撑引文，必须逐字命中原文


class CandidateClause(BaseModel):
    """候选条文（规则库 Clause 形状）"""
    clause_id: str
    law_ref: str
    logic: Literal["all", "any"] = "all"
    display: Optional[str] = None
    leaves: List[CandidateLeaf] = Field(min_length=1)


class CandidateContext(BaseModel):
    """候选归属坐标（层②/差距画像的引用单元 + L3 对齐键）"""
    board: str                       # SSE-MB / SZSE-MB / STAR / CHINEXT / BSE
    company_type: str                # general / redchip_listed / redchip_unlisted / weighted_voting / ...
    group_no: Optional[int] = None   # 官方套号
    group_id: str                    # 套 id（对应 rulebook Group.group_id）
    branch_id: Optional[str] = None  # 支路 id（对应 rulebook Branch.set_id；shared 条文为 None）
    role: Literal["shared", "branch"] = "branch"
    scope: Literal["set", "issuance", "positioning"] = "set"

    @model_validator(mode="after")
    def _branch_shape(self) -> "CandidateContext":
        if self.role == "branch" and not self.branch_id:
            raise ValueError(f"role=branch 需要 branch_id（group {self.group_id}）")
        if self.role == "shared" and self.branch_id:
            raise ValueError(f"role=shared 不应带 branch_id（group {self.group_id}）")
        return self


class CandidateRule(BaseModel):
    """一条候选（clause 级流动单元）"""
    clause_id: str
    context: CandidateContext
    clause: CandidateClause
    source: SourceClauseRef
    evidence: dict[str, Any] = Field(default_factory=dict)  # effective_from / doc_version 等
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    model_provider: str = "agent"
    model_name: str = "session"

    @model_validator(mode="after")
    def _ids_consistent(self) -> "CandidateRule":
        if self.clause.clause_id != self.clause_id:
            raise ValueError(
                f"clause_id 不一致：外层 {self.clause_id} vs 条文 {self.clause.clause_id}"
            )
        return self


# ── 闸门结果 ──

class GateFailure(BaseModel):
    gate: GateName
    check_code: str
    reason: str
    details: dict[str, Any] = Field(default_factory=dict)


class GateResult(BaseModel):
    clause_id: str
    gate: GateName
    status: GateStatus
    payload: Optional[dict[str, Any]] = None
    failure: Optional[GateFailure] = None


class L2Judgment(BaseModel):
    equivalent: EquivalenceJudgment
    differences: List[str] = Field(default_factory=list)
    rendered_text: str = ""


class L3Diff(BaseModel):
    clause_id: str
    item_ref: Optional[str] = None
    category: L3DiffCategory
    candidate_value: Optional[dict[str, Any]] = None
    snapshot_value: Optional[dict[str, Any]] = None
    detail: str = ""


class EvidencePack(BaseModel):
    """人工队列输入包（单条）"""
    clause_id: str
    board: str = ""          # 沪深镜像共享 clause_id（R3），队列文件名/审计须带 board
    source: SourceClauseRef
    candidate: CandidateClause
    gates: dict[str, GateResult]
    suggested_action: Literal["manual_review", "accept_as_is", "reject"] = "manual_review"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ConfidenceSynthesis(BaseModel):
    clause_id: str
    tier: ConfidenceTier
    basis: dict[str, str]
    gate_results: List[GateResult]
    auto_decision: Literal["candidates", "review_queue"]


class CalibrationReport(BaseModel):
    batch_id: str
    as_of_date: str
    source_version: str
    total_clauses: int
    passed_l0: int
    passed_l1b: int
    passed_l2: int
    passed_l3: int
    tier_counts: dict[str, int] = Field(default_factory=dict)
    candidates_written: int
    review_queue_written: int
    midas_diff_summary: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ── 配置模型 ──

class L1aModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 2048


class L2ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024


class CalibrationConfig(BaseModel):
    l1a: L1aModelConfig
    l2: L2ModelConfig
    source_dir: str = "rulebook/source_texts"
    output_dir: str = "results/calibration"
    metric_whitelist_path: str = "rulebook/metrics.yaml"
    item_whitelist_path: str = "rulebook/items.yaml"
    anchor_normalization_path: str = "config/anchor_normalization.yaml"
    snapshot_path: str = "calibration/midas_snapshot.yaml"


__all__ = [
    "GateName", "GateStatus", "ConfidenceTier",
    "L0CheckCode", "L1bCheckCode", "L3DiffCategory", "EquivalenceJudgment",
    "SourceClauseRef", "CandidateLeaf", "CandidateClause", "CandidateContext",
    "CandidateRule", "GateFailure", "GateResult", "L2Judgment", "L3Diff",
    "EvidencePack", "ConfidenceSynthesis", "CalibrationReport",
    "L1aModelConfig", "L2ModelConfig", "CalibrationConfig",
]
