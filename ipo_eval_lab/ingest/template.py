"""模板底稿与字段坐标（ADR-0013；工单 01）。

坐标常量是「模板 ↔ CompanyProfile」的单一事实源：builder 按它写格，importer
按它读格，两边不得各持一份。手工维护模板 + golden 对拍测试锁住不脱钩
（对拍测试在工单 02）。

单位与口径（与 fixtures/models.py 约定一致）：
- 金额一律整数元（E8）；股数按股；
- 百分比类（public_float_ratio / rd_staff_ratio）模板格填百分数数值（25 = 25%），
  importer 换算为小数 0.25；
- 枚举一律中文，zh→enum 映射常量在本文件，importer 复用；
- 留空 = 该字段 null（→ indeterminate），对申报口径 sheet 合法。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font

# -- sheet 名与网格坐标 -------------------------------------------------------

SHEET_SUBJECT = "主体信息"
SHEET_FIN = "财务三年一期"
SHEET_DECLARED = "申报口径"

HEADER_ROW = 1          # 财务 sheet 第 1 行：A=科目，B..D=三个完整年度（填整数年份），E=本期
YEAR_COLS = ("B", "C", "D")
STUB_COL = "E"          # 本期（可选）——原样透传 stub_period，永不进判定（E2-2）

SUBJECT_VALUE_COL = "B"
DECL_VALUE_COL = "B"
DECL_NOTE_COL = "C"     # 申报口径 sheet 的填写说明列

TEMPLATE_VERSION = 1    # ingest.json 记录；模板格式变更时 +1（旧目录可识别来源版本）


# -- 坐标常量：字段 ↔ 格子 -----------------------------------------------------

@dataclass(frozen=True)
class SubjectRow:
    row: int
    key: str            # CompanyProfile 内路径（相对 profile 顶层）
    label: str
    kind: str           # str | company_type | profit_status | company_stage | redchip_status
    required: bool


@dataclass(frozen=True)
class FinRow:
    row: int
    key: str            # statements[] 内相对路径
    label: str          # 中文名（含必填/可选标记，客户可读）
    kind: str           # int | audit_status | audit_opinion | str
    required: bool      # 条件必填（首年/已审计）也置 True：样例全填


@dataclass(frozen=True)
class DeclRow:
    row: int
    key: str            # "documentary.*" / "declared.*"
    label: str
    kind: str           # int | percent | bool | str | note
    required: bool      # 全部 False：留空合法（null → indeterminate）


SUBJECT_ROWS: tuple[SubjectRow, ...] = (
    # company_id 不在模板：由运营方分配（ADR-0013），客户自填名称不进路径
    SubjectRow(2, "display_name", "企业名称", "str", True),
    SubjectRow(3, "applicant_profile.company_type", "企业类型", "company_type", True),
    SubjectRow(4, "applicant_profile.profit_status", "盈利状态", "profit_status", True),
    SubjectRow(5, "applicant_profile.industry", "所属行业（国民经济行业分类）", "str", False),
    SubjectRow(6, "applicant_profile.company_stage", "红筹豁免情形（如有）", "company_stage", False),
    SubjectRow(7, "applicant_profile.redchip_status", "红筹境外上市状态（如有）", "redchip_status", False),
)

FIN_ROWS: tuple[FinRow, ...] = (
    FinRow(2, "income.operating_revenues", "营业收入（元）", "int", True),
    FinRow(3, "income.net_profit_total", "净利润总额（含少数股东损益，元）", "int", True),
    FinRow(4, "income.net_profit_attrib_parent.as_reported", "归母净利润——申报口径（元）", "int", True),
    FinRow(5, "income.net_profit_attrib_parent.excl_nonrecurring", "归母净利润——扣非口径（元，可选）", "int", False),
    FinRow(6, "income.rd_expensed", "研发投入——费用化（元，可选）", "int", False),
    FinRow(7, "income.rd_capitalized", "研发投入——资本化（元，可选）", "int", False),
    FinRow(8, "cash_flow.net_cash_flow_from_operating", "经营活动产生的现金流量净额（元）", "int", True),
    FinRow(9, "balance.total_assets", "资产总额（元）", "int", True),
    FinRow(10, "balance.total_liabilities", "负债总额（元）", "int", True),
    FinRow(11, "balance.total_equity", "所有者权益合计（元）", "int", True),
    FinRow(12, "balance.total_equity_attrib_to_parent", "归属于母公司所有者权益（元）", "int", True),
    FinRow(13, "balance.minority_interests", "少数股东权益（元，可选，可推导）", "int", False),
    FinRow(14, "equity_roll.opening_attrib_parent", "期初归母所有者权益（元，首年必填）", "int", True),
    FinRow(15, "equity_roll.dividends", "本年宣告分红——归母口径（元，可选）", "int", False),
    FinRow(16, "equity_roll.capital_injection", "本年股东增资（元，可选）", "int", False),
    FinRow(17, "reconciliation.adjustments", "间接法调节项合计（元，可选，可推导）", "int", False),
    FinRow(18, "audit.status", "审计状态", "audit_status", True),
    FinRow(19, "audit.opinion", "审计意见（已审计必填）", "audit_opinion", True),
    FinRow(20, "audit.report_id", "审计报告编号（已审计必填）", "str", True),
)

DECL_ROWS: tuple[DeclRow, ...] = (
    DeclRow(2, "documentary.mktcap_self_estimate.value", "预计市值（元）", "int", False),
    DeclRow(3, "documentary.mktcap_self_estimate.note", "预计市值说明（与市值同填）", "note", False),
    DeclRow(4, "documentary.invention_patents.granted_count", "发明专利授权数量（件）", "int", False),
    DeclRow(5, "documentary.invention_patents.applied_to_main_business", "发明专利应用于主营业务", "bool", False),
    DeclRow(6, "documentary.operating_years", "经营年限（整年）", "int", False),
    DeclRow(7, "documentary.public_float_ratio", "公开发行比例（%填 25 表示 25%）", "percent", False),
    DeclRow(8, "documentary.total_shares_after_ipo", "发行后股本总额（股）", "int", False),
    DeclRow(9, "documentary.rev_cagr_gt_peer_avg", "营收复合增长率高于同行业可比公司均值", "bool", False),
    DeclRow(10, "documentary.rd_staff_ratio", "研发人员占比（%填 18 表示 18%）", "percent", False),
    DeclRow(11, "declared.self_developed_tech_intl_leading", "拥有自主知识产权的国际领先核心技术", "bool", False),
    DeclRow(12, "declared.rd_stage_or_innovation_redchip", "研发阶段红筹或创新红筹", "bool", False),
    DeclRow(13, "declared.national_approved_or_phase2_clinic", "药品获批上市或进入Ⅱ期临床试验", "bool", False),
    DeclRow(14, "declared.org_structure_sound", "股份公司且组织机构健全（205号令第十条）", "bool", False),
    DeclRow(15, "declared.core_tech_national_recognition", "核心技术获国家科技创新咨询委员会认可", "bool", False),
    DeclRow(16, "declared.national_science_award", "获国家科技进步奖等国家级科技奖项", "bool", False),
    DeclRow(17, "declared.national_mega_science_project", "承担国家重大科技专项", "bool", False),
    DeclRow(18, "declared.import_substitution", "进口替代（科创属性例外(4)）", "bool", False),
    DeclRow(19, "declared.modern_industry_system", "属于创业板现代产业体系", "bool", False),
    DeclRow(20, "declared.main_board_fit", "符合主板定位", "bool", False),
    DeclRow(21, "declared.star_industry_fit", "符合科创板定位", "bool", False),
    DeclRow(22, "declared.chinext_growth_innovation_fit", "符合创业板成长型创新创业定位", "bool", False),
    DeclRow(23, "declared.bse_positioning_fit", "符合北交所市场定位", "bool", False),
    DeclRow(24, "declared.ic_clean_3y", "近三年内控鉴证均为无保留结论", "bool", False),
    DeclRow(25, "declared.biz_team_stable", "主营业务稳定、经营团队稳定", "bool", False),
    DeclRow(26, "declared.core_tech_team_stable", "核心技术团队稳定", "bool", False),
    DeclRow(27, "declared.equity_clear_controller_stable", "股权清晰、控制权稳定", "bool", False),
    DeclRow(28, "declared.no_major_dispute_contingency", "无重大权属纠纷或重大或有事项", "bool", False),
    DeclRow(29, "declared.lawful_business_3y", "近三年合法合规经营", "bool", False),
    DeclRow(30, "declared.nqtb_listed_12m", "新三板挂牌满 12 个月（北交所）", "bool", False),
    DeclRow(31, "declared.bse_offering_requirements", "符合北交所发行上市条件", "bool", False),
)


# -- 中文 ↔ 枚举映射（importer 复用，反向可推） --------------------------------

COMPANY_TYPE_ZH = {"一般企业": "general", "红筹未上市": "redchip_unlisted",
                   "红筹已上市": "redchip_listed", "表决权差异安排": "weighted_voting"}
PROFIT_STATUS_ZH = {"盈利": "profitable", "亏损": "loss_making"}
COMPANY_STAGE_ZH = {"成长型": "growth", "研发阶段": "rd_stage", "国家战略意义": "strategic_significance"}
REDCHIP_STATUS_ZH = {"已境外上市": "listed", "未境外上市": "unlisted"}
AUDIT_STATUS_ZH = {"已审计": "audited", "未审计": "unaudited"}
AUDIT_OPINION_ZH = {"标准无保留意见": "unqualified", "保留意见": "qualified",
                    "无法表示意见": "disclaimer", "否定意见": "adverse"}
BOOL_ZH = {"是": True, "否": False}

DECL_NOTE_HINTS = {  # 申报口径 sheet C 列的填写提示（builder 写入，importer 不读）
    "bool": "填 是 / 否；留空 = 未取得结论（按未定处理）",
    "percent": "填百分数数值，如 25 表示 25%",
    "note": "预计市值的估值依据一句话",
}


# -- 样例数据（勾稽①~⑤自洽；⑥虽企业模式跳过，区间内也无碍） ---------------------
# ③ 链：92+15−2+0=105；105+18−1+3=125；125+22−3+1=145（分红/增资按年配平）
# ② 链：15+5=20；18+6=24；22+8=30（adjustments = OCF − 净利总额）
# 少数股东权益 / 调节项合计 两行留空不填：golden 须覆盖「缺行 → 推导」路径
# （推导期望：5,000,000 ×3 / 5M、6M、8M）。

SAMPLE_YEARS = (2023, 2024, 2025)

SAMPLE_FIN: dict[str, tuple[Any, Any, Any]] = {
    "income.operating_revenues": (120_000_000, 150_000_000, 180_000_000),
    "income.net_profit_total": (15_000_000, 18_000_000, 22_000_000),
    "income.net_profit_attrib_parent.as_reported": (15_000_000, 18_000_000, 22_000_000),
    "income.net_profit_attrib_parent.excl_nonrecurring": (14_000_000, 17_500_000, 21_000_000),
    "income.rd_expensed": (8_000_000, 10_000_000, 12_500_000),
    "income.rd_capitalized": (2_000_000, 2_500_000, 3_000_000),
    "cash_flow.net_cash_flow_from_operating": (20_000_000, 24_000_000, 30_000_000),
    "balance.total_assets": (200_000_000, 230_000_000, 260_000_000),
    "balance.total_liabilities": (90_000_000, 100_000_000, 110_000_000),
    "balance.total_equity": (110_000_000, 130_000_000, 150_000_000),
    "balance.total_equity_attrib_to_parent": (105_000_000, 125_000_000, 145_000_000),
    "equity_roll.opening_attrib_parent": (92_000_000, 105_000_000, 125_000_000),
    "equity_roll.dividends": (2_000_000, 1_000_000, 3_000_000),
    "equity_roll.capital_injection": (0, 3_000_000, 1_000_000),
    "audit.status": ("已审计", "已审计", "已审计"),
    "audit.opinion": ("标准无保留意见", "标准无保留意见", "标准无保留意见"),
    "audit.report_id": ("样例审[2024]001号", "样例审[2025]002号", "样例审[2026]003号"),
}

SAMPLE_SUBJECT: dict[str, Any] = {
    "display_name": "样例实业股份有限公司",
    "applicant_profile.company_type": "一般企业",
    "applicant_profile.profit_status": "盈利",
    "applicant_profile.industry": "通用设备制造业",
}

SAMPLE_DECL: dict[str, Any] = {  # 填一半留一半：留空合法路径的夹具
    "documentary.mktcap_self_estimate.value": 3_000_000_000,
    "documentary.mktcap_self_estimate.note": "按可比公司法预估（样例）",
    "documentary.invention_patents.granted_count": 12,
    "documentary.invention_patents.applied_to_main_business": "是",
    "documentary.operating_years": 15,
    "documentary.public_float_ratio": 25,
    "documentary.total_shares_after_ipo": 400_000_000,
    "documentary.rd_staff_ratio": 18,
    "declared.self_developed_tech_intl_leading": "是",
    "declared.org_structure_sound": "是",
    "declared.biz_team_stable": "是",
    "declared.main_board_fit": "是",
}


# -- builder -------------------------------------------------------------------

_BOLD = Font(bold=True)


def _write_template(
    path: Path | str,
    *,
    years: tuple[int, int, int] | None,
    fin: dict[str, tuple[Any, Any, Any]] | None,
    subject: dict[str, Any] | None,
    decl: dict[str, Any] | None,
) -> Path:
    """按坐标常量写整本模板；各值参传 None 即空白底稿（表头/科目/说明列仍齐全）。"""
    p = Path(path)
    wb = Workbook()

    ws = wb.active
    ws.title = SHEET_SUBJECT
    ws["A1"], ws["B1"] = "项目", "内容"
    for r in SUBJECT_ROWS:
        ws[f"A{r.row}"] = r.label
        if subject and r.key in subject:
            ws[f"{SUBJECT_VALUE_COL}{r.row}"] = subject[r.key]
    ws.column_dimensions["A"].width = 34

    ws = wb.create_sheet(SHEET_FIN)
    ws["A1"] = "科目"
    if years:
        for col, y in zip(YEAR_COLS, years):
            ws[f"{col}{HEADER_ROW}"] = y
    ws[f"{STUB_COL}{HEADER_ROW}"] = "本期（可选）"
    for r in FIN_ROWS:
        ws[f"A{r.row}"] = r.label
        if fin and r.key in fin:
            for col, v in zip(YEAR_COLS, fin[r.key]):
                ws[f"{col}{r.row}"] = v
    ws.column_dimensions["A"].width = 44
    for col in (*YEAR_COLS, STUB_COL):
        ws.column_dimensions[col].width = 16

    ws = wb.create_sheet(SHEET_DECLARED)
    ws["A1"], ws["B1"], ws["C1"] = "项目", "内容", "填写说明"
    for r in DECL_ROWS:
        ws[f"A{r.row}"] = r.label
        ws[f"{DECL_NOTE_COL}{r.row}"] = DECL_NOTE_HINTS.get(r.kind, "留空 = 未定")
        if decl and r.key in decl:
            ws[f"{DECL_VALUE_COL}{r.row}"] = decl[r.key]
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 36

    for ws_ in wb.worksheets:  # 表头加粗：客户第一眼看到的是列结构
        for cell in ws_[1]:
            cell.font = _BOLD

    wb.save(p)
    return p


def build_sample_template(path: Path | str) -> Path:
    """样例模板（golden 夹具 + 客户参考样例）：必填全填，申报口径填一半留一半。"""
    return _write_template(
        path, years=SAMPLE_YEARS, fin=SAMPLE_FIN, subject=SAMPLE_SUBJECT, decl=SAMPLE_DECL
    )


def build_blank_template(path: Path | str) -> Path:
    """空白底稿（发给客户填写）：值区全空，表头/科目/说明列齐全。"""
    return _write_template(path, years=None, fin=None, subject=None, decl=None)
