"""M1 校准管线单元测试（U1~U5）。"""
from pathlib import Path
from datetime import datetime

import pytest

from ipo_eval_lab.calibration.models import (
    CandidateRule, CandidateClause, CandidateLeaf, SourceClauseRef,
    GateName, GateStatus, GateFailure, L0CheckCode, L1bCheckCode,
    L3DiffCategory, L2Judgment, EquivalenceJudgment, ConfidenceTier,
)
from ipo_eval_lab.calibration.l0_gate import (
    run_l0_gate, check_schema, check_uniqueness, check_window_enum,
    check_version_alignment,
)
from ipo_eval_lab.calibration.l1b_gate import (
    check_quote_verbatim, check_numeric_anchor, check_coverage_scan,
    normalize_chinese_number, extract_numbers_from_text, run_l1b_gate,
)
from ipo_eval_lab.calibration.l2_gate import (
    render_leaf, render_clause, render_candidate, build_l2_prompt,
    parse_l2_response, run_l2_gate_offline,
)
from ipo_eval_lab.calibration.l3_gate import (
    compare_leaf, build_snapshot_key, generate_midas_diff_report,
)


# ── 测试夹具 ──


def make_leaf(leaf_id="c1_l1", item_ref="profit_3y_cum", quantifier="sum",
              window="last_3_years", op="GE", threshold=2e8,
              threshold_format="2亿元", quote="最近三个会计年度净利润累计不低于2亿元"):
    return CandidateLeaf(
        leaf_id=leaf_id, item_ref=item_ref, quantifier=quantifier,
        window=window, op=op, threshold=threshold,
        threshold_format=threshold_format, quote=quote,
    )


def make_candidate(clause_id="SSE-MB:general:1:branch-a",
                   leaves=None, logic="all", text="最近三个会计年度净利润累计不低于2亿元"):
    leaves = leaves or [make_leaf()]
    return CandidateRule(
        clause_id=clause_id,
        source=SourceClauseRef(
            law_id="sse_main_2026", article="3.1.2",
            text=text,
        ),
        candidate=CandidateClause(
            clause_id=clause_id,
            law_ref="sse_main_2026#3.1.2",
            logic=logic,
            leaves=leaves,
        ),
        evidence={"law_id": "sse_main_2026", "article": "3.1.2",
                  "effective_from": "2026-04-30", "board": "SSE-MB",
                  "company_type": "general", "group_no": "1"},
        model_provider="agent",
        model_name="session",
    )


# ── L0 闸门测试 ──


def test_l0_schema_valid_pass():
    c = make_candidate()
    assert check_schema(c) == []


def test_l0_schema_invalid_quantifier():
    c = make_candidate(leaves=[make_leaf(quantifier="total")])
    fails = check_schema(c)
    assert len(fails) >= 1
    assert fails[0].check_code == L0CheckCode.SCHEMA_VALID
    assert "quantifier" in fails[0].reason


def test_l0_schema_invalid_window():
    c = make_candidate(leaves=[make_leaf(window="2000_to_2002")])
    fails = check_schema(c)
    assert any(f.check_code == L0CheckCode.SCHEMA_VALID for f in fails)


def test_l0_uniqueness_duplicate():
    c1 = make_candidate("dup_id", leaves=[make_leaf()])
    c2 = make_candidate("dup_id", leaves=[make_leaf()])
    fails = check_uniqueness([c1, c2])
    assert len(fails) >= 1
    assert fails[0].check_code == L0CheckCode.UNIQUENESS


def test_l0_window_enum_manual_range():
    c = make_candidate(leaves=[make_leaf(window="2019-2021")])
    fails = check_window_enum([c])
    assert len(fails) == 1
    assert fails[0].check_code == L0CheckCode.WINDOW_ENUM


def test_l0_version_alignment_old_version():
    c = make_candidate()
    c.evidence["effective_from"] = "2027-01-01"
    fails = check_version_alignment([c], "2026-11-11")
    assert len(fails) == 1
    assert fails[0].check_code == L0CheckCode.VERSION_ALIGN


def test_l0_gate_full_pass():
    c = make_candidate()
    results = run_l0_gate([c], "2026-11-11",
                          Path("rulebook/metrics.yaml"), Path("rulebook"))
    assert len(results) == 1
    assert results[0].status == GateStatus.PASS


def test_l0_gate_blocks_on_failure():
    c = make_candidate(leaves=[make_leaf(quantifier="invalid")])
    results = run_l0_gate([c], "2026-11-11",
                          Path("rulebook/metrics.yaml"), Path("rulebook"))
    assert results[0].status == GateStatus.FAIL
    assert results[0].failure is not None


# ── L1b 闸门测试 ──


def test_normalize_chinese_number():
    assert normalize_chinese_number("五十亿") == pytest.approx(5e9)
    assert normalize_chinese_number("5000万") == pytest.approx(5e7)
    assert normalize_chinese_number("15%") == pytest.approx(0.15)


def test_extract_numbers_from_text():
    text = "最近三个会计年度净利润累计不低于2亿元，且最近一年营业收入不低于1亿元"
    nums = extract_numbers_from_text(text)
    assert len(nums) >= 2  # 2亿 and 1亿


def test_l1b_quote_verbatim_pass():
    c = make_candidate(text="最近三个会计年度净利润累计不低于2亿元")
    assert check_quote_verbatim(c) == []


def test_l1b_quote_verbatim_fail():
    c = make_candidate(
        text="最近三个会计年度净利润累计不低于2亿元",
        leaves=[make_leaf(quote="最近三个会计年度净利润累计不低于3亿元")],
    )
    fails = check_quote_verbatim(c)
    assert len(fails) == 1
    assert fails[0].check_code == L1bCheckCode.QUOTE_VERBATIM


def test_l1b_numeric_anchor_fail():
    c = make_candidate(
        text="最近三个会计年度净利润累计不低于2亿元",
        leaves=[make_leaf(threshold=5e8, threshold_format="5亿元")],
    )
    fails = check_numeric_anchor(c, {})
    assert len(fails) >= 1
    assert fails[0].check_code == L1bCheckCode.NUMERIC_ANCHOR


def test_l1b_coverage_scan_missed_threshold():
    c = make_candidate(
        text="最近三个会计年度净利润累计不低于2亿元，且最近一年营业收入不低于1亿元",
        leaves=[make_leaf()],  # 只提取了净利润，漏了营收
    )
    fails = check_coverage_scan(c)
    assert len(fails) >= 1
    assert fails[0].check_code == L1bCheckCode.COVERAGE_SCAN


def test_l1b_gate_full_pass():
    c = make_candidate()
    results = run_l1b_gate([c], Path("config/anchor_normalization.yaml"))
    assert results[0].status == GateStatus.PASS


def test_l1b_gate_fails_on_bad_quote():
    c = make_candidate(
        leaves=[make_leaf(quote="完全编造的引文")]
    )
    results = run_l1b_gate([c], Path("config/anchor_normalization.yaml"))
    assert results[0].status == GateStatus.FAIL


# ── L2 渲染器测试 ──


def test_render_leaf_sum():
    leaf = make_leaf()
    out = render_leaf(leaf)
    assert "累计" in out
    assert "2亿元" in out
    assert "不低于" in out


def test_render_leaf_all_periods_positive():
    leaf = make_leaf(quantifier="all_periods", op="GT", threshold=0,
                     threshold_format="0元")
    out = render_leaf(leaf)
    assert "均为正" in out


def test_render_clause_all_logic():
    clause = CandidateClause(
        clause_id="c1", law_ref="sse_main_2026#3.1.2", logic="all",
        leaves=[make_leaf("c1_l1"), make_leaf("c1_l2", item_ref="rev_1y")],
    )
    out = render_clause(clause)
    assert "同时满足" in out
    assert "且" in out


def test_render_clause_any_logic():
    clause = CandidateClause(
        clause_id="c1", law_ref="sse_main_2026#3.1.2", logic="any",
        leaves=[make_leaf("c1_l1"), make_leaf("c1_l2", item_ref="rev_1y")],
    )
    out = render_clause(clause)
    assert "满足下列条件之一" in out
    assert "或" in out


def test_build_l2_prompt_contains_source_and_rendered():
    c = make_candidate()
    system, user, rendered = build_l2_prompt(c)
    assert c.source.text in user
    assert rendered in user
    assert "NLI" in system or "等价" in system


def test_parse_l2_response_yes():
    j = parse_l2_response('{"equivalent": "yes", "differences": []}')
    assert j.equivalent == EquivalenceJudgment.YES


def test_parse_l2_response_invalid_json():
    j = parse_l2_response("not json")
    assert j.equivalent == EquivalenceJudgment.NO
    assert len(j.differences) >= 1


def test_run_l2_gate_offline_pass():
    c = make_candidate()
    judgments = {c.clause_id: L2Judgment(
        equivalent=EquivalenceJudgment.YES, differences=[], rendered_text="")}
    results = run_l2_gate_offline([c], judgments)
    assert results[0].status == GateStatus.PASS


def test_run_l2_gate_offline_fail_or_partial():
    c = make_candidate()
    judgments = {c.clause_id: L2Judgment(
        equivalent=EquivalenceJudgment.PARTIAL,
        differences=["量词不同：累计 vs 各期"], rendered_text="")}
    results = run_l2_gate_offline([c], judgments)
    assert results[0].status == GateStatus.FAIL


def test_run_l2_gate_offline_missing_judgment():
    c = make_candidate()
    results = run_l2_gate_offline([c], {})
    assert results[0].status == GateStatus.FAIL


# ── L3 快照闸门测试 ──


def test_compare_leaf_exact():
    leaf = make_leaf()
    snap = {"leaf_id": "c1_l1", "op": "GE", "quantifier": "sum",
            "window": "last_3_years", "threshold": 2e8}
    diff = compare_leaf(leaf, snap)
    assert diff.category == L3DiffCategory.EXACT


def test_compare_leaf_value_diff():
    leaf = make_leaf(threshold=5e8)  # 候选 5亿
    snap = {"leaf_id": "c1_l1", "op": "GE", "quantifier": "sum",
            "window": "last_3_years", "threshold": 3.5e10}  # 快照 350亿
    diff = compare_leaf(leaf, snap)
    assert diff.category == L3DiffCategory.VALUE_DIFF


def test_compare_leaf_structure_diff():
    leaf = make_leaf()
    snap = {"leaf_id": "c1_l1", "op": "GT", "quantifier": "sum",
            "window": "last_3_years", "threshold": 2e8}
    diff = compare_leaf(leaf, snap)
    assert diff.category == L3DiffCategory.STRUCTURE_DIFF


def test_snapshot_key_format():
    key = build_snapshot_key("SSE-MB", "general", "1")
    assert key == "SSE-MB:general:1"


def test_generate_midas_diff_report():
    from ipo_eval_lab.calibration.models import L3Diff
    diffs = [
        L3Diff(leaf_id="c1_l1", category=L3DiffCategory.VALUE_DIFF,
               detail="阈值不同：500000000.0 vs 35000000000.0"),
        L3Diff(leaf_id="c2_l1", category=L3DiffCategory.SOURCE_ONLY,
               detail="快照无此条"),
    ]
    report = generate_midas_diff_report(diffs)
    assert "midas 存量差异清单" in report
    assert "value_diff" in report
    assert "source_only" in report
