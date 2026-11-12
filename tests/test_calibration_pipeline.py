"""M1 校准管线单元测试（U1~U5，schema 与规则库对齐版）。"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.calibration.models import (
    CandidateRule, CandidateClause, CandidateLeaf, CandidateContext, SourceClauseRef,
    GateName, GateStatus, L0CheckCode, L1bCheckCode, L3DiffCategory,
    L2Judgment, EquivalenceJudgment, ConfidenceTier, GateResult, GateFailure,
)
from ipo_eval_lab.calibration.l0_gate import (
    run_l0_gate, check_schema, check_unit_consistent, check_uniqueness,
    check_ref_integrity, check_window_enum, check_struct_complete,
    check_combination_coverage, check_version_alignment,
)
from ipo_eval_lab.calibration.l1b_gate import (
    check_quote_verbatim, check_numeric_anchor, check_coverage_scan,
    normalize_chinese_number, extract_numbers_from_text, run_l1b_gate, numbers_match,
)
from ipo_eval_lab.calibration.l2_gate import (
    render_leaf, render_clause, render_candidate, build_l2_prompt,
    parse_l2_response, run_l2_gate_offline,
)
from ipo_eval_lab.calibration.l3_gate import (
    compare_leaf, build_snapshot_key, generate_midas_diff_report, run_l3_gate,
)
from ipo_eval_lab.calibration.confidence import synthesize_confidence
from ipo_eval_lab.calibration.rulebook_refs import load_items, load_metrics

REPO = Path(__file__).resolve().parents[1]
RB = REPO / "rulebook"
ANCHOR = REPO / "config" / "anchor_normalization.yaml"

NP_TEXT = "最近3 年净利润均为正，且最近3 年净利润累计不低于2 亿元，最近一年净利润不低于1 亿元"


def make_leaf(leaf_id="c1_l1", item_ref="np_3y_allpos", op="gt",
              threshold=0, threshold_format="number", threshold_text="",
              quote="最近3 年净利润均为正"):
    return CandidateLeaf(
        leaf_id=leaf_id, item_ref=item_ref, op=op, threshold=threshold,
        threshold_format=threshold_format, threshold_text=threshold_text, quote=quote,
    )


def make_rule(clause_id="cn_main_g1_c1", leaves=None, logic="all",
              text=NP_TEXT, role="branch", group_id="cn_main_general_g1",
              branch_id="cn_main_general_g1-b1",
              board="SSE-MB", company_type="general", group_no=1,
              effective_from="2024-04-30"):
    leaves = leaves or [make_leaf()]
    return CandidateRule(
        clause_id=clause_id,
        context=CandidateContext(
            board=board, company_type=company_type, group_no=group_no,
            group_id=group_id,
            branch_id=branch_id if role == "branch" else None,
            role=role,
        ),
        clause=CandidateClause(
            clause_id=clause_id, law_ref="sse_main_2026#3.1.2", logic=logic,
            leaves=leaves,
        ),
        source=SourceClauseRef(law_id="sse_main_2026", article="3.1.2", text=text),
        evidence={"effective_from": effective_from},
    )


# ── L0 ──

def test_l0_schema_pass():
    assert check_schema(make_rule()) == []


def test_l0_schema_bad_law_ref():
    r = make_rule()
    r.clause.law_ref = "no-hash"
    fails = check_schema(r)
    assert any(f.check_code == L0CheckCode.SCHEMA_VALID for f in fails)


def test_l0_unit_consistent_percent_normalized():
    items, metrics = load_items(RB), load_metrics(RB)
    r = make_rule(leaves=[make_leaf(leaf_id="c_l1", item_ref="ros_latest",
                                    op="ge", threshold=25.0,
                                    threshold_format="percent", threshold_text="25%")])
    fails = check_unit_consistent(r, items, metrics)
    # item 不存在时 0-2 不报（由 0-4 管）；这里换成合法 percent item
    r2 = make_rule(leaves=[make_leaf(leaf_id="c_l1", item_ref="rd_intensity_3y",
                                    op="ge", threshold=0.05,
                                    threshold_format="percent", threshold_text="5%")])
    assert check_unit_consistent(r2, items, metrics) == []


def test_l0_unit_consistent_wrong_format():
    items, metrics = load_items(RB), load_metrics(RB)
    r = make_rule(leaves=[make_leaf(leaf_id="c_l1", item_ref="rev_3y_sum",
                                    op="ge", threshold=1.5e9,
                                    threshold_format="percent", threshold_text="15 亿元")])
    fails = check_unit_consistent(r, items, metrics)
    assert len(fails) >= 1
    assert fails[0].check_code == L0CheckCode.UNIT_CONSISTENT


def test_l0_ref_integrity_unknown_item():
    items, metrics = load_items(RB), load_metrics(RB)
    r = make_rule(leaves=[make_leaf(item_ref="total_share_capital_after")])
    fails = check_ref_integrity(r, items, metrics)
    assert len(fails) == 1
    assert fails[0].check_code == L0CheckCode.REF_INTEGRITY
    assert "total_share_capital_after" in fails[0].reason


def test_l0_uniqueness_duplicate_clause():
    r1, r2 = make_rule("dup"), make_rule("dup")
    fails = check_uniqueness([r1, r2])
    assert any(f.check_code == L0CheckCode.UNIQUENESS for f in fails)


def test_l0_uniqueness_duplicate_leaf():
    r = make_rule(leaves=[make_leaf("same"), make_leaf("same")])
    fails = check_uniqueness([r])
    assert any("leaf_id" in f.reason for f in fails)


def test_l0_window_token_bad_quantifier():
    items = dict(load_items(RB))
    items["fake_item"] = {"item_id": "fake_item", "quantifier": "total",
                          "window": {"kind": "last_n_years", "n": 3}}
    r = make_rule(leaves=[make_leaf(item_ref="fake_item")])
    fails = check_window_enum(r, items)
    assert len(fails) == 1
    assert fails[0].check_code == L0CheckCode.WINDOW_ENUM


def test_l0_struct_multi_branch_without_shared():
    r1 = make_rule("g1_b1_c1", role="branch", group_id="setX", branch_id="setX-b1")
    r2 = make_rule("g1_b2_c1", role="branch", group_id="setX", branch_id="setX-b2")
    fails = check_struct_complete([r1, r2])
    assert any("shared_clauses" in f.reason for f in fails)


def test_l0_struct_branch_plus_shared_ok():
    r1 = make_rule("g1_c1", role="shared", group_id="setX", branch_id=None)
    r2 = make_rule("g1_b1_c1", role="branch", group_id="setX", branch_id="setX-b1")
    r3 = make_rule("g1_b2_c1", role="branch", group_id="setX", branch_id="setX-b2")
    assert check_struct_complete([r1, r2, r3]) == []


def test_l0_combination_coverage_unknown_board():
    r = make_rule(board="HKEX", company_type="general")
    fails = check_combination_coverage([r], RB)
    assert any("board 'HKEX'" in f.reason for f in fails)


def test_l0_version_alignment_future_doc():
    r = make_rule(effective_from="2027-01-01")
    fails = check_version_alignment(r, "2026-11-11")
    assert len(fails) == 1
    assert fails[0].check_code == L0CheckCode.VERSION_ALIGN


def test_l0_version_alignment_missing():
    r = make_rule()
    r.evidence = {}
    fails = check_version_alignment(r, "2026-11-11")
    assert any("effective_from" in f.reason for f in fails)


def test_l0_gate_full_pass():
    r = make_rule()
    results = run_l0_gate([r], "2026-11-11", RB)
    assert results[0].status == GateStatus.PASS


def test_l0_gate_blocks_unknown_item():
    r = make_rule(leaves=[make_leaf(item_ref="total_share_capital_after")])
    results = run_l0_gate([r], "2026-11-11", RB)
    assert results[0].status == GateStatus.FAIL
    assert results[0].failure.check_code == L0CheckCode.REF_INTEGRITY


# ── L1b ──

def test_normalize_chinese_number():
    assert normalize_chinese_number("五十亿") == pytest.approx(5e9)
    assert normalize_chinese_number("5000万") == pytest.approx(5e7)
    assert normalize_chinese_number("15%") == pytest.approx(0.15)
    assert normalize_chinese_number("2 亿元") == pytest.approx(2e8)
    assert normalize_chinese_number("百分之十五") == pytest.approx(0.15)


def test_extract_numbers_from_text():
    nums = extract_numbers_from_text("不低于2 亿元，且不低于1 亿元")
    assert len(nums) == 2
    assert nums[0] == pytest.approx(2e8)
    assert nums[1] == pytest.approx(1e8)


def test_numbers_match_tolerance():
    assert numbers_match(2e8, 200000000.0)
    assert not numbers_match(2e8, 3.5e10)


def test_l1b_quote_verbatim_pass():
    r = make_rule()
    assert check_quote_verbatim(r) == []


def test_l1b_quote_verbatim_fail():
    r = make_rule(leaves=[make_leaf(quote="编造的引文：净利润不少于3 亿元")])
    fails = check_quote_verbatim(r)
    assert len(fails) == 1
    assert fails[0].check_code == L1bCheckCode.QUOTE_VERBATIM


def test_l1b_numeric_anchor_pass():
    r = make_rule(leaves=[make_leaf(leaf_id="c_l2", item_ref="np_3y_sum", op="ge",
                                    threshold=2e8, threshold_text="2 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")])
    assert check_numeric_anchor(r) == []


def test_l1b_numeric_anchor_fail_out_of_source():
    r = make_rule(leaves=[make_leaf(leaf_id="c_l2", item_ref="np_3y_sum", op="ge",
                                    threshold=5e8, threshold_text="5 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")])
    fails = check_numeric_anchor(r)
    assert len(fails) >= 1
    assert fails[0].check_code == L1bCheckCode.NUMERIC_ANCHOR


def test_l1b_numeric_anchor_threshold_text_mismatch():
    r = make_rule(leaves=[make_leaf(leaf_id="c_l2", item_ref="np_3y_sum", op="ge",
                                    threshold=3e8, threshold_text="2 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")])
    fails = check_numeric_anchor(r)
    assert any("不一致" in f.reason for f in fails)


def test_l1b_coverage_scan_missed_threshold():
    text = "最近3 年净利润累计不低于2 亿元，且最近一年营业收入不低于6 亿元"
    r = make_rule(text=text,
                  leaves=[make_leaf(leaf_id="c_l1", item_ref="np_3y_sum", op="ge",
                                    threshold=2e8, threshold_text="2 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")])
    fails = check_coverage_scan(r)
    assert len(fails) >= 1
    assert fails[0].check_code == L1bCheckCode.COVERAGE_SCAN
    assert "6 亿元" in fails[0].reason


def test_l1b_gate_pass_no_warning():
    r = make_rule(leaves=[make_leaf(leaf_id="c_l1", item_ref="np_3y_sum", op="ge",
                                    threshold=2e8, threshold_text="2 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")],
                  text="最近3 年净利润累计不低于2 亿元")
    out = run_l1b_gate([r], ANCHOR)[0]
    assert out.status == GateStatus.PASS
    assert "warnings" not in (out.payload or {})


def test_l1b_gate_pass_with_warning_is_g2_candidate():
    text = "最近3 年净利润累计不低于2 亿元，且最近一年营业收入不低于6 亿元"
    r = make_rule(text=text,
                  leaves=[make_leaf(leaf_id="c_l1", item_ref="np_3y_sum", op="ge",
                                    threshold=2e8, threshold_text="2 亿元",
                                    quote="最近3 年净利润累计不低于2 亿元")])
    out = run_l1b_gate([r], ANCHOR)[0]
    assert out.status == GateStatus.PASS
    assert out.payload["warnings"]


def test_l1b_gate_fails_on_fabricated_quote():
    r = make_rule(leaves=[make_leaf(quote="原文没有这句")])
    out = run_l1b_gate([r], ANCHOR)[0]
    assert out.status == GateStatus.FAIL


# ── L2 ──

def test_render_leaf_uses_item_display():
    items = load_items(RB)
    leaf = make_leaf(leaf_id="c_l1", item_ref="np_3y_sum", op="ge",
                     threshold=2e8, threshold_text="2 亿元")
    text = render_leaf(leaf, items["np_3y_sum"])
    assert "最近3年净利润累计" in text
    assert "不低于" in text
    assert "2 亿元" in text


def test_render_clause_all():
    items = load_items(RB)
    clause = CandidateClause(
        clause_id="c", law_ref="sse_main_2026#3.1.2", logic="all",
        leaves=[make_leaf("c_l1", "np_3y_allpos"), make_leaf("c_l2", "np_3y_sum", op="ge",
                                                            threshold=2e8, threshold_text="2 亿元")],
    )
    out = render_clause(clause, items)
    assert "同时满足" in out and "且" in out


def test_render_clause_any():
    items = load_items(RB)
    clause = CandidateClause(
        clause_id="c", law_ref="sse_main_2026#3.1.2(一)", logic="any",
        leaves=[make_leaf("c_l1", "ocf_3y_sum", op="ge", threshold=2e8, threshold_text="2 亿元"),
                make_leaf("c_l2", "rev_3y_sum", op="ge", threshold=1.5e9, threshold_text="15 亿元")],
    )
    out = render_clause(clause, items)
    assert "满足下列条件之一" in out and "或" in out


def test_build_l2_prompt_contains_both_texts():
    r = make_rule()
    system, user, rendered = build_l2_prompt(r, load_items(RB))
    assert r.source.text in user
    assert rendered in user
    assert "等价" in system


def test_parse_l2_response_plain_json():
    j = parse_l2_response('{"equivalent": "yes", "differences": []}')
    assert j.equivalent == EquivalenceJudgment.YES


def test_parse_l2_response_markdown_fenced():
    j = parse_l2_response('```json\n{"equivalent": "no", "differences": ["或→且"]}\n```')
    assert j.equivalent == EquivalenceJudgment.NO
    assert j.differences == ["或→且"]


def test_parse_l2_response_garbage():
    j = parse_l2_response("不是 JSON")
    assert j.equivalent == EquivalenceJudgment.NO


def test_run_l2_offline_yes_pass():
    r = make_rule()
    out = run_l2_gate_offline([r], {(r.context.board, r.clause_id): L2Judgment(
        equivalent=EquivalenceJudgment.YES)}, RB)[0]
    assert out.status == GateStatus.PASS


def test_run_l2_offline_missing_judgment_fails():
    r = make_rule()
    out = run_l2_gate_offline([r], {}, RB)[0]
    assert out.status == GateStatus.FAIL
    assert out.failure.check_code == "l2-missing"


def test_run_l2_offline_partial_fails():
    r = make_rule()
    out = run_l2_gate_offline([r], {(r.context.board, r.clause_id): L2Judgment(
        equivalent=EquivalenceJudgment.PARTIAL, differences=["语序"])}, RB)[0]
    assert out.status == GateStatus.FAIL


# ── L3 ──

def test_compare_leaf_exact_with_item():
    items = load_items(RB)
    leaf = make_leaf("c_l1", "np_3y_sum", op="ge", threshold=2e8, threshold_text="2 亿元")
    snap = {"item_ref": "np_3y_sum", "op": "ge", "threshold": 2e8,
            "quantifier": "sum", "window": {"kind": "last_n_years", "n": 3}}
    diff = compare_leaf(leaf, snap, items["np_3y_sum"])
    assert diff.category == L3DiffCategory.EXACT


def test_compare_leaf_value_diff_350yi():
    """calibration/0001 实锤案件：主板 sort3 市值快照 350 亿 vs 原文 50 亿"""
    items = load_items(RB)
    leaf = make_leaf("c_l1", "mktcap_forecast", op="ge", threshold=5e9, threshold_text="50 亿元")
    snap = {"item_ref": "mktcap_forecast", "op": "ge", "threshold": 3.5e10}
    diff = compare_leaf(leaf, snap, items["mktcap_forecast"])
    assert diff.category == L3DiffCategory.VALUE_DIFF
    assert "50" in diff.detail or "3.5e10" in diff.detail or "350" in diff.detail


def test_compare_leaf_structure_diff_quantifier():
    items = load_items(RB)
    leaf = make_leaf("c_l1", "np_3y_sum", op="ge", threshold=2e8, threshold_text="2 亿元")
    snap = {"item_ref": "np_3y_sum", "op": "ge", "threshold": 2e8,
            "quantifier": "all_periods"}
    diff = compare_leaf(leaf, snap, items["np_3y_sum"])
    assert diff.category == L3DiffCategory.STRUCTURE_DIFF
    assert "quantifier" in diff.detail


def test_snapshot_key_format():
    assert build_snapshot_key("SSE-MB", "general", 1) == "SSE-MB:general:1"
    assert build_snapshot_key("SSE-MB", "general", None) == "SSE-MB:general:None"


def test_l3_source_only_when_no_snapshot(tmp_path):
    empty = tmp_path / "snap.yaml"
    empty.write_text("snapshot: {}\n", encoding="utf-8")
    r = make_rule()
    results, diffs = run_l3_gate([r], empty, RB)
    assert results[0].payload["diff_category"] == "source_only"
    assert diffs and diffs[0].category == L3DiffCategory.SOURCE_ONLY


def _snap(tmp_path, entry: dict) -> Path:
    import yaml
    p = tmp_path / "snap.yaml"
    p.write_text(yaml.safe_dump({"snapshot": {"SSE-MB:general:1": entry}},
                                allow_unicode=True), encoding="utf-8")
    return p


def test_l3_qualitative_snapshot_leaf_not_reported_as_diff(tmp_path):
    """快照行无数值阈值（行业对比等定性路径）不参与签名比对——
    否则会把「候选 ge」与「快照 None」报成结构差异（批 2/3 各出现 4 次的假 diff）"""
    r = make_rule(leaves=[make_leaf("c1_l1", "rev_3y_cagr", op="ge", threshold=0.1,
                                   threshold_text="10%", quote="复合增长率10%以上")])
    snap = _snap(tmp_path, {"leaves": [
        {"item_ref": "rev_3y_cagr", "op": None, "threshold": None},   # 定性行
        {"item_ref": "rev_3y_cagr", "op": "ge", "threshold": 0.1},     # 数值行
    ]})
    results, diffs = run_l3_gate([r], snap, RB)
    assert results[0].status == GateStatus.PASS
    assert not diffs


def test_l3_boundary_op_diff_flagged_with_boundary_note(tmp_path):
    """同阈值、op 不同（≥ vs ＞）是实锤口径差，须报 structure_diff 并注明「边界含否」"""
    r = make_rule(leaves=[make_leaf("c1_l1", "rev_3y_cagr", op="ge", threshold=0.1,
                                    threshold_text="10%", quote="复合增长率10%以上")])
    snap = _snap(tmp_path, {"leaves": [
        {"item_ref": "rev_3y_cagr", "op": "gt", "threshold": 0.1},
    ]})
    results, diffs = run_l3_gate([r], snap, RB)
    assert results[0].status == GateStatus.FAIL
    assert any(d.category == L3DiffCategory.STRUCTURE_DIFF and "边界含否" in d.detail
               for d in diffs)


def test_l3_group_merge_across_wording_variants(tmp_path):
    """l3_group 同组的两个 item 在 midas 存量里无法区分（措辞拆分所致）→ 对拍按组归并"""
    r = make_rule(leaves=[make_leaf("c1_l1", "self_developed_tech", op="eq",
                                    threshold=True, threshold_format="boolean",
                                    threshold_text="是", quote="拥有自主研发、国际领先技术")])
    snap = _snap(tmp_path, {"leaves": [
        {"item_ref": "self_developed_tech_full", "op": "eq", "threshold": True},
    ]})
    results, diffs = run_l3_gate([r], snap, RB)
    assert results[0].status == GateStatus.PASS, (results[0].failure and
                                                  results[0].failure.reason)
    assert not diffs


def test_midas_diff_report_rendering():
    from ipo_eval_lab.calibration.models import L3Diff
    diffs = [
        L3Diff(clause_id="c1", item_ref="np_3y_sum",
               category=L3DiffCategory.VALUE_DIFF, detail="阈值不同"),
        L3Diff(clause_id="c2", category=L3DiffCategory.SOURCE_ONLY, detail="快照无此条"),
    ]
    report = generate_midas_diff_report(diffs, "2026-11-11")
    assert "midas 存量差异清单" in report
    assert "value_diff" in report and "source_only" in report
    assert "2026-11-11" in report


# ── 置信度 ──

def _gates(l0=GateStatus.PASS, l1b=GateStatus.PASS, l2=GateStatus.PASS,
           l3=GateStatus.PASS, l3_cat="exact", l1b_warn=False):
    def res(gate, status, payload=None, failure=None):
        return GateResult(clause_id="c", gate=gate, status=status,
                          payload=payload, failure=failure)
    out = {
        GateName.L0: res(GateName.L0, l0),
        GateName.L1B: res(GateName.L1B, l1b,
                          payload={"warnings": ["漏"]} if l1b_warn else {"checks": []}),
        GateName.L2: res(GateName.L2, l2),
    }
    if l3 is not None:
        out[GateName.L3] = res(
            GateName.L3, l3, payload={"diff_category": l3_cat} if l3 == GateStatus.PASS else None
        )
    return out


def test_confidence_g4_all_green():
    s = synthesize_confidence(make_rule(), _gates())
    assert s.tier == ConfidenceTier.G4
    assert s.auto_decision == "candidates"


def test_confidence_g3_snapshot_value_diff():
    s = synthesize_confidence(make_rule(), _gates(l3=GateStatus.FAIL))
    assert s.tier == ConfidenceTier.G3
    assert s.auto_decision == "candidates"


def test_confidence_g2_coverage_warning():
    s = synthesize_confidence(make_rule(), _gates(l1b_warn=True))
    assert s.tier == ConfidenceTier.G2
    assert s.auto_decision == "review_queue"


def test_confidence_g1_l0_fail():
    s = synthesize_confidence(make_rule(), _gates(l0=GateStatus.FAIL))
    assert s.tier == ConfidenceTier.G1
    assert s.auto_decision == "review_queue"


def test_confidence_g1_l2_fail():
    s = synthesize_confidence(make_rule(), _gates(l2=GateStatus.FAIL))
    assert s.tier == ConfidenceTier.G1


def test_confidence_g2_when_l3_missing():
    s = synthesize_confidence(make_rule(), _gates(l3=None))
    assert s.tier == ConfidenceTier.G2
    assert s.auto_decision == "review_queue"


def test_confidence_source_only_is_g4():
    s = synthesize_confidence(make_rule(), _gates(l3_cat="source_only"))
    assert s.tier == ConfidenceTier.G4
