"""
M1-U8 最强回归：批次 1 候选 vs 现有两套人工样板（逐条对拍）

样板的权威性：rulebook/sets/*.yaml 是 M2 已冻结、人工核过的样板套。
若 L1a 提取与样板在 item_ref / op / threshold / format / logic 任一项不一致，
本测试失败 —— 这是校准管线「不劣于人工」的底线证明。

覆盖：
- cn_main_general_g1（主板标准一：3 shared + 1 branch[logic=any 双叶]）
- star_general_g1（科创板标准一：1 shared + 2 branch[各 2 clause]）
"""

from pathlib import Path

import pytest
import yaml

from ipo_eval_lab.calibration.pipeline import load_candidates

REPO = Path(__file__).resolve().parents[1]
# 样板套已从正式库（rulebook/sets/，现为 export-official 产物）迁到测试夹具；
# 本测试的语义不变：L1a 候选 vs 人工样板逐条对拍（「不劣于人工」底线）。
SAMPLES = REPO / "tests" / "fixtures" / "rulebook"   # 人工样板套（结构层）
RB = REPO / "rulebook"                               # 正式库（items.yaml 等数据层）
BATCH1 = REPO / "calibration" / "l1a" / "output" / "candidates_batch1.jsonl"


def _load_set(name: str) -> dict:
    with (SAMPLES / "sets" / name).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)[0]


@pytest.fixture(scope="module")
def candidates():
    assert BATCH1.exists(), f"批次 1 候选未生成：{BATCH1}"
    return load_candidates(BATCH1)


@pytest.fixture(scope="module")
def by_clause(candidates):
    return {c.clause_id: c for c in candidates}


def _assert_leaf_matches(cand_leaf, sample_leaf: dict) -> None:
    assert cand_leaf.item_ref == sample_leaf["item_ref"], (
        f"item_ref: {cand_leaf.item_ref} != {sample_leaf['item_ref']}")
    assert cand_leaf.op == sample_leaf["op"], (
        f"{cand_leaf.leaf_id} op: {cand_leaf.op} != {sample_leaf['op']}")
    assert cand_leaf.threshold == sample_leaf["threshold"]["value"], (
        f"{cand_leaf.leaf_id} threshold: {cand_leaf.threshold} != {sample_leaf['threshold']['value']}")
    assert cand_leaf.threshold_format == sample_leaf["threshold"]["format"], (
        f"{cand_leaf.leaf_id} format: {cand_leaf.threshold_format} != {sample_leaf['threshold']['format']}")


def _assert_clause_matches(cand, sample: dict) -> None:
    if "logic" in sample:
        assert cand.clause.logic == sample["logic"], (
            f"{cand.clause_id} logic: {cand.clause.logic} != {sample['logic']}")
    assert len(cand.clause.leaves) == len(sample["leaves"]), (
        f"{cand.clause_id} leaf count: {len(cand.clause.leaves)} != {len(sample['leaves'])}")
    for cand_leaf, sample_leaf in zip(cand.clause.leaves, sample["leaves"]):
        _assert_leaf_matches(cand_leaf, sample_leaf)


def test_cn_main_sample_shared_clauses_match(by_clause):
    sample = _load_set("cn_main_general.yaml")
    for s in sample["shared_clauses"]:
        cand = by_clause[s["clause_id"]]
        _assert_clause_matches(cand, s)


def test_cn_main_sample_branches_match(by_clause):
    sample = _load_set("cn_main_general.yaml")
    for branch in sample["branches"]:
        for s in branch["clauses"]:
            cand = by_clause[s["clause_id"]]
            _assert_clause_matches(cand, s)


def test_star_sample_shared_clauses_match(by_clause):
    sample = _load_set("star_general.yaml")
    for s in sample["shared_clauses"]:
        cand = by_clause[s["clause_id"]]
        _assert_clause_matches(cand, s)


def test_star_sample_branches_match(by_clause):
    sample = _load_set("star_general.yaml")
    for branch in sample["branches"]:
        for s in branch["clauses"]:
            cand = by_clause[s["clause_id"]]
            _assert_clause_matches(cand, s)


def test_sample_coverage_complete(by_clause):
    """样板里的每条 clause 都必须被批次 1 提取到（不能漏）"""
    expected: set[str] = set()
    for name in ("cn_main_general.yaml", "star_general.yaml"):
        sample = _load_set(name)
        expected.update(c["clause_id"] for c in sample.get("shared_clauses", []))
        for branch in sample["branches"]:
            expected.update(c["clause_id"] for c in branch["clauses"])
    missing = expected - set(by_clause)
    assert not missing, f"批次 1 漏提取：{sorted(missing)}"


def test_batch1_quote_all_verbatim(candidates):
    """每条候选的每个 quote 都必须逐字命中原文（R9 地基）"""
    for c in candidates:
        for leaf in c.clause.leaves:
            assert leaf.quote in c.source.text, (
                f"{c.clause_id}/{leaf.leaf_id} quote 未逐字命中")


def test_batch1_all_items_in_whitelist(candidates):
    """item_ref 全部落在 items.yaml 26 项白名单内（L0-4）"""
    import yaml as _yaml
    with (RB / "items.yaml").open("r", encoding="utf-8") as f:
        items = {i["item_id"] for i in _yaml.safe_load(f)}
    for c in candidates:
        for leaf in c.clause.leaves:
            assert leaf.item_ref in items, (
                f"{c.clause_id}/{leaf.leaf_id} item_ref {leaf.item_ref} 不在白名单")
