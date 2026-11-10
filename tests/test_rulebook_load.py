"""规则库加载与 lint 断言测试（设计 0002 步骤 1+2 样板）。

正向：加载真实 rulebook/ 目录（样板模式，L2 缺口=警告）。
负向：对 model_dump() 副本注入缺陷，断言各 lint 规则触发。
"""
import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from ipo_eval_lab.rulebook import models as M
from ipo_eval_lab.rulebook.loader import RulebookLintError, load_rulebook

REPO = Path(__file__).resolve().parents[1]
RB_DIR = REPO / "rulebook"


@pytest.fixture(scope="module")
def loaded() -> Any:
    return load_rulebook(RB_DIR)


# ── 正向：结构盘点 ──


def test_load_and_inventory(loaded):
    rb = loaded.rulebook
    assert rb.meta.rulebook_version == "rb-2026.11"
    assert len(rb.metrics) == 7
    items = {i.item_id: i for i in rb.items}
    # 扣非成对叶被 measures(lower_of_both) 吸收：四变一（设计 0002 §2.3 算例）
    assert "check12" in items["np_3y_sum"].aliases.midas
    assert "check13" in items["np_latest"].aliases.midas
    # judgment 项：不挂取数结构、必带 pending_evidence（ADR-0003）
    assert items["self_developed_tech"].pending_evidence
    assert items["self_developed_tech"].metric_ref is None
    # ratio 项：分子分母即口径，不挂 metric_ref
    assert items["rd_intensity_3y"].numerator == "rd_investment_total"
    assert items["rd_intensity_3y"].metric_ref is None


def test_star_group_branch_or(loaded):
    star = next(g for g in loaded.rulebook.groups if g.group_id == "star_general_g1")
    assert [b.set_id for b in star.branches] == ["star_general_g1-b1", "star_general_g1-b2"]
    assert star.shared_clauses, "L3：多 branch 必有公共条文"
    np_sum = star.branches[0].clauses[1].leaves[0]
    assert (np_sum.item_ref, np_sum.threshold.value) == ("np_2y_sum", 50000000)


def test_cn_main_clause_any_and_collapse(loaded):
    main_g = next(g for g in loaded.rulebook.groups if g.group_id == "cn_main_general_g1")
    assert set(main_g.boards) == {"SSE-MB", "SZSE-MB"}  # R3：沪深同文共享 group
    or_clause = main_g.branches[0].clauses[0]
    assert or_clause.logic == "any"  # R2-a：单叶内联「或」→ clause any
    assert [lf.item_ref for lf in or_clause.leaves] == ["ocf_3y_sum", "rev_3y_sum"]
    # R2-a collapse：快照两行拆行 alias 到同一 branch
    assert main_g.branches[0].aliases.midas == ["IPO-01", "IPO-02"]


def test_l2_sample_mode_warns(loaded):
    assert loaded.warnings, "样板期（仅 2 个 group）应有 L2 组合覆盖警告"


def test_l2_strict_raises():
    with pytest.raises(RulebookLintError):
        load_rulebook(RB_DIR, strict_global=True)


# ── 负向：注入缺陷 → 对应 lint 触发 ──


def _mutate(loaded, fn) -> None:
    data = loaded.rulebook.model_dump()
    fn(data)
    M.Rulebook.model_validate(data)


def _star(data) -> dict:
    return next(g for g in data["groups"] if g["group_id"] == "star_general_g1")


def test_l4_unknown_item_ref(loaded):
    def bad(d):
        _star(d)["branches"][0]["clauses"][0]["leaves"][0]["item_ref"] = "ghost_item"

    with pytest.raises(ValidationError):
        _mutate(loaded, bad)


def test_l1_format_mismatch(loaded):
    def bad(d):
        # np_2y_sum 挂 net_profit_attrib_parent（yuan → number），改成 percent 必须被拦
        leaf = _star(d)["branches"][0]["clauses"][1]["leaves"][0]
        leaf["threshold"]["format"] = "percent"

    with pytest.raises(ValidationError):
        _mutate(loaded, bad)


def test_l3_multi_branch_requires_shared(loaded):
    def bad(d):
        _star(d)["shared_clauses"] = []

    with pytest.raises(ValidationError):
        _mutate(loaded, bad)


def test_l4_duplicate_midas_alias(loaded):
    def bad(d):
        # 把 IPO-15 再挂到 cn_main 的 branch → midas 别名重复挂载
        main_g = next(g for g in d["groups"] if g["group_id"] == "cn_main_general_g1")
        main_g["branches"][0]["aliases"]["midas"].append("IPO-15")

    with pytest.raises(ValidationError):
        _mutate(loaded, bad)


def test_l6_bad_law_ref(loaded):
    def bad(d):
        _star(d)["shared_clauses"][0]["law_ref"] = "no_such_law#9.9"

    with pytest.raises(ValidationError):
        _mutate(loaded, bad)


# ── 单元：窗口 token 与阈值类型（L5 / Threshold）──


def test_window_token_constraints():
    with pytest.raises(ValidationError):
        M.Window(kind="nth_year")  # 缺 n
    with pytest.raises(ValidationError):
        M.Window(kind="last_n_years", n=5)  # 超出 v1 报告期范围
    with pytest.raises(ValidationError):
        M.Window(kind="latest", n=1)  # latest 不带 n
    assert M.Window(kind="nth_year", n=2).n == 2


def test_threshold_value_type():
    with pytest.raises(ValidationError):
        M.Threshold(value=1, format="boolean")  # boolean 必须真布尔
    with pytest.raises(ValidationError):
        M.Threshold(value=1.5, format="integer")  # integer 必须整数
    with pytest.raises(ValidationError):
        M.Threshold(value=True, format="number")  # number 不接受布尔
    assert M.Threshold(value=0, format="number").value == 0
