"""适用性判定（设计 0004 §4 步④；ADR-0002 决策 3）。

applicant_profile × 套谓词：company_type 等值 + target（boards / sets）过滤。
不匹配 → 套级 not_applicable：**出分母、留在结果里可见**（不是消失）。
行业 in_list 负面清单谓词随 M1 全量铺开进入（样板套无行业限制）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ipo_eval_lab.fixtures.models import CompanyProfile
from ipo_eval_lab.rulebook.models import Group

from .context import RunTarget


@dataclass(frozen=True)
class ApplicabilityResult:
    applicable: list[Group]
    not_applicable: list[dict[str, Any]] = field(default_factory=list)


def judge_applicability(groups: list[Group], profile: CompanyProfile, target: RunTarget) -> ApplicabilityResult:
    """target 为 None 字段即不过滤；缺省（RunTarget()）= 全部适用套。"""
    applicable: list[Group] = []
    not_applicable: list[dict[str, Any]] = []

    for g in groups:
        reason: str | None = None
        if g.company_type != profile.applicant_profile.company_type:
            reason = f"company_type 不匹配（套={g.company_type}，企业={profile.applicant_profile.company_type}）"
        elif target.sets is not None and g.group_id not in target.sets:
            reason = f"target.sets 未包含（本次只评 {target.sets}）"
        elif target.boards is not None and not (set(g.boards) & set(target.boards)):
            reason = f"target.boards 未含该套板块（套={g.boards}，target={target.boards}）"
        if reason is None:
            applicable.append(g)
        else:
            not_applicable.append({"group_id": g.group_id, "display": g.display, "reason": reason})

    return ApplicabilityResult(applicable=applicable, not_applicable=not_applicable)
