"""T3：Calc 节点（窗口 token / 六量词 / 五态 / 差距三分列）。

对应票 .scratch/m4-engine/issues/03；语义单点 = 设计 0005 §3/§4。
票面「非标 → indeterminate」是简写，实按 §4.4-3 两分：**非标意见年涉叶 → needs_review；
未审计年涉叶 → indeterminate**（两降级样本各测一条）。
"""
import json
import math
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.engine.calc import _CMP, cagr, evaluate_leaf, evaluate_leaves
from ipo_eval_lab.engine.fetch import build_facts
from ipo_eval_lab.fixtures import CompanyProfile, load_profile
from ipo_eval_lab.rulebook.loader import load_rulebook
from ipo_eval_lab.rulebook.models import BasisKind, Item, Leaf, Lever, Nature, Op, Threshold, ThresholdFormat

REPO = Path(__file__).resolve().parents[1]
RB_DIR = REPO / "rulebook"
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
QUAL = FX / "companies" / "qualified_audit"
UNAUD = FX / "companies" / "unaudited_2023"
GOLDEN = BASE / "expected" / "summary.json"


@pytest.fixture(scope="module")
def ctx_base():
    return run_eval(company_dir=BASE, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")


def _check(ctx, leaf_id):
    return next(c for c in ctx.facts["checks"] if c["leaf_id"] == leaf_id)


# ── 甲公司主板 5 叶：定稿表 + golden 对拍 ──


def test_main_board_five_leaves(ctx_base):
    c1 = _check(ctx_base, "cn_main_g1_c1_l1")
    assert (c1["state"], c1["value"]) == ("met", 30_000_000)  # all_periods：value=窗口最小值
    c2 = _check(ctx_base, "cn_main_g1_c2_l1")
    assert (c2["state"], c2["value"]) == ("met", 214_000_000)  # 累计孰低 2.14 亿
    c3 = _check(ctx_base, "cn_main_g1_c3_l1")
    assert c3["state"] == "not_met"
    assert c3["value"] == 40_000_000
    assert c3["diff"] == 60_000_000  # golden：差 6000 万
    assert math.isclose(c3["gap_ratio"], 0.6, rel_tol=1e-9)
    ocf = _check(ctx_base, "cn_main_g1_b1_c1_l1")
    assert (ocf["state"], ocf["value"], ocf["diff"]) == ("not_met", 180_000_000, 20_000_000)
    rev = _check(ctx_base, "cn_main_g1_b1_c1_l2")
    assert (rev["state"], rev["value"]) == ("met", 1_600_000_000)


def test_golden_key_checks_leaf_level(ctx_base):
    """golden key_checks 叶级两条逐字对拍；OR 条文级（clause met）随 T4 折叠点亮。"""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    kc_np_latest = next(k for k in golden["key_checks"] if k.get("item_ref") == "np_latest")
    c3 = _check(ctx_base, "cn_main_g1_c3_l1")
    assert c3["state"] == kc_np_latest["state"] and c3["diff"] == kc_np_latest["diff"]
    kc_np_sum = next(k for k in golden["key_checks"] if k.get("item_ref") == "np_3y_sum")
    assert _check(ctx_base, "cn_main_g1_c2_l1")["state"] == kc_np_sum["state"]
    # OR 活例两侧（clause 级 met 判定在 T4）：
    assert _check(ctx_base, "cn_main_g1_b1_c1_l1")["state"] == "not_met"  # 现金流支路
    assert _check(ctx_base, "cn_main_g1_b1_c1_l2")["state"] == "met"  # 营收支路


def test_star_set_leaves(ctx_base):
    mktcap = _check(ctx_base, "star_g1_c0_l1")
    assert mktcap["state"] == "indeterminate"  # G-C：自估缺数据
    assert "G-C" in mktcap["reason"]
    assert _check(ctx_base, "star_g1_b1_c1_l1")["state"] == "met"  # 两年均为正
    assert _check(ctx_base, "star_g1_b1_c2_l1")["value"] == 70_000_000  # 3000+4000 万
    assert _check(ctx_base, "star_g1_b2_c1_l1")["state"] == "met"  # 最近年净利 > 0
    assert _check(ctx_base, "star_g1_b2_c2_l1")["value"] == 680_000_000


def test_check_metadata_and_count(ctx_base):
    checks = ctx_base.facts["checks"]
    assert len(checks) == 10  # 主板 5 + 科创板 5
    c3 = _check(ctx_base, "cn_main_g1_c3_l1")
    assert c3["group_id"] == "cn_main_general_g1" and c3["set_id"] is None  # shared clause
    b1 = _check(ctx_base, "cn_main_g1_b1_c1_l1")
    assert b1["set_id"] == "cn_main_general_g1-b1" and b1["clause_logic"] == "any"


# ── 窗口与缺数（E2 / E3）──


def _facts_of(mutate):
    data = load_profile(BASE / "profile.json").model_dump(mode="json")
    mutate(data)
    profile = CompanyProfile.model_validate(data)
    rb = load_rulebook(RB_DIR).rulebook
    facts = build_facts(rb, profile)
    return rb, facts


def test_window_insufficient_indeterminate_no_shrink():
    """窗口不足 → indeterminate（不缩窗/不外推/不补零）；np_latest 不受传染（叶级隔离）。"""

    def m(d):
        d["statements"] = [s for s in d["statements"] if s["fiscal_year"] != 2022]

    rb, facts = _facts_of(m)
    checks = {c["leaf_id"]: c for c in evaluate_leaves(rb, facts, rb.groups)}
    np_sum = checks["cn_main_g1_c2_l1"]
    assert np_sum["state"] == "indeterminate" and np_sum["value"] is None
    assert "窗口需 [2022, 2023, 2024]" in np_sum["reason"]
    assert "实有 [2023, 2024]" in np_sum["reason"]
    assert checks["cn_main_g1_c3_l1"]["state"] == "not_met"  # 只看 2024，照常判


def test_excl_null_kills_3y_leaves_not_latest():
    """扣非缺 → 含该年的叶 indeterminate（null≠0：若按 0 会算成 not_met 1.84 亿）。"""

    def m(d):
        d["statements"][1]["income"]["net_profit_attrib_parent"]["excl_nonrecurring"] = None

    rb, facts = _facts_of(m)
    checks = {c["leaf_id"]: c for c in evaluate_leaves(rb, facts, rb.groups)}
    np_sum = checks["cn_main_g1_c2_l1"]
    assert np_sum["state"] == "indeterminate"
    assert np_sum["value"] is None  # null 永不进比较（midas null→0 病灶的对照）
    assert "扣非" in np_sum["reason"]
    assert checks["cn_main_g1_c3_l1"]["state"] == "not_met"  # 2024 完好


# ── CAGR 修正公式（评审 0004 P0 防回归）──


def test_cagr_corrected_formula():
    assert math.isclose(cagr([100, 110, 121]), 0.1, rel_tol=1e-12)  # 教科书例
    # 甲公司营收：4.2 → 6.8 亿，(6.8/4.2)^(1/2)−1 = +27.24%（原颠倒式得 −21.4%，符号量级皆反）
    assert math.isclose(cagr([420, 500, 680]), (680 / 420) ** 0.5 - 1, rel_tol=1e-12)
    assert cagr([420, 500, 680]) > 0.27  # 方向锁死：递增序列复合增长率为正
    assert cagr([680, 500, 420]) < 0  # 递减序列为负（原颠倒式两例皆反号）
    assert math.isclose(cagr([50, 60]), 0.2, rel_tol=1e-12)  # 1 年增长（n=2，指数 1）
    assert cagr([100]) is None  # 窗口 < 2 年无定义
    assert cagr([-100, 50, 60]) is None  # 首年 ≤ 0 无定义
    assert cagr([100, 50, -60]) is None  # 末年 < 0 防御：负/正分数幂得复数，宁可无定义


# ── 审计覆盖降级（§4.4-3 两分：非标 → needs_review；未审计 → indeterminate）──


def test_qualified_audit_needs_review():
    ctx = run_eval(company_dir=QUAL, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")
    np_sum = _check(ctx, "cn_main_g1_c2_l1")
    assert np_sum["state"] == "needs_review"
    assert "2023" in np_sum["reason"] and "qualified" in np_sum["reason"]
    assert _check(ctx, "cn_main_g1_c1_l1")["state"] == "needs_review"  # 3 年窗口含 2023
    assert _check(ctx, "cn_main_g1_c3_l1")["state"] == "not_met"  # latest=2024 干净，照常判
    # 规则库仅净利声明 measures.audit=[audited]——ocf/rev 叶不受影响（数据驱动，AR3）
    assert _check(ctx, "cn_main_g1_b1_c1_l1")["state"] == "not_met"
    assert _check(ctx, "cn_main_g1_b1_c1_l2")["state"] == "met"


def test_unaudited_year_indeterminate():
    ctx = run_eval(company_dir=UNAUD, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")
    np_sum = _check(ctx, "cn_main_g1_c2_l1")
    assert np_sum["state"] == "indeterminate"
    assert "2023" in np_sum["reason"] and "未审计" in np_sum["reason"]
    assert _check(ctx, "cn_main_g1_b1_c1_l1")["state"] == "not_met"  # ocf 无 audit measure


# ── judgment × declared：恒 needs_review ──


def test_judgment_leaf_needs_review_never_met():
    rb = load_rulebook(RB_DIR).rulebook
    item = next(i for i in rb.items if i.nature == Nature.judgment)
    leaf = Leaf(
        leaf_id="t_judgment", item_ref=item.item_id, op=Op.ge,
        threshold=Threshold(value=0, format=ThresholdFormat.number),
    )
    check = evaluate_leaf(leaf, item, None, {}, {}, {})
    assert check["state"] == "needs_review"
    assert check["pending_evidence"] == list(item.pending_evidence)
    assert "永不 met" in check["reason"]


# ── op 语义：无 ε 比较 ──


def test_cmp_no_epsilon():
    assert _CMP["ge"](1.0, 1.0) and not _CMP["gt"](1.0, 1.0)  # 等值：ge 过 gt 不过
    assert _CMP["le"](1.0, 1.0) and not _CMP["lt"](1.0, 1.0)
