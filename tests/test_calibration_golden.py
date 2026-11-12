"""
M1-U6 黄金集校准夹具（设计 0003 §9 / R11）

三个量化维度：
1. 结构对拍：候选按 (board, company_type) 聚合的套数/支路数 vs 0001 归组表（43 套）。
   「套」锚定 midas 官方套号（L3 对齐键 group_no 的来源）——group 粒度错误在此暴露。
2. 毒株 false-pass：注入 0001 §3 实锤错误（350亿笔误、2.5 单位错、序号重复、引文编造），
   断言全部被 L0/L1b 拦截（false_pass == 0，硬指标）。
3. 误拦率 false-block：全量候选被硬拦（g1）比例 < 10%（防审核疲劳放水）。
"""

from collections import defaultdict
from pathlib import Path

import pytest
import yaml

from ipo_eval_lab.calibration.models import CandidateRule
from ipo_eval_lab.calibration.l0_gate import run_l0_gate
from ipo_eval_lab.calibration.l1b_gate import run_l1b_gate
from ipo_eval_lab.calibration.pipeline import load_candidates

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "calibration" / "golden" / "golden_sets.yaml"
MERGED = REPO / "calibration" / "l1a" / "output" / "candidates_merged.jsonl"
ANCHOR = REPO / "config" / "anchor_normalization.yaml"


def _golden() -> dict:
    with GOLDEN.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def candidates() -> list[CandidateRule]:
    assert MERGED.exists(), f"合并候选未生成：{MERGED}"
    return load_candidates(MERGED)


# ── 1. 结构对拍 ──

def test_structure_matches_golden_sets(candidates):
    golden = _golden()
    by_combo: dict[tuple, dict[int, set]] = defaultdict(lambda: defaultdict(set))
    for c in candidates:
        gno = c.context.group_no
        if gno is None:
            continue
        key = (c.context.board, c.context.company_type)
        if c.context.role == "branch" and c.context.branch_id:
            by_combo[key][gno].add(c.context.branch_id)

    errors: list[str] = []
    for exp in golden["expectations"]:
        if not exp["covered"]:
            continue
        key = (exp["board"], exp["company_type"])
        got_sets = by_combo.get(key, {})
        want_nos = {int(k) for k in exp["sets"]}
        got_nos = set(got_sets)
        if got_nos != want_nos:
            errors.append(
                f"{key}: 套号 {sorted(got_nos)} ≠ 黄金集 {sorted(want_nos)}（group 粒度错？）"
            )
            continue
        for gno, want in exp["sets"].items():
            want_branches = want["expected_branches"]
            got_branches = len(got_sets[int(gno)])
            if got_branches != want_branches:
                errors.append(
                    f"{key} 套{gno}: 支路数 {got_branches} ≠ 期望 {want_branches}"
                    f"（快照行数 {want['snapshot_branches']}）"
                )
    assert not errors, "结构对拍失败：\n  " + "\n  ".join(errors)


def test_uncovered_combinations_not_yet_extracted(candidates):
    """未覆盖组合不许悄悄出现（出现即应更新 golden 的 covered 标记加严）"""
    golden = _golden()
    covered = {(e["board"], e["company_type"])
               for e in golden["expectations"] if e["covered"]}
    present = {(c.context.board, c.context.company_type) for c in candidates}
    sneaky = present - covered
    assert not sneaky, f"出现未登记组合 {sneaky}——请更新 golden_sets.yaml 的 covered"


# ── 2. 毒株 false-pass = 0 ──

def test_poison_cases_all_caught(candidates):
    golden = _golden()
    by_id = {(c.context.board, c.clause_id): c for c in candidates}

    for case in golden["poison_cases"]:
        base = by_id[("SSE-MB", case["base_clause"])]
        poison = case["poison"]

        # 在全量上下文里替换毒株（闸门有批次级检查如 0-6，单条跑会误触发）
        if poison.get("duplicate"):
            rules = list(candidates) + [base.model_copy(deep=True)]  # 同 board 同 clause_id 复制一份
            l0 = run_l0_gate(rules, "2026-11-11", REPO / "rulebook")
            fails = [r for r in l0
                     if r.status.value == "fail" and r.clause_id == base.clause_id]
            assert fails, f"毒株未拦：{case['name']}（0-3 应拦同 board 重复）"
            assert any(r.failure.check_code == "0-3" for r in fails), case["name"]
            continue

        bad = base.model_copy(deep=True)
        leaf = bad.clause.leaves[0]
        if "threshold" in poison:
            leaf.threshold = poison["threshold"]
        if "threshold_text" in poison:
            leaf.threshold_text = poison["threshold_text"]
        if "quote" in poison:
            leaf.quote = poison["quote"]

        rules = [bad if (c.context.board, c.clause_id) == ("SSE-MB", case["base_clause"]) else c
                 for c in candidates]
        l0_all = {(r.clause_id): r for r in run_l0_gate(rules, "2026-11-11", REPO / "rulebook")}
        l0 = l0_all[bad.clause_id]
        assert l0.status.value == "pass", f"{case['name']}: L0 误拦（应交给 L1b 抓）：{l0.failure.reason if l0.failure else ''}"
        l0_pass = [c for c in rules if l0_all[c.clause_id].status.value == "pass"]
        l1b = {(r.clause_id, c.context.board): r
               for c, r in zip(l0_pass, run_l1b_gate(l0_pass, ANCHOR))}
        assert l1b[(bad.clause_id, "SSE-MB")].status.value == "fail", (
            f"毒株漏放（false-pass）: {case['name']} —— {case['must_be_caught_by']}"
        )


# ── 3. 误拦率 < 10% ──

def test_false_block_rate_below_10_percent(candidates):
    l0 = {r.clause_id: r for r in run_l0_gate(candidates, "2026-11-11", REPO / "rulebook")}
    l0_pass = [c for c in candidates if l0[c.clause_id].status.value == "pass"]
    l1b = {r.clause_id: r for r in run_l1b_gate(l0_pass, ANCHOR)}
    hard_blocked = [c for c in candidates
                    if (l0[c.clause_id].status.value == "fail")
                    or (c in l0_pass and l1b[c.clause_id].status.value == "fail")]
    rate = len(hard_blocked) / len(candidates) * 100
    # 打印供批次报告引用
    print(f"\nfalse-block: {len(hard_blocked)}/{len(candidates)} = {rate:.1f}%")
    assert rate < 10, f"误拦率 {rate:.1f}% ≥ 10%（审核疲劳风险）"
