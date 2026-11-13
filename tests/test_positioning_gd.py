"""段② 板块定位回归（G-D，底稿 0003；ADR-0011 三段收口）。

钉住的语义：
1. 硬筛双向——not_in 禁区清单命中才排除；None 不排除（交 judgment 兜底）。
2. positioning 组跨企业类型适用（applicability 免 company_type 过滤）。
3. 段② 折叠 = 复用 branch-OR；judgment 定性 → indeterminate（诚实，不硬判）。
4. 板块结论 = AND(段①, 段②, 段③)：not_met 优先于 indeterminate。
5. 甲公司算例（white-co_2029 定稿剧情）：可量值叶真实判定（科创 c1/c3/c4），
   定性叶 needs_review → 段② indeterminate + pending_judgments 计数。
"""
from pathlib import Path

import pytest

from ipo_eval_lab.engine import RunTarget, filter_by_as_of, judge_applicability
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


def _apply(rb, profile):
    eff = filter_by_as_of(rb.groups, AS_OF)
    return judge_applicability(eff.effective, profile, RunTarget())


POS_IDS = {"cn_main_positioning_g1", "star_positioning_g1",
           "chinext_positioning_g1", "bse_positioning_g1"}


# ── 1. 跨企业类型适用 + 硬筛 ──

def test_positioning_applies_across_company_types(rb, base_profile):
    """红筹未上市主体：sets 组按类型过滤，positioning 组仍全部适用。"""
    p = base_profile.model_copy(deep=True)
    p.applicant_profile.company_type = "redchip_unlisted"
    res = _apply(rb, p)
    got = {g.group_id for g in res.applicable if g.scope.value == "positioning"}
    assert got == POS_IDS


def test_hard_filter_not_in_excludes_forbidden_industry(rb, base_profile):
    """房地产业 → STAR 定位排除（指引第三条禁入清单），其余定位组不受影响。"""
    p = base_profile.model_copy(deep=True)
    p.applicant_profile.industry = "房地产业"
    res = _apply(rb, p)
    got = {g.group_id for g in res.applicable if g.scope.value == "positioning"}
    assert "star_positioning_g1" not in got
    assert got == POS_IDS - {"star_positioning_g1"}
    star = next(n for n in res.not_applicable if n["group_id"] == "star_positioning_g1")
    assert "禁入清单" in star["reason"]


def test_hard_filter_none_industry_not_excluded(rb, base_profile):
    """industry=None：无从证明即不剔除（交 judgment 项兜底），STAR 定位仍适用。"""
    p = base_profile.model_copy(deep=True)
    p.applicant_profile.industry = None
    res = _apply(rb, p)
    got = {g.group_id for g in res.applicable if g.scope.value == "positioning"}
    assert got == POS_IDS


# ── 2. 段② 折叠与板块 AND ──

def test_segment2_indeterminate_via_judgments(rb, base_profile):
    """甲公司（全 declared None）：定性定位叶 needs_review → 段② indeterminate。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    by_id = {s["group_id"]: s for s in ctx.facts["positioning"]}
    assert set(by_id) == POS_IDS
    for gid in POS_IDS:
        assert by_id[gid]["outcome"] == "indeterminate"
        assert by_id[gid]["needs_review_count"] >= 1
        pending = [p["item_ref"] for p in by_id[gid]["pending_judgments"]]
        assert pending, f"{gid} 应有 pending_judgments"


def test_board_and_not_met_dominates_indeterminate(rb, base_profile):
    """甲公司沪主板：段③ not_met ⊕ 段② indeterminate → 板块 not_met（Kleene AND）。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    by_board = {b["board"]: b for b in ctx.facts["boards"]}
    assert by_board["SSE-MB"]["outcome"] == "criteria_not_met"
    assert by_board["SSE-MB"]["segments"]["positioning"]["state"] == "indeterminate"
    assert by_board["SSE-MB"]["segments"]["listing_sets"]["state"] == "not_met"


def test_star_quantified_leaves_real_verdicts(rb, base_profile):
    """科创定位可量值叶按甲公司数据真实判定（白话算例锚点）：
    - 研发占比≈3.5%<5% 且 3年累计研发 5700万<8000万 → star_pos_reg_c1 not_met
    - 专利 5 项<7 → star_pos_reg_c3 not_met
    - cagr=(6.8/4.2)^(1/2)−1≈27.2%≥25% → star_pos_reg_c4 met（OR 短路）
    """
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    checks = {c["leaf_id"]: c for c in ctx.facts["checks"]}
    assert checks["star_pos_reg_c1_l1"]["state"] == "not_met"      # 占比
    assert checks["star_pos_reg_c1_l2"]["state"] == "not_met"      # 累计8000万
    assert checks["star_pos_reg_c3_l1"]["state"] == "not_met"      # 专利7项
    assert checks["star_pos_reg_c4_l1"]["state"] == "met"          # cagr 27.2%
    # 定性叶：needs_review，永不 met
    assert checks["star_pos_industry_c0_l1"]["state"] == "needs_review"


def test_unaudited_redchip_listed_cagr_exempt_in_positioning(rb, base_profile):
    """创业板定位 b1：红筹已上市 → rev_3y_cagr 叶豁免（not_applicable），
    OR 只剩 rev_latest≥3亿 约束——豁免语义贯穿段②（与 P5b 段③同机制）。"""
    from ipo_eval_lab.engine.calc import evaluate_leaves
    from ipo_eval_lab.engine.fetch import build_facts

    p = base_profile.model_copy(deep=True)
    p.applicant_profile.company_type = "redchip_listed"
    p.applicant_profile.redchip_status = "listed"
    eff = filter_by_as_of(rb.groups, AS_OF)
    app = judge_applicability(eff.effective, p, RunTarget())
    facts = build_facts(rb, p)
    checks = evaluate_leaves(rb, facts, app.applicable, p)
    by_leaf = {c["leaf_id"]: c for c in checks}
    assert by_leaf["cnx_pos_b1_c2_l1"]["state"] == "not_applicable"   # cagr 叶豁免
    assert by_leaf["cnx_pos_b1_c2_l2"]["state"] in ("met", "not_met", "indeterminate")  # 3亿叶照判
