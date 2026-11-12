"""P5b 裁定落地回归（底稿 0002 问题二/三，2026-11-12 拍板 confirmed）。

问题三（第三路径）：rev_cagr_gt_peer_avg 叶的三态——
  True → met；False → not_met；None → indeterminate（缺数三原则，不缩窗不回退）。

问题二（红筹增长认定豁免）：company_stage ∈ {rd_stage, strategic_significance}
→ 增长认定叶（营收前提/cagr/行业对比）取数前判 not_applicable；
  50亿标准的「营收≥5亿」是标准本体要求，**不豁免**（3.1.5(三) 明文）；
  company_stage=growth 或 None → 不豁免（缺省不豁免，ADR-0008 约定 2）。

验证对象是**正式库本体**（rulebook/），不是样板夹具——豁免标注与新支路
只存在于 export-official 的产物里。
"""
from pathlib import Path

import pytest

from ipo_eval_lab.engine.calc import evaluate_leaves
from ipo_eval_lab.engine.fetch import build_facts
from ipo_eval_lab.engine.applicability import judge_applicability
from ipo_eval_lab.engine.asof import filter_by_as_of
from ipo_eval_lab.engine.context import RunTarget
from ipo_eval_lab.engine.fold import fold_set
from ipo_eval_lab.fixtures import load_company, load_sanity
from ipo_eval_lab.rulebook.loader import load_rulebook

REPO = Path(__file__).resolve().parents[1]
RB = REPO / "rulebook"
FX = REPO / "fixtures"
AS_OF = "2026-06-30"


@pytest.fixture(scope="module")
def rb():
    return load_rulebook(RB, strict_global=True).rulebook


@pytest.fixture(scope="module")
def base_profile():
    sanity = load_sanity(FX / "sanity.yaml")
    return load_company(FX / "companies" / "base_co_2029", sanity).profile


def _redchip(base_profile, stage, peer_avg=None):
    p = base_profile.model_copy(deep=True)
    p.applicant_profile.company_type = "redchip_unlisted"
    p.applicant_profile.company_stage = stage
    p.documentary.rev_cagr_gt_peer_avg = peer_avg
    return p


def _checks(rb, profile):
    eff = filter_by_as_of(rb.groups, AS_OF)
    app = judge_applicability(eff.effective, profile, RunTarget())
    facts = build_facts(rb, profile)
    return evaluate_leaves(rb, facts, app.applicable, profile), app


def _check(checks, leaf_id):
    return next(c for c in checks if c["leaf_id"] == leaf_id)


# ── 问题三：行业对比叶三态 ──

def test_peer_avg_true_is_met(rb, base_profile):
    checks, _ = _checks(rb, _redchip(base_profile, "growth", peer_avg=True))
    c = _check(checks, "rc_unlisted_g2_b3_c1_l1")
    assert c["state"] == "met"
    assert c["refs"] == ["documentary.rev_cagr_gt_peer_avg"]


def test_peer_avg_false_is_not_met(rb, base_profile):
    checks, _ = _checks(rb, _redchip(base_profile, "growth", peer_avg=False))
    assert _check(checks, "rc_unlisted_g2_b3_c1_l1")["state"] == "not_met"


def test_peer_avg_none_is_indeterminate(rb, base_profile):
    """mock 契约 F7：None = 未取得行业对比结论 → indeterminate（不缩窗不回退）。"""
    checks, _ = _checks(rb, _redchip(base_profile, "growth", peer_avg=None))
    c = _check(checks, "rc_unlisted_g2_b3_c1_l1")
    assert c["state"] == "indeterminate"
    assert "F7" in c["reason"]


# ── 问题二：豁免命中/不命中 ──

GROWTH_LEAVES_G2 = [
    "rc_unlisted_g2_b1_c1_l1",   # 路径A 营收≥5亿 前提
    "rc_unlisted_g2_b1_c2_l1",   # 路径A cagr≥10%
    "rc_unlisted_g2_b2_c1_l1",   # 路径B 营收<5亿 前提
    "rc_unlisted_g2_b2_c2_l1",   # 路径B cagr≥20%
    "rc_unlisted_g2_b3_c1_l1",   # 路径C 行业对比
]
GROWTH_LEAVES_G3 = [
    "rc_unlisted_g3_b1_c4_l1",   # 50亿套 cagr≥10%
    "rc_unlisted_g3_b2_c1_l1",   # 50亿套 行业对比
]


@pytest.mark.parametrize("stage", ["rd_stage", "strategic_significance"])
def test_rd_stage_exempts_all_growth_leaves(rb, base_profile, stage):
    """研发阶段/国家战略红筹：增长认定五叶（100亿套）取数前全部 not_applicable。"""
    checks, _ = _checks(rb, _redchip(base_profile, stage, peer_avg=True))
    for lid in GROWTH_LEAVES_G2 + GROWTH_LEAVES_G3:
        c = _check(checks, lid)
        assert c["state"] == "not_applicable", f"{lid}: {c['state']}"
        assert "法定豁免" in c["reason"]


def test_rd_stage_does_not_exempt_standard_own_rev_clause(rb, base_profile):
    """50亿标准的「营收≥5亿」是标准本体（3.1.5(三) 明文），不在豁免范围。"""
    checks, _ = _checks(rb, _redchip(base_profile, "rd_stage"))
    c = _check(checks, "rc_unlisted_g3_b1_c3_l1")   # 营收≥5亿（已上移 shared）
    assert c["state"] != "not_applicable"


def test_growth_stage_exempts_nothing(rb, base_profile):
    """company_stage=growth（正常增长期主体）：豁免不命中，叶正常判定。"""
    checks, _ = _checks(rb, _redchip(base_profile, "growth", peer_avg=None))
    for lid in GROWTH_LEAVES_G2:
        assert _check(checks, lid)["state"] != "not_applicable"


def test_stage_none_exempts_nothing(rb, base_profile):
    """company_stage 缺省 None：缺省不豁免（ADR-0008 约定 2）。"""
    checks, _ = _checks(rb, _redchip(base_profile, None))
    for lid in GROWTH_LEAVES_G2:
        assert _check(checks, lid)["state"] != "not_applicable"


# ── 豁免后的折叠语义（kleene：全豁免 AND 支路 = met，约束消失）──

def test_rd_stage_folds_growth_branches_away(rb, base_profile):
    """研发阶段红筹评 100亿套：增长支路的约束消失，套结果由 shared（市值+定性）决定。"""
    profile = _redchip(base_profile, "rd_stage")
    checks, app = _checks(rb, profile)
    g2 = next(g for g in app.applicable if g.group_id == "cn_main_redchip_unlisted_g2")
    g2_checks = [c for c in checks if c["group_id"] == "cn_main_redchip_unlisted_g2"]
    folded = fold_set(g2, g2_checks)
    # 增长叶全 not_applicable → 各支路折叠退化为 shared-only：
    # 市值100亿（mktcap 缺数 indeterminate）+ 定性 needs_review → 支路 unknown，
    # 而增长叶不得出现在 blockers 里（约束已消失）。
    assert folded["outcome"] == "indeterminate"
    assert "rev_3y_cagr" not in folded["blockers"]
    assert "rev_latest" not in folded["blockers"]
    assert "rev_cagr_gt_peer_avg" not in folded["blockers"]
