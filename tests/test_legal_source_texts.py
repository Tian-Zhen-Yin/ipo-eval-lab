"""法规原文库回归测试（审核 0006 P3-4 建议）

锁三类语义敏感点：
1. 契约与 checksum 一致性（审的就是切的那份 PDF）
2. 核心上市标准条文的数值白名单（评测引擎命门：数值错一字结论即错）
3. 完整性自检：条文全部以句末标点收尾（审核 0006 四处 P0 的共同特征）

数值白名单来源：docs/reviews/0006-legal-source-texts-audit.md §3 矩阵
（17 条核心条文 67/67 逐字比对通过后的抽取值）。
"""

import hashlib
import re
from pathlib import Path

import pytest
import yaml

from ipo_eval_lab.legal.models import SourceDoc

SRC_DIR = Path("rulebook/source_texts")
RAW_DIR = Path("raw/legal_docs_20261111")

LAWS = [
    "sse_main_2026",
    "sse_star_2026",
    "szse_main_2026",
    "szse_chinext_2026",
    "bse_2026",
]

# 核心上市标准条文数值白名单：(law_id, article, [数值特征串])
# 匹配前对 text 做去空格归一化，避免 PDF 空格形态漂移（"50 亿元" vs "50亿元"）
CORE_VALUE_ASSERTS = [
    ("sse_main_2026", "3.1.2", [
        "最近3年净利润均为正", "累计不低于2亿元", "最近一年净利润不低于1亿元",
        "现金流量净额累计不低于2亿元", "营业收入累计不低于15亿元",
        "预计市值不低于50亿元", "营业收入不低于6亿元", "累计不低于2.5亿元",
        "预计市值不低于100亿元", "营业收入不低于10亿元",
    ]),
    ("szse_main_2026", "3.1.2", [
        "最近三年净利润均为正", "累计不低于2亿元", "最近一年净利润不低于1亿元",
        "现金流量净额累计不低于2亿元", "营业收入累计不低于15亿元",
        "预计市值不低于50亿元", "营业收入不低于6亿元", "累计不低于2.5亿元",
        "预计市值不低于100亿元", "营业收入不低于10亿元",
    ]),
    ("sse_star_2026", "2.1.2", [
        "预计市值不低于人民币10亿元", "累计净利润不低于人民币5000万元",
        "营业收入不低于人民币1亿元", "预计市值不低于人民币15亿元",
        "营业收入不低于人民币2亿元", "比例不低于15%",
        "预计市值不低于人民币20亿元", "营业收入不低于人民币3亿元",
        "现金流量净额累计不低于人民币1亿元", "预计市值不低于人民币30亿元",
        "预计市值不低于人民币40亿元",
    ]),
    ("szse_chinext_2026", "2.1.2", [
        "累计净利润不低于1亿元", "最近一年净利润不低于6000万元",
        "预计市值不低于15亿元", "营业收入不低于4亿元",
        "预计市值不低于50亿元", "营业收入不低于3亿元",
        "预计市值不低于30亿元", "复合增长率不低于30%",
        "预计市值不低于40亿元", "累计研发投入不低于1亿元", "比例不低于15%",
    ]),
    ("bse_2026", "2.1.3", [
        "预计市值不低于2亿元", "净利润均不低于1500万元", "收益率平均不低于8%",
        "最近一年净利润不低于2500万元", "预计市值不低于4亿元",
        "营业收入平均不低于1亿元", "增长率不低于30%", "预计市值不低于8亿元",
        "营业收入不低于2亿元", "比例不低于8%", "预计市值不低于15亿元",
        "研发投入合计不低于5000万元",
    ]),
]

# 核心条文存在性清单（审核 0006 §3 覆盖的 17 条中的关键存在项）
CORE_ARTICLES = [
    ("sse_main_2026", ["3.1.1", "3.1.2"]),
    ("sse_star_2026", ["2.1.1", "2.1.2", "2.1.3"]),
    ("szse_main_2026", ["3.1.1", "3.1.2"]),
    ("szse_chinext_2026", ["2.1.1", "2.1.2", "2.1.3", "2.1.4"]),
    ("bse_2026", ["2.1.1", "2.1.2", "2.1.3", "2.1.4"]),
]

SENT_END_CHARS = ("。", "；", "：", "）", "”", "…", "!")


def _norm(text: str) -> str:
    """去空格归一化（匹配时规避 PDF 空格形态漂移）"""
    return re.sub(r"\s+", "", text)


@pytest.fixture(scope="module", params=LAWS)
def doc(request):
    """按契约加载各板块原文库"""
    path = SRC_DIR / f"{request.param}.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceDoc.model_validate(data)


# ---- 1. 契约与 checksum ----

def test_checksum_matches_pdf(doc):
    """YAML checksum 必须等于 PDF 实际 sha256——审的就是切的那份"""
    pdf = RAW_DIR / f"{doc.law_id}.pdf"
    actual = "sha256:" + hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert doc.checksum == actual, f"{doc.law_id} checksum 与 PDF 不一致"


def test_articles_non_empty_text(doc):
    assert len(doc.articles) > 0
    assert all(a.text.strip() for a in doc.articles)


# ---- 2. 核心条文存在性与数值白名单 ----

@pytest.mark.parametrize("law_id,article_ids", CORE_ARTICLES)
def test_core_articles_exist(law_id, article_ids):
    data = yaml.safe_load((SRC_DIR / f"{law_id}.yaml").read_text(encoding="utf-8"))
    ids = {a["article"] for a in data["articles"]}
    missing = [aid for aid in article_ids if aid not in ids]
    assert not missing, f"{law_id} 缺核心条文: {missing}"


@pytest.mark.parametrize("law_id,article,expects", CORE_VALUE_ASSERTS)
def test_core_value_whitelist(law_id, article, expects):
    """核心上市标准数值白名单——任一缺失即数值回归"""
    data = yaml.safe_load((SRC_DIR / f"{law_id}.yaml").read_text(encoding="utf-8"))
    art = next(a for a in data["articles"] if a["article"] == article)
    norm = _norm(art["text"])
    lost = [e for e in expects if _norm(e) not in norm]
    assert not lost, f"{law_id} {article} 数值特征丢失: {lost}"


# ---- 3. 完整性自检（审核 0006 P3-4：未完句特征拦截同类 P0 回归） ----

def test_no_unterminated_article(doc):
    bad = [
        a.article
        for a in doc.articles
        if a.text.rstrip() and not a.text.rstrip().endswith(SENT_END_CHARS)
    ]
    assert not bad, f"{doc.law_id} 存在未完句条文（疑似截断）: {bad[:5]}"


def test_article_id_sequence_monotonic(doc):
    """同前缀内条款号尾号单调递增（回退 = 误切信号）"""
    prev_prefix, prev_tail = None, 0
    for a in doc.articles:
        parts = a.article.split(".")
        prefix, tail = tuple(parts[:-1]), int(parts[-1])
        if prefix == prev_prefix:
            assert tail == prev_tail + 1, f"{doc.law_id} 条款号异常: {a.article}"
        prev_prefix, prev_tail = prefix, tail
