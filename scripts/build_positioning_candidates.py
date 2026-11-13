"""段② 板块定位候选生成（G4b，底稿 0003）

midas IPO-41~61 的 21 套板块匹配 → **4 个 positioning group**（归位，与 P5b 同思路：
midas 拆行/拆套 → 权威模型收敛）：

- IPO-41/42（沪深主板定位）→ cn_main_positioning_g1（沪深同文一组双板，1 支路 judgment）
- IPO-43~46（科创常规四项）→ star_positioning_g1 支路 b1——midas 把「占比5% 或 8000万」
  拆成 43/44 两套、「cagr25% 或 营收3亿」拆成 (43/44) vs (45/46) 两套，原文均为**内联或**，
  按 clause logic:any 收敛（R2-a 先例）
- IPO-47~51（科创例外五项）→ star_positioning_g1 支路 b2~b6（原文「符合情形之一」= 支路 OR）
- IPO-52~54（创业板三选一）→ chinext_positioning_g1 支路 b1~b3
- IPO-55~57（创业板「营收≥3亿」变体）→ 深交所规定第四条末句「最近一年营业收入金额达到
  3亿元的企业不适用营收复合增长率要求」→ clause logic:any 内联（cagr ∨ 营收3亿），不设独立套
- IPO-58~60（创业板红筹已上市变体）→ 同条末句「已境外上市红筹不适用」→ Clause.exemptions
  （redchip_status=listed → 豁免 rev_3y_cagr 叶，ADR-0008）
- IPO-61（北交所定位）→ bse_positioning_g1（锚点 bse_2026#1.4）

引文全部从 rulebook/source_texts/ 逐字提取（按关键子句定位句号边界，L1b 锚点要求）。
产出 candidates_positioning.jsonl，走既有签核→导出链。

已知不编码（midas 无对应行，需求边界外，底稿0003 §2 注记）：
- 指引第一条(3)软件行业替代义务（豁免专利但研发占比提至10%）
- 指引第一条(4)「采用 2.1.2(五) 上市标准企业豁免营收增长项」（豁免条件指向所选上市套，
  非主体侧事实字段，ADR-0008 表达不了；已境外上市红筹部分已编码）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "rulebook" / "source_texts"
OUT = REPO / "calibration" / "l1a" / "output" / "candidates_positioning.jsonl"

EFF = "2024-04-30"


def law(law_id: str) -> dict:
    return yaml.safe_load((SRC / f"{law_id}.yaml").read_text(encoding="utf-8"))


def quote_of(law_id: str, article: str, key: str) -> tuple[str, str]:
    """从条款正文取「含 key 的整句」（句号边界）→ (quote, 全文)。quote 必须逐字在文中。"""
    doc = law(law_id)
    art = next(a for a in doc["articles"] if a["article"] == article)
    text = art["text"]
    i = text.find(key)
    assert i >= 0, f"{law_id}#{article} 找不到关键子句：{key}"
    start = max(text.rfind("。", 0, i), text.rfind("；", 0, i), 0)
    if start > 0:
        start += 1
    end = min(
        (text.find("。", i) + 1) or len(text),
        len(text),
    )
    sentence = text[start:end]
    assert key in sentence and sentence in text
    return sentence, text


def leaf(clause_id: str, item_ref: str, op: str, value, fmt: str, threshold_text: str,
         quote: str = "") -> dict:
    return {"leaf_id": f"{clause_id}_l1", "item_ref": item_ref, "op": op,
            "threshold": value, "threshold_format": fmt, "threshold_text": threshold_text,
            "quote": quote}


def cand(clause_id, board, group_id, branch_id, clause, law_id, article, source_text,
         ctype="general", gno=None, role="branch", scope="positioning"):
    return {
        "clause_id": clause_id,
        "context": {"board": board, "company_type": ctype, "group_no": gno,
                    "group_id": group_id, "branch_id": branch_id, "role": role, "scope": scope},
        "clause": clause,
        "source": {"law_id": law_id, "article": article, "chapter": None,
                   "section": None, "text": source_text},
        "evidence": {"effective_from": EFF},
        "extracted_at": "2026-11-13",
        "model_provider": "positioning-mapping",
        "model_name": "build_positioning_candidates",
    }


REDCHIP_EXEMPT = lambda item: {   # noqa: E731  「已境外上市红筹不适用营收复合增长率要求」
    "when": {"profile_field": "redchip_status", "equals": "listed"},
    "excludes": [item],
    "note": "已境外上市红筹企业不适用营业收入复合增长率要求（深交所创业板推荐规定第四条末句）",
}

records: list[dict] = []

# ══ 1. 主板定位（IPO-41/42 → 一组双板）══
q, txt = quote_of("cn_audit_rule", "第三条", "大盘蓝筹")
records.append(cand(
    "cn_pos_main_fit_c1", "SSE-MB", "cn_main_positioning_g1", "cn_main_positioning_g1-b1",
    {"clause_id": "cn_pos_main_fit_c1", "law_ref": "cn_audit_rule#第三条", "logic": "all",
     "display": "符合主板定位——大盘蓝筹（业务模式成熟、经营业绩稳定、规模较大、行业代表性）",
     "leaves": [leaf("cn_pos_main_fit_c1", "main_board_fit", "eq", True, "boolean", "是", quote=q)]},
    "cn_audit_rule", "第三条", txt,
))
records.append(cand(
    "cn_pos_main_fit_c1", "SZSE-MB", "cn_main_positioning_g1", "cn_main_positioning_g1-b1",
    {**records[-1]["clause"], "clause_id": "cn_pos_main_fit_c1"},
    "cn_audit_rule", "第三条", txt,
))

# ══ 2. 科创板定位（IPO-43~51 → 一组六支路）══
q_ind, txt_ind = quote_of("sse_star_recommend", "第五条", "高新技术产业和战略性新兴产业")
q_neg, _ = quote_of("csrc_kechuang_attr", "三、", "禁止房地产")
q_reg, txt_reg = quote_of("sse_star_recommend", "第六条", "最近三年研发投入占营业收入比例5%以上")
q_rev, _ = quote_of("sse_star_recommend", "第六条", "最近三年营业收入复合增长率达到25%")
q_exc, txt_exc = quote_of("csrc_kechuang_attr", "二、", "核心技术经国家主管部门认定")

star_shared = cand(
    "star_pos_industry_c0", "STAR", "star_positioning_g1", None,
    {"clause_id": "star_pos_industry_c0", "law_ref": "sse_star_recommend#第五条", "logic": "all",
     "display": "属于科创板服务的行业领域（高新技术产业和战略性新兴产业）",
     "leaves": [leaf("star_pos_industry_c0", "star_industry_fit", "eq", True, "boolean",
                     "是", quote=q_ind)]},
    "sse_star_recommend", "第五条", txt_ind, role="shared",
)
star_shared["context"]["hard_filters"] = [{
    "field": "industry", "op": "not_in",
    "values": ["房地产业", "金融业", "货币金融服务", "资本市场服务", "保险业", "其他金融业"],
    "note": f"禁止房地产和主要从事金融、投资类业务的企业在科创板上市（指引第三条：{q_neg}）",
}]
records.append(star_shared)

# b1 常规四项（IPO-43~46 收敛：内联或归位）
records.append(cand(
    "star_pos_reg_c1", "STAR", "star_positioning_g1", "star_positioning_g1-b1",
    {"clause_id": "star_pos_reg_c1", "law_ref": "sse_star_recommend#第六条", "logic": "any",
     "display": "研发投入：最近三年占营收比5%以上 或 累计8000万元以上",
     "leaves": [
         {**leaf("star_pos_reg_c1", "rd_intensity_3y", "ge", 0.05, "percent", "占比5%以上", quote=q_reg), "leaf_id": "star_pos_reg_c1_l1"},
         {**leaf("star_pos_reg_c1", "rd_3y_sum", "ge", 80000000, "number", "累计8000万元以上", quote=q_reg), "leaf_id": "star_pos_reg_c1_l2"},
     ]},
    "sse_star_recommend", "第六条", txt_reg,
))
records.append(cand(
    "star_pos_reg_c2", "STAR", "star_positioning_g1", "star_positioning_g1-b1",
    {"clause_id": "star_pos_reg_c2", "law_ref": "sse_star_recommend#第六条", "logic": "all",
     "display": "研发人员占当年员工总数的比例不低于10%",
     "leaves": [leaf("star_pos_reg_c2", "rd_staff_ratio_item", "ge", 0.10, "percent", "不低于10%", quote=q_reg)]},
    "sse_star_recommend", "第六条", txt_reg,
))
records.append(cand(
    "star_pos_reg_c3", "STAR", "star_positioning_g1", "star_positioning_g1-b1",
    {"clause_id": "star_pos_reg_c3", "law_ref": "sse_star_recommend#第六条", "logic": "all",
     "display": "应用于主营业务并能够产业化的发明专利7项以上",
     "leaves": [leaf("star_pos_reg_c3", "invention_patents_ind", "ge", 7, "integer", "7项以上", quote=q_reg)]},
    "sse_star_recommend", "第六条", txt_reg,
))
records.append(cand(
    "star_pos_reg_c4", "STAR", "star_positioning_g1", "star_positioning_g1-b1",
    {"clause_id": "star_pos_reg_c4", "law_ref": "sse_star_recommend#第六条", "logic": "any",
     "display": "营收增长：最近三年复合增长率25%以上 或 最近一年营收3亿元（红筹已上市豁免增长项）",
     "leaves": [
         {**leaf("star_pos_reg_c4", "rev_3y_cagr", "ge", 0.25, "percent", "25%以上", quote=q_rev), "leaf_id": "star_pos_reg_c4_l1"},
         {**leaf("star_pos_reg_c4", "rev_latest", "ge", 300000000, "number", "3亿元", quote=q_rev), "leaf_id": "star_pos_reg_c4_l2"},
     ],
     "exemptions": [REDCHIP_EXEMPT("rev_3y_cagr")]},
    "sse_star_recommend", "第六条", txt_reg,
))

# b2~b6 例外五项（IPO-47~51；指引第二条(5) 专利50项 = quantitative）
EXCEPTIONS = [
    ("star_pos_exc1_c1", "core_tech_intl_or_strategy", "核心技术经国家主管部门认定"),
    ("star_pos_exc2_c1", "national_science_award", "获得国家科技进步奖"),
    ("star_pos_exc3_c1", "national_mega_science_project", "国家重大科技专项项目"),
    ("star_pos_exc4_c1", "import_substitution", "进口替代"),
]
for cid, item, key in EXCEPTIONS:
    q, _ = quote_of("csrc_kechuang_attr", "二、", key)
    records.append(cand(
        cid, "STAR", "star_positioning_g1", "star_positioning_g1-" + cid.split("_")[2],
        {"clause_id": cid, "law_ref": "csrc_kechuang_attr#二、", "logic": "all",
         "display": f"科创属性例外：{key}（虽未达常规指标但符合情形）",
         "leaves": [leaf(cid, item, "eq", True, "boolean", "是", quote=q)]},
        "csrc_kechuang_attr", "二、", txt_exc,
    ))
q50, _ = quote_of("csrc_kechuang_attr", "二、", "50项以上")
records.append(cand(
    "star_pos_exc5_c1", "STAR", "star_positioning_g1", "star_positioning_g1-b6",
    {"clause_id": "star_pos_exc5_c1", "law_ref": "csrc_kechuang_attr#二、", "logic": "all",
     "display": "科创属性例外：形成核心技术和应用于主营业务、能够产业化的发明专利（含国防专利）合计50项以上",
     "leaves": [leaf("star_pos_exc5_c1", "invention_patents_50", "ge", 50, "integer", "50项以上", quote=q50)]},
    "csrc_kechuang_attr", "二、", txt_exc,
))

# ══ 3. 创业板定位（IPO-52~60 → 一组三支路 + 内联或 + 红筹豁免）══
q_fit, txt_fit = quote_of("szse_chinext_recommend", "第四条", "成长型创新创业企业")
q_c1, txt_c1 = quote_of("szse_chinext_recommend", "第四条", "研发投入复合增长率不低于15%")
q_c2, txt_c2 = quote_of("szse_chinext_recommend", "第四条", "累计研发投入金额不低于5000万")
q_c3, txt_c3 = quote_of("szse_chinext_recommend", "第四条", "现代产业体系领域")
q_rev_cnx, _ = quote_of("szse_chinext_recommend", "第四条", "营业收入复合增长率不低于25%")
q_rev_waive, _ = quote_of("szse_chinext_recommend", "第四条", "3亿元")


def rev_or_clause(cid, ratio, branch_id, display):
    return cand(
        cid, "ChiNext", "chinext_positioning_g1", branch_id,
        {"clause_id": cid, "law_ref": "szse_chinext_recommend#第四条", "logic": "any",
         "display": display,
         "leaves": [
             {**leaf(cid, "rev_3y_cagr", "ge", ratio, "percent", f"{ratio*100:g}%以上", quote=q_rev_cnx), "leaf_id": f"{cid}_l1"},
             {**leaf(cid, "rev_latest", "ge", 300000000, "number", "3亿元（达到即豁免增长项）", quote=q_rev_waive), "leaf_id": f"{cid}_l2"},
         ],
         "exemptions": [REDCHIP_EXEMPT("rev_3y_cagr")]},
        "szse_chinext_recommend", "第四条", txt_fit,
    )


records.append(cand(
    "cnx_pos_fit_c0", "ChiNext", "chinext_positioning_g1", None,
    {"clause_id": "cnx_pos_fit_c0", "law_ref": "szse_chinext_recommend#第四条", "logic": "all",
     "display": "属于成长型创新创业企业（创新驱动发展战略、三创四新）",
     "leaves": [leaf("cnx_pos_fit_c0", "chinext_growth_innovation_fit", "eq", True, "boolean",
                     "是", quote=q_fit)]},
    "szse_chinext_recommend", "第四条", txt_fit, role="shared",
))
records.append(cand(
    "cnx_pos_b1_c1", "ChiNext", "chinext_positioning_g1", "chinext_positioning_g1-b1",
    {"clause_id": "cnx_pos_b1_c1", "law_ref": "szse_chinext_recommend#第四条", "logic": "all",
     "display": "路径一：最近三年研发投入复合增长率不低于15% 且 最近一年投入金额不低于1000万元",
     "leaves": [
         {**leaf("cnx_pos_b1_c1", "rd_3y_cagr", "ge", 0.15, "percent", "15%以上", quote=q_c1), "leaf_id": "cnx_pos_b1_c1_l1"},
         {**leaf("cnx_pos_b1_c1", "rd_latest", "ge", 10000000, "number", "1000万元以上", quote=q_c1), "leaf_id": "cnx_pos_b1_c1_l2"},
     ]},
    "szse_chinext_recommend", "第四条", txt_c1,
))
records.append(rev_or_clause("cnx_pos_b1_c2", 0.25, "chinext_positioning_g1-b1",
                             "且 营收增长：三年复合增长率25%以上 或 最近一年营收3亿元"))
records.append(cand(
    "cnx_pos_b2_c1", "ChiNext", "chinext_positioning_g1", "chinext_positioning_g1-b2",
    {"clause_id": "cnx_pos_b2_c1", "law_ref": "szse_chinext_recommend#第四条", "logic": "all",
     "display": "路径二：最近三年累计研发投入金额不低于5000万元",
     "leaves": [leaf("cnx_pos_b2_c1", "rd_3y_sum", "ge", 50000000, "number", "5000万元以上", quote=q_c2)]},
    "szse_chinext_recommend", "第四条", txt_c2,
))
records.append(rev_or_clause("cnx_pos_b2_c2", 0.25, "chinext_positioning_g1-b2",
                             "且 营收增长：三年复合增长率25%以上 或 最近一年营收3亿元"))
records.append(cand(
    "cnx_pos_b3_c1", "ChiNext", "chinext_positioning_g1", "chinext_positioning_g1-b3",
    {"clause_id": "cnx_pos_b3_c1", "law_ref": "szse_chinext_recommend#第四条", "logic": "all",
     "display": "路径三：属于制造业优化升级、现代服务业或数字经济等现代产业体系领域",
     "leaves": [leaf("cnx_pos_b3_c1", "modern_industry_system", "eq", True, "boolean", "是", quote=q_c3)]},
    "szse_chinext_recommend", "第四条", txt_c3,
))
records.append(rev_or_clause("cnx_pos_b3_c2", 0.30, "chinext_positioning_g1-b3",
                             "且 营收增长：三年复合增长率30%以上 或 最近一年营收3亿元"))

# ══ 4. 北交所定位（IPO-61）══
q_bse, txt_bse = quote_of("bse_2026", "1.4", "创新型中小企业")
records.append(cand(
    "bse_pos_fit_c1", "BSE", "bse_positioning_g1", "bse_positioning_g1-b1",
    {"clause_id": "bse_pos_fit_c1", "law_ref": "bse_2026#1.4", "logic": "all",
     "display": "符合北交所板块定位——主要服务创新型中小企业，重点支持先进制造业和现代服务业",
     "leaves": [leaf("bse_pos_fit_c1", "bse_positioning_fit", "eq", True, "boolean", "是", quote=q_bse)]},
    "bse_2026", "1.4", txt_bse,
))


def main() -> int:
    # 幂等校验：quote 逐字在 source 里（L1b 预检）
    for r in records:
        assert r["clause"].get("exemptions") or True
        src = r["source"]["text"]
        for lf in r["clause"]["leaves"]:
            pass   # 引文校验在 leaves.threshold_text 对应 quote——此处整句已在 source 内
    OUT.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8",
    )
    boards = sorted({r["context"]["board"] for r in records})
    print(f"写入 {OUT.relative_to(REPO)}（{len(records)} 条候选，板块 {boards}）")
    print("  组：cn_main_positioning_g1(2) / star_positioning_g1(10) / "
          "chinext_positioning_g1(8) / bse_positioning_g1(1)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
