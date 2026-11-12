"""T1：Init 节点（run 坐标 + as_of 过滤 + 适用性 + 五节点骨架 + eval run CLI）。

对应票 .scratch/m4-engine/issues/01；关闭 CONTEXT #9-V6（effective_from 从此参与过滤）。
规则库包（M2，c68d02e 冻结）不改——as_of 过滤是引擎侧视图，单点在 engine/asof。
"""
import json
from datetime import date
from pathlib import Path

import pytest

from ipo_eval_lab.engine import EngineError, RunTarget, filter_by_as_of, judge_applicability, run_eval
from ipo_eval_lab.fixtures import load_company, load_sanity

from fixture_rulebook import fixture_rulebook_dir

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"

AS_OF_BOTH = "2025-06-30"  # 主板 2024-04-30 修订与科创板 2019 版均生效
AS_OF_PRE_MAIN = "2024-04-01"  # 主板修订（effective_from=2024-04-30）未生效


@pytest.fixture(scope="module")
def rb_dir():
    """夹具规则库根：正式库数据层 + 样板套结构层。

    引擎机制测试（as_of 过滤、适用性、节点骨架）验的是**引擎**不是规则库内容，
    所以用样板套——它才有 2024 版生效日与设计 0002 步骤 2 的两种结构形态。
    正式库（28 套 / 现行版生效日）的端到端回归在 test_official_rulebook_e2e.py。
    """
    with fixture_rulebook_dir() as d:
        yield d


@pytest.fixture(scope="module")
def loaded(rb_dir):
    from ipo_eval_lab.rulebook.loader import load_rulebook

    sanity = load_sanity(FX / "sanity.yaml")
    return load_rulebook(rb_dir).rulebook, load_company(BASE, sanity)


# ── as_of 过滤（V6）──


def test_asof_both_sets_effective(loaded):
    result = filter_by_as_of(loaded[0].groups, AS_OF_BOTH)
    assert {g.group_id for g in result.effective} == {"cn_main_general_g1", "star_general_g1"}
    assert result.excluded == []


def test_asof_main_board_revision_not_yet_effective(loaded):
    result = filter_by_as_of(loaded[0].groups, AS_OF_PRE_MAIN)
    assert [g.group_id for g in result.effective] == ["star_general_g1"]
    assert len(result.excluded) == 1
    ex = result.excluded[0]
    assert ex["group_id"] == "cn_main_general_g1"
    assert "2024-04-30" in ex["reason"]  # 原因里写明生效日


def test_asof_boundary_effective_on_exact_date(loaded):
    """生效日当天 = 已生效（effective_from ≤ as_of，闭区间）。"""
    result = filter_by_as_of(loaded[0].groups, "2024-04-30")
    assert "cn_main_general_g1" in {g.group_id for g in result.effective}


# ── 适用性判定 ──


def test_applicability_general_matches_both(loaded):
    rb, company = loaded
    eff = filter_by_as_of(rb.groups, AS_OF_BOTH)
    result = judge_applicability(eff.effective, company.profile, target=RunTarget())
    assert {g.group_id for g in result.applicable} == {"cn_main_general_g1", "star_general_g1"}
    assert result.not_applicable == []


def test_applicability_redchip_not_applicable_stays_visible(loaded):
    """红筹公司 → 套级 not_applicable：出分母、留在结果里可见（设计 0001 §2.4）。"""
    rb, company = loaded
    profile = company.profile.model_copy(deep=True)
    profile.applicant_profile.company_type = "redchip_unlisted"
    eff = filter_by_as_of(rb.groups, AS_OF_BOTH)
    result = judge_applicability(eff.effective, profile, target=RunTarget())
    assert result.applicable == []
    assert {n["group_id"] for n in result.not_applicable} == {"cn_main_general_g1", "star_general_g1"}
    assert all("company_type" in n["reason"] for n in result.not_applicable)


def test_applicability_target_boards_filter(loaded):
    rb, company = loaded
    eff = filter_by_as_of(rb.groups, AS_OF_BOTH)
    result = judge_applicability(eff.effective, company.profile, target=RunTarget(boards=["STAR"]))
    assert [g.group_id for g in result.applicable] == ["star_general_g1"]
    reasons = {n["group_id"]: n["reason"] for n in result.not_applicable}
    assert "target" in reasons["cn_main_general_g1"]


def test_applicability_target_sets_filter(loaded):
    rb, company = loaded
    eff = filter_by_as_of(rb.groups, AS_OF_BOTH)
    result = judge_applicability(eff.effective, company.profile, target=RunTarget(sets=["cn_main_general_g1"]))
    assert [g.group_id for g in result.applicable] == ["cn_main_general_g1"]


# ── run_eval：run 坐标 + 五节点骨架 ──


def test_run_coordinates_written(loaded, rb_dir):
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of=AS_OF_BOTH)
    run = ctx.run
    assert run["company_id"] == "base_co_2029"
    assert run["as_of_date"] == AS_OF_BOTH  # 显式写入（可复算）
    assert run["report_period"]["fiscal_years"] == [2022, 2023, 2024]
    assert run["report_period"]["audit_status"] == "audited"
    assert run["report_period"]["audit_opinion"] == "unqualified"
    assert run["applicant_profile"]["company_type"] == "general"
    assert run["target"] == {"boards": None, "sets": None}
    # 版本链（设计 0003-R6）：逐套记录实际生效版本
    versions = {v["group_id"]: v["rulebook_version"] for v in run["applied_rule_versions"]}
    assert versions == {"cn_main_general_g1": "rb-2026.11", "star_general_g1": "rb-2026.11"}


def test_run_qualified_variant_aggregates_worst_opinion(rb_dir):
    ctx = run_eval(
        company_dir=FX / "companies" / "qualified_audit",
        rulebook_dir=rb_dir,
        fixtures_root=FX,
        as_of=AS_OF_BOTH,
    )
    assert ctx.run["report_period"]["audit_opinion"] == "qualified"


def test_chain_five_nodes_in_order(loaded, rb_dir):
    """链骨架（票 08 更新）：五节点全部点亮——Fetch 产 facts、Result 产契约四段。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of=AS_OF_BOTH)
    assert ctx.facts["metrics"]["operating_revenues"]["series"][2024]["value"] == 680_000_000
    assert set(ctx.layers) == {"gap", "path", "attribution"}  # Result 不再是占位直通
    assert set(ctx.result) == {"run", "facts", "layers", "narrative_handoff"}
    assert [g.group_id for g in ctx.selection.applicable] == ["cn_main_general_g1", "star_general_g1"]


def test_run_eval_asof_exclusion_visible_in_selection(rb_dir):
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of=AS_OF_PRE_MAIN)
    ids = [g.group_id for g in ctx.selection.applicable]
    assert ids == ["star_general_g1"]
    assert "2024-04-30" in ctx.selection.excluded_by_asof[0]["reason"]


def test_asof_default_is_today(rb_dir):
    """缺省 = 当日且显式写入 run.as_of_date（可复算；票 L12）。"""
    ctx = run_eval(company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX, as_of=None)
    assert ctx.run["as_of_date"] == date.today().isoformat()


def test_target_sets_shrinks_applied_versions(rb_dir):
    """applied_rule_versions = 真正参评的套（as_of + 适用性双重收敛，非全量生效集）。"""
    ctx = run_eval(
        company_dir=BASE, rulebook_dir=rb_dir, fixtures_root=FX,
        as_of=AS_OF_BOTH, target=RunTarget(sets=["cn_main_general_g1"]),
    )
    versions = [v["group_id"] for v in ctx.run["applied_rule_versions"]]
    assert versions == ["cn_main_general_g1"]


def test_lint_red_blocks_run(tmp_path):
    """AR4：规则库 lint 红 → 起不了 run（包成 EngineError，CLI 干净退出）。"""
    empty = tmp_path / "rulebook"
    empty.mkdir()
    with pytest.raises(EngineError, match="lint"):
        run_eval(company_dir=BASE, rulebook_dir=empty, fixtures_root=FX, as_of=AS_OF_BOTH)


def test_missing_company_raises(rb_dir):
    with pytest.raises(EngineError, match="base_co_999"):
        run_eval(company_dir=FX / "companies" / "base_co_999", rulebook_dir=rb_dir, fixtures_root=FX, as_of=AS_OF_BOTH)


# ── CLI（python -m ipo_eval_lab.cli eval run …）──


def test_cli_eval_run_smoke(capsys, rb_dir):
    from ipo_eval_lab.cli import main

    code = main(["eval", "run", "--company", "base_co_2029", "--as-of", AS_OF_BOTH,
                 "--rulebook", str(rb_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "cn_main_general_g1" in out and "star_general_g1" in out
    assert "适用" in out
    assert "rb-2026.11" in out


def test_cli_eval_run_asof_pre_main(capsys, rb_dir):
    from ipo_eval_lab.cli import main

    code = main(["eval", "run", "--company", "base_co_2029", "--as-of", AS_OF_PRE_MAIN,
                 "--rulebook", str(rb_dir)])
    out = capsys.readouterr().out
    assert code == 0
    assert "star_general_g1" in out
    assert "2024-04-30" in out  # 排除原因可见


def test_cli_bad_company_exits_nonzero(capsys):
    from ipo_eval_lab.cli import main

    with pytest.raises(SystemExit) as ei:
        main(["eval", "run", "--company", "base_co_999", "--as-of", AS_OF_BOTH])
    assert ei.value.code == 2
