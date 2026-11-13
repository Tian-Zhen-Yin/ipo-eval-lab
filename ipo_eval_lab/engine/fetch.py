"""Fetch 节点（设计 0005 §2 取数面；票 02）。

六驱动（原始字段直录）+ 七指标（按规则库 metrics 逐个构造，引擎只实现语义——AR3）。
缺数据 = {value: None, reason}，**永不落 0**（E3 无静默回退）。
窗口聚合（sum/latest/cagr…）归 Calc（票 03），Fetch 只出逐年序列——不做窗口数学。
每个数字带 refs（不变量 5）：drivers 与 metrics 一视同仁。

字段路径知识单点在 _SIMPLE_FIELDS（drivers 与单字段指标共用一张表）；
「逐年孰低」单点在 _np_lower（净利指标与 ROE 分子共用）。

ROE 加权派生（编报规则 9 号，事件无日期信息取年中中性假设 Mi=6/12）：
    分子 = 逐年孰低净利（metrics.yaml decision_measure: lower_of_both）
    分母 = E0 + 申报NP/2 + 增资/2 − 分红/2（申报 NP 与 equity_roll 勾稽③同源）
    分母 ≤ 0 → 缺值（负净资产年份不硬算）
首个消费叶（M1 全量）落地时对年中假设复核对拍。
"""
from __future__ import annotations

from typing import Any, Callable

from ipo_eval_lab.fixtures.models import CompanyProfile, Statement
from ipo_eval_lab.rulebook.models import Rulebook

from .errors import EngineError


def _entry(value: Any, *refs: str, reason: str | None = None) -> dict[str, Any]:
    return {"value": value, "refs": list(refs), "reason": reason}


# 字段路径单点：drivers 与单字段指标共用（新增字段只改这里）
_SIMPLE_FIELDS: list[tuple[str, Callable[[Statement], Any], str]] = [
    ("operating_revenues", lambda s: s.income.operating_revenues, "income.operating_revenues"),
    ("net_profit_as_reported", lambda s: s.income.net_profit_attrib_parent.as_reported,
     "income.net_profit_attrib_parent.as_reported"),
    ("net_profit_excl_nonrecurring", lambda s: s.income.net_profit_attrib_parent.excl_nonrecurring,
     "income.net_profit_attrib_parent.excl_nonrecurring"),
    ("net_cash_flow_from_oper", lambda s: s.cash_flow.net_cash_flow_from_operating,
     "cash_flow.net_cash_flow_from_operating"),
    ("total_equity_attrib_to_parent", lambda s: s.balance.total_equity_attrib_to_parent,
     "balance.total_equity_attrib_to_parent"),
    ("rd_expensed", lambda s: s.income.rd_expensed, "income.rd_expensed"),
    ("rd_capitalized", lambda s: s.income.rd_capitalized, "income.rd_capitalized"),
]


def _field_series(
    stmts: dict[int, Statement], getter: Callable[[Statement], Any], path: str
) -> dict[int, dict[str, Any]]:
    return {y: _entry(getter(s), f"statements.{y}.{path}") for y, s in stmts.items()}


def _np_lower(s: Statement) -> int | None:
    """逐年孰低：扣非缺 → None（不用申报顶替，E3）。单点，净利指标与 ROE 分子共用。"""
    excl = s.income.net_profit_attrib_parent.excl_nonrecurring
    if excl is None:
        return None
    return min(s.income.net_profit_attrib_parent.as_reported, excl)


def roe_year(
    opening: int, np_reported: int | None, np_lower: int | None, dividends: int, capital_injection: int
) -> float | None:
    """单年加权 ROE（小数）。分子孰低、分母申报（与 equity_roll 勾稽同源）；分母 ≤ 0 → None。"""
    if np_lower is None or np_reported is None:
        return None
    denom = opening + np_reported / 2 + capital_injection / 2 - dividends / 2
    if denom <= 0:
        return None
    return np_lower / denom


def _metric_net_profit(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    lower: dict[int, dict[str, Any]] = {}
    for y, s in stmts.items():
        ref = f"statements.{y}.income.net_profit_attrib_parent"
        v = _np_lower(s)
        lower[y] = (
            _entry(v, f"{ref}.as_reported", f"{ref}.excl_nonrecurring", reason="min(申报, 扣非)")
            if v is not None
            else _entry(None, f"{ref}.as_reported", f"{ref}.excl_nonrecurring",
                        reason="扣非缺 → 孰低缺值（不用申报顶替）")
        )
    return {
        "as_reported": _field_series(stmts, lambda s: s.income.net_profit_attrib_parent.as_reported,
                                     "income.net_profit_attrib_parent.as_reported"),
        "excl_nonrecurring": _field_series(
            stmts, lambda s: s.income.net_profit_attrib_parent.excl_nonrecurring,
            "income.net_profit_attrib_parent.excl_nonrecurring"),
        "lower_of_both": lower,
    }


def _metric_rd_total(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    series: dict[int, dict[str, Any]] = {}
    for y, s in stmts.items():
        exp, cap = s.income.rd_expensed, s.income.rd_capitalized
        refs = (f"statements.{y}.income.rd_expensed", f"statements.{y}.income.rd_capitalized")
        if exp is None or cap is None:
            series[y] = _entry(None, *refs, reason="研发两源任一缺 → 该年缺值")
        else:
            series[y] = _entry(exp + cap, *refs, reason="费用化+资本化")
    return {"series": series}


def _metric_roe(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    series: dict[int, dict[str, Any]] = {}
    for y, s in stmts.items():
        value = roe_year(
            opening=s.equity_roll.opening_attrib_parent,
            np_reported=s.equity_roll.net_profit_attrib_parent,  # 申报（勾稽③同源）
            np_lower=_np_lower(s),
            dividends=s.equity_roll.dividends,
            capital_injection=s.equity_roll.capital_injection,
        )
        series[y] = _entry(
            value,
            f"statements.{y}.income.net_profit_attrib_parent",
            f"statements.{y}.equity_roll.opening_attrib_parent",
            f"statements.{y}.equity_roll.net_profit_attrib_parent",
            f"statements.{y}.equity_roll.dividends",
            f"statements.{y}.equity_roll.capital_injection",
            reason=None if value is not None else "孰低缺值或分母 ≤ 0 → 不硬算",
        )
    return {"series": series}


def _metric_mktcap(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    est = profile.documentary.mktcap_self_estimate
    if est is None:
        return _entry(None, "documentary.mktcap_self_estimate", reason="企业自估缺数据（G-C）→ indeterminate")
    return _entry(est.value, "documentary.mktcap_self_estimate.value", reason=est.note or None)


def _metric_rd_staff_ratio(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    """研发人员占比（F9）：底表值，缺 → indeterminate。"""
    v = profile.documentary.rd_staff_ratio
    return _entry(
        v, "documentary.rd_staff_ratio",
        reason=None if v is not None else "研发人员占比缺数据（F9）→ indeterminate",
    )


def _metric_invention_patents(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    """发明专利数量（check50/check55）：documentary.invention_patents.granted_count。"""
    n = profile.documentary.invention_patents.granted_count
    return _entry(
        n, "documentary.invention_patents.granted_count",
        reason=None if n is not None else "发明专利数缺数据 → indeterminate",
    )


def _metric_peer_cagr(stmts: dict[int, Statement], profile: CompanyProfile) -> dict[str, Any]:
    """行业对比结论（设计 0006 F7）：底稿布尔，缺 → indeterminate（缺数三原则）。"""
    v = profile.documentary.rev_cagr_gt_peer_avg
    return _entry(
        v, "documentary.rev_cagr_gt_peer_avg",
        reason=None if v is not None else "行业对比结论缺数据（F7）→ indeterminate",
    )


_SPEC_BY_KEY = {key: (getter, path) for key, getter, path in _SIMPLE_FIELDS}


def _simple_builder(driver_key: str) -> Callable[[dict[int, Statement], CompanyProfile], dict[str, Any]]:
    getter, path = _SPEC_BY_KEY[driver_key]
    return lambda stmts, profile: {"series": _field_series(stmts, getter, path)}


# 指标 id 用缩写 attr（rulebook/metrics.yaml），驱动字段名是全拼 attrib——映射在此显式声明
_BUILDERS: dict[str, Callable[[dict[int, Statement], CompanyProfile], dict[str, Any]]] = {
    "operating_revenues": _simple_builder("operating_revenues"),
    "net_cash_flow_from_oper": _simple_builder("net_cash_flow_from_oper"),
    "total_equity_attr_to_parent": _simple_builder("total_equity_attrib_to_parent"),
    "net_profit_attrib_parent": _metric_net_profit,
    "rd_investment_total": _metric_rd_total,
    "roe_weighted_avg": _metric_roe,
    "mktcap": _metric_mktcap,
    "rev_cagr_vs_peer": _metric_peer_cagr,
    "rd_staff_ratio": _metric_rd_staff_ratio,
    "invention_patent_count": _metric_invention_patents,
}


def build_facts(rulebook: Rulebook, profile: CompanyProfile) -> dict[str, Any]:
    """六驱动 + 七指标 → facts（内部结构；契约 v0.2 组装在票 08）。结果可 JSON 序列化。"""
    stmts = {s.fiscal_year: s for s in sorted(profile.statements, key=lambda s: s.fiscal_year)}

    drivers = {
        key: _field_series(stmts, getter, path) for key, getter, path in _SIMPLE_FIELDS
    }

    metrics: dict[str, Any] = {}
    for m in rulebook.metrics:
        builder = _BUILDERS.get(m.metric_id)
        if builder is None:
            raise EngineError(
                f"引擎无此指标的取数语义：{m.metric_id}"
                f"（已知：{sorted(_BUILDERS)}）——新指标需先实现 builder（AR3：语义在引擎，数据在规则库）"
            )
        metrics[m.metric_id] = builder(stmts, profile)

    return {
        "drivers": drivers,
        "metrics": metrics,
        "audit": {  # 逐年审计形态（票 03 Calc 的审计覆盖降级输入；§4.4-3）
            y: {"status": s.audit.status, "opinion": s.audit.opinion, "report_id": s.audit.report_id}
            for y, s in stmts.items()
        },
        "documentary": profile.documentary.model_dump(),
        "declared": profile.declared.model_dump(),
        "stub": profile.stub_period,  # 展示用，永不进窗口与判定（E2-2）
    }
