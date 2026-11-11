"""层①情景推演（设计 0005 §6；票 06）。

window_roll：确定性、零假设重算。窗口滚动一年（FY_end+1 进入、FY_end−n+1 滑出），
按 quantifier 给「进入年所需值」：
  sum        : thr − Σ(窗口剩余年，即滑出最老一年后的合计)
               np_3y_sum：2.0 亿 − (0.3+0.4) 亿 = 1.3 亿
  avg        : n×thr − Σ(剩余年)，n = 窗口年数（新窗口重算均值）
  latest     : thr（进入年即新最近年，直接换年）
  all_periods: thr（进入年须逐期满足 op；GT 0 → 进入年需为正）
  cagr       : 首年′ × (1+thr)^(n−1)（首年′ = 滚动后新窗口首年 = 原第 2 年）
  ratio      : 不适用（分子分母各自变化，无单值滚动语义），跳过

注：设计 0005 §6 表仅列 sum/all_periods/cagr，判 latest/avg 不适用；
本票（06）显式要求四种量词各有公式，此处遵从票清单实现（latest/avg 补充）。

滚动风险分档（k 入规则库配置，缺省 2）：
  required > 最近年实际 × k → high；required > 最近年实际 → medium；否则 low。
情景噪声控制：仅对 not_met 叶，或「已 met 但滚动风险非 low」（余量在滚动口径下变薄）的
叶输出情景；已 met 且风险 low 的叶（如均为正叶）不出——避免给几乎无风险的叶编情景。

growth：v1 两点情景 r ∈ {0（零增长）, historical_cagr}，输出 years_low / years_high、
r_low / r_high；一律 is_forecast: true（绝不写成预测结论）。零编造：r 只取这两个值，
不出现 1.5×cagr 之类系数；CAGR 无定义（窗口 < 2 年 / 首年 ≤ 0）则不出该叶情景。
"""

from __future__ import annotations

from ipo_eval_lab.rulebook.models import Group

from .calc import cagr, resolve_window

_K_DEFAULT = 2.0
_LOW = "low"
_MEDIUM = "medium"
_HIGH = "high"


def _k(rulebook) -> float:
    """滚动风险倍数 k：规则库配置优先（_meta.yaml conventions.risk_k），缺省 2（设计 0005 §6）。"""
    meta = getattr(rulebook, "meta", None)
    for holder in (getattr(meta, "conventions", None), meta):
        if holder is None:
            continue
        raw = holder.get("risk_k") if isinstance(holder, dict) else getattr(holder, "risk_k", None)
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                break
    return _K_DEFAULT


def risk_tier(required: float, recent: float, k: float) -> str:
    """风险三档：超过最近年实际 ×k → high；仅超过最近年实际 → medium；否则 low。"""
    if required > recent * k:
        return _HIGH
    if required > recent:
        return _MEDIUM
    return _LOW


def _decision_series(metric_node: dict, metric) -> dict | None:
    """按 decision_measure 取判定用序列；documentary 单值无序列 → None。"""
    if metric.decision_measure == "lower_of_both":
        return metric_node.get("lower_of_both")
    if "series" in metric_node:
        return metric_node["series"]
    return None


def _series_values(series_node: dict, periods: list[int]) -> list[float] | None:
    """窗口内各年实测值；任一年缺 → None（与 Calc 同为无静默回退）。"""
    vals = []
    for y in periods:
        entry = series_node.get(y)
        if entry is None or entry.get("value") is None:
            return None
        vals.append(entry["value"])
    return vals


def _num(x) -> str:
    """整数不带小数点、浮点保留两位；均加千分位分隔（仅供人类阅读的 note）。"""
    x = round(x, 2)
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return f"{x:,}" if isinstance(x, int) else f"{x:,.2f}"


def required_entering_year(quantifier: str, vals: list[float], thr: float, op: str) -> float | None:
    """
    窗口滚动一年后的进入年所需值（确定性、零假设）。

    quantifier ∈ {sum, avg, latest, all_periods, cagr}；ratio/未知 → None。
    vals 为窗口内按年份升序的实测值；remaining = vals[1:]（最老一年滑出后剩余）。
    """
    if quantifier == "sum":
        return thr - sum(vals[1:])
    if quantifier == "avg":
        return len(vals) * thr - sum(vals[1:])
    if quantifier == "latest":
        return thr
    if quantifier == "all_periods":
        # 进入年须逐期满足 op；GT 0 → 进入年需为正
        return thr
    if quantifier == "cagr":
        if len(vals) < 2:
            return None
        return vals[1] * (1 + thr) ** (len(vals) - 1)
    return None


def _window_roll_note(quantifier: str, periods: list[int], vals: list[float],
                      thr: float, required: float, op: str) -> str:
    slide = periods[0]
    if quantifier == "sum":
        return (f"窗口滚动：{slide} 年滑出，进入年需 ≥ 阈值 {_num(thr)} − "
                f"剩余年合计 {_num(sum(vals[1:]))} = {_num(required)}")
    if quantifier == "avg":
        return (f"窗口滚动：{slide} 年滑出，新 {len(vals)} 年均值 ≥ {_num(thr)} → "
                f"进入年需 ≥ {_num(required)}")
    if quantifier == "latest":
        return f"窗口滚动：进入年即新最近年，需满足 {op} {_num(thr)}（进入年需 ≥ {_num(required)}）"
    if quantifier == "all_periods":
        return f"窗口滚动：进入年须逐期满足 {op} {_num(thr)}（GT 0 → 进入年需为正）"
    if quantifier == "cagr":
        return (f"窗口滚动：首年′ {_num(vals[1])} × (1+{_num(thr)})^{len(vals)-1} → "
                f"进入年需 ≥ {_num(required)}")
    return f"{quantifier} 窗口 {periods}：进入年需 ≥ {_num(required)}"


def growth_points(vals: list[float]) -> dict | None:
    """
    两点增长率情景的纯计算：r ∈ {0, historical_cagr}。

    CAGR 无定义（窗口 < 2 年 / 首年 ≤ 0）→ None（不编数，ADR-0004 残点关闭）。
    返回字典含 r_low/r_high/years_low/years_high/hist_cagr/is_forecast/basis。
    """
    if len(vals) < 2:
        return None
    g = cagr(vals)
    if g is None:
        return None  # 首年 ≤ 0 或末年 < 0，CAGR 无定义，不编数
    latest = vals[-1]
    return {
        "r_low": 0.0,
        "r_high": round(g, 6),
        "years_low": round(latest * (1 + 0.0), 6),
        "years_high": round(latest * (1 + g), 6),
        "hist_cagr": round(g, 6),
        "is_forecast": True,
        "basis": "historical_cagr",
    }


def compute_scenario(rulebook, groups: list[Group], facts: dict) -> dict:
    """
    返回 {window_roll: list[dict], growth: list[dict]}。

    window_roll 条目键：
      leaf_id, item_ref, quantifier,
      required_entering_year_value, recent_actual, k, risk, note
    growth 条目键：
      leaf_id, item_ref,
      r_low, r_high, years_low, years_high, hist_cagr,
      is_forecast, basis, note

    仅对 state ∈ {met, not_met} 的叶且满足：
      - not_met 叶始终输出
      - met 叶仅当滚动风险 != low（即 required > 最近年实际）输出
    跳过 ratio、documentary、indeterminate/needs_review 叶。
    """
    items_by_id = {i.item_id: i for i in rulebook.items}
    metrics_by_id = {m.metric_id: m for m in rulebook.metrics}
    metric_nodes = facts.get("metrics", {})
    fiscal_years = sorted(facts["audit"].keys())
    k = _k(rulebook)
    allowed = {g.group_id for g in groups} if groups else None

    window_roll = []
    growth = []

    for c in facts.get("checks", []):
        if allowed is not None and c.get("group_id") not in allowed:
            continue
        # 未定义叶（indeterminate/needs_review）无确定实测，不出情景
        if c["state"] not in ("met", "not_met"):
            continue

        item = items_by_id.get(c["item_ref"])
        if item is None or item.quantifier is None or item.window is None:
            continue
        metric = metrics_by_id.get(item.metric_ref) if item.metric_ref else None
        if metric is None:
            continue

        series = _decision_series(metric_nodes.get(metric.metric_id, {}), metric)
        if series is None:
            continue

        periods, _ = resolve_window(item.window, fiscal_years)
        if periods is None:
            continue

        vals = _series_values(series, periods)
        if vals is None:
            continue

        thr = c["threshold"]["value"]
        op = c["op"]
        quantifier = item.quantifier.value
        required = required_entering_year(quantifier, vals, thr, op)
        recent = vals[-1]

        # 情景噪声控制：not_met 始终出；met 仅当滚动风险非 low（required > recent）
        emit = c["state"] == "not_met"
        if required is not None:
            risk = risk_tier(required, recent, k)
            if risk != _LOW:
                emit = True
        if not emit:
            continue

        if required is not None:
            window_roll.append({
                "leaf_id": c["leaf_id"],
                "item_ref": item.item_id,
                "quantifier": quantifier,
                "required_entering_year_value": round(required, 6),
                "recent_actual": recent,
                "k": k,
                "risk": risk,
                "note": _window_roll_note(quantifier, periods, vals, thr, required, op),
            })

        # growth 两点情景（同噪声门：not_met 或 met+风险非 low）
        gp = growth_points(vals)
        if gp is not None:
            growth.append({
                "leaf_id": c["leaf_id"],
                "item_ref": item.item_id,
                **gp,
                "note": "两点情景 r ∈ {0, historical_cagr}；一律 is_forecast；零来源不编数（ADR-0004 残点关闭）",
            })

    return {"window_roll": window_roll, "growth": growth}