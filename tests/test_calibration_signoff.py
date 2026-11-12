"""签核队列回归（ADR-0005 R3 两级入库）。

钉住四条不可让步的约定：

1. **分层只按内容风险**：闸门红 / midas 非 exact → A 档必核；两闸皆绿 → C 档抽检。
   黄金集 covered 覆盖**不**单独构成必核——它核的是套结构，不是条款内容。
   （否则 133 条全进 A 档，抽检档永远为空，「黄金集先签 + 分层抽检」名存实亡。）
2. **B 档是套级裁定，不是条款级签核**：一个套若无法律依据，签它每条条款都没意义。
3. **抽样可复现**：同 seed 必得同一批；换 seed 换批。
4. **签核记录 append-only**：同一条可多次签核（改判留痕），取最后一次。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.calibration.signoff import (
    LegalQuestion, SetAdjudicationStatus, SignoffStatus, SignoffTier,
    append_record, apply_records, build_signoff_queue, build_set_adjudications,
    load_records, write_queue,
)


# ── 夹具 ──

def _cand(clause_id, board="SSE-MB", ctype="general", gno=1, article="3.1.2"):
    return {
        "clause_id": clause_id,
        "context": {
            "board": board, "company_type": ctype, "group_no": gno,
            "group_id": f"{board}_{ctype}_g{gno}", "branch_id": None,
            "role": "shared", "scope": "set",
        },
        "clause": {
            "clause_id": clause_id, "law_ref": "sse_main_2026#3.1.2", "logic": "all",
            "display": "最近三年净利润均为正",
            "leaves": [{
                "leaf_id": f"{clause_id}_l1", "item_ref": "np_3y_allpos",
                "op": "gt", "threshold": 0, "threshold_format": "number",
                "threshold_text": "为正", "quote": "最近3 年净利润均为正",
            }],
        },
        "source": {
            "law_id": "sse_main_2026", "article": article, "chapter": None,
            "section": None, "text": "（测试用占位条文）",
        },
    }


GOLDEN = {
    "expectations": [
        {
            "board": "SSE-MB", "company_type": "general", "covered": True,
            "sets": {1: {"snapshot_branches": 2, "expected_branches": 1}},
        },
        {
            "board": "ChiNext", "company_type": "redchip_listed", "covered": False,
            "sets": {1: {"snapshot_branches": 1, "expected_branches": 1},
                     2: {"snapshot_branches": 1, "expected_branches": 1}},
        },
        {
            "board": "SSE-MB", "company_type": "redchip_unlisted", "covered": True,
            "sets": {1: {"snapshot_branches": 1, "expected_branches": 1}},
            "gaps": ["研发阶段/国家战略红筹豁免未编码"],
        },
    ],
}


def _build(cands, gates=None, l3=None, rate=0.2, seed="s1"):
    gates = gates or {}
    l3 = l3 or {}
    return build_signoff_queue(cands, GOLDEN, gates, l3,
                               spot_check_rate=rate, seed=seed)


# ── 1. 分层只按内容风险 ──

def test_gate_failure_goes_to_tier_a():
    items, _ = _build([_cand("c1")], gates={("SSE-MB", "c1"): {"L2": "fail"}})
    assert items[0].tier is SignoffTier.A
    assert any("闸门未通过" in r for r in items[0].reasons)


def test_midas_diff_goes_to_tier_a():
    items, _ = _build([_cand("c1")], l3={("SSE-MB", "general", 1): "value_diff"})
    assert items[0].tier is SignoffTier.A


def test_clean_clause_goes_to_tier_c():
    """闸门全绿 + midas exact → C 档（即便落在黄金集覆盖组合内）。"""
    items, _ = _build([_cand("c1")], gates={("SSE-MB", "c1"): {"L0": "pass"}})
    assert items[0].tier is SignoffTier.C
    # 但黄金集覆盖信息作为依据留存，供审核人参考
    assert any("黄金集覆盖" in r for r in items[0].reasons)


def test_golden_coverage_alone_does_not_force_tier_a():
    """约定 1：黄金集 covered 不单独构成必核。

    否则 133 条候选全部落 A 档、C 档为空——分层形同虚设。
    """
    cands = [_cand(f"c{i}") for i in range(5)]
    items, _ = _build(cands, rate=0.0)
    assert all(it.tier is SignoffTier.C for it in items)


# ── 2. C 档抽样 ──

def test_spot_check_is_deterministic_same_seed():
    cands = [_cand(f"c{i}") for i in range(20)]
    a, _ = _build(cands, rate=0.25, seed="seed-x")
    b, _ = _build(cands, rate=0.25, seed="seed-x")
    assert [it.key for it in a] == [it.key for it in b]
    assert [it.status for it in a] == [it.status for it in b]


def test_spot_check_picks_expected_count():
    cands = [_cand(f"c{i}") for i in range(20)]
    items, _ = _build(cands, rate=0.25)
    pending = [it for it in items if it.status is SignoffStatus.PENDING]
    assert len(pending) == 5          # round(20 × 0.25)
    assert all(it.tier is SignoffTier.C for it in pending)


def test_unpicked_items_are_marked_exempt_not_pending():
    """未抽中的免签（留档），不占审核工作量——但状态要写明是自动免签。"""
    cands = [_cand(f"c{i}") for i in range(10)]
    items, _ = _build(cands, rate=0.2)
    for it in items:
        if it.status is SignoffStatus.ACCEPTED:
            assert "自动免签" in it.notes
            assert any("未落入抽检" in r for r in it.reasons)


# ── 3. B 档是套级裁定 ──

def test_covered_false_produces_set_level_adjudication():
    """约定 2：covered=false → 套级裁定项，不混进条款级队列。"""
    items, adjs = _build([_cand("c1")])
    # 条款级只有 A/C 两档——B（法律适用性裁定）是套级，不占条款档位
    assert {it.tier for it in items} <= {SignoffTier.A, SignoffTier.C}
    keys = [a.key for a in adjs]
    assert "ChiNext:redchip_listed:1:no_anchor" in keys
    assert "ChiNext:redchip_listed:2:no_anchor" in keys


def test_covered_false_set_with_no_candidates_still_adjudicated():
    """候选库里一条都没有的套照样要裁定——那正是「规则库缺套」信号。"""
    _, adjs = _build([_cand("c1")])
    a = [x for x in adjs if x.key.startswith("ChiNext:redchip_listed:1")][0]
    assert a.candidate_clause_count == 0
    assert a.status is SetAdjudicationStatus.PENDING


def test_gap_produces_unencoded_gap_adjudication():
    _, adjs = _build([_cand("c1")])
    gaps = [a for a in adjs if a.question is LegalQuestion.UNENCODED_GAP]
    assert gaps
    assert any("豁免" in (a.gaps[0] if a.gaps else "") for a in gaps)


def test_adjudication_keys_do_not_collide():
    """同一组合的多条 gap 不得撞键（撞键会让两条裁定互相覆盖）。"""
    golden = {
        "expectations": [{
            "board": "SSE-MB", "company_type": "redchip_unlisted", "covered": True,
            "sets": {1: {}},
            "gaps": ["增长认定第三路径无 item", "研发阶段豁免未编码"],
        }],
    }
    adjs = build_set_adjudications(golden, {})
    keys = [a.key for a in adjs]
    assert len(keys) == len(set(keys)) == 2


# ── 4. 落盘与记录 ──

def test_write_queue_outputs_all_files(tmp_path: Path):
    items, adjs = _build([_cand("c1")], rate=0.0)
    stats = write_queue(items, adjs, tmp_path, "2026-11-12")
    q = tmp_path / "signoff-queue"
    assert (q / "items.jsonl").exists()
    assert (q / "pending.jsonl").exists()
    assert (q / "adjudications.jsonl").exists()
    assert (q / "summary.md").exists()
    assert stats["total"] == 1


def test_write_queue_clears_stale_files(tmp_path: Path):
    """上一轮残留会误导审核人——重跑必须清场。"""
    q = tmp_path / "signoff-queue"
    q.mkdir(parents=True)
    (q / "items.jsonl").write_text("stale", encoding="utf-8")
    items, adjs = _build([_cand("c1")], rate=0.0)
    write_queue(items, adjs, tmp_path, "2026-11-12")
    content = (q / "items.jsonl").read_text(encoding="utf-8")
    assert "stale" not in content


def test_records_are_append_only_and_latest_wins(tmp_path: Path):
    """约定 4：改判留痕，历史不可删；状态取最后一次。"""
    path = tmp_path / "records.jsonl"
    from ipo_eval_lab.calibration.signoff import SignoffRecord

    append_record(SignoffRecord(key="SSE-MB:c1", decision=SignoffStatus.ACCEPTED,
                                reviewer="a", at="2026-11-12T10:00:00"), path)
    append_record(SignoffRecord(key="SSE-MB:c1", decision=SignoffStatus.REJECTED,
                                reviewer="b", at="2026-11-12T11:00:00"), path)
    recs = load_records(path)
    assert len(recs) == 2                      # 历史保留
    items, _ = _build([_cand("c1")])
    apply_records(items, recs)
    assert items[0].status is SignoffStatus.REJECTED   # 最新为准


def test_amendment_record_keeps_content(tmp_path: Path):
    from ipo_eval_lab.calibration.signoff import SignoffRecord

    path = tmp_path / "records.jsonl"
    amend = {"threshold": 50e8}
    append_record(SignoffRecord(key="SSE-MB:c1", decision=SignoffStatus.AMENDED,
                                reviewer="a", at="2026-11-12T10:00:00",
                                amendment=amend), path)
    recs = load_records(path)
    assert recs[0].amendment == amend
