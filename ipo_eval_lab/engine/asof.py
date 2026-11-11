"""as_of 生效过滤（设计 0003-R6 版本链；关闭 CONTEXT #9-V6）。

规则库包（M2，c68d02e 冻结）不改——本模块是 effective_from 参与过滤的**单点**：
全量加载 + lint 照旧（先验完整性，再裁运行时视图），引擎按 as_of 取生效 group。
闭区间：effective_from ≤ as_of 即生效（生效日当天可用）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ipo_eval_lab.rulebook.models import Group


@dataclass(frozen=True)
class AsOfFilter:
    effective: list[Group]
    excluded: list[dict[str, Any]] = field(default_factory=list)


def parse_as_of(value: str | date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as e:
        raise ValueError(f"as_of 非法日期：{value!r}（YYYY-MM-DD）") from e


def filter_by_as_of(groups: list[Group], as_of: str | date) -> AsOfFilter:
    """按生效区间裁剪套清单；未生效套带原因保留（历史结果按当次规则版本冻结展示）。"""
    cutoff = parse_as_of(as_of)
    effective: list[Group] = []
    excluded: list[dict[str, Any]] = []
    for g in groups:
        if g.effective_from <= cutoff:
            effective.append(g)
        else:
            excluded.append(
                {
                    "group_id": g.group_id,
                    "display": g.display,
                    "effective_from": g.effective_from.isoformat(),
                    "reason": f"effective_from {g.effective_from.isoformat()} 晚于 as_of {cutoff.isoformat()}（修订未生效）",
                }
            )
    return AsOfFilter(effective=effective, excluded=excluded)
