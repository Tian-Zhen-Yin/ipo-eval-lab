"""规则库加载器（设计 0002 §4；R6：加载期断言，坏配置起不来）。

用法：
    from ipo_eval_lab.rulebook import load_rulebook
    result = load_rulebook("rulebook")            # 样板模式：全局覆盖缺口 → 警告
    result = load_rulebook("rulebook", strict_global=True)  # 全量模式：缺口 → 报错
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import Rulebook

# L5：期间码（YYYY-12）只允许出现在 legal/ 的法条原文里，规则结构中一律用 window token
PERIOD_CODE_RE = re.compile(r"\d{4}-12")

_STRUCTURAL_SUBDIRS = ("sets", "issuance", "positioning")


class RulebookLintError(Exception):
    def __init__(self, messages: list[str]) -> None:
        self.messages = list(messages)
        super().__init__("\n".join(messages))


@dataclass
class LoadResult:
    rulebook: Rulebook
    warnings: list[str] = field(default_factory=list)


def _read_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_rulebook(root: Path | str, strict_global: bool = False) -> LoadResult:
    root = Path(root)
    warnings: list[str] = []

    meta = _read_yaml(root / "_meta.yaml")
    metrics = _read_yaml(root / "metrics.yaml")
    items = _read_yaml(root / "items.yaml")

    laws: list[Any] = []
    for f in sorted((root / "legal").glob("*.yaml")):
        laws.extend(_read_yaml(f))

    groups: list[Any] = []
    scan_targets: list[Path] = [root / "_meta.yaml", root / "metrics.yaml", root / "items.yaml"]
    for sub in _STRUCTURAL_SUBDIRS:
        d = root / sub
        if d.is_dir():
            files = sorted(d.glob("*.yaml"))
            for f in files:
                groups.extend(_read_yaml(f))
            scan_targets.extend(files)

    # 模型断言：L1 / L3 / L4 / L6（结构性 lint，错误直接抛 ValidationError）
    rb = Rulebook(meta=meta, metrics=metrics, items=items, laws=laws, groups=groups)

    # L5：非 legal 文件的原始文本中不允许出现手写期间码
    l5: list[str] = []
    for f in scan_targets:
        if PERIOD_CODE_RE.search(f.read_text(encoding="utf-8")):
            l5.append(f"L5 手写期间码（YYYY-12）出现在 {f.name}——窗口只允许 token（设计 0002 §3）")
    if l5:
        raise RulebookLintError(l5)

    # L2：组合覆盖（全局检查；样板期=警告，strict_global=报错）
    covered = {(b, g.company_type) for g in rb.groups for b in g.boards}
    declared = {(pair[0], pair[1]) for pair in rb.meta.declared_no_sets}
    missing = sorted(
        {(b, t) for b in rb.meta.boards for t in rb.meta.company_types} - covered - declared
    )
    if missing:
        msg = (
            "L2 组合覆盖缺口（尚无 group 且未声明 declared_no_sets）："
            + "，".join(f"{b}×{t}" for b, t in missing)
        )
        if strict_global:
            raise RulebookLintError([msg])
        warnings.append(msg)

    return LoadResult(rb, warnings)
