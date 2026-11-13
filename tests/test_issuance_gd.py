"""段① 发行条件回归（底稿 0003 续；M1 三段收口收官件）。

钉住的语义：
1. 双档择一 = branch OR（主板 5000万∧25% 或 4亿∧10%；midas IPO-37/38 归位）。
2. issuance 组跨企业类型一体适用（红筹也要满足发行条件）。
3. 缺数语义：公开比例 None → indeterminate（甲公司即此算例，不补零不缩窗）。
4. judgment 定性（205号令第十~十三条）→ needs_review，段① indeterminate 诚实不硬判。
5. 甲公司算例：经营 12 年 ✓、股本 8000万 → b1 档 met / b2 档 not_met（OR 取 b1）。
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

ISS_IDS = {"iss_qual_main_g1", "iss_qual_gem_g1", "iss_qual_bse_g1", "iss_conduct_g1"}


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


def test_issuance_applies_across_company_types(rb, base_profile):
    p = base_profile.model_copy(deep=True)
    p.applicant_profile.company_type = "redchip_unlisted"
    res = _apply(rb, p)
    got = {g.group_id for g in res.applicable if g.scope.value == "issuance"}
    assert got == ISS_IDS


def test_dual_tier_or_semantics(rb, base_profile):
    """甲公司（股本8000万）：b1 档 met（≥5000万∧25%…比例缺数）、b2 档 not_met（<4亿）。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    checks = {c["leaf_id"]: c for c in ctx.facts["checks"]}
    assert checks["iss_q_cap_b1_c1_l1"]["state"] == "met"        # ≥5000万
    assert checks["iss_q_cap_b2_c1_l1"]["state"] == "not_met"    # <4亿
    assert checks["iss_q_op_years_c1_l1"]["state"] == "met"      # 12年≥3


def test_missing_public_float_is_indeterminate(rb, base_profile):
    """公开比例底稿缺（None）→ indeterminate，不补零（甲公司即此算例）。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    checks = {c["leaf_id"]: c for c in ctx.facts["checks"]}
    c = checks["iss_q_pf_b1_c2_l1"]
    assert c["state"] == "indeterminate"
    assert c["reason"] and "缺" in c["reason"]


def test_conduct_group_is_needs_review(rb, base_profile):
    """205号令第十~十三条定性族：judgment × declared → needs_review，永不 met。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    checks = {c["leaf_id"]: c for c in ctx.facts["checks"]}
    for lid in ("iss_c_audit_c1_l1", "iss_c_stable_c2_l1", "iss_c_lawful_c6_l1"):
        assert checks[lid]["state"] == "needs_review"


def test_segment1_indeterminate_via_missing_and_judgment(rb, base_profile):
    """段① = OR(4 组)：组全 indeterminate（缺数+judgment）→ 段① indeterminate。"""
    from ipo_eval_lab.engine import run_eval

    ctx = run_eval(company_dir=FX / "companies" / "base_co_2029", rulebook_dir=RB,
                   fixtures_root=FX, as_of=AS_OF)
    by_id = {s["group_id"]: s for s in ctx.facts["issuance"]}
    assert set(by_id) == ISS_IDS
    assert all(s["outcome"] == "indeterminate" for s in by_id.values())
    by_board = {b["board"]: b for b in ctx.facts["boards"]}
    assert by_board["SSE-MB"]["segments"]["issuance"]["state"] == "indeterminate"