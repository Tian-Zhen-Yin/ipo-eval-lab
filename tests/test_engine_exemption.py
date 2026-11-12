"""ADR-0008：豁免语义（法定「本主体不适用某项标准」）。

三条不可让步的约定，逐条钉住：
1. 命中在**取数前** → not_applicable，不查 metric、不取数（「不约束」≠「查不到」）；
2. 缺省**不豁免** → 主体侧事实字段为 None 时不命中（null 永不进比较）；
3. 豁免叶**既不进 progress 聚合、也不进 coverage 分母**（有确定结论，不是数据缺口）。

另测折叠语义：豁免叶在 Kleene 折叠前剔除；全豁免的 AND 子句恒等元为 met，
全豁免的 OR 支路为 not_met（该路径不成立）。
"""
from datetime import date

import pytest

from ipo_eval_lab.engine.calc import evaluate_leaves
from ipo_eval_lab.engine.exemption import exempted_items, profile_exemption_attrs
from ipo_eval_lab.engine.fold import kleene_and, kleene_or
from ipo_eval_lab.engine.progress import compute_progress_coverage
from ipo_eval_lab.fixtures.models import ApplicantProfile, CompanyProfile
from ipo_eval_lab.rulebook.models import (
    Branch, Clause, Exemption, ExemptionCondition, Group, Leaf, Op, Threshold,
    ThresholdFormat,
)


# ── 夹具：一套含豁免的最小规则库 ──

def _leaf(leaf_id, item_ref, thr=1.0, op="ge"):
    return Leaf(leaf_id=leaf_id, item_ref=item_ref, op=Op(op),
                threshold=Threshold(value=thr, format=ThresholdFormat.number))


def _clause(clause_id="ex_c1", exemptions=None, items=("m1", "m2")):
    return Clause(
        clause_id=clause_id,
        law_ref="sse_main_2026#3.1.5",
        logic="all",
        leaves=[_leaf(f"{clause_id}_l{i+1}", it) for i, it in enumerate(items)],
        exemptions=exemptions or [],
    )


def _group(clauses, group_id="g1", branches=None):
    """套：clause 放 shared_clauses；branch 需至少 1 个 clause，故给一条占位。

    真实规则库里 shared_clauses 与 branch.clauses 并存；本夹具把受测 clause
    放 shared，branch 放一条无关 clause 以满足 Branch 的 min_length=1。
    """
    filler = Clause(
        clause_id=f"{group_id}-b1_c0", law_ref="sse_main_2026#3.1.5",
        logic="all", leaves=[_leaf(f"{group_id}-b1_c0_l1", "m3")],
    )
    return Group(
        group_id=group_id, display="豁免测试套", boards=["SSE-MB"],
        company_type="general", group_no=1,
        effective_from=date(2024, 4, 30),
        shared_clauses=list(clauses),
        branches=branches or [Branch(set_id=f"{group_id}-b1", clauses=[filler])],
    )


EXEMPTION = Exemption(
    when=ExemptionCondition(profile_field="company_stage", equals="rd_stage"),
    excludes=["m2"],
    note="原文：处于研发阶段的红筹企业……不适用“营业收入快速增长”的规定",
)


def _no_metric_facts():
    """facts 夹具：审计年有、指标值缺——未豁免的叶应落 indeterminate。"""
    return {
        "metrics": {"met1": {2023: {"value": None, "refs": [], "reason": "底稿缺值"}}},
        "audit": {2023: {"status": "audited", "opinion": "standard"}},
    }


# ── 1. 豁免命中 → not_applicable，且不取数 ──

def test_exempted_leaf_is_not_applicable():
    """命中豁免 → 该叶产 not_applicable，理由含豁免依据。"""
    clause = _clause(exemptions=[EXEMPTION])
    attrs = {"company_stage": "rd_stage"}
    ex = exempted_items(clause, attrs)
    assert ex == {"m2": ex["m2"]}
    assert "rd_stage" in ex["m2"]


def test_exemption_not_matched_when_field_missing():
    """约定 2：主体侧事实为 None → 不豁免（宁可按不豁免算）。"""
    clause = _clause(exemptions=[EXEMPTION])
    assert exempted_items(clause, {"company_stage": None}) == {}
    assert exempted_items(clause, {}) == {}


def test_exemption_not_matched_when_value_differs():
    clause = _clause(exemptions=[EXEMPTION])
    assert exempted_items(clause, {"company_stage": "growth"}) == {}


def test_exemption_in_list_condition():
    clause = _clause(
        exemptions=[Exemption(
            when=ExemptionCondition(profile_field="company_stage",
                                    in_list=["rd_stage", "strategic_significance"]),
            excludes=["m2"], note="研发阶段或国家战略意义",
        )]
    )
    assert "m2" in exempted_items(clause, {"company_stage": "strategic_significance"})
    assert exempted_items(clause, {"company_stage": "growth"}) == {}


def test_exemption_target_must_exist_in_clause_leaves():
    """写错的空豁免须在加载期报（不是静默不生效）。"""
    with pytest.raises(ValueError, match="不在本 clause 的叶里"):
        _clause(exemptions=[Exemption(
            when=ExemptionCondition(profile_field="company_stage", equals="rd_stage"),
            excludes=["not_a_real_item"],
        )])


def test_exemption_condition_requires_exactly_one_operator():
    with pytest.raises(ValueError, match="恰给一个"):
        ExemptionCondition(profile_field="company_stage")
    with pytest.raises(ValueError, match="恰给一个"):
        ExemptionCondition(profile_field="company_stage", equals="a", in_list=["b"])


# ── 2. 引擎侧：calc 取数前生效 ──

def test_calc_marks_exempted_leaf_not_applicable():
    """豁免叶在取数前即判 not_applicable——不受 metric 缺失影响。"""
    clause = _clause(exemptions=[EXEMPTION])
    group = _group([clause])
    rb = _rulebook_stub([group])
    facts = _no_metric_facts()
    # 刻意不给任何可用数值：豁免叶不该因取数失败而出错
    checks = evaluate_leaves(
        rb, facts, [group],
        profile=ApplicantProfile(company_type="general", profit_status="profitable",
                                  industry=None, company_stage="rd_stage"),
    )
    by_item = {c["item_ref"]: c for c in checks}
    assert by_item["m2"]["state"] == "not_applicable"
    assert by_item["m2"]["reason"]
    # 未被豁免的叶照常走取数路径（metric 缺失 → indeterminate，不是 not_applicable）
    assert by_item["m1"]["state"] == "indeterminate"


def test_calc_without_profile_does_not_exempt():
    """profile 缺失 → 无人可判豁免 → 全部照常判定（缺省不豁免）。"""
    clause = _clause(exemptions=[EXEMPTION])
    group = _group([clause])
    checks = evaluate_leaves(_rulebook_stub([group]), _no_metric_facts(), [group], profile=None)
    assert all(c["state"] != "not_applicable" for c in checks)


def test_profile_exemption_attrs_only_exposes_exemption_fields():
    """谓词空间只暴露豁免相关字段（免得谓词名写错时静默不命中）。"""
    p = ApplicantProfile(company_type="general", profit_status="profitable",
                         industry="半导体", company_stage="rd_stage")
    attrs = profile_exemption_attrs(p)
    assert attrs == {"company_stage": "rd_stage", "redchip_status": None}
    assert "industry" not in attrs


# ── 3. 折叠语义：豁免叶先剔除 ──

def test_kleene_and_excludes_exempt_leaves():
    """AND：豁免叶不作约束；剩余全 met → met。"""
    assert kleene_and([("met", []), ("not_applicable", [])]) == ("met", [])


def test_kleene_and_all_exempt_is_met():
    """全豁免的 AND 子句 = 空约束集，恒等元 met（无约束，不是「不达标」）。"""
    assert kleene_and([("not_applicable", []), ("not_applicable", [])]) == ("met", [])


def test_kleene_or_all_exempt_is_not_met():
    """全豁免的 OR 支路 = 无可走路径 = not_met（不是 met——否则「全豁免」读成「满足」）。"""
    assert kleene_or([("not_applicable", [])]) == ("not_met", [])


def test_kleene_or_excludes_exempt_leaves():
    assert kleene_or([("not_applicable", []), ("met", [])]) == ("met", [])


# ── 4. 进度与覆盖率口径 ──

def test_exempted_leaf_excluded_from_coverage_denominator():
    """豁免叶不进 coverage 分母——它是「不约束」，不是「数据缺口」。"""
    group = _group([_clause()])
    checks = [
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l1", "item_ref": "m1", "state": "met",
         "threshold": {"value": 1.0, "format": "number"}, "gap_ratio": None},
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l2", "item_ref": "m2", "state": "not_applicable",
         "threshold": {"value": 1.0, "format": "number"}, "gap_ratio": None},
    ]
    pc = compute_progress_coverage([group], checks)["g1"]
    assert pc["coverage"] == 100      # 分母只有 m1，已评估 → 100%（不是 50%）
    assert pc["progress"] == 100


def test_progress_still_reflects_unmet_constraint_alongside_exemption():
    """豁免与真实不达标并存：豁免不影响其余叶的进度。"""
    group = _group([_clause()])
    checks = [
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l1", "item_ref": "m1", "state": "not_met",
         "threshold": {"value": 10.0, "format": "number"}, "gap_ratio": 0.5},
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l2", "item_ref": "m2", "state": "not_applicable",
         "threshold": {"value": 1.0, "format": "number"}, "gap_ratio": None},
    ]
    pc = compute_progress_coverage([group], checks)["g1"]
    assert pc["progress"] == 50       # 1 - 0.5
    assert pc["coverage"] == 100
    assert pc["binding_clause_id"] == "ex_c1"


def test_all_exempt_group_progress_is_100():
    """全组豁免 → 无约束 → progress=100（不是 0）。"""
    group = _group([_clause()])
    checks = [
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l1", "item_ref": "m1", "state": "not_applicable",
         "threshold": {"value": 1.0, "format": "number"}, "gap_ratio": None},
    ]
    pc = compute_progress_coverage([group], checks)["g1"]
    assert pc["progress"] == 100
    assert pc["coverage"] == 100
    assert pc["binding_clause_id"] is None


def test_all_indeterminate_group_progress_is_0():
    """对照组：全未定义叶 → progress=0（判不了，与「全豁免」必须分开）。"""
    group = _group([_clause()])
    checks = [
        {"group_id": "g1", "clause_id": "ex_c1", "clause_logic": "all",
         "leaf_id": "ex_c1_l1", "item_ref": "m1", "state": "indeterminate",
         "threshold": {"value": 1.0, "format": "number"}, "gap_ratio": None},
    ]
    pc = compute_progress_coverage([group], checks)["g1"]
    assert pc["progress"] == 0
    assert pc["coverage"] == 0


# ── 5. 夹具构造 ──

def _rulebook_stub(groups=None):
    """最小 Rulebook 壳（只供 calc 读 items/metrics）。

    走真模型而非 Mock——Rulebook 有 L1/L4/L6 跨实体校验，Mock 会绕过它，
    那样 schema 破坏（如阈值 format 与 metric.unit 不一致）在本测试里看不出来。
    """
    from ipo_eval_lab.rulebook.models import (
        BasisKind, Conventions, Item, Law, LawArticle, Lever, Meta, Metric,
        Nature, Rulebook,
    )

    items = [
        Item(item_id="m1", display="指标一", nature=Nature.quantitative,
             basis=BasisKind.calc, metric_ref="met1", quantifier="latest",
             window={"kind": "latest"}, lever=Lever.grow),
        Item(item_id="m2", display="指标二", nature=Nature.quantitative,
             basis=BasisKind.calc, metric_ref="met1", quantifier="latest",
             window={"kind": "latest"}, lever=Lever.grow),
        Item(item_id="m3", display="指标三", nature=Nature.quantitative,
             basis=BasisKind.calc, metric_ref="met1", quantifier="latest",
             window={"kind": "latest"}, lever=Lever.grow),
    ]
    metrics = [Metric(metric_id="met1", display="指标", unit="yuan", kind="flow")]
    laws = [Law(
        law_id="sse_main_2026", title="上海证券交易所股票上市规则（2026）",
        source_type="exchange_rule", effective_from=date(2024, 4, 30),
        articles=[LawArticle(article="3.1.5", text="（测试用占位条文）")],
    )]
    return Rulebook(
        meta=Meta(rulebook_version="test",
                  conventions=Conventions(percent="decimal", money="yuan",
                                          op=["eq", "ne", "gt", "ge", "lt", "le"],
                                          format=["number", "percent", "integer", "boolean"]),
                  boards=["SSE-MB"], company_types=["general"]),
        items=items, metrics=metrics, laws=laws, groups=list(groups or []),
    )
