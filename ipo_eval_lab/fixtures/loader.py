"""fixtures 加载器（设计 0006 §1/§4；F1/F3）。

七条勾稽中的 ①~⑥ 在此落地；⑦ ±ε 边界归生成器（测试期动态生成，不落盘、不在此断言）。
断言风格：一次收集全部违例再抛（比首错即抛好排错）；AR4：坏数据起不了 run。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .models import CompanyProfile


class FixtureDataError(Exception):
    """勾稽/卫生断言失败。messages 收集全部违例（逐条带勾稽编号与年度）。"""

    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        super().__init__("\n".join(messages))


@dataclass(frozen=True)
class Range:
    min: float
    max: float

    def contains(self, g: float) -> bool:
        return self.min <= g <= self.max


@dataclass(frozen=True)
class SanityBounds:
    """⑥ 增长率合理区间（fixtures/sanity.yaml；数据卫生参数，非法规语义——F3）。"""

    revenue: Range
    ocf: Range
    net_profit: Range  # 申报与扣非两维同此区间


def load_sanity(path: Path | str) -> SanityBounds:
    raw: Any = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return SanityBounds(
        revenue=Range(**raw["revenue"]),
        ocf=Range(**raw["ocf"]),
        net_profit=Range(**raw["net_profit"]),
    )


def load_profile(path: Path | str) -> CompanyProfile:
    return CompanyProfile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def check_profile(profile: CompanyProfile, sanity: SanityBounds) -> None:
    """勾稽 ①~⑥（设计 0006 §4）。全过 = 静默返回；有违例 = FixtureDataError。"""
    errs: list[str] = []
    stmts = sorted(profile.statements, key=lambda s: s.fiscal_year)

    for s in stmts:
        y = s.fiscal_year
        b = s.balance
        np_rep = s.income.net_profit_attrib_parent.as_reported
        ocf = s.cash_flow.net_cash_flow_from_operating

        # ① 资产 = 负债 + 权益；归母 + 少数 = 合并权益
        if b.total_assets != b.total_liabilities + b.total_equity:
            errs.append(
                f"勾稽① {y}: total_assets({b.total_assets}) != "
                f"liabilities({b.total_liabilities}) + equity({b.total_equity})"
            )
        if b.total_equity_attrib_to_parent + b.minority_interests != b.total_equity:
            errs.append(
                f"勾稽① {y}: 归母({b.total_equity_attrib_to_parent}) + 少数({b.minority_interests})"
                f" != 合并权益({b.total_equity})"
            )

        # ② 间接法调节表平 + 与主表交叉一致（V9：起点为净利润总额，非归母）
        r = s.reconciliation
        np_total = s.income.net_profit_total
        if r.net_profit_total + r.adjustments != r.net_cash_flow_from_operating:
            errs.append(
                f"勾稽② {y}: np_total({r.net_profit_total}) + adjustments({r.adjustments})"
                f" != ocf({r.net_cash_flow_from_operating})"
            )
        if r.net_profit_total != np_total:
            errs.append(
                f"勾稽② {y}: 调节表净利润总额({r.net_profit_total}) != 利润表净利润总额({np_total})"
            )
        if r.net_cash_flow_from_operating != ocf:
            errs.append(f"勾稽② {y}: 调节表 ocf({r.net_cash_flow_from_operating}) != 现金流量表 ocf({ocf})")

        # ③ 权益滚动（归母）+ 与利润表/资产负债表交叉一致
        e = s.equity_roll
        if e.opening_attrib_parent + e.net_profit_attrib_parent - e.dividends + e.capital_injection != e.closing_attrib_parent:
            errs.append(
                f"勾稽③ {y}: opening({e.opening_attrib_parent}) + np({e.net_profit_attrib_parent})"
                f" − dividends({e.dividends}) + injection({e.capital_injection}) != closing({e.closing_attrib_parent})"
            )
        if e.net_profit_attrib_parent != np_rep:
            errs.append(f"勾稽③ {y}: equity_roll np({e.net_profit_attrib_parent}) != 利润表归母申报({np_rep})")
        if e.closing_attrib_parent != b.total_equity_attrib_to_parent:
            errs.append(
                f"勾稽③ {y}: equity_roll closing({e.closing_attrib_parent})"
                f" != 资产负债表归母({b.total_equity_attrib_to_parent})"
            )

        # ⑤ 审计字段（schema 必填由 pydantic 保证；此处管语义必填）
        if s.audit.status == "audited" and s.audit.opinion is None:
            errs.append(f"勾稽⑤ {y}: status=audited 但 opinion 为空")
        if s.audit.status == "audited" and s.audit.report_id is None:
            errs.append(f"勾稽⑤ {y}: status=audited 但 report_id 为空")

    # ③ 链：本年期初 = 上年期末
    for prev, cur in zip(stmts, stmts[1:]):
        if cur.equity_roll.opening_attrib_parent != prev.equity_roll.closing_attrib_parent:
            errs.append(
                f"勾稽③ {cur.fiscal_year}: 期初({cur.equity_roll.opening_attrib_parent})"
                f" != 上年期末({prev.equity_roll.closing_attrib_parent})"
            )

    # ④ 年份连续；stub 与末年相邻（stub 形状随 M4 定，含 fiscal_year 才检查）
    years = [s.fiscal_year for s in stmts]
    for prev, cur in zip(years, years[1:]):
        if cur - prev != 1:
            errs.append(f"勾稽④: 年份不连续 {prev} → {cur}")
    if isinstance(profile.stub_period, dict) and "fiscal_year" in profile.stub_period:
        if profile.stub_period["fiscal_year"] != years[-1] + 1:
            errs.append(f"勾稽④: stub({profile.stub_period['fiscal_year']}) 与末年({years[-1]})不相邻")

    # ⑥ 增长率区间（上年 ≤ 0 无法计算则跳过——卫生参数只为拦正常序列的手滑）
    for prev, cur in zip(stmts, stmts[1:]):
        y = cur.fiscal_year
        pairs: list[tuple[int, int, Range, str]] = [
            (prev.income.operating_revenues, cur.income.operating_revenues, sanity.revenue, "营收"),
            (
                prev.cash_flow.net_cash_flow_from_operating,
                cur.cash_flow.net_cash_flow_from_operating,
                sanity.ocf,
                "经营现金流",
            ),
            (
                prev.income.net_profit_attrib_parent.as_reported,
                cur.income.net_profit_attrib_parent.as_reported,
                sanity.net_profit,
                "归母净利(申报)",
            ),
        ]
        np_prev = prev.income.net_profit_attrib_parent.excl_nonrecurring
        np_cur = cur.income.net_profit_attrib_parent.excl_nonrecurring
        if np_prev is not None and np_cur is not None:
            pairs.append((np_prev, np_cur, sanity.net_profit, "归母净利(扣非)"))
        for p, c, rng, label in pairs:
            if p <= 0:
                continue
            g = (c - p) / p
            if not rng.contains(g):
                errs.append(
                    f"勾稽⑥ {y}: {label} 增长率 {g:.1%} 超出区间 [{rng.min:.0%}, {rng.max:.0%}]"
                )

    if errs:
        raise FixtureDataError(errs)


@dataclass
class LoadedCompany:
    profile: CompanyProfile
    expected: dict[str, Any] | None = None  # golden（设计 0006 §6：只锁语义敏感点，绑 rulebook_version）


def load_company(company_dir: Path | str, sanity: SanityBounds) -> LoadedCompany:
    """加载 profile.json + 勾稽断言 + 附带 expected/summary.json（如存在）。

    引擎 Init 节点与测试共用本入口（F1 / AR4）。
    """
    d = Path(company_dir)
    profile = load_profile(d / "profile.json")
    check_profile(profile, sanity)
    expected_path = d / "expected" / "summary.json"
    expected = json.loads(expected_path.read_text(encoding="utf-8")) if expected_path.exists() else None
    return LoadedCompany(profile=profile, expected=expected)
