"""T8：Result 出口与 eval run 端到端（契约 v0.2 组装 + golden 对拍；票 08）。

对拍口径（设计 0006 §6）：golden 只锁语义敏感点——sets/key_checks/window_roll 逐条目
命中（同字段同值），progress 段逐字对拍。note 为注释不锁。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.cli import main as cli_main
from ipo_eval_lab.engine import run_eval

from fixture_rulebook import fixture_rulebook_dir

REPO = Path(__file__).resolve().parents[1]

# 夹具规则库根（正式库数据层＋样板套结构层）：见 tests/fixture_rulebook.py
@pytest.fixture(scope="module")
def rb_dir():
    with fixture_rulebook_dir() as d:
        yield d
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
QUALIFIED = FX / "companies" / "qualified_audit"
GOLDEN = BASE / "expected" / "summary.json"

PC_KEYS = ("progress", "coverage", "binding_clause_id", "next_binding_clause_id")


def _run(rb_dir, company_dir=BASE):
    ctx = run_eval(company_dir=company_dir, rulebook_dir=rb_dir, fixtures_root=FX, as_of="2025-06-30")
    return ctx, ctx.result


# ── 四段与 AR5 ────────────────────────────────────────────────

def test_four_sections_and_ar5_identity(rb_dir):
    ctx, r = _run(rb_dir)
    assert set(r) == {"run", "facts", "layers", "narrative_handoff"}
    assert set(r["layers"]) == {"gap", "path", "attribution"}
    assert r["facts"] is ctx.facts  # AR5：与 Fold 出口冻结对象同源（同一引用）
    assert json.dumps(r, ensure_ascii=False)  # 契约要求整个文件可序列化


# ── golden 语义敏感点对拍 ──────────────────────────────────────

def test_golden_alignment(rb_dir):
    _, r = _run(rb_dir)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    gap = r["layers"]["gap"]

    for gid, exp in golden["sets"].items():
        got = next(s for s in gap["sets"] if s["group_id"] == gid)
        assert got["outcome"] == exp["outcome"], gid
        assert got["blockers"] == exp["blockers"], gid

    for exp in golden["key_checks"]:
        if "leaf_id" in exp:
            got = next(k for k in gap["key_checks"] if k.get("leaf_id") == exp["leaf_id"])
            assert got["item_ref"] == exp["item_ref"]
            assert got["state"] == exp["state"]
            if "diff" in exp:
                assert got["diff"] == exp["diff"]
        else:
            got = next(k for k in gap["key_checks"] if k.get("clause_id") == exp["clause_id"])
            assert got["state"] == exp["state"]

    for exp in golden["window_roll"]:
        got = next(w for w in gap["window_roll"] if w["leaf_id"] == exp["leaf_id"])
        assert got["item_ref"] == exp["item_ref"]
        assert got["required"] == exp["required"]  # 1.3 亿
        assert got["risk"] == exp["risk"]  # high（k=2）
        assert got["rolled_state"] == exp["rolled_state"]  # 零增长推演：1.1 亿 < 2 亿 → 反转
        assert got["assumption"] == exp["assumption"] == "zero_growth"

    # progress 段逐字对拍（E9 双指标——min 聚合与未定义叶不进聚合两处最易错）
    got_pc = {s["group_id"]: {k: s[k] for k in PC_KEYS} for s in gap["sets"]}
    assert got_pc == golden["progress"]


# ── narrative_handoff（自包含） ────────────────────────────────

def test_narrative_handoff_self_contained(rb_dir):
    _, r = _run(rb_dir)
    h = r["narrative_handoff"]
    assert set(h) == {"units", "citation_index", "disclaimers", "forbidden_claims"}
    text = json.dumps(h, ensure_ascii=False)
    # 三条固定边界（段①抽样核查 / 甜区声明 / 市值自估）+ 资格认定
    for keyword in ("抽样核查", "甜区声明", "自估", "交易所/证监会认定"):
        assert keyword in text
    # 固定禁令 + coverage<100 追加禁令（科创板 80%）+ scenario is_forecast 义务
    fc = h["forbidden_claims"]
    for keyword in ("符合发行条件", "保证过会", "可替代专业意见", "is_forecast"):
        assert any(keyword in c for c in fc)
    assert any("star_general_g1" in c and "80%" in c for c in fc)  # E9 追加禁令随文件传递
    # 进度不进叙述素材：units 里不出现分数式表述
    for u in h["units"]:
        assert "progress" not in u["text"] and "分" != u["text"][-1]


def test_citation_index_chains_to_law(rb_dir):
    """阈值判定 → item → metric → law_ref（law_id#article）直达法条。"""
    _, r = _run(rb_dir)
    ci = r["narrative_handoff"]["citation_index"]
    leaves = {c["leaf_id"] for c in r["facts"]["checks"]}
    assert {e["leaf_id"] for e in ci} == leaves  # 全叶覆盖
    np_latest = next(e for e in ci if e["item_ref"] == "np_latest")
    assert np_latest["metric_ref"] == "net_profit_attrib_parent"
    assert "#" in np_latest["law_ref"]  # law_id#article 直达
    assert np_latest["op"] == "ge" and np_latest["threshold"]["value"] == 100000000


def test_numbers_carry_refs(rb_dir):
    """不变量 5：key_checks / window_roll 每行带 refs（law_ref）。"""
    _, r = _run(rb_dir)
    gap = r["layers"]["gap"]
    assert all(k.get("refs") for k in gap["key_checks"])
    assert all(w["refs"] and "#" in w["refs"][0] for w in gap["window_roll"])
    assert all(g.get("refs") for g in gap["growth_rows"])


# ── 端到端：qualified_audit 样本（E3 降级路径全链） ─────────────

def test_qualified_audit_e2e(rb_dir):
    """非标意见样本全链跑通：降级路径不崩、契约完整、JSON 可序列化。"""
    ctx, r = _run(rb_dir, QUALIFIED)
    assert set(r) == {"run", "facts", "layers", "narrative_handoff"}
    assert r["facts"] is ctx.facts
    assert json.dumps(r, ensure_ascii=False)
    assert r["run"]["report_period"]["audit_opinion"] == "qualified"
    states = {c["state"] for c in r["facts"]["checks"]}
    assert "indeterminate" in states  # E3：审计覆盖降级 → 相关叶 indeterminate
    assert len(r["layers"]["gap"]["sets"]) >= 1


# ── CLI：--report 落盘 + 终端摘要禁令 ──────────────────────────

def test_cli_report_and_summary_bans(capsys, rb_dir):
    rc = cli_main(
        [
            "eval", "run",
            "--company", "base_co_2029",
            "--as-of", "2025-06-30",
            "--rulebook", str(rb_dir),
            "--fixtures", str(FX),
            "--report",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # 呈现禁令：不出现总分 / 维度分 / 雷达图
    for banned in ("总分", "维度分", "雷达"):
        assert banned not in out
    assert "检查叶计数" in out and "推荐：无" in out
    f = Path("results") / "base_co_2029_2025-06-30.json"
    assert f.exists()
    data = json.loads(f.read_text(encoding="utf-8"))
    assert set(data) == {"run", "facts", "layers", "narrative_handoff"}
