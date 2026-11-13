"""段① 发行条件候选生成（底稿0003 续，M1 三段收口的最后一段）

法律源两轨（G1 勘察结论）：
- **证监会发行条件**（205号令第十~十三条）：定性合规族——经营年限/组织机构/会计
  与内控/业务与团队稳定/权属与实控人/合法经营（midas IPO-40 的 check39~49 锚点）
- **交易所上市条件首条的数值档**（已在库！五部规则 3.1.1 / 2.1.1 / 2.1.2）：
  发行后股本 + 公开发行比例双档择一（midas IPO-37/38/39 锚点）——无需新采购

midas 归位（与 P5b/段② 同思路）：
- IPO-37（主板 5000万∧25%）+ IPO-38（全板 4亿∧10%）→ iss_qual_main_g1 双支路
  （数值档择一 = branch；midas 拆两套系拆行）
- IPO-39（科创/创业/北交 3000万∧0.25）→ iss_qual_gem_g1 双支路（科创创业）+
  iss_qual_bse_g1（北交所按 2.1.2 原文全条件：midas 漏挂牌12月/100万股/100人/
  200股东/净资产5000万——差异清单注记）
- IPO-40（治理 11 条定性）→ iss_conduct_g1 六 clause（205号令第十~十三条锚点，
  check47/48 审计无保留 v1 判 judgment——引擎 audit 叶扩展后可真实判定，底稿注记）

op 口径：midas check38「大于」25% vs 原文「25%以上」→ ge（ADR-0010 先例）。

用法：
    python scripts/build_issuance_candidates.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "rulebook" / "source_texts"
OUT = REPO / "calibration" / "l1a" / "output" / "candidates_issuance.jsonl"

EFF_205 = "2023-02-17"
EFF_RULES = {"sse_main_2026": "2026-04-30", "szse_main_2026": "2026-04-30",
             "sse_star_2026": "2026-04-30", "szse_chinext_2026": "2026-04-30",
             "bse_2026": "2026-04-24"}


def law(law_id: str) -> dict:
    return yaml.safe_load((SRC / f"{law_id}.yaml").read_text(encoding="utf-8"))


def quote_of(law_id: str, article: str, key: str) -> tuple[str, str]:
    doc = law(law_id)
    art = next(a for a in doc["articles"] if a["article"] == article)
    text = art["text"]
    i = text.find(key)
    assert i >= 0, f"{law_id}#{article} 找不到关键子句：{key}"
    start = max(text.rfind("。", 0, i), text.rfind("；", 0, i), 0)
    start = start + 1 if start > 0 else 0
    end = text.find("。", i)
    end = end + 1 if end > 0 else len(text)
    sentence = text[start:end]
    assert key in sentence and sentence in text
    return sentence, text


def leaf(cid, item_ref, op, value, fmt, threshold_text, quote):
    return {"leaf_id": f"{cid}_l1", "item_ref": item_ref, "op": op, "threshold": value,
            "threshold_format": fmt, "threshold_text": threshold_text, "quote": quote}


def cand(clause_id, board, group_id, branch_id, clause, law_id, article, source_text,
         section, role="branch", gno=None):
    return {
        "clause_id": clause_id,
        "context": {"board": board, "company_type": "general", "group_no": gno,
                    "group_id": group_id, "branch_id": branch_id, "role": role,
                    "scope": "issuance", "section": section},
        "clause": clause,
        "source": {"law_id": law_id, "article": article, "chapter": None,
                   "section": None, "text": source_text},
        "evidence": {"effective_from": EFF_RULES.get(law_id, EFF_205)},
        "extracted_at": "2026-11-13",
        "model_provider": "issuance-mapping",
        "model_name": "build_issuance_candidates",
    }


MIRROR = {"SSE-MB": "sse_main_2026", "SZSE-MB": "szse_main_2026",
          "STAR": "sse_star_2026", "ChiNext": "szse_chinext_2026", "BSE": "bse_2026"}

q_205_10, t_205_10 = quote_of("csrc_ipo_measure", "第十条", "持续经营三年以上")
q_205_11, t_205_11 = quote_of("csrc_ipo_measure", "第十一条", "无保留意见的审计报告")
q_205_12, t_205_12 = quote_of("csrc_ipo_measure", "第十二条", "主营业务、控制权和管理团队稳定")
q_205_12c, _ = quote_of("csrc_ipo_measure", "第十二条", "权属清晰")
q_205_12d, _ = quote_of("csrc_ipo_measure", "第十二条", "重大权属纠纷")
q_205_13, t_205_13 = quote_of("csrc_ipo_measure", "第十三条", "符合国家产业政策")
q_205_org, _ = quote_of("csrc_ipo_measure", "第十条", "组织机构")

records: list[dict] = []

# ══ 主体资格组·主板（midas IPO-37/38 → 双支路）══
q_main_cap, t_main = quote_of("sse_main_2026", "3.1.1", "股本总额不低于5000")
q_main_pf, _ = quote_of("sse_main_2026", "3.1.1", "25%以上")
q_main_pf10, _ = quote_of("sse_main_2026", "3.1.1", "10%以上")

QUAL_SHARED = [
    ("iss_q_op_years_c1", "op_years_ge3", "ge", 3, "integer", "三年以上", q_205_10,
     "csrc_ipo_measure", "第十条", "依法设立且持续经营三年以上（有限责任公司折股整体变更自成立日起算）"),
    ("iss_q_org_c2", "org_structure_sound", "eq", True, "boolean", "是", q_205_org,
     "csrc_ipo_measure", "第十条", "依法设立的股份有限公司，组织机构健全且运行良好"),
]
QUAL_B1 = [
    ("iss_q_cap_b1_c1", "shares_after_ipo", "ge", 50000000, "integer", "不低于5000万", q_main_cap, "sse_main_2026", "3.1.1", "发行后股本总额不低于5000万元"),
    ("iss_q_pf_b1_c2", "public_float_ge", "ge", 0.25, "percent", "25%以上", q_main_pf, "sse_main_2026", "3.1.1", "公开发行的股份达到公司股份总数的25%以上"),
]
QUAL_B2 = [
    ("iss_q_cap_b2_c1", "shares_after_ipo", "gt", 400000000, "integer", "超过4亿元", q_main_cap, "sse_main_2026", "3.1.1", "公司股本总额超过4亿元"),
    ("iss_q_pf_b2_c2", "public_float_ge", "ge", 0.10, "percent", "10%以上", q_main_pf10, "sse_main_2026", "3.1.1", "公开发行股份的比例为10%以上"),
]


def qual_records(group_id, boards, cap_law_map, b1_def, b2_def, art_no):
    """主板/科创创业 资格组：shared 2 + 双支路各 2，逐板出候选（镜像板挂镜像法）。

    art_no 显式指定（主板 3.1.1 / 科创创业 2.1.1）——主板规则同样有 2.1.1（红筹
    上市条款，文档序在前），按 in 元组取第一个会误抓。
    """
    out = []
    for board in boards:
        cap_law = cap_law_map[board]
        t_cap = law(cap_law)
        art_211 = next(a for a in t_cap["articles"] if a["article"] == art_no)
        text_211 = art_211["text"]
        art_id = art_211["article"]   # = art_no
        for cid, item, op, v, fmt, tt, quote, law_id, article, display in QUAL_SHARED:
            out.append(cand(cid, board, group_id, None,
                            {"clause_id": cid, "law_ref": f"{law_id}#{article}", "logic": "all",
                             "display": display, "leaves": [leaf(cid, item, op, v, fmt, tt, quote)]},
                            law_id, article, t_205_10,
                            section="subject_qualification", role="shared"))
        for cid, item, op, v, fmt, tt, _q, law_id, article, display in b1_def:
            q = quote_of(cap_law, art_id, "以上" if item == "public_float_ge" else "不低于")[0]
            out.append(cand(cid, board, group_id, f"{group_id}-b1",
                            {"clause_id": cid, "law_ref": f"{cap_law}#{art_id}", "logic": "all",
                             "display": display, "leaves": [leaf(cid, item, op, v, fmt, tt, q)]},
                            cap_law, art_id, text_211, section="subject_qualification"))
        for cid, item, op, v, fmt, tt, _q, law_id, article, display in b2_def:
            q = quote_of(cap_law, art_id, "10%以上" if item == "public_float_ge" else "超过")[0]
            out.append(cand(cid, board, group_id, f"{group_id}-b2",
                            {"clause_id": cid, "law_ref": f"{cap_law}#{art_id}", "logic": "all",
                             "display": display, "leaves": [leaf(cid, item, op, v, fmt, tt, q)]},
                            cap_law, art_id, text_211, section="subject_qualification"))
    return out


records += qual_records(
    "iss_qual_main_g1", ["SSE-MB", "SZSE-MB"],
    MIRROR,
    QUAL_B1, QUAL_B2, "3.1.1",
)

# 科创/创业：3000万档（midas IPO-39 科创创业部分）
q_gem_cap, _ = quote_of("sse_star_2026", "2.1.1", "3000")
GEM_B1 = [
    ("iss_gq_cap_b1_c1", "shares_after_ipo", "ge", 30000000, "integer", "不低于3000万", q_gem_cap, "sse_star_2026", "2.1.1", "发行后股本总额不低于3000万元"),
    ("iss_gq_pf_b1_c2", "public_float_ge", "ge", 0.25, "percent", "25%以上", q_main_pf, "sse_star_2026", "2.1.1", "公开发行的股份达到公司股份总数的25%以上"),
]
GEM_B2 = [
    ("iss_gq_cap_b2_c1", "shares_after_ipo", "gt", 400000000, "integer", "超过4亿元", q_gem_cap, "sse_star_2026", "2.1.1", "公司股本总额超过人民币4亿元"),
    ("iss_gq_pf_b2_c2", "public_float_ge", "ge", 0.10, "percent", "10%以上", q_main_pf10, "sse_star_2026", "2.1.1", "公开发行股份的比例为10%以上"),
]
records += qual_records(
    "iss_qual_gem_g1", ["STAR", "ChiNext"],
    MIRROR,
    GEM_B1, GEM_B2, "2.1.1",
)

# ══ 主体资格组·北交所（bse_2026#2.1.2 全条件；midas IPO-39 北交所部分归位+漏项补齐）══
q_bse_all, t_bse = quote_of("bse_2026", "2.1.2", "净资产不低于5000")
records.append(cand(
    "iss_bq_op_years_c0", "BSE", "iss_qual_bse_g1", None,
    {"clause_id": "iss_bq_op_years_c0", "law_ref": "csrc_ipo_measure#第十条", "logic": "all",
     "display": "依法设立且持续经营三年以上", "leaves": [leaf("iss_bq_op_years_c0", "op_years_ge3", "ge", 3, "integer", "三年以上", q_205_10)]},
    "csrc_ipo_measure", "第十条", t_205_10, section="subject_qualification", role="shared",
))
BSE_B1 = [
    ("iss_bq_net_assets_c1", "net_assets_ge_50m", "ge", 50000000, "number", "不低于5000万元", q_bse_all, "bse_2026", "2.1.2", "最近一年期末净资产不低于5000万元"),
    ("iss_bq_offering_c2", "bse_offering_requirements", "eq", True, "boolean", "是", q_bse_all, "bse_2026", "2.1.2", "公开发行不少于100万股、对象不少于100人；股东不少于200人"),
    ("iss_bq_cap_c3", "shares_after_ipo", "ge", 30000000, "integer", "不少于3000万", q_bse_all, "bse_2026", "2.1.2", "公开发行后股本总额不少于3000万元"),
    ("iss_bq_pf_c4", "public_float_ge", "ge", 0.25, "percent", "25%以上", q_bse_all, "bse_2026", "2.1.2", "公众股东持股比例不低于25%（超4亿为10%以上）"),
]
for cid, item, op, v, fmt, tt, quote, law_id, article, display in BSE_B1:
    records.append(cand(
        cid, "BSE", "iss_qual_bse_g1", "iss_qual_bse_g1-b1",
        {"clause_id": cid, "law_ref": f"{law_id}#{article}", "logic": "all",
         "display": display, "leaves": [leaf(cid, item, op, v, fmt, tt, quote)]},
        law_id, article, t_bse, section="subject_qualification",
    ))

# ══ 规范运行组（midas IPO-40 → 205号令第十~十三条六 clause；全板块适用）══
# c1 拆双叶（logic=all）：audit_clean_3y 定量真实判定（facts.audit）∧
# ic_clean_3y judgment（内控鉴证需专业核查）——midas check47/48 拆行对齐。
CONDUCT = [
    ("iss_c_audit_c1", None, q_205_11, "csrc_ipo_measure", "第十一条",
     "会计基础规范，最近三年审计报告无保留意见，内控制度健全有效"),
    ("iss_c_stable_c2", "biz_team_stable", q_205_12, "csrc_ipo_measure", "第十二条",
     "主营业务、控制权和管理团队稳定（主板三年/科创创业二年无重大不利变化）"),
    ("iss_c_coretech_c3", "core_tech_team_stable", q_205_12, "csrc_ipo_measure", "第十二条",
     "核心技术人员稳定且最近二年无重大不利变化（科创板）"),
    ("iss_c_equity_c4", "equity_clear_controller_stable", q_205_12c, "csrc_ipo_measure", "第十二条",
     "股份权属清晰、不存在重大权属纠纷；实际控制人没有变更"),
    ("iss_c_dispute_c5", "no_major_dispute_contingency", q_205_12d, "csrc_ipo_measure", "第十二条",
     "不存在重大权属纠纷、偿债风险、担保诉讼仲裁等对持续经营有重大不利影响的事项"),
    ("iss_c_lawful_c6", "lawful_business_3y", q_205_13, "csrc_ipo_measure", "第十三条",
     "生产经营合法合规、符合国家产业政策；最近三年无重大违法犯罪"),
]
ALL_BOARDS = ["SSE-MB", "SZSE-MB", "STAR", "ChiNext", "BSE"]
for cid, item, q, law_id, article, display in CONDUCT:
    if item is None:   # c1：定量审计叶 + judgment 内控叶（logic=all 合取）
        leaves = [
            leaf(f"{cid}_a", "audit_clean_3y", "eq", True, "boolean", "是", q),
            leaf(f"{cid}_i", "ic_clean_3y", "eq", True, "boolean", "是", q),
        ]
    else:
        leaves = [leaf(cid, item, "eq", True, "boolean", "是", q)]
    for board in ALL_BOARDS:
        records.append(cand(
            cid, board, "iss_conduct_g1", "iss_conduct_g1-b1",
            {"clause_id": cid, "law_ref": f"{law_id}#{article}", "logic": "all",
             "display": display, "leaves": leaves},
            law_id, article,
            {"第十一条": t_205_11, "第十二条": t_205_12, "第十三条": t_205_13}[article],
            section="conduct_compliance",
        ))


def main() -> int:
    OUT.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    from collections import Counter
    groups = Counter(r["context"]["group_id"] for r in records)
    print(f"写入 {OUT.relative_to(REPO)}（{len(records)} 条候选）")
    for gid, n in sorted(groups.items()):
        print(f"  {gid}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
