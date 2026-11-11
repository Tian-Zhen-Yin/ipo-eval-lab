"""M3 生成器族测试（设计 0006 §7；F5/F6）：±ε 边界族 + knockout 缺数族。

边界族：每变体必须 (a) 通过 CompanyProfile 模型 + 勾稽①~⑥（生成器维持会计网络，
AR4 同一条路复核），(b) 目标叶聚合值精确等于 thr±1（E8 无 ε 的整数验证），
(c) 在 op 两侧各差 1 元必翻转。knockout 族：四变体全部可加载 + E3 三原则的数据前置。
"""
import json
import operator
from pathlib import Path
from typing import Any

import pytest

from ipo_eval_lab.fixtures import CompanyProfile, SanityBounds, check_profile, load_sanity
from ipo_eval_lab.fixtures.generators import boundary_variants, knockout_variants, quantified_value
from ipo_eval_lab.rulebook.loader import load_rulebook
from ipo_eval_lab.rulebook.models import Nature, Op

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"

OPS = {Op.ge: operator.ge, Op.gt: operator.gt, Op.le: operator.le, Op.lt: operator.lt}

# 当前样板规则库中可 ±ε 翻转的 7 个叶。跳过的（规则见 generators.py docstring）：
# 三个 thr=0 叶（np_3y_allpos / np_2y_allpos / star np_latest>0）与 judgment 叶。
# 若往样板套加新的 latest/sum 数值叶，这里的期望集与条数断言会先红——按需扩。
EXPECTED_BOUNDARY_LEAVES = {
    "cn_main_g1_c2_l1",       # np_3y_sum（sum：改 2024 → 三年合计 = thr±1）
    "cn_main_g1_c3_l1",       # np_latest（latest：全序列等比缩放，2024 精确 = thr±1）
    "cn_main_g1_b1_c1_l1",    # ocf_3y_sum
    "cn_main_g1_b1_c1_l2",    # rev_3y_sum
    "star_g1_c0_l1",          # mktcap_forecast（documentary：底稿值 = thr±1）
    "star_g1_b1_c2_l1",       # np_2y_sum
    "star_g1_b2_c2_l1",       # rev_latest
}


@pytest.fixture(scope="module")
def sanity() -> SanityBounds:
    return load_sanity(FX / "sanity.yaml")


@pytest.fixture(scope="module")
def rb():
    return load_rulebook(REPO / "rulebook").rulebook


@pytest.fixture(scope="module")
def base_dict() -> dict[str, Any]:
    return json.loads((FX / "companies" / "base_co_2029" / "profile.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def leaves_and_items(rb):
    leaves: dict[str, Any] = {}
    items = {i.item_id: i for i in rb.items}
    for g in rb.groups:
        for c in [*g.shared_clauses, *(cl for b in g.branches for cl in b.clauses)]:
            for lf in c.leaves:
                leaves[lf.leaf_id] = lf
    return leaves, items


# ── ±ε 边界族（F5）──


def test_boundary_coverage(rb, base_dict):
    variants = boundary_variants(rb, base_dict)
    names = {v.name for v in variants}
    assert len(variants) == 14  # 7 叶 × {thr+1, thr−1}
    for leaf_id in EXPECTED_BOUNDARY_LEAVES:
        assert f"{leaf_id}__plus" in names, f"缺 {leaf_id}__plus"
        assert f"{leaf_id}__minus" in names, f"缺 {leaf_id}__minus"


def test_boundary_variants_loadable_and_flip(rb, base_dict, sanity, leaves_and_items):
    leaves, items = leaves_and_items
    for v in boundary_variants(rb, base_dict):
        leaf, item = leaves[v.leaf_id], items[v.item_id]

        # (a) 变体是合法 profile：模型 + 勾稽①~⑥全过（生成器不得产出过不了 loader 的数据）
        profile = CompanyProfile.model_validate(v.profile)
        check_profile(profile, sanity)

        # (b) 目标叶聚合值精确 = thr ± 1
        if item.nature is Nature.documentary:
            value = profile.documentary.mktcap_self_estimate.value
        else:
            value = quantified_value(v.profile, item)
        delta = 1 if v.name.endswith("plus") else -1
        assert value == v.expected_value == leaf.threshold.value + delta, v.name

        # (c) 阈值两侧精确翻转（E8：比较无 ε，1 元之差必换态）
        assert OPS[leaf.op](value, leaf.threshold.value) == (v.expected_state == "met"), v.name


def test_latest_variant_preserves_growth_trajectory(rb, base_dict, sanity):
    """latest 变体的等比缩放：末年精确落 thr−1，其余年保**判定口径（逐年孰低）**的同比轨迹。

    若直改单年（0.4 → 1 亿），2023→2024 同比 = +233% 虽仍在区间内，但轨迹被末年跳变
    扭曲；缩放让边界值「长在同一家公司上」。缩放的基准是孰低序列（叶的判定口径）：
    base 1.44 → 0.3 亿 = −79.2%（申报序列的 −80% 剧情不受影响，仍在区间内）。
    """
    by_name = {v.name: v for v in boundary_variants(rb, base_dict)}
    v = by_name["cn_main_g1_c3_l1__minus"]  # np_latest，thr = 1 亿
    profile = CompanyProfile.model_validate(v.profile)
    check_profile(profile, sanity)  # ⑥ 全过本身即轨迹未破的证据

    s22, s23, s24 = profile.statements
    np22 = s22.income.net_profit_attrib_parent.as_reported
    np23 = s23.income.net_profit_attrib_parent.as_reported
    assert s24.income.net_profit_attrib_parent.as_reported == 99_999_999  # 末年精确
    g_base = (30_000_000 - 144_000_000) / 144_000_000  # base 孰低序列 2022→2023 同比
    g = (np23 - np22) / np22
    assert abs(g - g_base) < 0.001  # 缩放版保持同一轨迹（取整误差 < 0.1%）


# ── knockout 缺数族（F6）──


def test_knockout_variants(base_dict, sanity, leaves_and_items):
    _, items = leaves_and_items
    vs = {v.name: v for v in knockout_variants(base_dict)}
    assert set(vs) == {"drop_2022", "null_excl_2023", "null_mktcap", "qualified_2023"}

    # 四变体全部是合法 profile：删项/置空/改意见不破坏勾稽①~⑥
    for v in vs.values():
        check_profile(CompanyProfile.model_validate(v.profile), sanity)

    # E3-1 叶级隔离（数据前置）：缺 2022 只杀含 2022 的窗口，两年/最新窗口照常有值
    p = vs["drop_2022"].profile
    assert [s["fiscal_year"] for s in p["statements"]] == [2023, 2024]
    assert quantified_value(p, items["np_3y_sum"]) is None  # 窗口 {2022..2024} 缺年 → 未定义
    assert quantified_value(p, items["np_2y_sum"]) == 70_000_000  # {2023, 2024} 照常
    assert quantified_value(p, items["np_latest"]) == 40_000_000  # {2024} 照常

    # E3-2 无静默回退（数据前置）：扣非缺 → 整叶无值，不用申报值顶替
    p = vs["null_excl_2023"].profile
    assert quantified_value(p, items["np_3y_sum"]) is None
    assert quantified_value(p, items["np_2y_sum"]) is None  # 窗口含 2023 → 同杀
    assert quantified_value(p, items["np_latest"]) == 40_000_000  # 不含 2023 → 照常

    # G-C：市值自估置空（base 即此形态，变体保形供引擎回归对照）
    assert vs["null_mktcap"].profile["documentary"]["mktcap_self_estimate"] is None

    # E3-3 审计覆盖降级（数据前置）：意见改 qualified，财务数据本身一字不动
    p = vs["qualified_2023"].profile
    assert p["statements"][1]["audit"]["opinion"] == "qualified"
    assert p["statements"][1]["income"]["net_profit_attrib_parent"]["as_reported"] == 30_000_000
