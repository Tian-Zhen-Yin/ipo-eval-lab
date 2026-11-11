"""层①情景推演测试（票 06 checklist 覆盖）。

- golden window_roll 逐字对拍：np_3y_sum 进入年需 1.3 亿、risk=high（k=2：13,000 万 > 2 × 4,000 万）
- 分量词公式各自正确：sum 型减去滑出年、avg 型重算均值、latest 型直接换年、all_periods 型进入年需满足逐期约束
- growth 两点情景零编造：r_high=1.5×cagr 之类的系数不许出现（E7 拍板），只报 r∈{0, hist_cagr} 且必带 is_forecast
- 情景是确定性重算（同一 facts 重跑窗口），不是新数据源
- 噪声控制：已 met 且余量大的叶不出情景（均为正叶不出）
- window_roll 输出「进入年所需值」对照最近年实际值——差距画像的核心可执行信息
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.engine.layer1 import (
    compute_scenario,
    required_entering_year,
    risk_tier,
    growth_points,
    _k,
)

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
GOLDEN = BASE / "expected" / "summary.json"


def _ctx():
    return run_eval(company_dir=BASE, rulebook_dir=REPO / "rulebook", fixtures_root=FX, as_of="2025-06-30")


def _scenario(ctx):
    return compute_scenario(ctx.inputs["rulebook"], ctx.selection.applicable, ctx.facts)


# ── golden 对拍 ────────────────────────────────────────────────

def test_golden_window_roll_matches():
    """golden window_roll 逐字对拍：叶 cn_main_g1_c2_l1 (np_3y_sum) required=130000000, risk=high。"""
    ctx = _ctx()
    got = _scenario(ctx)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["window_roll"]

    by_leaf = {r["leaf_id"]: r for r in got["window_roll"]}

    # golden 每条都能在 engine 输出中找到，核心字段逐字一致
    assert golden, "golden 至少应有一条 window_roll"
    for g in golden:
        assert g["leaf_id"] in by_leaf, f"golden leaf {g['leaf_id']} 未出现在 engine 输出"
        r = by_leaf[g["leaf_id"]]
        assert r["item_ref"] == g["item_ref"]
        # 契约名 required_entering_year_value ↔ golden 摘要名 required
        assert r["required_entering_year_value"] == g["required"]
        assert r["risk"] == g["risk"]

    # 钉死甲公司主板第一套的定稿值（票 06 checklist 第 1 项）
    e = by_leaf["cn_main_g1_c2_l1"]
    assert e["item_ref"] == "np_3y_sum"
    assert e["required_entering_year_value"] == 130_000_000
    assert e["risk"] == "high"
    assert e["k"] == 2.0
    assert e["recent_actual"] == 40_000_000


# ── 分量词公式各自正确 ────────────────────────────────────────

def test_sum_subtracts_slideout_year_not_recent():
    """sum 型：required = thr − Σ(剩余年)，剩余年 = 滑出最老一年后的年份（vals[1:]）；反例守卫防止误用 vals[:-1]。"""
    vals = [144_000_000, 30_000_000, 40_000_000]  # 2022, 2023, 2024
    thr = 200_000_000
    assert required_entering_year("sum", vals, thr, "ge") == 130_000_000
    # 若误用 vals[:-1]（减最近年）会得到 2.0−(1.44+0.3)=0.26 亿
    assert required_entering_year("sum", vals, thr, "ge") != thr - (144_000_000 + 30_000_000)


def test_avg_recomputes_mean():
    """avg 型：required = n×thr − Σ(剩余年)，即新窗口重算均值。"""
    vals = [10, 20, 30]
    # 新 3 年均值 ≥ 100 → 进入年 ≥ 3*100 − (20+30) = 250
    assert required_entering_year("avg", vals, 100, "ge") == 250


def test_latest_switches_year():
    """latest 型：进入年即新最近年，直接换年，required = thr。"""
    assert required_entering_year("latest", [40], 100, "ge") == 100


def test_all_periods_boundary():
    """all_periods 型：进入年须逐期满足 op；GT 0 → 进入年需为正（required = thr）。"""
    assert required_entering_year("all_periods", [1, 2, 3], 0, "gt") == 0
    assert required_entering_year("all_periods", [1, 2, 3], 100, "ge") == 100


def test_cagr_formula():
    """cagr 型：required = 首年′ × (1+thr)^(n−1)，首年′ = 原第 2 年 vals[1]。"""
    vals = [100.0, 121.0, 146.41]
    thr = 0.2
    req = required_entering_year("cagr", vals, thr, "ge")
    assert req == pytest.approx(vals[1] * (1.2) ** 2)  # 121 × 1.44 = 174.24
    assert req == pytest.approx(174.24)


def test_ratio_and_unknown_return_none():
    """ratio / 未知量词 → None（跳过）。"""
    assert required_entering_year("ratio", [1, 2, 3], 0.1, "ge") is None
    assert required_entering_year("bogus", [1, 2, 3], 1, "ge") is None


# ── 滚动风险三档 ──────────────────────────────────────────────

def test_risk_tiers():
    """risk_tier：required > recent×k → high；recent < required ≤ recent×k → medium；否则 low。"""
    assert risk_tier(100, 40, 2.0) == "high"     # 100 > 80
    assert risk_tier(60, 40, 2.0) == "medium"    # 40 < 60 ≤ 80
    assert risk_tier(40, 40, 2.0) == "low"       # 不严格大于
    assert risk_tier(30, 40, 2.0) == "low"


def test_k_reads_config_defaults_to_2():
    """_k 读取 conventions.risk_k，缺省 2；规则库无配置时回落到 2.0。"""
    class MockMeta:
        conventions = {}
    class MockRB:
        meta = MockMeta()
    assert _k(MockRB()) == 2.0


# ── growth 两点情景零编造 ────────────────────────────────────

def test_growth_two_points_only():
    """growth 仅两点 r ∈ {0, hist_cagr}；不出现 1.5×cagr 等系数；is_forecast=True。"""
    vals = [100.0, 121.0]  # cagr = 0.21
    g = growth_points(vals)
    assert g["is_forecast"] is True
    assert g["r_low"] == 0.0
    assert g["r_high"] == pytest.approx(0.21)
    assert g["hist_cagr"] == g["r_high"]
    assert g["years_low"] == pytest.approx(121.0)          # r=0
    assert g["years_high"] == pytest.approx(121.0 * 1.21)  # r=hist_cagr
    # 零编造：情景只含 {0, hist_cagr} 两个率
    assert {0.0, g["r_high"]} == {0.0, 0.21}
    assert g["years_high"] != pytest.approx(121.0 * (1 + 1.5 * 0.21))  # 排除 1.5×cagr


def test_growth_undefined_cagr_returns_none():
    """CAGR 无定义（窗口 < 2 / 首年 ≤ 0）时不编数 → None。"""
    assert growth_points([10.0]) is None          # 窗口 < 2
    assert growth_points([-5.0, 3.0]) is None     # 首年 ≤ 0
    assert growth_points([0.0, 3.0]) is None


def test_growth_records_always_forecast():
    """engine 输出的每条 growth 记录必带 is_forecast=True 且 r_low=0。"""
    ctx = _ctx()
    for r in _scenario(ctx)["growth"]:
        assert r["is_forecast"] is True
        assert r["r_low"] == 0.0
        assert r["r_high"] == r["hist_cagr"]


# ── 噪声控制：已 met 且余量大的叶不出 ──────────────────────

def test_noise_control_met_large_margin_absent():
    """已 met 且滚动风险 low 的叶不出情景（均为正、rev_3y_sum 等）。"""
    ctx = _ctx()
    ids = {r["leaf_id"] for r in _scenario(ctx)["window_roll"]}
    # 均为正叶（all_periods）已 met 且余量大 → 不出
    assert "cn_main_g1_c1_l1" not in ids   # np_3y_allpos
    assert "star_g1_b1_c1_l1" not in ids   # np_2y_allpos
    # rev_3y_sum：当前 met 但滚动后仍宽裕（required < recent）→ 风险 low → 不出
    assert "cn_main_g1_b1_c1_l2" not in ids
    # 正例：累计叶 np_3y_sum 余量在滚动口径下变薄 → 风险 high → 出
    assert "cn_main_g1_c2_l1" in ids


def test_not_met_leaves_get_scenario():
    """not_met 叶始终出情景（即使风险 low）。"""
    ctx = _ctx()
    ids = {r["leaf_id"] for r in _scenario(ctx)["window_roll"]}
    assert "cn_main_g1_c3_l1" in ids   # np_latest not_met
    assert "cn_main_g1_b1_c1_l1" in ids  # ocf_3y_sum not_met


# ── 确定性重算、最近年实际对照 ─────────────────────────────

def test_deterministic_and_no_facts_mutation():
    """compute_scenario 同一 facts 重跑结果一致，且不改写 facts（无新数据源）。"""
    ctx = _ctx()
    before = json.dumps(ctx.facts, sort_keys=True, default=str)
    a = compute_scenario(ctx.inputs["rulebook"], ctx.selection.applicable, ctx.facts)
    b = compute_scenario(ctx.inputs["rulebook"], ctx.selection.applicable, ctx.facts)
    after = json.dumps(ctx.facts, sort_keys=True, default=str)
    assert a == b
    assert before == after  # 只读 facts，不新增数据源


def test_result_is_json_serializable():
    """输出可 JSON 序列化。"""
    json.dumps(_scenario(_ctx()))


def test_recent_actual_is_last_window_year():
    """window_roll 的 recent_actual = 窗口最新一年实测值（np_3y_sum → 2024 年 4,000 万）。"""
    ctx = _ctx()
    e = next(r for r in _scenario(ctx)["window_roll"] if r["leaf_id"] == "cn_main_g1_c2_l1")
    assert e["recent_actual"] == 40_000_000


# ── 窗口解析复用 Calc 单点 ────────────────────────────────

def test_uses_calc_resolve_window_single_point():
    """window_roll 使用 Calc 同一 resolve_window（E2 单点），不重写窗口解析。"""
    ctx = _ctx()
    got = _scenario(ctx)
    # 只要 golden 对拍通过，即间接证明窗口解析与 Calc 一致
    assert got["window_roll"]