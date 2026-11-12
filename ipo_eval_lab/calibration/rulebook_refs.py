"""
规则库白名单引用（L0-2 / 0-4 / 0-5 / 0-7 的判据来源）

只读，不改规则库：校准管线以 rulebook/metrics.yaml + items.yaml + _meta.yaml 为白名单。
"""

from pathlib import Path
from typing import Any
import yaml

# metric.unit → 允许的 threshold.format（与 rulebook/models.py UNIT_TO_FORMAT 同源）
UNIT_TO_FORMAT = {
    "yuan": "number",
    "percent": "percent",
    "count": "integer",
    "year": "integer",
    "boolean": "boolean",
}

VALID_WINDOW_KINDS = {"nth_year", "last_n_years", "latest"}
VALID_QUANTIFIERS = {"latest", "all_periods", "sum", "avg", "cagr", "ratio"}


def load_yaml_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return data if isinstance(data, list) else []


def load_metrics(rulebook_dir: Path) -> dict[str, dict]:
    return {m["metric_id"]: m for m in load_yaml_list(rulebook_dir / "metrics.yaml")}


def load_items(rulebook_dir: Path) -> dict[str, dict]:
    return {i["item_id"]: i for i in load_yaml_list(rulebook_dir / "items.yaml")}


def load_meta(rulebook_dir: Path) -> dict:
    path = rulebook_dir / "_meta.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def declared_no_sets(rulebook_dir: Path) -> list[list[str]]:
    return load_meta(rulebook_dir).get("declared_no_sets", []) or []


def board_company_types(rulebook_dir: Path) -> tuple[list[str], list[str]]:
    meta = load_meta(rulebook_dir)
    return meta.get("boards", []) or [], meta.get("company_types", []) or []


def item_window_token_ok(item: dict) -> tuple[bool, str]:
    """0-5：item 的 quantifier/window 必须是枚举 token（窗口由公式引擎单点实现）"""
    quantifier = item.get("quantifier")
    window = item.get("window")

    if quantifier is not None and quantifier not in VALID_QUANTIFIERS:
        return False, f"quantifier '{quantifier}' 非枚举值 {VALID_QUANTIFIERS}"

    if window is None:
        return True, ""

    if not isinstance(window, dict):
        return False, f"window 不是 token 结构：{window!r}"

    kind = window.get("kind")
    if kind not in VALID_WINDOW_KINDS:
        return False, f"window.kind '{kind}' 非枚举值 {VALID_WINDOW_KINDS}"

    n = window.get("n")
    if kind == "latest" and n is not None:
        return False, "window=latest 不得带 n"
    if kind in ("nth_year", "last_n_years") and not isinstance(n, int):
        return False, f"window.kind={kind} 需要整数 n"

    return True, ""


def item_required_format(item: dict, metrics: dict[str, dict]) -> str | None:
    """0-2：比率/增长率类量词（ratio / cagr）固定 percent；其余按 metric.unit 映射。

    cagr 挂的 metric 是金额（yuan），但阈值是增长率（30% → 0.3）——按 metric 单位
    走会误判成 number，故量词优先（batch2 校准勘误）。
    """
    if item.get("quantifier") in ("ratio", "cagr"):
        return "percent"
    metric_ref = item.get("metric_ref")
    metric = metrics.get(metric_ref) if metric_ref else None
    if not metric:
        return None
    return UNIT_TO_FORMAT.get(metric.get("unit", ""))


__all__ = [
    "load_metrics", "load_items", "load_meta", "declared_no_sets",
    "board_company_types", "item_window_token_ok", "item_required_format",
    "UNIT_TO_FORMAT", "VALID_WINDOW_KINDS", "VALID_QUANTIFIERS",
]
