"""T4：Fold 节点（Kleene 双规则 → 套终态 → 三段板块结论 → AR5 冻结）。

对应票 .scratch/m4-engine/issues/04；语义单点 = 设计 0005 §5（含 0001 §2.3 勘误）。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.engine import EngineError, run_eval
from ipo_eval_lab.engine.fold import kleene_and, kleene_or

REPO = Path(__file__).resolve().parents[1]
RB_DIR = REPO / "rulebook"
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
QUAL = FX / "companies" / "qualified_audit"
UNAUD = FX / "companies" / "unaudited_2023"
GOLDEN = BASE / "expected" / "summary.json"

U_MET = ("met", [])
U_NOT = ("not_met", ["x"])
U_UNK = ("unknown", ["u"])


@pytest.fixture(scope="module")
def ctx_base():
    return run_eval(company_dir=BASE, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")


def _set_entry(ctx, group_id):
    return next(s for s in ctx.facts["sets"] if s["group_id"] == group_id)


# ── Kleene 双规则（§5 表逐行）──


def test_kleene_and_priority():
    assert kleene_and([U_MET, U_NOT, U_UNK])[0] == "not_met"  # 任一 not_met 优先
    assert kleene_and([U_MET, U_UNK])[0] == "unknown"  # 否则 unknown 传染
    assert kleene_and([U_MET, U_MET]) == ("met", [])


def test_kleene_or_priority():
    assert kleene_or([U_NOT, U_MET])[0] == "met"  # 任一 met 优先（0001 §2.3 字面会得 not_met——错杀）
    assert kleene_or([U_MET, U_UNK])[0] == "met"  # met 吸收 unknown
    assert kleene_or([U_NOT, U_UNK])[0] == "unknown"
    assert kleene_or([U_NOT, U_NOT]) == ("not_met", ["x"])  # blockers 去重保序


def test_blocker_merge_dedup():
    assert kleene_or([("not_met", ["a", "b"]), ("not_met", ["b", "c"])]) == ("not_met", ["a", "b", "c"])


# ── golden sets 对拍（票 04 验收 1）──


def test_golden_sets_match(ctx_base):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for group_id, expected in golden["sets"].items():
        entry = _set_entry(ctx_base, group_id)
        assert entry["outcome"] == expected["outcome"], group_id
        assert entry["blockers"] == expected["blockers"], group_id


def test_or_clause_met_losing_branch_absorbed(ctx_base):
    """Kleene OR 活例：现金流叶 not_met、营收叶 met → 条文 met，落败叶不进 blockers。"""
    main = _set_entry(ctx_base, "cn_main_general_g1")
    b1 = next(b for b in main["branches"] if b["set_id"] == "cn_main_general_g1-b1")
    assert b1["state"] == "not_met"  # branch 含 shared c3 → branch 整体 not_met
    assert "ocf_3y_sum" not in main["blockers"]  # OR 落败支路被吸收（§5）
    assert main["blockers"] == ["np_latest"]


def test_star_shared_unknown_propagates(ctx_base):
    """科创板：shared 市值叶 unknown 折进两个 branch → 双 branch unknown → group indeterminate。"""
    star = _set_entry(ctx_base, "star_general_g1")
    assert star["outcome"] == "indeterminate"
    assert star["blockers"] == ["mktcap_forecast"]
    assert all(b["state"] == "unknown" or b["state"] == "indeterminate" for b in star["branches"])


# ── 未知不可能翻盘成 met（票 04 验收 5）──


def test_unknown_never_folds_to_met():
    assert kleene_and([U_MET, U_UNK])[0] != "met"
    assert kleene_or([U_NOT, U_UNK])[0] != "met"
    # 嵌套：OR(unknown, met)=met → AND(met, not_met)=not_met；OR(unknown∧not_met, met)=met
    assert kleene_and([kleene_or([U_UNK, U_MET])[0], U_NOT])[0] == "not_met"
    assert kleene_or([kleene_and([U_UNK, U_NOT])[0], U_MET])[0] == "met"


# ── needs_review 视同 unknown；AND 下 not_met 优先（§5-P3）──


def test_qualified_needs_review_dominated_by_not_met():
    ctx = run_eval(company_dir=QUAL, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")
    main = _set_entry(ctx, "cn_main_general_g1")
    # c1/c2 needs_review（2023 非标）视同 unknown；c3 not_met（2024 干净照判）→ AND 优先 not_met
    assert main["outcome"] == "criteria_not_met"
    assert main["blockers"] == ["np_latest"]
    assert main["needs_review_count"] == 2  # 叶级 needs_review 保留可见（P3 相容性）
    assert {p["item_ref"] for p in main["pending_judgments"]} == {"np_3y_allpos", "np_3y_sum"}


def test_unaudited_indeterminate_dominated_by_not_met():
    ctx = run_eval(company_dir=UNAUD, rulebook_dir=RB_DIR, fixtures_root=FX, as_of="2025-06-30")
    main = _set_entry(ctx, "cn_main_general_g1")
    assert main["outcome"] == "criteria_not_met"  # c3 not_met 优先于 c1/c2 indeterminate


# ── 三段树：段①② pass-through 占位 ──


def test_three_segment_board_rollup(ctx_base):
    boards = {b["board"]: b for b in ctx_base.facts["boards"]}
    assert set(boards) == {"SSE-MB", "SZSE-MB", "STAR"}  # 沪深同文共享 group → 双板块同结论
    assert boards["SSE-MB"]["outcome"] == "criteria_not_met"
    assert boards["SZSE-MB"]["outcome"] == "criteria_not_met"
    assert boards["STAR"]["outcome"] == "indeterminate"
    for b in boards.values():
        assert b["segments"]["issuance"]["state"] == "met"  # pass-through 占位，不阻塞
        assert "占位" in b["segments"]["positioning"]["note"]
        assert b["segments"]["listing_sets"]["state"] in {"not_met", "unknown"}


# ── AR5：facts 在 Fold 出口冻结 ──


def test_ar5_facts_frozen(ctx_base):
    assert ctx_base.facts_frozen is True
    assert "sets" in ctx_base.facts and "boards" in ctx_base.facts  # 冻结前写入完成
    with pytest.raises(EngineError, match="AR5"):
        ctx_base.assert_writable_facts()
