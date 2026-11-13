"""适用性判定（设计 0004 §4 步④；ADR-0002 决策 3）。

applicant_profile × 套谓词：company_type 等值 + target（boards / sets）过滤
+ hard_filters（scope=positioning 的板块定位硬筛，设计 0002 §2.6）。
不匹配 → 套级 not_applicable：**出分母、留在结果里可见**（不是消失）。

scope=positioning 的组**不按 company_type 过滤**——板块定位对在该板上市的
全部企业类型一体适用（Group 模型注记「多类型适用性走 positioning 扩展」的落地）。
行业 in_list 负面清单谓词随 G-D 铺开进入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ipo_eval_lab.fixtures.models import CompanyProfile
from ipo_eval_lab.rulebook.models import Group, Scope

from .context import RunTarget


@dataclass(frozen=True)
class ApplicabilityResult:
    applicable: list[Group]
    not_applicable: list[dict[str, Any]] = field(default_factory=list)


def _hard_filter_reason(g: Group, profile: CompanyProfile) -> str | None:
    """定位硬筛（设计 0002 §2.6）：命中 → 不适用本板块。

    字段值 None 不命中——无从证明即不剔除，行业定性交由 judgment 项兜底
    （与「缺省不豁免」同一保守方向，但后果是「不排除」）。
    """
    attrs = {
        "industry": profile.applicant_profile.industry,
    }
    for hf in g.hard_filters:
        actual = attrs.get(hf.field)
        if actual is None:
            continue
        in_list = actual in hf.values
        # 排除条件按 op 定向：
        # - not_in（values=禁区清单，指引第三条禁止类）：主体**落入**禁区 → 排除；
        # - in（values=正面清单）：主体**不在**清单 → 排除（正面清单的过滤式用法）。
        excluded = in_list if hf.op == "not_in" else not in_list
        if excluded:
            return (
                f"板块定位硬筛（{hf.field}={actual} "
                f"{'属禁入清单' if hf.op == 'not_in' else '不在限定清单'}）："
                f"{hf.note or '本主体不属于该板块定位范围'}"
            )
    return None


def judge_applicability(groups: list[Group], profile: CompanyProfile, target: RunTarget) -> ApplicabilityResult:
    """target 为 None 字段即不过滤；缺省（RunTarget()）= 全部适用套。"""
    applicable: list[Group] = []
    not_applicable: list[dict[str, Any]] = []

    for g in groups:
        reason: str | None = None
        # positioning 组不按 company_type 过滤（板块定位跨企业类型一体适用），
        # 但 hard_filters 与 target 过滤照常参与。
        if g.scope is not Scope.positioning and g.company_type != profile.applicant_profile.company_type:
            reason = f"company_type 不匹配（套={g.company_type}，企业={profile.applicant_profile.company_type}）"
        if reason is None and g.hard_filters:
            reason = _hard_filter_reason(g, profile)
        if reason is None and target.sets is not None and g.group_id not in target.sets:
            reason = f"target.sets 未包含（本次只评 {target.sets}）"
        if reason is None and target.boards is not None and not (set(g.boards) & set(target.boards)):
            reason = f"target.boards 未含该套板块（套={g.boards}，target={target.boards}）"
        if reason is None:
            applicable.append(g)
        else:
            not_applicable.append({"group_id": g.group_id, "display": g.display, "reason": reason})

    return ApplicabilityResult(applicable=applicable, not_applicable=not_applicable)
