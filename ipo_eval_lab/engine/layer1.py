"""层①情景推演（设计 0005 §6；票 06）。

window_roll：确定性、零假设。窗口滚动一年（FY_end+1 进入、FY_end−n+1 滑出），按 quantifier
给进入年所需值：
  sum   : thr − Σ(窗口剩余年)            甲公司 np_3y_sum: 2.0 − (0.3+0.4) = 1.3 亿
  all_periods: 满足 op 所需（GT 0 → 进入年需为正）
  cagr  : 首年′ × (1+thr)^(n−1)，首年′ = 滚动后新窗口首年值
  latest/avg/ratio: 不适用，跳过
滚动风险：required > 最近年实际 × k → high；k 入规则库配置（_meta.yaml），缺省 2。
growth：v1 两点情景 r ∈ {0（零增长）, historical_cagr}，输出 years_low / years_high；一律 is_forecast；
零来源不编数（仅历史_cagr，ADR-0004 残点就此关闭）。
"""
from __future__ import annotations

from ipo_eval_lab.rulebook.models import Group

_K_DEFAULT = 2.0


def _k(rulebook) -> float:
    try:
        return float(rulebook.meta.conventions.get("risk_k", _K_DEFAULT))  # type: ignore[attr-defined]
    except Exception:
        return _K_DEFAULT


def _decision_series(metric_node: dict, metric) -> dict | None:
    """按 decision_measure 取判定用序列；documentary 单值无序列 → None。"""
    if metric.decision_measure == "lower_of_both":
        return metric_node.get("lower_of_both")
    if "series" in metric_node:
        return metric_node["series"]
    return None


def _series_values(series_node: dict, periods: list[int]) -> list[float] | None:
    """窗口内各年实测值；任一年缺 → None。"""
    vals: list[float] = []
    for y in periods:
        entry = series_node.get(y)
        if entry is None or entry.get("value") is None:
            return None
        vals.append(entry["value"])
    return vals


def _resolve_periods(window, fiscal_years: list[int]) -> list[int] | None:
    fy_end = fiscal_years[-1]
    if window.kind == "latest":
        want = [fy_end]
    elif window.kind == "last_n_years":
        want = list(range(fy_end - window.n + 1, fy_end + 1))
    elif window.kind == "nth_year":
        want = [fy_end - window.n + 1]
    else:
        return None
    have = set(fiscal_years)
    return want if want and all(y in have for y in want) else None


def compute_scenario(rulebook, groups: list[Group], facts: dict) -> dict:
    """返回 {window_roll: {leaf_id: {...}}, growth: {leaf_id: {...}}}。"""
    items_by_id = {i.item_id: i for i in rulebook.items}
    metrics_by_id = {m.metric_id: m for m in rulebook.metrics}
    metric_nodes = facts["metrics"]
    fiscal_years = sorted(facts["audit"].keys())
    fy_end = fiscal_years[-1]
    k = _k(rulebook)

    window_roll: dict[str, dict] = {}
    growth: dict[str, dict] = {}

    checks = facts.get("checks", [])
    for c in checks:
        if c["state"] not in ("met", "not_met"):
            continue  # 无确定实测，不出情景
        item = items_by_id.get(c["item_ref"])
        if item is None or item.quantifier is None or item.window is None:
            continue
        quantifier = item.quantifier
        if quantifier in ("latest", "avg", "ratio"):
            continue
        metric = metrics_by_id.get(item.metric_ref)
        if metric is None:
            continue
        series_node = _decision_series(metric_nodes.get(metric.metric_id, {}), metric)
        if series_node is None:
            continue
        periods = _resolve_periods(item.window, fiscal_years)
        if periods is None:
            continue
        vals = _series_values(series_node, periods)
        if vals is None:
            continue
        thr = c["threshold"]["value"]
        op = c["op"]

        if quantifier == "sum":
            remaining = vals[:-1]  # 窗口中除 FY_end 之外的年
            required = thr - sum(remaining)
            recent = vals[-1]
        elif quantifier == "all_periods":
            required = 0.0 if op == "gt" else None  # GT 0 → 进入年需为正
            recent = vals[-1]
        elif quantifier == "cagr":
            n = len(vals)
            if n < 2:
                continue
            first_next = vals[1]  # 滚动后新窗口首年 = 原第2年
            required = first_next * (1 + thr) ** (n - 1)
            recent = vals[-1]
        else:
            continue

        if required is None:
            continue
        risk = "high" if required > recent * k else "low"
        window_roll[c["leaf_id"]] = {
            "quantifier": quantifier,
            "required_entering_year_value": round(required, 6),
            "recent_actual": recent,
            "k": k,
            "risk": risk,
            "note": f"{quantifier} 窗口 {periods}，进入年需 {required:g}",
        }

    # growth：两点情景 r ∈ {0, hist_cagr}，一律 is_forecast；hist_cagr 取该叶指标的窗口 CAGR
    for c in checks:
        if c["state"] not in ("met", "not_met"):
            continue
        item = items_by_id.get(c["item_ref"])
        if item is None or item.quantifier not in ("sum", "latest", "cagr") or item.window is None:
            continue
        metric = metrics_by_id.get(item.metric_ref)
        if metric is None:
            continue
        series_node = _decision_series(metric_nodes.get(metric.metric_id, {}), metric)
        if series_node is None:
            continue
        periods = _resolve_periods(item.window, fiscal_years)
        if periods is None or len(periods) < 2:
            continue
        vals = _series_values(series_node, periods)
        if vals is None or vals[0] <= 0:
            continue  # CAGR 无定义
        hist_cagr = (vals[-1] / vals[0]) ** (1 / (len(vals) - 1)) - 1
        latest = vals[-1]
        growth[c["leaf_id"]] = {
            "years_low": round(latest * (1 + 0.0), 6),      # r = 0
            "years_high": round(latest * (1 + hist_cagr), 6),  # r = hist_cagr
            "hist_cagr": round(hist_cagr, 6),
            "is_forecast": True,
            "note": "两点情景 r ∈ {0, historical_cagr}；零来源不编数",
        }

    return {"window_roll": window_roll, "growth": growth}
