"""T5：进度与覆盖率（E9 / ADR-0007，设计 0005 §5.2）。

golden 对拍段落：main 40/100（binding cn_main_g1_c3，next cn_main_g1_c2）；
star 100/80（binding/next 为 null，未定义叶不进聚合但进覆盖分母）。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.engine.progress import _leaf_score, compute_progress_coverage

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
GOLDEN = BASE / "expected" / "summary.json"


def _progress_of(ctx):
    return compute_progress_coverage(ctx.selection.applicable, ctx.facts["checks"])


def test_golden_progress_coverage():
    ctx = run_eval(company_dir=BASE, rulebook_dir=REPO / "rulebook", fixtures_root=FX, as_of="2025-06-30")
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


def test_star_undefined_leaf_excluded_from_progress_only():
    """科创板 mktcap 未定义 → progress 仍 100（min 不过它），coverage 80（进分母）。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=REPO / "rulebook", fixtures_root=FX, as_of="2025-06-30")
    got = _progress_of(ctx)
    assert got["star_general_g1"]["progress"] == 100
    assert got["star_general_g1"]["coverage"] == 80
    assert got["star_general_g1"]["binding_clause_id"] is None
    assert got["star_general_g1"]["next_binding_clause_id"] is None


def test_main_binding_and_next_weak():
    ctx = run_eval(company_dir=BASE, rulebook_dir=REPO / "rulebook", fixtures_root=FX, as_of="2025-06-30")
    got = _progress_of(ctx)
    assert got["cn_main_general_g1"]["binding_clause_id"] == "cn_main_g1_c3"  # 最近一年净利，0.4
    assert got["cn_main_general_g1"]["next_binding_clause_id"] == "cn_main_g1_c2"  # 次弱子句


def test_progress_hundred_clears_binding():
    """progress=100 → binding/next 为 null（无卡点）。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=REPO / "rulebook", fixtures_root=FX, as_of="2025-06-30")
    assert _progress_of(ctx)["star_general_g1"]["progress"] == 100
    assert _progress_of(ctx)["star_general_g1"]["binding_clause_id"] is None
