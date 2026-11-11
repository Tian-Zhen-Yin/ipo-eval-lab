"""CONTEXT #9-V13 未审计年度样本测试（设计 0006 fixtures 契约）。

V13 落地：unaudited_2023 变体 = base_co_2029 复制，仅改 company_id / display_name /
2023 audit 三处。语义意义：E3 审计覆盖降级路径的样本——measures.audit=[audited] 下
未审计年度不进判定（勾稽⑤只约束 audited 年：status=audited 必须有 opinion 与
report_id，unaudited 无此要求）；叶级影响（哪些年度被剔除）随 T3 引擎落地验证，
本文件只测 fixtures 层：加载通过勾稽①~⑥、审计字段形状、数字与 base 逐字一致。
注意：不 import ipo_eval_lab.engine（引擎并行改动中，本测试独立于引擎演进）。
"""
from pathlib import Path

from ipo_eval_lab.fixtures import (
    CompanyProfile,
    SanityBounds,
    check_profile,
    load_company,
    load_profile,
    load_sanity,
)

REPO = Path(__file__).resolve().parents[1]
FX = REPO / "fixtures"
BASE = FX / "companies" / "base_co_2029"
VAR = FX / "companies" / "unaudited_2023"


def test_unaudited_variant_loads_and_passes_checks():
    sanity: SanityBounds = load_sanity(FX / "sanity.yaml")
    loaded = load_company(VAR, sanity)  # load_company 内部已跑勾稽①~⑥
    check_profile(loaded.profile, sanity)  # 再显式跑一次：全过 = 静默
    assert loaded.profile.company_id == "unaudited_2023"
    assert loaded.expected is None  # 变体不带 golden（与 qualified_audit 一致）


def test_audit_shape_by_year():
    profile = load_profile(VAR / "profile.json")
    audits = {s.fiscal_year: s.audit for s in profile.statements}
    assert set(audits) == {2022, 2023, 2024}

    a23 = audits[2023]
    assert a23.status == "unaudited"  # 唯一降级点：2023 未审计
    assert a23.opinion is None
    assert a23.report_id is None  # 勾稽⑤：unaudited 无 opinion/report_id 要求

    for y in (2022, 2024):  # 其余年度不受影响，仍 audited + unqualified
        assert audits[y].status == "audited"
        assert audits[y].opinion == "unqualified"
        assert audits[y].report_id is not None


def test_financials_identical_to_base():
    base = load_profile(BASE / "profile.json")
    var = load_profile(VAR / "profile.json")

    def key(s):  # 审计字段是变体差异本身，其余（数字）必须逐字一致
        return (
            s.fiscal_year,
            s.income.model_dump(),
            s.cash_flow.model_dump(),
            s.balance.model_dump(),
            s.equity_roll.model_dump(),
            s.reconciliation.model_dump(),
        )

    assert [key(s) for s in var.statements] == [key(s) for s in base.statements]

    s23 = next(s for s in var.statements if s.fiscal_year == 2023)  # 抽查锚点值
    assert s23.income.operating_revenues == 500000000
    assert s23.income.net_profit_attrib_parent.excl_nonrecurring == 30000000
    assert s23.income.net_profit_attrib_parent.as_reported == 30000000


def test_variant_metadata():
    profile: CompanyProfile = load_profile(VAR / "profile.json")
    assert profile.display_name == "甲公司（2023 未审计变体）"
    assert profile.applicant_profile == load_profile(BASE / "profile.json").applicant_profile
