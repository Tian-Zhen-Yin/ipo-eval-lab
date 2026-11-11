"""T2：Fetch 节点（facts 构建：六驱动 + 七指标，两维 measures）。

对应票 .scratch/m4-engine/issues/02；对拍设计 0006 §5 定稿数值表。
"""
import json
import math
from pathlib import Path

import pytest

from ipo_eval_lab.engine import EngineError, run_eval
from ipo_eval_lab.engine.fetch import build_facts, roe_year
from ipo_eval_lab.fixtures import CompanyProfile, load_company, load_profile, load_sanity
from ipo_eval_lab.rulebook.loader import load_rulebook
from ipo_eval_lab.rulebook.models import Metric

REPO = Path(__file__).resolve().parents[1]
RB_DIR = REPO / "rulebook"
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"

@pytest.fixture(scope="module")
def facts():
    sanity = load_sanity(FX / "sanity.yaml")
    rb = load_rulebook(RB_DIR).rulebook
    profile = load_company(BASE, sanity).profile
    return build_facts(rb, profile)


# ── 驱动层：原始字段直录 ──


def test_drivers_raw_fields(facts):
    d = {k: {y: e["value"] for y, e in series.items()} for k, series in facts["drivers"].items()}
    assert d["operating_revenues"] == {2022: 420_000_000, 2023: 500_000_000, 2024: 680_000_000}
    assert d["net_profit_as_reported"] == {2022: 150_000_000, 2023: 30_000_000, 2024: 40_000_000}
    assert d["net_profit_excl_nonrecurring"] == {2022: 144_000_000, 2023: 30_000_000, 2024: 40_000_000}
    assert d["net_cash_flow_from_oper"] == {2022: 50_000_000, 2023: 60_000_000, 2024: 70_000_000}
    assert d["total_equity_attrib_to_parent"] == {2022: 934_000_000, 2023: 962_000_000, 2024: 1_000_000_000}
    assert d["rd_expensed"] == {2022: 16_000_000, 2023: 18_000_000, 2024: 25_000_000}
    assert d["rd_capitalized"] == {2022: 3_000_000, 2023: 3_000_000, 2024: 5_000_000}


def test_drivers_have_refs(facts):
    for series in facts["drivers"].values():
        for entry in series.values():
            assert entry["refs"]  # 票面：每个数字带 refs（drivers 不豁免）


# ── 指标层：七指标就位，定稿表对拍 ──


def _values(node):
    """指标节点 → {年: value}（简单指标带 series 键；净利三口径直接是年映射）。"""
    node = node.get("series", node)
    return {y: e["value"] for y, e in node.items()}


def _year_keys(node):
    keys = set()
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(k, int):
                keys.add(k)
            keys |= _year_keys(v)
    return keys


def test_metrics_seven_present(facts):
    assert set(facts["metrics"]) == {
        "operating_revenues",
        "net_profit_attrib_parent",
        "net_cash_flow_from_oper",
        "total_equity_attr_to_parent",
        "rd_investment_total",
        "roe_weighted_avg",
        "mktcap",
    }


def test_net_profit_two_measures_and_lower_of_both(facts):
    m = facts["metrics"]["net_profit_attrib_parent"]
    assert _values(m["as_reported"]) == {2022: 150_000_000, 2023: 30_000_000, 2024: 40_000_000}
    assert _values(m["excl_nonrecurring"]) == {2022: 144_000_000, 2023: 30_000_000, 2024: 40_000_000}
    # 逐年孰低：min(申报, 扣非) 逐年进行；累计孰低 2.14 亿（申报口径累计 2.2 亿）
    lower = _values(m["lower_of_both"])
    assert lower == {2022: 144_000_000, 2023: 30_000_000, 2024: 40_000_000}
    assert sum(lower.values()) == 214_000_000
    assert sum(_values(m["as_reported"]).values()) == 220_000_000


def test_flow_metric_sums(facts):
    assert sum(_values(facts["metrics"]["net_cash_flow_from_oper"]).values()) == 180_000_000  # OCF 累计 1.8 亿
    assert sum(_values(facts["metrics"]["operating_revenues"]).values()) == 1_600_000_000  # 营收累计 16 亿


def test_rd_total_two_sources(facts):
    assert _values(facts["metrics"]["rd_investment_total"]) == {
        2022: 19_000_000,
        2023: 21_000_000,
        2024: 30_000_000,
    }


# ── ROE 加权派生（编报规则 9 号简化：事件无日期信息取年中中性假设）──


def test_roe_hand_computed(facts):
    """分子 = 逐年孰低；分母 = E0 + 申报NP/2 + 增资/2 − 分红/2（申报 NP 与 equity_roll 勾稽③同源）。

    2022: 14400 / (79400 + 7500 − 500) = 14400/86400 万
    2023:  3000 / (93400 + 1500 − 100) =  3000/94800 万
    2024:  4000 / (96200 + 2000 − 100) =  4000/98100 万
    """
    roe = _values(facts["metrics"]["roe_weighted_avg"])
    assert math.isclose(roe[2022], 144_000_000 / 864_000_000, rel_tol=1e-9)
    assert math.isclose(roe[2023], 30_000_000 / 948_000_000, rel_tol=1e-9)
    assert math.isclose(roe[2024], 40_000_000 / 981_000_000, rel_tol=1e-9)


def test_roe_denominator_guard():
    """分母 ≤ 0 → 缺值，不硬算（负净资产年份不许出 ROE）。"""
    assert roe_year(opening=100, np_reported=20, np_lower=20, dividends=250, capital_injection=0) is None


# ── 缺数据语义：是「没有」，不是 0 ──


def _mutated_profile(mutate):
    data = load_profile(BASE / "profile.json").model_dump(mode="json")
    mutate(data)
    return CompanyProfile.model_validate(data)


def test_excl_null_year_lower_of_both_missing():
    """扣非 null → 该年孰低缺值，不用申报值顶替（E3）。"""

    def m(d):
        d["statements"][1]["income"]["net_profit_attrib_parent"]["excl_nonrecurring"] = None

    profile = _mutated_profile(m)
    rb = load_rulebook(RB_DIR).rulebook
    node = build_facts(rb, profile)["metrics"]["net_profit_attrib_parent"]["lower_of_both"]
    assert node[2023]["value"] is None
    assert "扣非" in node[2023]["reason"]
    assert node[2022]["value"] == 144_000_000  # 其余年不受传染（叶级隔离的前置）


def test_rd_missing_source_year():
    def m(d):
        d["statements"][1]["income"]["rd_capitalized"] = None

    profile = _mutated_profile(m)
    rb = load_rulebook(RB_DIR).rulebook
    node = build_facts(rb, profile)["metrics"]["rd_investment_total"]["series"]
    assert node[2023]["value"] is None
    assert node[2024]["value"] == 30_000_000


def test_mktcap_missing_not_zero(facts):
    m = facts["metrics"]["mktcap"]
    assert m["value"] is None  # G-C 落点：企业自估缺数据 → 缺值
    assert "documentary.mktcap_self_estimate" in m["refs"][0]


# ── 不变量 5 打底：每个数字带 refs ──


def test_every_number_has_refs(facts):
    def walk(node):
        if isinstance(node, dict):
            if "value" in node:
                assert node.get("refs"), f"数字无 refs：{node}"
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(facts["metrics"])


def test_facts_json_serializable(facts):
    """票面：facts 可 dump 成 JSON 检视（可序列化是底座；CLI dump 面随票 08 result.json）。"""
    json.dumps(facts, ensure_ascii=False)


def test_stub_non_null_echoed_not_in_series():
    """stub 非空场景：进 facts 展示位，序列仍只含报表年（E2-2）。"""

    def m(d):
        d["stub_period"] = {"fiscal_year": 2025, "note": "申报期一期（展示用）"}

    profile = _mutated_profile(m)
    rb = load_rulebook(RB_DIR).rulebook
    facts = build_facts(rb, profile)
    assert facts["stub"]["fiscal_year"] == 2025
    for metric in facts["metrics"].values():
        years = _year_keys(metric)
        assert not years or max(years) <= 2024


def test_stub_echoed_only(facts):
    """stub 只进 facts 展示位，永不进序列（E2-2）。"""
    assert facts["stub"] is None
    for metric in facts["metrics"].values():
        years = _year_keys(metric)
        assert not years or max(years) <= 2024  # 序列只含报表年；stub 年永不进（mktcap 单值无年键；首版踩坑：浮点小数位含"2025"的假阳性）


def test_unknown_metric_fails_loud():
    rb = load_rulebook(RB_DIR).rulebook
    rb.metrics.append(Metric(metric_id="fake_metric", display="假指标", unit="yuan", kind="flow"))
    profile = load_profile(BASE / "profile.json")
    with pytest.raises(EngineError, match="fake_metric"):
        build_facts(rb, profile)


# ── 链路集成：run_eval 之后 facts 已就位 ──


def test_fetch_integrated_into_chain():
    ctx = run_eval(company_dir=BASE, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")
    assert set(ctx.facts["metrics"]) == {m.metric_id for m in ctx.inputs["rulebook"].metrics}
    assert ctx.facts["drivers"]["operating_revenues"][2024]["value"] == 680_000_000
