"""T7：层②帕累托路径 + 层③归因（设计 0005 §7；票 07）。

样板套对拍：甲公司 recommendation = 空、两套都进 excluded（not_met 硬叶 / indeterminate
数据缺口）；帕累托在全部适用套上算（互不支配，四轴保有区分度）；归因格位：
np_latest = verified × numeric_gap（实质差距）、mktcap_forecast = missing_data × none
（企业自估缺数据 → 可验证性降档）。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.engine.layer23 import compute_layers23

from fixture_rulebook import fixture_rulebook_dir

REPO = Path(__file__).resolve().parents[1]

# 夹具规则库根（正式库数据层＋样板套结构层）：见 tests/fixture_rulebook.py
@pytest.fixture(scope="module")
def rb_dir():
    with fixture_rulebook_dir() as d:
        yield d
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"

MAIN = "cn_main_general_g1"
STAR = "star_general_g1"


def _layers23_of(ctx):
    return compute_layers23(ctx.inputs["rulebook"], ctx.selection.applicable, ctx.facts)


def _excluded_by_gid(result):
    return {e["group_id"]: e for e in result["excluded"]}


# ── 样板套对拍（golden） ────────────────────────────────────────

def test_recommendation_empty_both_excluded(rb_dir):
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    assert r["recommendation"] == []  # 宁可说清差在哪，不硬推一个套
    assert r["alternatives"] == []
    ex = _excluded_by_gid(r)
    assert set(ex) == {MAIN, STAR}
    assert ex[MAIN]["reason"] == "hard_leaf_not_met"  # np_latest not_met 硬叶
    assert [h["item_ref"] for h in ex[MAIN]["hard_leaves"]] == ["np_latest"]
    assert ex[STAR]["reason"] == "indeterminate_data_gap"  # 企业自估缺数据 → 数据缺口


def test_pareto_frontier_covers_all_sets(rb_dir):
    """前沿算全部适用套（不只过闸套，E6）：两套互不支配——主板赢轴 1/2，科创板赢轴 4。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    assert sorted(r["pareto_frontier"]) == sorted([MAIN, STAR])
    assert sorted(r["hard_gate"]["passing"]) == [STAR]  # 科创板无 not_met 硬叶，过闸


def test_no_superlative_wording(rb_dir):
    """禁「最优」表述（E1~E4）：输出任何位置不出现该词、不合成单值排序。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    assert "最优" not in json.dumps(r, ensure_ascii=False)


# ── 层③归因格位 ────────────────────────────────────────────────

def test_np_latest_attribution_verified_numeric_gap(rb_dir):
    """净利差 60% 是实质差距不是数据问题：verified × numeric_gap。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    cells = {c["item_ref"]: c for c in r["attribution"]["cells"]}
    c = cells["np_latest"]
    assert (c["verifiability"], c["substantive_obstacle"]) == ("verified", "numeric_gap")
    assert "实质差距" in c["basis"]
    assert c["group_id"] == MAIN


def test_mktcap_attribution_missing_data(rb_dir):
    """企业自估缺数据 → 可验证性降档（documentary 缺源），与净利类区分开。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    cells = {c["item_ref"]: c for c in r["attribution"]["cells"]}
    c = cells["mktcap_forecast"]
    assert (c["verifiability"], c["substantive_obstacle"]) == ("missing_data", "none")
    assert "可验证性降档" in c["basis"]
    assert c["group_id"] == STAR


def test_attribution_counts_or_loser_absorbed(rb_dir):
    """只计数不合成标量；OR 落败支路（ocf 0.9）不进格位——blocker 与 Fold 同源。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    r = _layers23_of(ctx)
    assert r["attribution"]["counts"] == {
        "verified × numeric_gap": 1,   # np_latest
        "missing_data × none": 1,      # mktcap_forecast
    }
    refs = [c["item_ref"] for c in r["attribution"]["cells"]]
    assert "ocf_3y_sum" not in refs  # 落败支路被 Kleene OR 吸收，不是 blocker


# ── 合成场景：dominated 与 P3 judgment 型 ──────────────────────

def _syn(gid, item, leaf, state, thr=100, gap=None, reason=None):
    return {
        "group_id": gid, "clause_id": f"{gid}_c1", "clause_logic": "all",
        "leaf_id": leaf, "item_ref": item, "set_id": f"{gid}-b1",
        "state": state, "op": "ge",
        "threshold": {"value": thr, "format": "number"},
        "gap_ratio": gap, "reason": reason, "diff": None,
    }


def _syn_sets(rows):
    by_group: dict[str, list[dict]] = {}
    for c in rows:
        by_group.setdefault(c["group_id"], []).append(c)
    return [
        {
            "group_id": gid,
            "blockers": sorted({c["item_ref"] for c in cs if c["state"] != "met"}),
        }
        for gid, cs in by_group.items()
    ]


def test_dominated_reason_attached(rb_dir):
    """被支配套 excluded 附 dominated_by：主板零缺口支配 needs_review 缺口的科创板。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    rows = [
        _syn(MAIN, "np_latest", "l1", "met"),                       # 主板零缺口 (0,0,∞,0)
        _syn(STAR, "np_latest", "l1", "met"),
        _syn(STAR, "np_3y_sum", "l2", "needs_review"),              # 科创板 judgment 缺口 (0,0,∞,1)
    ]
    facts = {"checks": rows, "sets": _syn_sets(rows)}
    r = compute_layers23(ctx.inputs["rulebook"], ctx.selection.applicable, facts)
    assert r["recommendation"] == [MAIN]  # 主板被推荐
    ex = _excluded_by_gid(r)
    assert ex[STAR]["reason"] == "dominated"
    assert ex[STAR]["dominated_by"] == [MAIN]


def test_judgment_gap_goes_to_alternatives(rb_dir):
    """P3：judgment 型不确定不挡——纯 pending_judgment 缺口的过闸套进 alternatives 而非 excluded。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    rows = [
        _syn(MAIN, "np_latest", "l1", "needs_review"),   # 两套同轴 (0,0,∞,1)，互不支配
        _syn(STAR, "np_latest", "l1", "needs_review"),
    ]
    facts = {"checks": rows, "sets": _syn_sets(rows)}
    r = compute_layers23(ctx.inputs["rulebook"], ctx.selection.applicable, facts)
    assert r["recommendation"] == []            # 无缺口套才进推荐
    assert sorted(r["alternatives"]) == sorted([MAIN, STAR])  # 带 uncertainty 的备选
    assert r["excluded"] == []
