"""M3 企业数据契约模型（设计 0006 §2；F2 字段全集）。

单位约定：金额一律整数元（E8）；百分比一律小数（conventions.percent，0.25 = 25%）。
stub_period 形状随 M4 展示层定稿，加载期原样透传——展示用，永不进判定（E2-2）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# 与 rulebook/_meta.yaml 的 company_types 同源（general/红筹未上市/红筹已上市/表决权差异）
CompanyType = Literal["general", "redchip_unlisted", "redchip_listed", "weighted_voting"]


class _Strict(BaseModel):
    """extra=forbid：profile.json 里的字段拼写错误在加载期即报（AR4）。"""

    model_config = ConfigDict(extra="forbid")


class ApplicantProfile(_Strict):
    """适用性谓词的输入（industry 供 in_list 负面清单）。"""

    company_type: CompanyType
    profit_status: Literal["profitable", "loss_making"]
    industry: str | None


class AuditInfo(_Strict):
    """E3 审计覆盖降级输入；status/opinion 逐年必填（勾稽⑤，断言在 loader）。"""

    status: Literal["audited", "unaudited"]
    opinion: Literal["unqualified", "qualified", "disclaimer", "adverse"] | None = None
    report_id: str | None = None


class NetProfit(_Strict):
    """measures 两维：申报 + 扣非。扣非缺 → 整叶 indeterminate，不用申报值顶替（0006 §3）。"""

    as_reported: int
    excl_nonrecurring: int | None = None


class Income(_Strict):
    operating_revenues: int
    net_profit_attrib_parent: NetProfit
    rd_expensed: int | None = None  # 研发两源，任一缺 → 该年缺值（0006 §3）
    rd_capitalized: int | None = None


class CashFlow(_Strict):
    net_cash_flow_from_operating: int


class Balance(_Strict):
    total_assets: int
    total_liabilities: int
    total_equity: int
    total_equity_attrib_to_parent: int
    minority_interests: int


class EquityRoll(_Strict):
    """ROE 加权派生的输入 + 勾稽③（归母口径逐年滚动）。"""

    opening_attrib_parent: int
    net_profit_attrib_parent: int
    dividends: int
    capital_injection: int
    closing_attrib_parent: int


class Reconciliation(_Strict):
    """间接法调节表；勾稽② np + adjustments == ocf（逐年）。"""

    net_profit_attrib_parent: int
    adjustments: int
    net_cash_flow_from_operating: int


class Statement(_Strict):
    fiscal_year: int
    audit: AuditInfo
    income: Income
    cash_flow: CashFlow
    balance: Balance
    equity_roll: EquityRoll
    reconciliation: Reconciliation


class MktcapSelfEstimate(_Strict):
    """basis: self_estimate；整体 null → 该叶 indeterminate（G-C 落点）。"""

    value: int | None
    note: str


class InventionPatents(_Strict):
    """专利两叶合取的载体（0001 B5）。"""

    granted_count: int | None
    applied_to_main_business: bool | None


class Documentary(_Strict):
    """底稿事实项（documentary × worksheet 判定矩阵的载体，设计 0006 §2.3）。"""

    mktcap_self_estimate: MktcapSelfEstimate | None = None
    invention_patents: InventionPatents
    operating_years: int | None = None
    public_float_ratio: float | None = None


class Declared(_Strict):
    """judgment × declared：只作证据，永不 met（needs_review + pending_evidence）。"""

    self_developed_tech_intl_leading: bool | None = None
    rd_stage_or_innovation_redchip: bool | None = None
    national_approved_or_phase2_clinic: bool | None = None


class CompanyProfile(_Strict):
    """单文件 profile.json（F1）：statements 内嵌为年度数组，加载断言一次完成。"""

    company_id: str
    display_name: str
    applicant_profile: ApplicantProfile
    statements: list[Statement]
    stub_period: dict[str, Any] | None = None
    documentary: Documentary
    declared: Declared
