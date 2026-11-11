"""M3 fixtures 加载与勾稽断言测试（设计 0006 §4 勾稽①~⑥；AR4 坏数据起不了 run）。

正向：基准样本与 qualified 变体全过七条勾稽中的 ①~⑥。
负向：对 model_dump() 副本注入缺陷，逐条断言各勾稽规则触发。
"""
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from ipo_eval_lab.fixtures import (
    CompanyProfile,
    FixtureDataError,
    Range,
    SanityBounds,
    check_profile,
    load_company,
    load_profile,
    load_sanity,
)

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
QUAL = FX / "companies" / "qualified_audit"


@pytest.fixture(scope="module")
def sanity() -> SanityBounds:
    return load_sanity(FX / "sanity.yaml")


@pytest.fixture(scope="module")
def base() -> CompanyProfile:
    return load_profile(BASE / "profile.json")


def _mutated(tmp_path: Path, profile: CompanyProfile, mutate: Callable[[dict], None]) -> CompanyProfile:
    """dump → 注入缺陷 → 落临时文件 → 重载（负向用例与 loader 走同一条路）。"""
    data = profile.model_dump(mode="json")
    mutate(data)
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return load_profile(p)


def _stmt(data: dict, year: int) -> dict:
    return next(s for s in data["statements"] if s["fiscal_year"] == year)


# ── 正向 ──


def test_base_passes_all_checks(sanity, base):
    check_profile(base, sanity)  # 全过 = 静默


def test_base_fixture_facts(base):
    assert base.company_id == "base_co_2029"
    assert base.applicant_profile.company_type == "general"
    assert base.documentary.mktcap_self_estimate is None  # G-C 路径：市值叶 → indeterminate
    assert base.documentary.invention_patents.granted_count == 5
    assert base.documentary.invention_patents.applied_to_main_business is True
    assert base.declared.self_developed_tech_intl_leading is None  # declared 全 null → needs_review 演示


def test_qualified_variant_loads(sanity):
    profile = load_profile(QUAL / "profile.json")
    opinions = {s.fiscal_year: s.audit.opinion for s in profile.statements}
    assert opinions[2023] == "qualified"  # 唯一差异：2023 意见改 qualified（E3 降级路径）
    assert opinions[2022] == "unqualified" and opinions[2024] == "unqualified"
    check_profile(profile, sanity)  # 审计意见变化不破坏勾稽 ①~⑥


def test_load_company_carries_golden(sanity):
    loaded = load_company(BASE, sanity)
    assert loaded.expected is not None
    assert loaded.expected["rulebook_version"] == "rb-2026.11"


def test_load_company_without_expected(sanity):
    assert load_company(QUAL, sanity).expected is None


# ── 负向：逐条勾稽 ──


def test_balance_identity_violation(sanity, base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2024)["balance"]["total_assets"] += 1

    with pytest.raises(FixtureDataError, match=r"勾稽① 2024.*total_assets"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_reconciliation_violation(sanity, base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2023)["reconciliation"]["adjustments"] += 1

    with pytest.raises(FixtureDataError, match=r"勾稽② 2023"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_equity_roll_violation(sanity, base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2024)["equity_roll"]["dividends"] += 1

    with pytest.raises(FixtureDataError, match=r"勾稽③ 2024.*dividends"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_equity_roll_chain_violation(sanity, base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2023)["equity_roll"]["opening_attrib_parent"] += 1  # 期初 ≠ 上年期末

    with pytest.raises(FixtureDataError, match=r"勾稽③ 2023: 期初"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_year_gap_detected(sanity, base, tmp_path):
    def m(d: dict) -> None:
        d["statements"] = [s for s in d["statements"] if s["fiscal_year"] != 2023]

    with pytest.raises(FixtureDataError, match=r"勾稽④: 年份不连续 2022 → 2024"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_audited_year_requires_opinion(sanity, base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2024)["audit"]["opinion"] = None

    with pytest.raises(FixtureDataError, match=r"勾稽⑤ 2024.*opinion"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_growth_bound_revenue_too_fast(sanity, base, tmp_path):
    def m(d: dict) -> None:
        # 5 亿 → 18 亿 = +260%，超出营收区间上界 +200%
        _stmt(d, 2024)["income"]["operating_revenues"] = 1800000000

    with pytest.raises(FixtureDataError, match=r"勾稽⑥ 2024.*营收.*260.0%"):
        check_profile(_mutated(tmp_path, base, m), sanity)


def test_widened_net_profit_band_is_load_bearing(base):
    """:回归护栏: 净利区间放宽 (−90%, +300%) 是承重设计——

    甲公司 1.5 → 0.3 亿 = −80% 是 window_roll 剧情的数字基础（勘误注二第 2 条）。
    换回默认区间 (−50%, +200%) 必须触发 ⑥，证明这个放宽不是摆设。
    """
    strict = SanityBounds(
        revenue=Range(min=-0.5, max=2.0),
        ocf=Range(min=-0.5, max=2.0),
        net_profit=Range(min=-0.5, max=2.0),
    )
    with pytest.raises(FixtureDataError, match=r"勾稽⑥ 2023.*归母净利.*-80.0%"):
        check_profile(base, strict)


# ── schema：extra=forbid 拼写防线 ──


def test_typo_field_rejected(base, tmp_path):
    def m(d: dict) -> None:
        _stmt(d, 2024)["income"]["operating_revnue"] = 1  # 拼错

    with pytest.raises(Exception):  # pydantic ValidationError（extra=forbid）
        _mutated(tmp_path, base, m)
