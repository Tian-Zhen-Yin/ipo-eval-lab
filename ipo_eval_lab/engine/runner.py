"""引擎编排（设计 0004 §4 十步的 T1 子集：①~④ 坐标装配 / 加载 / as_of / 适用性）。

run_eval 是测试与 CLI 共用的入口；十步在五节点上的归并随 T2~T8 展开。
生效判据单点在 asof.filter_by_as_of——applied_rule_versions 由过滤与适用性结果
**派生**，不重写 `effective_from <= as_of`（code-review Standards 轴发现）。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable

from ipo_eval_lab.fixtures import load_company, load_sanity
from ipo_eval_lab.fixtures.models import CompanyProfile
from ipo_eval_lab.rulebook.loader import RulebookLintError, load_rulebook
from ipo_eval_lab.rulebook.models import Rulebook

from .applicability import judge_applicability
from .asof import filter_by_as_of, parse_as_of
from .chain import run_chain
from .context import RunContext, RunTarget, Selection
from .errors import EngineError

# 审计意见劣化序（run 级聚合取最差；逐年关系是 V12，此处只做 run 坐标摘要）
_OPINION_ORDER = ["unqualified", "qualified", "disclaimer", "adverse"]


def _report_period(profile: CompanyProfile) -> dict[str, Any]:
    years = sorted(s.fiscal_year for s in profile.statements)
    statuses = [s.audit.status for s in profile.statements]
    if all(s == "audited" for s in statuses):
        audit_status = "audited"
    elif all(s == "unaudited" for s in statuses):
        audit_status = "unaudited"
    else:
        audit_status = "partial"
    opinions = [s.audit.opinion for s in profile.statements if s.audit.opinion is not None]
    worst = max(opinions, key=_OPINION_ORDER.index) if opinions else None
    return {
        "fiscal_years": years,
        "stub": profile.stub_period,
        "audit_status": audit_status,
        "audit_opinion": worst,
    }


def _make_init(
    rulebook: Rulebook, profile: CompanyProfile, as_of: date, target: RunTarget
) -> Callable[[RunContext], None]:
    """闭包注入加载产物；写 run 坐标 + 套选择（append-only 的第一笔）。"""

    def init(ctx: RunContext) -> None:
        asof_view = filter_by_as_of(rulebook.groups, as_of)
        applicability = judge_applicability(asof_view.effective, profile, target)
        ctx.selection = Selection(
            applicable=applicability.applicable,
            not_applicable=applicability.not_applicable,
            excluded_by_asof=asof_view.excluded,
        )
        ctx.run = {
            "company_id": profile.company_id,
            "as_of_date": as_of.isoformat(),  # 显式写入（可复算；缺省=当日也落字）
            "report_period": _report_period(profile),
            "applicant_profile": profile.applicant_profile.model_dump(),
            "target": {"boards": target.boards, "sets": target.sets},
            # 版本链（设计 0003-R6）——「本次实际生效」= 真正参评的套（经 as_of + 适用性双重收敛）
            "applied_rule_versions": [
                {
                    "rulebook_version": rulebook.meta.rulebook_version,
                    "group_id": g.group_id,
                    "effective_from": g.effective_from.isoformat(),
                }
                for g in ctx.selection.applicable
            ],
        }

    return init


def run_eval(
    company_dir: Path | str,
    rulebook_dir: Path | str,
    fixtures_root: Path | str,
    as_of: str | date | None = None,
    target: RunTarget | None = None,
) -> RunContext:
    """装配坐标并跑通五节点（T1：后四节点占位直通）。"""
    company_dir = Path(company_dir)
    if not (company_dir / "profile.json").exists():
        raise EngineError(f"公司不存在：{company_dir}（缺 profile.json）")
    try:
        cutoff = parse_as_of(as_of) if as_of is not None else date.today()
    except ValueError as e:
        raise EngineError(str(e)) from e

    # AR4：规则库 lint 红 / 规则库缺失 / 企业勾稽红 → 起不了 run（统一包成 EngineError，CLI 干净退出）
    try:
        rulebook = load_rulebook(Path(rulebook_dir)).rulebook
    except RulebookLintError as e:
        raise EngineError(f"规则库 lint 未通过：{e}") from e
    except FileNotFoundError as e:
        raise EngineError(f"规则库不可用：{e}") from e
    sanity = load_sanity(Path(fixtures_root) / "sanity.yaml")
    profile = load_company(company_dir, sanity).profile

    ctx = RunContext()
    return run_chain(ctx, _make_init(rulebook, profile, cutoff, target or RunTarget()))
