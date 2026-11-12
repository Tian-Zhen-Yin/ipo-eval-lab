"""豁免判定（ADR-0008）——语义单点。

豁免 = 法定「本主体不适用某项标准」。落地形态**不是新状态**：被豁免的叶直接产
`not_applicable`——ADR-0003 已定义的第五态，折叠时按既有规则「先剔除」。

三条不可让步的约定：

1. **命中在取数之前**：豁免命中 → 直接 `not_applicable`，不查 metric、不取数。
   理由是「法律上不约束」，不是「查不到数据」——两者语义相反，混为一谈会把
   义务性缺口伪装成数据缺口。
2. **缺省不豁免**：主体侧事实字段为 None 时**不命中**。宁可按不豁免算、进人工
   复核，也不擅自免除法定义务（与 ADR-0003「null 永不进比较」同原则）。
3. **豁免叶既不进 progress 聚合、也不进 coverage 分母**：它有确定结论「不约束」，
   既非未定义叶，也非数据缺口。豁免计入分母会让 coverage 虚低、误触「禁可达标」。

本模块只回答「这条叶是否被豁免、依据是什么」，不产出判定结果——产态在 calc。
"""
from __future__ import annotations

from typing import Any

from ipo_eval_lab.rulebook.models import Clause, Exemption, ExemptionCondition


def _condition_matches(cond: ExemptionCondition, actual: Any) -> bool:
    """谓词求值；actual 为 None 一律不命中（约定 2）。

    equals 与 in_list 是**两种不同的算子**，不可压成一个期望值再比相等：
    in_list 压成列表后走 `actual == [..]` 恒为假，条件永不命中（静默失效）。
    """
    if actual is None:
        return False
    if cond.equals is not None:
        return actual == cond.equals
    return actual in (cond.in_list or [])


def exempted_items(
    clause: Clause, profile_attrs: dict[str, Any]
) -> dict[str, str]:
    """返回 {item_ref: 豁免理由}——该 clause 中被豁免的叶及其理由。

    profile_attrs 是主体侧事实字段的扁平字典（如 {"company_stage": "rd_stage"}），
    由调用方从 ApplicantProfile 投影而来（避免本模块依赖 fixtures 层）。
    """
    out: dict[str, str] = {}
    for ex in clause.exemptions:
        actual = profile_attrs.get(ex.when.profile_field)
        if not _condition_matches(ex.when, actual):
            continue
        reason = (
            f"法定豁免（{ex.when.profile_field}={actual}）："
            f"{ex.note or '本主体不适用该项'}"
        )
        for item_ref in ex.excludes:
            out.setdefault(item_ref, reason)
    return out


def profile_exemption_attrs(profile: Any) -> dict[str, Any]:
    """ApplicantProfile → 豁免谓词用的扁平属性字典。

    只取**豁免相关**的字段（company_stage / redchip_status）——其余 profile 字段
    与豁免无关，不进谓词空间（免得谓词名写错时静默不命中而无从察觉）。
    """
    return {
        "company_stage": getattr(profile, "company_stage", None),
        "redchip_status": getattr(profile, "redchip_status", None),
    }


__all__ = ["exempted_items", "profile_exemption_attrs"]
