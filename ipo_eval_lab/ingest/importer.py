"""importer：模板 Excel → 三件套主体目录（ADR-0013；工单 02 主链路 + 工单 03 收集式）。

接缝：外界只认识 import_profile() 与其产出的 company_dir；引擎不知道 Excel。

校验两层、收集式（对齐 fixtures/loader 的「一次报全」风格）：
1. 格层：必填/类型/枚举逐格查（带 sheet!坐标 + 中文字段）——违例则**不落盘**早退；
2. 勾稽层：profile 构造成功后复用 check_profile(profile, None)——①~⑤带勾稽号，
   ⑥是 mock 生成器卫生参数，企业数据不查（ADR-0013 分流）。
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from openpyxl import load_workbook
from pydantic import ValidationError

from ipo_eval_lab.fixtures.loader import FixtureDataError, check_profile
from ipo_eval_lab.fixtures.models import (
    ApplicantProfile,
    AuditInfo,
    Balance,
    CashFlow,
    CompanyProfile,
    Declared,
    Documentary,
    EquityRoll,
    Income,
    InventionPatents,
    MktcapSelfEstimate,
    NetProfit,
    Reconciliation,
    Statement,
)

from .template import (
    AUDIT_OPINION_ZH,
    AUDIT_STATUS_ZH,
    BOOL_ZH,
    COMPANY_STAGE_ZH,
    COMPANY_TYPE_ZH,
    DECL_ROWS,
    DECL_VALUE_COL,
    FIN_ROWS,
    HEADER_ROW,
    PROFIT_STATUS_ZH,
    REDCHIP_STATUS_ZH,
    SHEET_DECLARED,
    SHEET_FIN,
    SHEET_SUBJECT,
    STUB_COL,
    SUBJECT_ROWS,
    SUBJECT_VALUE_COL,
    TEMPLATE_VERSION,
    YEAR_COLS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_ROOT = REPO_ROOT / ".scratch" / "ingest"


@dataclass(frozen=True)
class IngestResult:
    """import_profile 的全部产出：目录 + 校验结论 + 推导披露。"""

    status: Literal["ok", "violations"]
    company_dir: Path | None = None
    violations: list[str] = field(default_factory=list)
    derived_fields: list[str] = field(default_factory=list)


# -- 读格工具 -------------------------------------------------------------------

def _val(ws: Any, coord: str) -> Any:
    """读一格：字符串去空白；空串归一为 None（留空 = 未填）。"""
    v = ws[coord].value
    if isinstance(v, str):
        v = v.strip() or None
    return v


def _is_intlike(v: Any) -> bool:
    """整数数值判定（Excel 数字格可能是 int/float；布尔不算数）。"""
    return isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer()


def _as_int(v: Any) -> int:
    """整数 coercion：格层校验后到达这里的都是整值数字。"""
    return int(v)


# -- 格层校验（必填/类型/枚举，逐格收集） -----------------------------------------

_ENUMS: dict[str, dict[str, str]] = {
    "applicant_profile.company_type": COMPANY_TYPE_ZH,
    "applicant_profile.profit_status": PROFIT_STATUS_ZH,
    "applicant_profile.company_stage": COMPANY_STAGE_ZH,
    "applicant_profile.redchip_status": REDCHIP_STATUS_ZH,
    "audit.status": AUDIT_STATUS_ZH,
    "audit.opinion": AUDIT_OPINION_ZH,
}

# 必填查不覆盖这两行：审计意见/报告编号是「已审计才必填」，语义归勾稽⑤（带年份）
_PRESENCE_EXEMPT = {"audit.opinion", "audit.report_id"}


def _validate_cells(ws_sub: Any, ws_fin: Any, ws_dec: Any, sub: dict[str, Any]) -> list[str]:
    v: list[str] = []

    def bad(sheet: str, coord: str, label: str, why: str) -> None:
        v.append(f"{sheet}!{coord} {label}：{why}")

    # 主体信息：名称 + 四个枚举
    sub_row = {r.key: r.row for r in SUBJECT_ROWS}
    if not sub["display_name"]:
        bad(SHEET_SUBJECT, f"B{sub_row['display_name']}", "企业名称", "必填缺失")
    for r in SUBJECT_ROWS:
        val = sub[r.key]
        if r.key not in _ENUMS:
            continue
        if val is None:
            if r.required:
                bad(SHEET_SUBJECT, f"B{r.row}", r.label, "必填缺失")
        elif val not in _ENUMS[r.key]:
            bad(SHEET_SUBJECT, f"B{r.row}", r.label, f"应填 {'/'.join(_ENUMS[r.key])}，实际 {val!r}")

    # 财务表头：三个整数年份
    for col in YEAR_COLS:
        raw = _val(ws_fin, f"{col}{HEADER_ROW}")
        if raw is None:
            bad(SHEET_FIN, f"{col}{HEADER_ROW}", "表头年份", "必填缺失")
        elif not _is_intlike(raw):
            bad(SHEET_FIN, f"{col}{HEADER_ROW}", "表头年份", f"应为整数年份（如 2024），实际 {raw!r}")

    # 财务科目行
    for r in FIN_ROWS:
        for i, col in enumerate(YEAR_COLS):
            val = _val(ws_fin, f"{col}{r.row}")
            if val is None:
                # 期初归母只有首年必填（后续年可由上年期末推导）
                first_year_only = r.key == "equity_roll.opening_attrib_parent" and i > 0
                if r.required and r.key not in _PRESENCE_EXEMPT and not first_year_only:
                    bad(SHEET_FIN, f"{col}{r.row}", r.label, "必填缺失")
                continue
            if r.key in _ENUMS:
                if val not in _ENUMS[r.key]:
                    bad(SHEET_FIN, f"{col}{r.row}", r.label, f"应填 {'/'.join(_ENUMS[r.key])}，实际 {val!r}")
            elif r.kind == "int" and not _is_intlike(val):
                bad(SHEET_FIN, f"{col}{r.row}", r.label, f"应为整数数值，实际 {val!r}")

    # 申报口径：bool 是/否；数值类整数
    for r in DECL_ROWS:
        val = _val(ws_dec, f"{DECL_VALUE_COL}{r.row}")
        if val is None:
            continue  # 留空合法（null → indeterminate）
        if r.kind == "bool":
            if val not in BOOL_ZH:
                bad(SHEET_DECLARED, f"{DECL_VALUE_COL}{r.row}", r.label, f"应填 是/否，实际 {val!r}")
        elif r.kind in ("int", "percent") and not _is_intlike(val):
            bad(SHEET_DECLARED, f"{DECL_VALUE_COL}{r.row}", r.label, f"应为数值，实际 {val!r}")
    return v


# -- import_profile：对外唯一入口 ------------------------------------------------

def import_profile(
    xlsx_path: Path | str, company_id: str, out_root: Path | str | None = None
) -> IngestResult:
    """模板 Excel → 三件套 company_dir（profile.json + source.xlsx + ingest.json）。

    company_id 由运营方分配（ADR-0013），绝不取自 Excel 内客户自填名称。
    status="violations" 时不落盘；违例收集式（一次报全）。
    """
    src = Path(xlsx_path)
    wb = load_workbook(src, data_only=True)
    ws_sub, ws_fin, ws_dec = wb[SHEET_SUBJECT], wb[SHEET_FIN], wb[SHEET_DECLARED]
    derived: list[str] = []

    sub: dict[str, Any] = {r.key: _val(ws_sub, f"{SUBJECT_VALUE_COL}{r.row}") for r in SUBJECT_ROWS}

    violations = _validate_cells(ws_sub, ws_fin, ws_dec, sub)
    if violations:
        return IngestResult(status="violations", violations=violations)

    def _enum(value: Any, mapping: dict[str, str]) -> str | None:
        return None if value is None else mapping[value]  # 格层已拦非法枚举

    applicant = ApplicantProfile(
        company_type=_enum(sub["applicant_profile.company_type"], COMPANY_TYPE_ZH),
        profit_status=_enum(sub["applicant_profile.profit_status"], PROFIT_STATUS_ZH),
        industry=sub["applicant_profile.industry"],
        company_stage=_enum(sub["applicant_profile.company_stage"], COMPANY_STAGE_ZH),
        redchip_status=_enum(sub["applicant_profile.redchip_status"], REDCHIP_STATUS_ZH),
    )

    # -- 财务三年一期 --
    years = [_as_int(_val(ws_fin, f"{c}{HEADER_ROW}")) for c in YEAR_COLS]
    grid: dict[str, list[Any]] = {r.key: [_val(ws_fin, f"{c}{r.row}") for c in YEAR_COLS] for r in FIN_ROWS}

    stub_raw = {r.key: _val(ws_fin, f"{STUB_COL}{r.row}") for r in FIN_ROWS}
    stub_items = {k: v for k, v in stub_raw.items() if v is not None}
    stub_period: dict[str, Any] | None = (
        {"fiscal_year": years[-1] + 1, "items": stub_items} if stub_items else None  # 原样透传，永不进判定
    )

    statements: list[Statement] = []
    prev_closing: int | None = None
    for i, year in enumerate(years):
        def col(key: str) -> Any:
            return grid[key][i]

        audit = AuditInfo(
            status=_enum(col("audit.status"), AUDIT_STATUS_ZH),
            opinion=_enum(col("audit.opinion"), AUDIT_OPINION_ZH),
            report_id=col("audit.report_id"),
        )
        np_as_reported = _as_int(col("income.net_profit_attrib_parent.as_reported"))
        excl = col("income.net_profit_attrib_parent.excl_nonrecurring")
        income = Income(
            operating_revenues=_as_int(col("income.operating_revenues")),
            net_profit_total=_as_int(col("income.net_profit_total")),
            net_profit_attrib_parent=NetProfit(
                as_reported=np_as_reported, excl_nonrecurring=None if excl is None else _as_int(excl)
            ),
            rd_expensed=None if col("income.rd_expensed") is None else _as_int(col("income.rd_expensed")),
            rd_capitalized=None if col("income.rd_capitalized") is None else _as_int(col("income.rd_capitalized")),
        )
        ocf = _as_int(col("cash_flow.net_cash_flow_from_operating"))
        equity = _as_int(col("balance.total_equity"))
        parent = _as_int(col("balance.total_equity_attrib_to_parent"))

        minority = col("balance.minority_interests")
        if minority is None:  # 推导：权益合计 − 归母
            minority = equity - parent
            derived.append("balance.minority_interests")

        # equity_roll：np/closing 无模板行，恒由主表推导
        derived.append("equity_roll.net_profit_attrib_parent")
        derived.append("equity_roll.closing_attrib_parent")

        opening = col("equity_roll.opening_attrib_parent")
        if opening is None:  # 格层已保证首年有值；此处只剩「中间年由上年期末链推」
            opening = prev_closing
            derived.append("equity_roll.opening_attrib_parent")
        else:
            opening = _as_int(opening)
        prev_closing = parent

        dividends, injection = col("equity_roll.dividends"), col("equity_roll.capital_injection")
        # ③ 恒等式：opening + np − div + inj = closing
        if dividends is None and injection is None:  # 双缺：残差归分红、增资记 0（ADR-0013 披露）
            dividends = opening + np_as_reported - parent
            injection = 0
            derived += ["equity_roll.dividends", "equity_roll.capital_injection"]
        elif dividends is None:
            dividends = opening + np_as_reported + _as_int(injection) - parent
            derived.append("equity_roll.dividends")
        elif injection is None:
            injection = _as_int(dividends) - opening - np_as_reported + parent
            derived.append("equity_roll.capital_injection")

        adjustments = col("reconciliation.adjustments")
        if adjustments is None:  # 推导：OCF − 净利润总额（勾稽②恒等式）
            adjustments = ocf - income.net_profit_total
            derived.append("reconciliation.adjustments")

        statements.append(
            Statement(
                fiscal_year=year,
                audit=audit,
                income=income,
                cash_flow=CashFlow(net_cash_flow_from_operating=ocf),
                balance=Balance(
                    total_assets=_as_int(col("balance.total_assets")),
                    total_liabilities=_as_int(col("balance.total_liabilities")),
                    total_equity=equity,
                    total_equity_attrib_to_parent=parent,
                    minority_interests=_as_int(minority),
                ),
                equity_roll=EquityRoll(
                    opening_attrib_parent=opening,
                    net_profit_attrib_parent=np_as_reported,
                    dividends=_as_int(dividends),
                    capital_injection=_as_int(injection),
                    closing_attrib_parent=parent,
                ),
                reconciliation=Reconciliation(
                    net_profit_total=income.net_profit_total,
                    adjustments=_as_int(adjustments),
                    net_cash_flow_from_operating=ocf,
                ),
            )
        )

    # -- 申报口径 --
    dec: dict[str, Any] = {r.key: _val(ws_dec, f"{DECL_VALUE_COL}{r.row}") for r in DECL_ROWS}

    def to_bool(key: str) -> bool | None:
        return None if dec[key] is None else BOOL_ZH[dec[key]]  # 格层已拦非法值

    def to_percent(key: str) -> float | None:
        return None if dec[key] is None else _as_int(dec[key]) / 100  # 25 → 0.25

    mktcap_value = dec["documentary.mktcap_self_estimate.value"]
    documentary = Documentary(
        mktcap_self_estimate=(
            MktcapSelfEstimate(
                value=None if mktcap_value is None else _as_int(mktcap_value),
                note=dec["documentary.mktcap_self_estimate.note"] or "",
            )
            if (mktcap_value is not None or dec["documentary.mktcap_self_estimate.note"])
            else None
        ),
        invention_patents=InventionPatents(
            granted_count=(
                None if dec["documentary.invention_patents.granted_count"] is None
                else _as_int(dec["documentary.invention_patents.granted_count"])
            ),
            applied_to_main_business=to_bool("documentary.invention_patents.applied_to_main_business"),
        ),
        operating_years=(
            None if dec["documentary.operating_years"] is None else _as_int(dec["documentary.operating_years"])
        ),
        public_float_ratio=to_percent("documentary.public_float_ratio"),
        total_shares_after_ipo=(
            None if dec["documentary.total_shares_after_ipo"] is None
            else _as_int(dec["documentary.total_shares_after_ipo"])
        ),
        rev_cagr_gt_peer_avg=to_bool("documentary.rev_cagr_gt_peer_avg"),
        rd_staff_ratio=to_percent("documentary.rd_staff_ratio"),
    )
    declared = Declared(**{
        r.key.split(".", 1)[1]: to_bool(r.key)
        for r in DECL_ROWS
        if r.key.startswith("declared.")
    })

    profile = CompanyProfile(
        company_id=company_id,
        display_name=sub["display_name"],
        applicant_profile=applicant,
        statements=statements,
        stub_period=stub_period,
        documentary=documentary,
        declared=declared,
    )

    # -- 勾稽层：①~⑤（⑥不查企业数据）--
    try:
        check_profile(profile, None)
    except FixtureDataError as e:
        return IngestResult(status="violations", violations=list(e.messages))

    # -- 落盘三件套 --
    root = Path(out_root) if out_root else DEFAULT_OUT_ROOT
    base = root / f"{company_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    company_dir = base
    n = 1
    while company_dir.exists():  # 同秒重复导入：加序号防撞，不覆盖既有会话
        company_dir = base.with_name(f"{base.name}_{n}")
        n += 1
    company_dir.mkdir(parents=True, exist_ok=False)
    (company_dir / "profile.json").write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.copyfile(src, company_dir / "source.xlsx")
    derived_unique = list(dict.fromkeys(derived))  # 保持首次出现顺序，逐年去重
    (company_dir / "ingest.json").write_text(
        json.dumps(
            {
                "data_source": "enterprise",
                "company_id": company_id,
                "display_name": sub["display_name"],
                "derived_fields": derived_unique,
                "template_version": TEMPLATE_VERSION,
                "source_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
                "imported_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return IngestResult(status="ok", company_dir=company_dir, derived_fields=derived_unique)
