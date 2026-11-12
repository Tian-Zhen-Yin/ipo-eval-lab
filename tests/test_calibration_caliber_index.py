"""口径定义索引与 L2 等价前提（ADR-0010）。

钉住三件事：

1. **口径作用域有两级**：规则级（释义条）+ 节级（「本节所称 X」）。
   索引必须把两者都取到——少一级，L2 就会把有依据的口径后缀判成「来源外补充」。
2. **术语精确匹配**：「净资产收益率」不是「净资产」，前缀匹配会把口径张冠李戴。
3. **L2 提示词带作用域前提**：没有这条前提，判定模型按「本条自足」判，必然误判。
"""
from pathlib import Path

import pytest

from ipo_eval_lab.calibration.caliber_index import (
    build_index_from_doc, load_index,
)
from ipo_eval_lab.calibration.l2_gate import (
    L2_SYSTEM_PROMPT, L2_USER_TEMPLATE, build_l2_prompt, caliber_basis_for,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "rulebook" / "source_texts"


@pytest.fixture(scope="module")
def indexes():
    return load_index(SRC)


# ── 1. 规则级口径（释义条）──

@pytest.mark.parametrize("law_id", ["sse_main_2026", "szse_main_2026",
                                    "szse_chinext_2026", "sse_star_2026", "bse_2026"])
def test_rule_level_defines_net_profit_as_attributable_parent(indexes, law_id):
    """五部规则的释义条都要把净利润定为「归属于母公司所有者的净利润」。

    这是渲染后缀「（归母）」在每一处都成立的依据（ADR-0010 查实的法律事实一）。
    """
    idx = indexes[law_id]
    np_defs = [d for d in idx.rule_level if d.term == "净利润"]
    assert np_defs, f"{law_id} 释义条未取到净利润定义"
    assert any("归属于母公司所有者" in d.text for d in np_defs), \
        f"{law_id} 净利润定义缺归属口径：{[d.text for d in np_defs]}"


@pytest.mark.parametrize("law_id", ["sse_main_2026", "szse_main_2026",
                                    "szse_chinext_2026", "sse_star_2026", "bse_2026"])
def test_rule_level_defines_equity_as_attributable_parent(indexes, law_id):
    idx = indexes[law_id]
    eq_defs = [d for d in idx.rule_level if d.term == "净资产"]
    assert eq_defs, f"{law_id} 释义条未取到净资产定义"
    assert any("归属于母公司所有者" in d.text for d in eq_defs)


# ── 2. 节级口径 ──

def test_section_level_caliber_is_indexed_under_its_section(indexes):
    """沪主板 3.1.2 的「本节所称净利润…」要挂到「第一节 首次公开发行股票上市」名下。"""
    idx = indexes["sse_main_2026"]
    sec = "第一节 首次公开发行股票上市"
    assert sec in idx.by_section
    texts = [d.text for d in idx.by_section[sec]]
    assert any("本节所称净利润" in t and "孰低者为准" in t for t in texts), \
        f"节级净利润口径未取到：{texts}"
    # 同节内 3.1.6 也要能查到（3.1.6 无自己的口径定义，靠节级继承）
    assert idx.section_of("3.1.6") == sec


def test_article_section_lookup_works_for_mirror_boards(indexes):
    """沪深主板同文但节名/条文号不同，两边都要查得到。"""
    assert indexes["szse_main_2026"].section_of("3.1.6") is not None
    assert indexes["szse_chinext_2026"].section_of("2.1.2") is not None
    assert indexes["sse_star_2026"].section_of("2.1.2") is not None


# ── 3. 术语精确匹配（不张冠李戴）──

def test_roe_is_not_mistaken_for_net_assets(indexes):
    """「净资产收益率」是另一个术语，口径完全不同。

    前缀匹配会把 ROE 的定义挂到「净资产」名下——那会让引擎话术说错口径。
    """
    for law_id, idx in indexes.items():
        for d in idx.rule_level:
            if d.term == "净资产":
                assert "收益率" not in d.text, \
                    f"{law_id} 把净资产收益率当成了净资产口径：{d.text}"


def test_term_head_must_match_exactly():
    """释义条里「（十六）净资产收益率，…」不应被算作「净资产」的定义。"""
    doc = {
        "law_id": "t",
        "articles": [{
            "article": "15.1", "chapter": "第十五章 释义", "section": None,
            "text": "（一）净资产：指上市公司资产负债表列报的所有者权益。"
                    "（二）净资产收益率：根据中国证监会有关规定计算的净资产收益率。",
        }],
    }
    idx = build_index_from_doc(doc)
    eq = [d for d in idx.rule_level if d.term == "净资产"]
    assert len(eq) == 1
    assert "收益率" not in eq[0].text


# ── 4. L2 提示词带作用域前提 ──

def test_l2_prompt_states_two_level_scope():
    """提示词必须写明口径作用域有规则级/节级两级。

    没有这条，判定模型按「本条自足」判，把有依据的口径后缀判成来源外补充。
    """
    assert "规则级" in L2_SYSTEM_PROMPT
    assert "节级" in L2_SYSTEM_PROMPT
    assert "不得因" in L2_SYSTEM_PROMPT


def test_l2_prompt_contains_caliber_basis_section():
    """用户模板要有「口径定义依据」这一段输入。"""
    assert "【口径定义依据】" in L2_USER_TEMPLATE


def test_caliber_basis_renders_applicable_definitions(indexes):
    """装配出的依据段要同时含规则级与节级两条，且标明各自作用域。"""
    from ipo_eval_lab.calibration.models import (
        CandidateRule, CandidateClause, CandidateLeaf, CandidateContext,
        SourceClauseRef,
    )
    rule = CandidateRule(
        clause_id="wv_g1_c1",
        context=CandidateContext(board="SSE-MB", company_type="weighted_voting",
                                 group_no=1, group_id="cn_main_weighted_voting_g1",
                                 role="shared", scope="set"),
        clause=CandidateClause(
            clause_id="wv_g1_c1", law_ref="sse_main_2026#3.1.6", logic="all",
            display="最近一年净利润为正",
            leaves=[CandidateLeaf(leaf_id="l1", item_ref="np_latest", op="gt",
                                  threshold=0, threshold_format="number",
                                  threshold_text="为正", quote="最近一年净利润为正")],
        ),
        source=SourceClauseRef(law_id="sse_main_2026", article="3.1.6",
                                text="（占位）"),
    )
    basis = caliber_basis_for(rule, indexes)
    assert "规则级" in basis
    assert "节级" in basis
    assert "归属于母公司所有者" in basis       # 规则级归母
    assert "孰低者为准" in basis               # 节级扣非孰低


def test_caliber_basis_is_empty_when_no_index(indexes):
    """索引里没有该规则时不编造依据。"""
    from ipo_eval_lab.calibration.models import (
        CandidateRule, CandidateClause, CandidateLeaf, CandidateContext,
        SourceClauseRef,
    )
    rule = CandidateRule(
        clause_id="x",
        context=CandidateContext(board="SSE-MB", company_type="general",
                                 group_no=1, group_id="g1", role="shared"),
        clause=CandidateClause(
            clause_id="x", law_ref="x#1", logic="all", display="d",
            leaves=[CandidateLeaf(leaf_id="l1", item_ref="np_latest", op="gt",
                                  threshold=0, threshold_format="number",
                                  threshold_text="为正", quote="净利润为正")]),
        source=SourceClauseRef(law_id="不存在的规则", article="1", text="t"),
    )
    assert caliber_basis_for(rule, indexes) == ""
