"""
L1a 提取规格 · 批次 1（agent 会话当模型执行者，P7）

范围：沪深主板与科创板首节「首次公开发行」的市值财务条件条文
- sse_main_2026#3.1.2  境内发行人三个标准 → cn_main_general_g1 / g2 / g3
- sse_star_2026#2.1.2  科创板五个标准     → star_general_g1 ~ g5

口径：
- item_ref 只能取 rulebook/items.yaml 白名单（L0-4 会拦自造指标）
- quote 必须逐字命中原文（本文件加载时断言，L1b-1 再复核）
- threshold_text 保留原文数值形态（如 "2 亿元"），供 L1b-2 数值锚点比对
- 一条条文可产出多条候选（按标准拆套），覆盖率扫描按条文并集计算

产出：calibration/l1a/output/candidates_batch1.jsonl（可回放的 L1a 结果）
"""

from pathlib import Path
import sys

import yaml

from ipo_eval_lab.calibration.models import (
    CandidateContext, CandidateClause, CandidateLeaf, CandidateRule, SourceClauseRef,
)

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "rulebook" / "source_texts"
OUT = REPO / "calibration" / "l1a" / "output" / "candidates_batch1.jsonl"


def load_doc(law_id: str) -> dict:
    path = SRC / f"{law_id}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def article_text(doc: dict, article: str) -> str:
    for art in doc["articles"]:
        if str(art["article"]) == article:
            return art["text"]
    raise KeyError(f"{doc['law_id']}#{article} 不在原文库")


def leaf(leaf_id, item_ref, op, threshold, fmt, text, quote) -> CandidateLeaf:
    return CandidateLeaf(
        leaf_id=leaf_id, item_ref=item_ref, op=op, threshold=threshold,
        threshold_format=fmt, threshold_text=text, quote=quote,
    )


class Builder:
    def __init__(self):
        self.rules: list[CandidateRule] = []
        self.checked: list[str] = []

    def add(self, *, clause_id, group_id, branch_id, role, scope, board, ctype, group_no,
            law_id, article, doc, logic, leaves, display):
        source_text = article_text(doc, article)
        for lf in leaves:
            if lf.quote not in source_text:
                raise AssertionError(
                    f"[{clause_id}] quote 未逐字命中 {law_id}#{article}:\n  {lf.quote!r}"
                )
            self.checked.append(f"{clause_id}/{lf.leaf_id}")

        self.rules.append(CandidateRule(
            clause_id=clause_id,
            context=CandidateContext(
                board=board, company_type=ctype, group_no=group_no,
                group_id=group_id, branch_id=branch_id, role=role, scope=scope,
            ),
            clause=CandidateClause(
                clause_id=clause_id, law_ref=f"{law_id}#{article}",
                logic=logic, display=display, leaves=leaves,
            ),
            source=SourceClauseRef(
                law_id=law_id, article=article,
                chapter=doc.get("_chapter"), section=doc.get("_section"),
                text=source_text,
            ),
            evidence={
                "effective_from": str(doc.get("effective_from", "")),
                "doc_version": f"{law_id}@{doc.get('effective_from')}",
                "as_of_doc_version": f"{law_id}@{doc.get('effective_from')}",
                "extraction_batch": "batch1",
            },
        ))


def build() -> list[CandidateRule]:
    b = Builder()

    # ══════════════════ 沪主板 3.1.2：三个标准 ══════════════════
    sse = load_doc("sse_main_2026")
    art = "3.1.2"

    # 标准一：净利润三道 + （经营现金流 或 营业收入）
    b.add(clause_id="cn_main_g1_c1", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="general", group_no=1,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近三年净利润均为正",
          leaves=[leaf("cn_main_g1_c1_l1", "np_3y_allpos", "gt", 0, "number", "为正",
                       "最近3 年净利润均为正")])
    b.add(clause_id="cn_main_g1_c2", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="general", group_no=1,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近三年净利润累计不低于2亿元",
          leaves=[leaf("cn_main_g1_c2_l1", "np_3y_sum", "ge", 2e8, "number", "2 亿元",
                       "最近3 年净利润累计不低于2 亿元")])
    b.add(clause_id="cn_main_g1_c3", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="general", group_no=1,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近一年净利润不低于1亿元",
          leaves=[leaf("cn_main_g1_c3_l1", "np_latest", "ge", 1e8, "number", "1 亿元",
                       "最近一年净利润不低于1 亿元")])
    b.add(clause_id="cn_main_g1_b1_c1", group_id="cn_main_general_g1", branch_id="cn_main_general_g1-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=1,
          law_id="sse_main_2026", article=art, doc=sse, logic="any",
          display="经营现金流累计2亿元 或 营业收入累计15亿元",
          leaves=[
              leaf("cn_main_g1_b1_c1_l1", "ocf_3y_sum", "ge", 2e8, "number", "2 亿元",
                   "最近3 年经营活动产生的现金流量净额累计不低于2 亿元或营业收入累计不低于15 亿元"),
              leaf("cn_main_g1_b1_c1_l2", "rev_3y_sum", "ge", 1.5e9, "number", "15 亿元",
                   "最近3 年经营活动产生的现金流量净额累计不低于2 亿元或营业收入累计不低于15 亿元"),
          ])

    # 标准二：市值 50 亿 + 净利正 + 营收 6 亿 + 现金流累计 2.5 亿
    b.add(clause_id="cn_main_g2_b1_c1", group_id="cn_main_general_g2", branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=2,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("cn_main_g2_b1_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "预计市值不低于50 亿元")])
    b.add(clause_id="cn_main_g2_b1_c2", group_id="cn_main_general_g2", branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=2,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("cn_main_g2_b1_c2_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="cn_main_g2_b1_c3", group_id="cn_main_general_g2", branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=2,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近一年营业收入不低于6亿元",
          leaves=[leaf("cn_main_g2_b1_c3_l1", "rev_latest", "ge", 6e8, "number", "6 亿元",
                       "最近一年营业收入不低于6 亿元")])
    b.add(clause_id="cn_main_g2_b1_c4", group_id="cn_main_general_g2", branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=2,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近三年经营现金流净额累计不低于2.5亿元",
          leaves=[leaf("cn_main_g2_b1_c4_l1", "ocf_3y_sum", "ge", 2.5e8, "number", "2.5 亿元",
                       "最近3 年经营活动产生的现金流量净额累计不低于2.5 亿元")])

    # 标准三：市值 100 亿 + 净利正 + 营收 10 亿
    b.add(clause_id="cn_main_g3_b1_c1", group_id="cn_main_general_g3", branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=3,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("cn_main_g3_b1_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="cn_main_g3_b1_c2", group_id="cn_main_general_g3", branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=3,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("cn_main_g3_b1_c2_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="cn_main_g3_b1_c3", group_id="cn_main_general_g3", branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="general", group_no=3,
          law_id="sse_main_2026", article=art, doc=sse, logic="all",
          display="最近一年营业收入不低于10亿元",
          leaves=[leaf("cn_main_g3_b1_c3_l1", "rev_latest", "ge", 1e9, "number", "10 亿元",
                       "最近一年营业收入不低于10 亿元")])

    # ══════════════════ 科创板 2.1.2：五个标准 ══════════════════
    star = load_doc("sse_star_2026")
    art2 = "2.1.2"

    # 标准一：市值 10 亿 + （两年净利均为正且累计 5000 万）或（一年净利正且营收 1 亿）
    b.add(clause_id="star_g1_c0", group_id="star_general_g1", branch_id=None, role="shared",
          scope="set", board="STAR", ctype="general", group_no=1,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="预计市值不低于10亿元（两条路径共用）",
          leaves=[leaf("star_g1_c1_l1", "mktcap_forecast", "ge", 1e9, "number", "10 亿元",
                       "预计市值不低于人民币10 亿元")])
    b.add(clause_id="star_g1_b1_c1", group_id="star_general_g1", branch_id="star_general_g1-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=1,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近两年净利润均为正",
          leaves=[leaf("star_g1_b1_c1_l1", "np_2y_allpos", "gt", 0, "number", "为正",
                       "最近两年净利润均为正")])
    b.add(clause_id="star_g1_b1_c2", group_id="star_general_g1", branch_id="star_general_g1-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=1,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近两年净利润累计不低于5000万元",
          leaves=[leaf("star_g1_b1_c2_l1", "np_2y_sum", "ge", 5e7, "number", "5000 万元",
                       "累计净利润不低于人民币5000 万元")])
    b.add(clause_id="star_g1_b2_c1", group_id="star_general_g1", branch_id="star_general_g1-b2", role="branch",
          scope="set", board="STAR", ctype="general", group_no=1,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("star_g1_b2_c1_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="star_g1_b2_c2", group_id="star_general_g1", branch_id="star_general_g1-b2", role="branch",
          scope="set", board="STAR", ctype="general", group_no=1,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近一年营业收入不低于1亿元",
          leaves=[leaf("star_g1_b2_c2_l1", "rev_latest", "ge", 1e8, "number", "1 亿元",
                       "营业收入不低于人民币1 亿元")])

    # 标准二：市值 15 亿 + 营收 2 亿 + 研发强度 15%
    b.add(clause_id="star_g2_b1_c1", group_id="star_general_g2", branch_id="star_general_g2-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=2,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="预计市值不低于15亿元",
          leaves=[leaf("star_g2_b1_c1_l1", "mktcap_forecast", "ge", 1.5e9, "number", "15 亿元",
                       "预计市值不低于人民币15 亿元")])
    b.add(clause_id="star_g2_b1_c2", group_id="star_general_g2", branch_id="star_general_g2-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=2,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近一年营业收入不低于2亿元",
          leaves=[leaf("star_g2_b1_c2_l1", "rev_latest", "ge", 2e8, "number", "2 亿元",
                       "最近一年营业收入不低于人民币2 亿元")])
    b.add(clause_id="star_g2_b1_c3", group_id="star_general_g2", branch_id="star_general_g2-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=2,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近三年研发投入占营业收入比例不低于15%",
          leaves=[leaf("star_g2_b1_c3_l1", "rd_intensity_3y", "ge", 0.15, "percent", "15%",
                       "最近三年累计研发投入占最近三年累计营业收入的比例不低于15%")])

    # 标准三：市值 20 亿 + 营收 3 亿 + 经营现金流累计 1 亿
    b.add(clause_id="star_g3_b1_c1", group_id="star_general_g3", branch_id="star_general_g3-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=3,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="预计市值不低于20亿元",
          leaves=[leaf("star_g3_b1_c1_l1", "mktcap_forecast", "ge", 2e9, "number", "20 亿元",
                       "预计市值不低于人民币20 亿元")])
    b.add(clause_id="star_g3_b1_c2", group_id="star_general_g3", branch_id="star_general_g3-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=3,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近一年营业收入不低于3亿元",
          leaves=[leaf("star_g3_b1_c2_l1", "rev_latest", "ge", 3e8, "number", "3 亿元",
                       "最近一年营业收入不低于人民币3 亿元")])
    b.add(clause_id="star_g3_b1_c3", group_id="star_general_g3", branch_id="star_general_g3-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=3,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近三年经营现金流净额累计不低于1亿元",
          leaves=[leaf("star_g3_b1_c3_l1", "ocf_3y_sum", "ge", 1e8, "number", "1 亿元",
                       "最近三年经营活动产生的现金流量净额累计不低于人民币1 亿元")])

    # 标准四：市值 30 亿 + 营收 3 亿
    b.add(clause_id="star_g4_b1_c1", group_id="star_general_g4", branch_id="star_general_g4-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=4,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="预计市值不低于30亿元",
          leaves=[leaf("star_g4_b1_c1_l1", "mktcap_forecast", "ge", 3e9, "number", "30 亿元",
                       "预计市值不低于人民币30 亿元")])
    b.add(clause_id="star_g4_b1_c2", group_id="star_general_g4", branch_id="star_general_g4-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=4,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="最近一年营业收入不低于3亿元",
          leaves=[leaf("star_g4_b1_c2_l1", "rev_latest", "ge", 3e8, "number", "3 亿元",
                       "最近一年营业收入不低于人民币3 亿元")])

    # 标准五：市值 40 亿 + 业务/产品条件（judgment：医药临床 或 技术优势）
    b.add(clause_id="star_g5_b1_c1", group_id="star_general_g5", branch_id="star_general_g5-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=5,
          law_id="sse_star_2026", article=art2, doc=star, logic="all",
          display="预计市值不低于40亿元",
          leaves=[leaf("star_g5_b1_c1_l1", "mktcap_forecast", "ge", 4e9, "number", "40 亿元",
                       "预计市值不低于人民币40 亿元")])
    b.add(clause_id="star_g5_b1_c2", group_id="star_general_g5", branch_id="star_general_g5-b1", role="branch",
          scope="set", board="STAR", ctype="general", group_no=5,
          law_id="sse_star_2026", article=art2, doc=star, logic="any",
          display="主要业务/产品条件：医药核心产品二期临床 或 明显技术优势",
          leaves=[
              leaf("star_g5_b1_c2_l1", "product_approved_clinical", "eq", True, "boolean", "是",
                   "医药行业企业需至少有一项核心产品获准开展二期临床试验"),
              leaf("star_g5_b1_c2_l2", "self_developed_tech", "eq", True, "boolean", "是",
                   "其他符合科创板定位的企业需具备明显的技术优势并满足相应条件"),
          ])

    return b.rules


def main() -> int:
    rules = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rules:
            f.write(r.model_dump_json() + "\n")
    print(f"写出 {len(rules)} 条候选 → {OUT}")
    print(f"quote 逐字校验通过：{len(Builder().checked) if False else len(rules)} 条规则")
    return 0


if __name__ == "__main__":
    sys.exit(main())
