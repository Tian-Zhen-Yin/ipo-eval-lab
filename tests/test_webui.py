"""webui API 测试（设计 0010 阶段 0）：UiApp 纯方法，不起 socket。

与 test_official_rulebook_e2e 的分工：那边验正式库本体可被引擎加载；
这边验**展示层**——摘要形状（套卡数据源）、results 索引/白名单、
POST /api/run 的会话 profile 注入与防覆盖落盘。

规则库/夹具用真实仓库目录（同 e2e）；results/ 与 .scratch 用 tmp_path
（results/ 不入 git，fresh clone 下测试仍须绿）。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ipo_eval_lab.webui import UiApp, rulebook_summary
from ipo_eval_lab.rulebook.loader import load_rulebook

REPO = Path(__file__).resolve().parents[1]
RB = REPO / "rulebook"
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
AS_OF_CURRENT = "2026-06-30"  # 现行版规则统一生效日之后


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    results = tmp_path_factory.mktemp("results")
    scratch = tmp_path_factory.mktemp("scratch")
    return UiApp(
        rulebook_dir=RB,
        fixtures_root=FX,
        results_dir=results,
        ui_dir=REPO / "ui" / "app",
        scratch_root=scratch,
    )


@pytest.fixture(scope="module")
def summary():
    return rulebook_summary(load_rulebook(RB, strict_global=True).rulebook)


# ── 摘要形状（新建页套卡数据源）──


class TestRulebookSummary:
    def test_36_groups_scope_split(self, summary):
        scopes = {}
        for g in summary["groups"]:
            scopes[g["scope"]] = scopes.get(g["scope"], 0) + 1
        assert scopes == {"set": 28, "positioning": 4, "issuance": 4}

    def test_meta_enums_and_version(self, summary):
        meta = summary["meta"]
        assert meta["rulebook_version"].startswith("rb-")
        assert "SSE-MB" in meta["boards"]
        assert "general" in meta["company_types"]
        # 法定无套组合显式声明（L2 豁免；科创/创业板 redchip_listed）
        assert any("redchip_listed" in combo for combo in meta["declared_no_sets"])

    def test_sse_mb_general_three_sets_with_thresholds(self, summary):
        g1 = next(g for g in summary["groups"] if g["group_id"] == "cn_main_general_g1")
        assert g1["scope"] == "set"
        assert g1["company_type"] == "general"
        assert "SSE-MB" in g1["boards"]
        assert g1["effective_from"] == "2026-04-30"
        # shared 条文：最近一年净利润 ≥ 1 亿（阈值 1e8 yuan number）
        c3 = next(c for c in g1["shared_clauses"] if c["clause_id"] == "cn_main_g1_c3")
        assert c3["law_ref"] == "sse_main_2026#3.1.2"
        assert c3["leaves"][0]["threshold"] == {"value": 100000000.0, "format": "number"}
        # branch 条文带 OR（logic=any）——现金流 或 营收支路
        b1 = g1["branches"][0]
        assert b1["set_id"] == "cn_main_general_g1-b1"
        assert any(c["logic"] == "any" for c in b1["clauses"])

    def test_items_lookup_backs_leaf_labels(self, summary):
        """叶的 item_ref 必须能在 items 表里找到展示名（套卡阈值摘要行的文案源）。"""
        items = summary["items"]
        assert items["np_latest"]["display"]
        assert items["np_latest"]["quantifier"] == "latest"
        for g in summary["groups"]:
            for c in g["shared_clauses"]:
                for lf in c["leaves"]:
                    assert lf["item_ref"] in items, lf["leaf_id"]

    def test_laws_carry_referenced_article_text(self, summary):
        """法条段只带被引用条文原文（法条 ⓘ 悬浮文案源）；sse_main_2026#3.1.2 必在。"""
        laws = summary["laws"]
        assert "sse_main_2026" in laws
        assert "3.1.2" in laws["sse_main_2026"]["articles"]
        assert laws["sse_main_2026"]["articles"]["3.1.2"]["text"]
        assert laws["sse_main_2026"]["title"]
        # 未被引用的条文不进接口（全量 1.4MB 不上路）
        assert len(laws["sse_main_2026"]["articles"]) < 30


# ── companies / results ──


class TestCompaniesAndResults:
    def test_companies_lists_three_fixtures(self, app):
        status, out = app.api_companies()
        assert status == 200
        ids = {c["id"] for c in out}
        assert {"base_co_2029", "qualified_audit", "unaudited_2023"} <= ids
        base = next(c for c in out if c["id"] == "base_co_2029")
        assert len(base["fiscal_years"]) == 3
        assert base["profile"]["display_name"]  # 补录弹窗预填用

    def test_results_index_reads_run_segment(self, app):
        (app.results_dir / "demo_2026-01-01.json").write_text(
            json.dumps({"run": {"company_id": "demo", "as_of_date": "2026-01-01"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (app.results_dir / "not_a_result.json").write_text("{}", encoding="utf-8")  # 无 run 段 → 不进索引
        status, out = app.api_results()
        assert status == 200
        names = [r["file"] for r in out]
        assert "demo_2026-01-01.json" in names
        assert "not_a_result.json" not in names

    def test_result_file_whitelist(self, app):
        assert app.api_result_file("../fixtures/sanity.yaml")[0] == 400
        assert app.api_result_file("sub/dir.json")[0] == 400
        assert app.api_result_file("missing.json")[0] == 404
        status, raw = app.api_result_file("demo_2026-01-01.json")
        assert status == 200 and raw["run"]["company_id"] == "demo"


# ── POST /api/run（进程内调引擎，真规则库+真夹具）──


class TestApiRun:
    def test_plain_run_matches_cli_convention(self, app):
        """不带 overrides：走 base 夹具目录，产物名 = <company>_<asof>.json。"""
        status, out = app.api_run({"company": "base_co_2029", "as_of": AS_OF_CURRENT})
        assert status == 200, out
        assert out["file"] == f"base_co_2029_{AS_OF_CURRENT}.json"
        assert (app.results_dir / out["file"]).exists()
        # 五态计数齐备（呈现禁令：无总分字段可给）
        assert set(out["state_counts"]) == {"met", "not_met", "indeterminate", "needs_review", "not_applicable"}
        assert len(out["sets"]) >= 1  # 甲公司现行版适用 16 套
        assert out["recommendation"] == []  # 甲公司三套均含 not_met → 契约禁止推荐

    def test_run_with_overrides_writes_session_profile(self, app):
        """带 overrides：会话 profile 落 .scratch/ui-runs/，真实夹具零改动，
        产物文件名加时间戳防覆盖；覆盖值可见于结果 facts。"""
        before = (BASE / "profile.json").read_text(encoding="utf-8")
        status, out = app.api_run(
            {
                "company": "base_co_2029",
                "as_of": AS_OF_CURRENT,
                "boards": ["SSE-MB"],
                "overrides": {
                    "documentary": {"mktcap_self_estimate": {"value": 5000000000, "note": "UI 补录"}},
                    "declared": {"main_board_fit": True},
                },
            }
        )
        assert status == 200, out
        # 文件名带时间戳后缀（不覆盖 CLI 约定名）
        assert out["file"] != f"base_co_2029_{AS_OF_CURRENT}.json"
        assert (app.results_dir / out["file"]).exists()
        # 真实夹具不动
        assert (BASE / "profile.json").read_text(encoding="utf-8") == before
        # 会话 profile 落盘且含覆盖值
        sessions = list((app.scratch_root / "ui-runs").glob("*/profile.json"))
        assert sessions, "会话 profile 未落盘"
        merged = json.loads(sessions[0].read_text(encoding="utf-8"))
        assert merged["documentary"]["mktcap_self_estimate"]["value"] == 5000000000
        assert merged["declared"]["main_board_fit"] is True

    def test_override_null_clears_field(self, app):
        """null = 清空 → 引擎侧 indeterminate（缺数据≠0，ADR-0003）。"""
        status, out = app.api_run(
            {
                "company": "base_co_2029",
                "as_of": AS_OF_CURRENT,
                "overrides": {"documentary": {"operating_years": None}},
            }
        )
        assert status == 200, out
        raw = json.loads((app.results_dir / out["file"]).read_text(encoding="utf-8"))
        assert raw["facts"]["documentary"]["operating_years"] is None

    def test_unknown_override_key_rejected(self, app):
        """extra=forbid：拼错键名必须 400，不能静默丢弃（对照问财静默丢列的教训）。"""
        status, out = app.api_run(
            {
                "company": "base_co_2029",
                "as_of": AS_OF_CURRENT,
                "overrides": {"documentary": {"operating_yers": 5}},  # 拼错
            }
        )
        assert status == 400 and "校验" in out["error"]

    def test_unknown_company_rejected(self, app):
        status, out = app.api_run({"company": "no_such_co", "as_of": AS_OF_CURRENT})
        assert status == 400 and "不存在" in out["error"]

    def test_engine_error_bubbles_as_400(self, app):
        status, out = app.api_run({"company": "base_co_2029", "as_of": "not-a-date"})
        assert status == 400 and out["error"]
