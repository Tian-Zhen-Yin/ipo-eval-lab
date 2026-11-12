"""T5：进度与覆盖率（E9 / ADR-0007，设计 0005 §5.2）。

golden 对拍段落：main 40/100（binding cn_main_g1_c3，next cn_main_g1_c2）；
star 100/80（binding/next 为 null，未定义叶不进聚合但进覆盖分母）。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.engine.progress import (
    _leaf_score,
    compute_progress_coverage,
    coverage_forbidden_claims,
)

from fixture_rulebook import fixture_rulebook_dir

REPO = Path(__file__).resolve().parents[1]

# 夹具规则库根（正式库数据层＋样板套结构层）：见 tests/fixture_rulebook.py
@pytest.fixture(scope="module")
def rb_dir():
    with fixture_rulebook_dir() as d:
        yield d
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
GOLDEN = BASE / "expected" / "summary.json"


def _progress_of(ctx):
    return compute_progress_coverage(ctx.selection.applicable, ctx.facts["checks"])


def test_golden_progress_coverage(rb_dir):
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    got = _progress_of(ctx)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["progress"]
    assert got == golden


def test_leaf_score_basic():
    met = {"state": "met"}
    assert _leaf_score(met) == 1.0
    nm = {"state": "not_met", "threshold": {"value": 100}, "gap_ratio": 0.6}
    assert _leaf_score(nm) == 0.4
    nm_thr0 = {"state": "not_met", "threshold": {"value": 0}, "gap_ratio": None}
    assert _leaf_score(nm_thr0) == 0.0  # thr=0 → 0，不造无穷大
    assert _leaf_score({"state": "indeterminate"}) is None
    assert _leaf_score({"state": "needs_review"}) is None


def test_star_undefined_leaf_excluded_from_progress_only(rb_dir):
    """科创板 mktcap 未定义 → progress 仍 100（min 不过它），coverage 80（进分母）。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    got = _progress_of(ctx)
    assert got["star_general_g1"]["progress"] == 100
    assert got["star_general_g1"]["coverage"] == 80
    assert got["star_general_g1"]["binding_clause_id"] is None
    assert got["star_general_g1"]["next_binding_clause_id"] is None


def test_main_binding_and_next_weak(rb_dir):
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    got = _progress_of(ctx)
    assert got["cn_main_general_g1"]["binding_clause_id"] == "cn_main_g1_c3"  # 最近一年净利，0.4
    assert got["cn_main_general_g1"]["next_binding_clause_id"] == "cn_main_g1_c2"  # 次弱子句


def test_progress_hundred_clears_binding(rb_dir):
    """progress=100 → binding/next 为 null（无卡点）。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    assert _progress_of(ctx)["star_general_g1"]["progress"] == 100
    assert _progress_of(ctx)["star_general_g1"]["binding_clause_id"] is None


def _synthetic_check(group_id, clause_id, logic, leaf_id, state, thr, gap):
    """合成 check 行（compute_progress_coverage 只触这几个字段）。"""
    return {
        "group_id": group_id,
        "clause_id": clause_id,
        "clause_logic": logic,
        "leaf_id": leaf_id,
        "item_ref": leaf_id,
        "state": state,
        "op": "ge",
        "threshold": {"value": thr, "format": "number"},
        "gap_ratio": gap,
    }


def test_next_binding_excludes_or_loser_and_gapless(rb_dir):
    """OR 落败支路（0.9，第 2 小叶分数）与 thr=0 叶（无 gap）不得成为次弱；无可排序候选 → null。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    gid = "cn_main_general_g1"
    checks = [
        _synthetic_check(gid, "c3", "all", "c3_l1", "not_met", 100, 0.6),   # binding（0.4）
        _synthetic_check(gid, "b1_c1", "any", "b1_l1", "not_met", 200, 0.1),  # OR 落败支路 0.9 → 排除
        _synthetic_check(gid, "b1_c1", "any", "b1_l2", "met", 1500, -0.07),   # OR 获胜支路 → 支路非约束
        _synthetic_check(gid, "c1", "all", "c1_l1", "met", 0, None),          # thr=0 → 无 gap 语义
    ]
    got = compute_progress_coverage(ctx.selection.applicable, checks)[gid]
    assert got["binding_clause_id"] == "c3"
    assert got["next_binding_clause_id"] is None  # 候选被 OR/无 gap 规则排空


def test_next_binding_orders_by_gap_among_met(rb_dir):
    """binding 之外有多个有 gap 语义的叶 → 按 gap_ratio 降序，距门槛最近者（富余最小）为次弱。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    gid = "cn_main_general_g1"
    checks = [
        _synthetic_check(gid, "c3", "all", "c3_l1", "not_met", 100, 0.6),  # binding
        _synthetic_check(gid, "c2", "all", "c2_l1", "met", 200, -0.07),    # 富余 7% → 次弱
        _synthetic_check(gid, "c4", "all", "c4_l1", "met", 300, -0.30),    # 富余 30% → 更强
    ]
    got = compute_progress_coverage(ctx.selection.applicable, checks)[gid]
    assert got["binding_clause_id"] == "c3"
    assert got["next_binding_clause_id"] == "c2"


def test_coverage_forbidden_claims():
    """coverage < 100% 的套出追加禁令；coverage = 100% 不出。"""
    pc = {
        "g_full": {"progress": 100, "coverage": 100, "binding_clause_id": None, "next_binding_clause_id": None},
        "g_star": {"progress": 100, "coverage": 80, "binding_clause_id": None, "next_binding_clause_id": None},
    }
    claims = coverage_forbidden_claims(pc)
    assert claims == [
        "套 g_star coverage=80%<100%：禁「可达标 / 预计能过」表述，进度仅代表已评估部分（20% 叶因数据缺口未判定）"
    ]
