"""M3 企业数据契约模型（设计 0006 §2；F2 字段全集）。

单位约定：金额一律整数元（E8）；百分比一律小数（conventions.percent，0.25 = 25%）。
stub_period 形状随 M4 展示层定稿，加载期原样透传——展示用，永不进判定（E2-2）。
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

# 与 rulebook/_meta.yaml 的 company_types 同源（general/红筹未上市/红筹已上市/表决权差异）
CompanyType = Literal["general", "redchip_unlisted", "redchip_listed", "weighted_voting"]

# 豁免判定的主体侧事实（ADR-0008 §3）：
# company_stage —— 原文「处于研发阶段的红筹企业和对国家创新驱动发展战略有重要意义的
#                  红筹企业，不适用『营业收入快速增长』的规定」
# redchip_status —— 红筹境外上市状态（已在境外 / 尚未在境外）
CompanyStage = Literal["growth", "rd_stage", "strategic_significance"]
RedchipStatus = Literal["listed", "unlisted"]


class _Strict(BaseModel):
    """extra=forbid：profile.json 里的字段拼写错误在加载期即报（AR4）。"""

    model_config = ConfigDict(extra="forbid")


class ApplicantProfile(_Strict):
    """适用性谓词的输入（industry 供 in_list 负面清单）。

    豁免相关字段（ADR-0008）：company_stage / redchip_status 均为**可空**——
    缺省 None 时豁免**不命中**（宁可按不豁免算进人工复核，也不擅自免除法定义务）。
    """

    company_type: CompanyType
    profit_status: Literal["profitable", "loss_making"]
    industry: str | None
    company_stage: CompanyStage | None = None
    redchip_status: RedchipStatus | None = None


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
    # 净利润总额（含少数股东损益）——评审 0004 V9：让「归母 vs 合并」口径差在数据层显性化。
    # 本契约样本少数股东权益逐年恒定 → 少数损益恒 0 → 数值上 == as_reported；字段保留口径语义。
    net_profit_total: int
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
    """间接法调节表；勾稽② net_profit_total + adjustments == ocf（逐年）。

    起点是**净利润总额（含少数股东损益）**，非归母（评审 0004 V9）——
    旧口径用归母起算时，少数损益被迫由 adjustments 静默吸收。
    adjustments 含少数股东损益、折旧摊销等调节项。
    """

    net_profit_total: int
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
    # 发行后股本总额（单位：股；评审 0004 V10 / 设计 0002 §2.7 issuance 叶、设计 0007 §6 甲公司 8000 万股）。
    # A 股面值 1 元/股时与「股本总额 ≥ X 元」类阈值数值同口径。引擎 v1 无消费方，先落数据契约。
    total_shares_after_ipo: int | None = None
    # 行业对比结论（设计 0006 F7，底稿0002问题三）：增长认定第三路径的判定载体。
    # 企业数据底表预置布尔（midas check07 同源）；None = 未取得对比结论 → indeterminate。
    rev_cagr_gt_peer_avg: bool | None = None
    # 研发人员占比（设计 0006 F9，底稿0003）：科创属性常规指标（二）的底表值（小数，0.10=10%）。
    rd_staff_ratio: float | None = None


class Declared(_Strict):
    """judgment × declared：只作证据，永不 met（needs_review + pending_evidence）。

    F9（底稿0003）新增段② 板块定位 9 项——判定权在专业意见，declared 值只佐证。
    """

    self_developed_tech_intl_leading: bool | None = None
    rd_stage_or_innovation_redchip: bool | None = None
    national_approved_or_phase2_clinic: bool | None = None
    org_structure_sound: bool | None = None   # 205号令第十条：股份公司+组织机构健全（F10）
    # 科创属性例外（指引第二条(1)~(4)，midas check51~54）
    core_tech_national_recognition: bool | None = None
    national_science_award: bool | None = None
    national_mega_science_project: bool | None = None
    import_substitution: bool | None = None
    # 创业板现代产业体系（深交所推荐规定第四条(三)，midas check56）
    modern_industry_system: bool | None = None
    # 板块定位定性（midas check57/58/59/60/61）
    main_board_fit: bool | None = None
    star_industry_fit: bool | None = None
    chinext_growth_innovation_fit: bool | None = None
    bse_positioning_fit: bool | None = None
    # 段① 发行条件定性（205号令第十~十三条；F10，底稿0003 续）
    ic_clean_3y: bool | None = None   # 内控鉴证无保留（judgment；审计意见走 audit_clean 量词）
    biz_team_stable: bool | None = None
    core_tech_team_stable: bool | None = None
    equity_clear_controller_stable: bool | None = None
    no_major_dispute_contingency: bool | None = None
    lawful_business_3y: bool | None = None
    nqtb_listed_12m: bool | None = None
    bse_offering_requirements: bool | None = None


class CompanyProfile(_Strict):
    """单文件 profile.json（F1）：statements 内嵌为年度数组，加载断言一次完成。"""

    company_id: str
    display_name: str
    applicant_profile: ApplicantProfile
    statements: list[Statement]
    stub_period: dict[str, Any] | None = None
    documentary: Documentary
    declared: Declared
