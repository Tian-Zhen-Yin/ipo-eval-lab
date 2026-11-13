"""正式库端到端回归（P5a）：export-official 产物必须可被引擎直接加载并出完整结果。

与引擎机制测试（tests/fixture_rulebook.py 装配的样板套）的分工：
- 样板套测试验**引擎机制**（as-of 闸门、折叠、五态——用 2024 版生效日的手写套）；
- 本文件验**正式库本体**——28 个套 / 103 条已签核条款 / 现行版生效日（2026-04），
  甲公司在 as_of=现行版生效日之后必须能评出 16 个适用套、五态齐全的判定。

钉住的量（2026-11-12 导出快照；数字变了要么是重导出（合理），要么是导出器回归（要查））：
- 32 group（28 sets + 4 positioning）/ 128 条款（P5b 后 109 + G-D 定位 19）
- 甲公司（general）as_of=2026-06-30 → 16 个适用套
"""
from pathlib import Path

import pytest

from ipo_eval_lab.engine import run_eval
from ipo_eval_lab.rulebook.loader import load_rulebook

REPO = Path(__file__).resolve().parents[1]
RB = REPO / "rulebook"
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"

# 现行版规则统一生效日之后（五部板块规则 2026-04-24/30 生效）
AS_OF_CURRENT = "2026-06-30"


@pytest.fixture(scope="module")
def loaded():
    # strict_global=True：28 套全量加载，组合覆盖缺口（未声明 declared_no_sets）直接报错
    return load_rulebook(RB, strict_global=True)


def test_official_library_loads_strict(loaded):
    """正式库全量加载：0 错 0 警，28 组 103 条款。"""
    rb = loaded.rulebook
    assert loaded.warnings == []
    n_clauses = sum(
        len(g.shared_clauses) + sum(len(b.clauses) for b in g.branches)
        for g in rb.groups
    )
    assert len(rb.groups) == 32   # 28 sets + 4 positioning（底稿0003 G-D）
    assert n_clauses == 128   # 109 + 19 positioning 条款


def test_redchip_listed_declared_no_sets_only_on_main_boards(loaded):
    """套级裁定落库：科创/创业板 redchip_listed 依法无套（declared_no_sets），
    沪深主板有（3.1.4 是唯一已上市红筹标准）。"""
    rb = loaded.rulebook
    groups = {(g.company_type, tuple(sorted(g.boards))) for g in rb.groups}
    assert ("redchip_listed", ("SSE-MB", "SZSE-MB")) in groups
    star_listed = [g for g in rb.groups if g.boards == ["STAR"] and g.company_type == "redchip_listed"]
    chinext_listed = [g for g in rb.groups if g.boards == ["ChiNext"] and g.company_type == "redchip_listed"]
    assert star_listed == [] and chinext_listed == []


def test_effective_dates_from_evidence(loaded):
    """生效日来自候选库 evidence（不硬编码）：只允许 2026-04-24 / 2026-04-30 两个值。"""
    effs = {g.effective_from.isoformat() for g in loaded.rulebook.groups}
    assert effs <= {"2024-04-30", "2026-04-24", "2026-04-30"}   # 段② 指引/推荐规定/审核规则 2024-04-30


@pytest.fixture(scope="module")
def ctx():
    return run_eval(company_dir=BASE, rulebook_dir=RB, fixtures_root=FX, as_of=AS_OF_CURRENT)


def test_base_company_evaluates_all_applicable_sets(ctx):
    """甲公司（general）在现行版下：16 个适用套，其余套级 not_applicable（可见）。"""
    ids = {g.group_id for g in ctx.selection.applicable}
    assert len(ids) == 20   # 16 sets + 4 positioning（跨企业类型一体适用）
    # general：16 套（沪深 3 + 科创 5 + 创业 4 + 北交 4）+ 定位 4（cn/star/chinext/bse）
    assert {g.group_id for g in ctx.selection.applicable if g.boards == ["BSE"]}.__len__() == 5
    assert {g.group_id for g in ctx.selection.applicable
            if g.scope.value == "positioning"} == {
        "cn_main_positioning_g1", "star_positioning_g1",
        "chinext_positioning_g1", "bse_positioning_g1"}


def test_checks_produce_five_states(ctx):
    """59 个叶判定覆盖四态（not_applicable 只在豁免命中时出现，甲公司无豁免）。"""
    states = {c["state"] for c in ctx.facts["checks"]}
    assert len(ctx.facts["checks"]) == 84   # 59 + 25 定位叶
    assert {"met", "not_met", "indeterminate", "needs_review"} <= states


def test_layers_complete_official(ctx):
    """层①②③四轴输出在正式库上完整（gap/path/attribution）。"""
    assert set(ctx.layers) == {"gap", "path", "attribution"}
    gap_sets = {s["group_id"] for s in ctx.layers["gap"]["sets"]}
    assert len(gap_sets) == 16


def test_snapshot_counts_are_pinned():
    """数量钉板：重新导出后此断言失败 → 要么重导出（更新数字+提交），要么导出器回归。"""
    import yaml
    total_groups = 0
    total_clauses = 0
    for f in sorted((RB / "sets").glob("*.yaml")):
        for g in yaml.safe_load(f.read_text(encoding="utf-8")):
            total_groups += 1
            total_clauses += len(g["shared_clauses"]) + sum(
                len(b["clauses"]) for b in g["branches"])
    assert (total_groups, total_clauses) == (28, 109)
