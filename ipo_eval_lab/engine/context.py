"""责任链共享 Context（设计 0005 §1；D5 复用 midas 链模式）。

约定：Context append-only——节点只**新增**自己的段，不改写别人的段；
facts 在 Fold 出口冻结（AR5，断言随 T4 落地）。
契约 v0.2 的四段（run / facts / layers / narrative_handoff）由 T8 从本结构汇编。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ipo_eval_lab.rulebook.models import Group


@dataclass(frozen=True)
class RunTarget:
    """目标范围（设计 0001 §1.1）：缺省 None = 全部适用套。CLI 一次构造，引擎各处免再规整。"""

    boards: list[str] | None = None
    sets: list[str] | None = None


@dataclass
class Selection:
    """Init 产出的套选择结果（内部结构；契约组装在 T8）。"""

    applicable: list[Group] = field(default_factory=list)
    not_applicable: list[dict[str, Any]] = field(default_factory=list)
    excluded_by_asof: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunContext:
    run: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    layers: dict[str, Any] = field(default_factory=dict)
    selection: Selection = field(default_factory=Selection)
