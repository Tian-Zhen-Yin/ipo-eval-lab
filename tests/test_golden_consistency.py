"""golden ↔ 规则库实物 ID 一致性（设计 0006 §6：golden 绑 rulebook_version，ID 用实物）。

引擎（M4）未落地前，这道测试防 golden 与规则库各自漂移：
套 / 条款 / 叶 / 指标任一 ID 改名，先红这里——而不是等到引擎对不上。
另锁 coverage 分母的隐含前提（两套各 5 叶）与 progress 定稿值。
"""
import json
from pathlib import Path
from typing import Any

import pytest

from ipo_eval_lab.rulebook.loader import load_rulebook

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "fixtures" / "companies" / "base_co_2029" / "expected" / "summary.json"


@pytest.fixture(scope="module")
def golden() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rb():
    return load_rulebook(REPO / "rulebook").rulebook


def _group(rb, group_id):
    return next(g for g in rb.groups if g.group_id == group_id)


def _leaf_ids(group) -> list[str]:
    ids = [lf.leaf_id for c in group.shared_clauses for lf in c.leaves]
    for b in group.branches:
        ids.extend(lf.leaf_id for c in b.clauses for lf in c.leaves)
    return ids


def _clause_ids(group) -> list[str]:
    ids = [c.clause_id for c in group.shared_clauses]
    for b in group.branches:
        ids.extend(c.clause_id for c in b.clauses)
    return ids


def test_golden_binds_rulebook_version(golden, rb):
    assert golden["rulebook_version"] == rb.meta.rulebook_version == "rb-2026.11"


def test_set_ids_are_real_group_ids(golden, rb):
    real = {g.group_id for g in rb.groups}
    assert set(golden["sets"]) <= real
    assert set(golden["progress"]) == set(golden["sets"])  # progress 逐套成对出现（不变量 10）


def test_blockers_are_real_items(golden, rb):
    item_ids = {i.item_id for i in rb.items}
    for entry in golden["sets"].values():
        assert set(entry["blockers"]) <= item_ids


def test_progress_pinned_values(golden):
    """进度/覆盖率定稿值（设计 0005 §5.2 / 0006 §6.1）——主板 40/100，科创板 100/80。

    科创板 100/80 是双指标必要性的活例：市值叶未定义 → 不进聚合（progress 仍 100）
    但计入覆盖分母（coverage 80）。
    """
    assert golden["progress"]["cn_main_general_g1"] == {
        "progress": 40,
        "coverage": 100,
        "binding_clause_id": "cn_main_g1_c3",
        "next_binding_clause_id": "cn_main_g1_c2",
    }
    assert golden["progress"]["star_general_g1"] == {
        "progress": 100,
        "coverage": 80,
        "binding_clause_id": None,
        "next_binding_clause_id": None,
    }


def test_binding_clauses_exist_in_their_set(golden, rb):
    main_clauses = set(_clause_ids(_group(rb, "cn_main_general_g1")))
    p = golden["progress"]["cn_main_general_g1"]
    assert p["binding_clause_id"] in main_clauses  # 卡点 = 最近一年净利条款
    assert p["next_binding_clause_id"] in main_clauses  # 次弱 = 净利累计条款
    assert golden["progress"]["star_general_g1"]["binding_clause_id"] is None  # 已定义叶全 1.0 → 无卡点


def test_key_check_ids_exist(golden, rb):
    item_ids = {i.item_id for i in rb.items}
    main = _group(rb, "cn_main_general_g1")
    leaves, clauses = set(_leaf_ids(main)), set(_clause_ids(main))

    leaf_checks = [k for k in golden["key_checks"] if "leaf_id" in k]
    clause_checks = [k for k in golden["key_checks"] if "clause_id" in k]
    assert len(leaf_checks) + len(clause_checks) == len(golden["key_checks"])

    for k in leaf_checks:
        assert k["leaf_id"] in leaves
        assert k["item_ref"] in item_ids
    for k in clause_checks:
        assert k["clause_id"] in clauses  # Kleene OR 活例挂在择一条文上


def test_window_roll_leaf_exists(golden, rb):
    main = _group(rb, "cn_main_general_g1")
    for w in golden["window_roll"]:
        assert w["leaf_id"] in set(_leaf_ids(main))
        assert w["risk"] in {"low", "medium", "high"}


def test_coverage_denominator_leaf_counts(golden, rb):
    """coverage 分母的隐含前提：两套各 5 叶（100 = 5/5；80 = 4/5）。

    若有人往样板套加/删叶子，golden 的 coverage 语义就变了——先红这里。
    """
    assert len(_leaf_ids(_group(rb, "cn_main_general_g1"))) == 5
    assert len(_leaf_ids(_group(rb, "star_general_g1"))) == 5
