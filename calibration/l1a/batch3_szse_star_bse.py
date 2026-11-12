# -*- coding: utf-8 -*-
"""
L1a 提取规格 · 批次 3（agent 会话当模型执行者，P7）

范围（golden_sets.yaml 尚未 covered 的全部**有法条锚点**组合）：
- szse_main 3.1.4/3.1.5/3.1.6  深主板红筹/表决权（与沪主板逐字同文，quote 摘深文）
- szse_chinext 2.1.3/2.1.4     创业板红筹未上市（100亿/50亿）+ 表决权差异
- sse_star    2.1.3/2.1.4     科创板红筹未上市（100亿/50亿）+ 表决权差异
- bse_2026    2.1.2(三)/2.1.3  北交所四套（净资产为全套装 shared；套1 双支路）

已知缺口（无法条锚点或语义未支持，golden 保持 covered: false）：
- ChiNext/STAR redchip_listed（2000亿/200亿+技术）：midas 有行、五板块上市规则原文
  无条款（可能在证监会试点意见等未入库文件）——提取无 quote 依据
- 红筹未上市特殊豁免档（研发阶段/国家战略红筹，redchip_special）：豁免语义 v1 不支持
- 红筹增长第三认定（行业下行期对比）：无 item
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from batch1_sse_mb_star import Builder, leaf, load_doc  # noqa: E402

OUT = Path(__file__).resolve().parent / "output" / "candidates_batch3.jsonl"


def build() -> list:
    b = Builder()

    # ══════════ 深主板镜像：3.1.4 / 3.1.5 / 3.1.6（同文，quote 摘深文）══════════
    szse = load_doc("szse_main_2026")
    a314, a315, a316 = "3.1.4", "3.1.5", "3.1.6"

    # 红筹已上市 2 套
    b.add(clause_id="rc_listed_g1_b1_c1", group_id="cn_main_redchip_listed_g1",
          branch_id="cn_main_redchip_listed_g1-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_listed", group_no=1,
          law_id="szse_main_2026", article=a314, doc=szse, logic="all",
          display="市值不低于2000亿元",
          leaves=[leaf("rc_listed_g1_b1_c1_l1", "mktcap_actual", "ge", 2e11, "number", "2000 亿元",
                       "市值不低于2000 亿元")])
    b.add(clause_id="rc_listed_g2_b1_c1", group_id="cn_main_redchip_listed_g2",
          branch_id="cn_main_redchip_listed_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_listed", group_no=2,
          law_id="szse_main_2026", article=a314, doc=szse, logic="all",
          display="市值200亿元以上",
          leaves=[leaf("rc_listed_g2_b1_c1_l1", "mktcap_actual", "ge", 2e10, "number", "200 亿元",
                       "市值200 亿元以上")])
    b.add(clause_id="rc_listed_g2_b1_c2", group_id="cn_main_redchip_listed_g2",
          branch_id="cn_main_redchip_listed_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_listed", group_no=2,
          law_id="szse_main_2026", article=a314, doc=szse, logic="all",
          display="自主研发、国际领先技术，科技创新能力较强，同行业相对优势",
          leaves=[leaf("rc_listed_g2_b1_c2_l1", "self_developed_tech_full", "eq", True, "boolean", "是",
                       "拥有自主研发、国际领先技术，科技创新能力较强，在同行业竞争中处于相对优势地位")])

    # 红筹未上市 3 套（结构同沪主板：套2 提升 shared，增长两支路）
    b.add(clause_id="rc_unlisted_g1_b1_c1", group_id="cn_main_redchip_unlisted_g1",
          branch_id="cn_main_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=1,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="预计市值不低于200亿元",
          leaves=[leaf("rc_unlisted_g1_b1_c1_l1", "mktcap_forecast", "ge", 2e10, "number", "200 亿元",
                       "预计市值不低于200 亿元")])
    b.add(clause_id="rc_unlisted_g1_b1_c2", group_id="cn_main_redchip_unlisted_g1",
          branch_id="cn_main_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=1,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="最近一年营业收入不低于30亿元",
          leaves=[leaf("rc_unlisted_g1_b1_c2_l1", "rev_latest", "ge", 3e9, "number", "30 亿元",
                       "最近一年营业收入不低于30 亿元")])

    for gid, gno in [("cn_main_redchip_unlisted_g2", 2)]:
        b.add(clause_id="rc_unlisted_g2_c1", group_id=gid, branch_id=None, role="shared",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="预计市值不低于100亿元（两支路公共）",
              leaves=[leaf("rc_unlisted_g2_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                           "预计市值不低于100 亿元")])
        b.add(clause_id="rc_unlisted_g2_c2", group_id=gid, branch_id=None, role="shared",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="自主研发、国际领先技术，同行业相对优势（两支路公共）",
              leaves=[leaf("rc_unlisted_g2_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                           "拥有自主研发、国际领先技术，在同行业竞争中处于相对优势地位，且预计市值不低于100 亿元")])
        b.add(clause_id="rc_unlisted_g2_b1_c1", group_id=gid,
              branch_id=f"{gid}-b1", role="branch",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="营收快速增长·路径A：最近一年营收≥5亿",
              leaves=[leaf("rc_unlisted_g2_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                           "最近一年营业收入不低于5 亿元的")])
        b.add(clause_id="rc_unlisted_g2_b1_c2", group_id=gid,
              branch_id=f"{gid}-b1", role="branch",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="营收快速增长·路径A：3年复合增长率10%以上",
              leaves=[leaf("rc_unlisted_g2_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                           "最近三年营业收入复合增长率10%以上")])
        b.add(clause_id="rc_unlisted_g2_b2_c1", group_id=gid,
              branch_id=f"{gid}-b2", role="branch",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="营收快速增长·路径B：最近一年营收低于5亿",
              leaves=[leaf("rc_unlisted_g2_b2_c1_l1", "rev_latest", "lt", 5e8, "number", "5 亿元",
                           "最近一年营业收入低于5 亿元的")])
        b.add(clause_id="rc_unlisted_g2_b2_c2", group_id=gid,
              branch_id=f"{gid}-b2", role="branch",
              scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_main_2026", article=a315, doc=szse, logic="all",
              display="营收快速增长·路径B：3年复合增长率20%以上",
              leaves=[leaf("rc_unlisted_g2_b2_c2_l1", "rev_3y_cagr", "ge", 0.20, "percent", "20%",
                           "最近三年营业收入复合增长率20%以上")])

    b.add(clause_id="rc_unlisted_g3_b1_c1", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("rc_unlisted_g3_b1_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "且预计市值不低于50 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c2", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="自主研发、国际领先技术，同行业相对优势",
          leaves=[leaf("rc_unlisted_g3_b1_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                       "拥有自主研发、国际领先技术，在同行业竞争中处于相对优势地位，且预计市值不低于50 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c3", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("rc_unlisted_g3_b1_c3_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c4", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="szse_main_2026", article=a315, doc=szse, logic="all",
          display="营收快速增长·路径A：3年复合增长率10%以上",
          leaves=[leaf("rc_unlisted_g3_b1_c4_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近三年营业收入复合增长率10%以上")])

    # 表决权差异 1 套（np_latest 提升 shared）
    b.add(clause_id="wv_g1_c1", group_id="cn_main_weighted_voting_g1", branch_id=None, role="shared",
          scope="set", board="SZSE-MB", ctype="weighted_voting", group_no=1,
          law_id="szse_main_2026", article=a316, doc=szse, logic="all",
          display="最近一年净利润为正（两支路公共）",
          leaves=[leaf("wv_g1_c1_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="wv_g1_b1_c1", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="weighted_voting", group_no=1,
          law_id="szse_main_2026", article=a316, doc=szse, logic="all",
          display="预计市值不低于200亿元",
          leaves=[leaf("wv_g1_b1_c1_l1", "mktcap_forecast", "ge", 2e10, "number", "200 亿元",
                       "预计市值不低于200 亿元")])
    b.add(clause_id="wv_g1_b2_c1", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b2", role="branch",
          scope="set", board="SZSE-MB", ctype="weighted_voting", group_no=1,
          law_id="szse_main_2026", article=a316, doc=szse, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("wv_g1_b2_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="wv_g1_b2_c2", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b2", role="branch",
          scope="set", board="SZSE-MB", ctype="weighted_voting", group_no=1,
          law_id="szse_main_2026", article=a316, doc=szse, logic="all",
          display="最近一年营业收入不低于10亿元",
          leaves=[leaf("wv_g1_b2_c2_l1", "rev_latest", "ge", 1e9, "number", "10 亿元",
                       "最近一年营业收入不低于10 亿元")])

    # ══════════ 创业板红筹未上市（2.1.3：套1 100亿 / 套2 50亿；套3 特殊豁免缺口）══════════
    cnx = load_doc("szse_chinext_2026")
    rc = "2.1.3"
    # 创业板定性措辞：无「科技创新能力较强」→ self_developed_tech（短版）
    cnx_tech_quote = "拥有自主研发、国际领先技术，同行业竞争中处于相对优势地位"

    for gid, gno, mc_thr, mc_text, mc_quote in [
        ("chinext_redchip_unlisted_g1", 1, 1e10, "100 亿元", "预计市值不低于100 亿元"),
        ("chinext_redchip_unlisted_g2", 2, 5e9, "50 亿元", "预计市值不低于50 亿元"),
    ]:
        b.add(clause_id=f"cnx_rc_g{gno}_c1", group_id=gid, branch_id=None, role="shared",
              scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
              display=f"预计市值不低于{mc_text}（适用主体定性：快速增长+技术优势）",
              leaves=[leaf(f"cnx_rc_g{gno}_c1_l1", "mktcap_forecast", "ge", mc_thr, "number", mc_text, mc_quote)])
        b.add(clause_id=f"cnx_rc_g{gno}_c2", group_id=gid, branch_id=None, role="shared",
              scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=gno,
              law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
              display="自主研发、国际领先技术，同行业相对优势",
              leaves=[leaf(f"cnx_rc_g{gno}_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                           cnx_tech_quote)])

    # 套1（100亿）增长两支路；套2（50亿）自带营收≥5亿 → 仅路径A
    b.add(clause_id="cnx_rc_g1_b1_c1", group_id="chinext_redchip_unlisted_g1",
          branch_id="chinext_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=1,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="营收快速增长·路径A：最近一年营收≥5亿",
          leaves=[leaf("cnx_rc_g1_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元的")])
    b.add(clause_id="cnx_rc_g1_b1_c2", group_id="chinext_redchip_unlisted_g1",
          branch_id="chinext_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=1,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="营收快速增长·路径A：三年复合增长率10%以上",
          leaves=[leaf("cnx_rc_g1_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近三年营业收入复合增长率10%以上")])
    b.add(clause_id="cnx_rc_g1_b2_c1", group_id="chinext_redchip_unlisted_g1",
          branch_id="chinext_redchip_unlisted_g1-b2", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=1,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="营收快速增长·路径B：最近一年营收低于5亿",
          leaves=[leaf("cnx_rc_g1_b2_c1_l1", "rev_latest", "lt", 5e8, "number", "5 亿元",
                       "最近一年营业收入低于5 亿元的")])
    b.add(clause_id="cnx_rc_g1_b2_c2", group_id="chinext_redchip_unlisted_g1",
          branch_id="chinext_redchip_unlisted_g1-b2", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=1,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="营收快速增长·路径B：三年复合增长率20%以上",
          leaves=[leaf("cnx_rc_g1_b2_c2_l1", "rev_3y_cagr", "ge", 0.20, "percent", "20%",
                       "最近三年营业收入复合增长率20%以上")])

    b.add(clause_id="cnx_rc_g2_b1_c1", group_id="chinext_redchip_unlisted_g2",
          branch_id="chinext_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=2,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("cnx_rc_g2_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元")])
    b.add(clause_id="cnx_rc_g2_b1_c2", group_id="chinext_redchip_unlisted_g2",
          branch_id="chinext_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="ChiNext", ctype="redchip_unlisted", group_no=2,
          law_id="szse_chinext_2026", article=rc, doc=cnx, logic="all",
          display="营收快速增长·路径A：三年复合增长率10%以上",
          leaves=[leaf("cnx_rc_g2_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近三年营业收入复合增长率10%以上")])

    # ══════════ 创业板表决权差异（2.1.4：1 套 2 支路，无公共条文）══════════
    wv = "2.1.4"
    b.add(clause_id="cnx_wv_g1_b1_c1", group_id="chinext_weighted_voting_g1",
          branch_id="chinext_weighted_voting_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="weighted_voting", group_no=1,
          law_id="szse_chinext_2026", article=wv, doc=cnx, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("cnx_wv_g1_b1_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="cnx_wv_g1_b2_c1", group_id="chinext_weighted_voting_g1",
          branch_id="chinext_weighted_voting_g1-b2", role="branch",
          scope="set", board="ChiNext", ctype="weighted_voting", group_no=1,
          law_id="szse_chinext_2026", article=wv, doc=cnx, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("cnx_wv_g1_b2_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "预计市值不低于50 亿元")])
    b.add(clause_id="cnx_wv_g1_b2_c2", group_id="chinext_weighted_voting_g1",
          branch_id="chinext_weighted_voting_g1-b2", role="branch",
          scope="set", board="ChiNext", ctype="weighted_voting", group_no=1,
          law_id="szse_chinext_2026", article=wv, doc=cnx, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("cnx_wv_g1_b2_c2_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元")])

    # ══════════ 科创板红筹未上市（2.1.3：同创业板结构，措辞带「人民币」「3 年」）══════════
    star = load_doc("sse_star_2026")
    src_rc = "2.1.3"
    star_tech_quote = "拥有自主研发、国际领先技术，同行业竞争中处于相对优势地位"

    for gid, gno, mc_thr, mc_text, mc_quote in [
        ("star_redchip_unlisted_g1", 1, 1e10, "100 亿元", "预计市值不低于人民币100 亿元"),
        ("star_redchip_unlisted_g2", 2, 5e9, "50 亿元", "预计市值不低于人民币50 亿元"),
    ]:
        b.add(clause_id=f"star_rc_g{gno}_c1", group_id=gid, branch_id=None, role="shared",
              scope="set", board="STAR", ctype="redchip_unlisted", group_no=gno,
              law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
              display=f"预计市值不低于{mc_text}",
              leaves=[leaf(f"star_rc_g{gno}_c1_l1", "mktcap_forecast", "ge", mc_thr, "number", mc_text, mc_quote)])
        b.add(clause_id=f"star_rc_g{gno}_c2", group_id=gid, branch_id=None, role="shared",
              scope="set", board="STAR", ctype="redchip_unlisted", group_no=gno,
              law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
              display="自主研发、国际领先技术，同行业相对优势",
              leaves=[leaf(f"star_rc_g{gno}_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                           star_tech_quote)])

    b.add(clause_id="star_rc_g1_b1_c1", group_id="star_redchip_unlisted_g1",
          branch_id="star_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=1,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="营收快速增长·路径A：最近一年营收≥5亿",
          leaves=[leaf("star_rc_g1_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于人民币5 亿元的")])
    b.add(clause_id="star_rc_g1_b1_c2", group_id="star_redchip_unlisted_g1",
          branch_id="star_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=1,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="营收快速增长·路径A：3年复合增长率10%以上",
          leaves=[leaf("star_rc_g1_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近3 年营业收入复合增长率10%以上")])
    b.add(clause_id="star_rc_g1_b2_c1", group_id="star_redchip_unlisted_g1",
          branch_id="star_redchip_unlisted_g1-b2", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=1,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="营收快速增长·路径B：最近一年营收低于5亿",
          leaves=[leaf("star_rc_g1_b2_c1_l1", "rev_latest", "lt", 5e8, "number", "5 亿元",
                       "最近一年营业收入低于人民币5 亿元的")])
    b.add(clause_id="star_rc_g1_b2_c2", group_id="star_redchip_unlisted_g1",
          branch_id="star_redchip_unlisted_g1-b2", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=1,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="营收快速增长·路径B：3年复合增长率20%以上",
          leaves=[leaf("star_rc_g1_b2_c2_l1", "rev_3y_cagr", "ge", 0.20, "percent", "20%",
                       "最近3年营业收入复合增长率20%以上")])

    b.add(clause_id="star_rc_g2_b1_c1", group_id="star_redchip_unlisted_g2",
          branch_id="star_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=2,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("star_rc_g2_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于人民币5 亿元")])
    b.add(clause_id="star_rc_g2_b1_c2", group_id="star_redchip_unlisted_g2",
          branch_id="star_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="STAR", ctype="redchip_unlisted", group_no=2,
          law_id="sse_star_2026", article=src_rc, doc=star, logic="all",
          display="营收快速增长·路径A：3年复合增长率10%以上",
          leaves=[leaf("star_rc_g2_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近3 年营业收入复合增长率10%以上")])

    # ══════════ 科创板表决权差异（2.1.4：1 套 2 支路）══════════
    src_wv = "2.1.4"
    b.add(clause_id="star_wv_g1_b1_c1", group_id="star_weighted_voting_g1",
          branch_id="star_weighted_voting_g1-b1", role="branch",
          scope="set", board="STAR", ctype="weighted_voting", group_no=1,
          law_id="sse_star_2026", article=src_wv, doc=star, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("star_wv_g1_b1_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于人民币100 亿元")])
    b.add(clause_id="star_wv_g1_b2_c1", group_id="star_weighted_voting_g1",
          branch_id="star_weighted_voting_g1-b2", role="branch",
          scope="set", board="STAR", ctype="weighted_voting", group_no=1,
          law_id="sse_star_2026", article=src_wv, doc=star, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("star_wv_g1_b2_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "预计市值不低于人民币50 亿元")])
    b.add(clause_id="star_wv_g1_b2_c2", group_id="star_weighted_voting_g1",
          branch_id="star_weighted_voting_g1-b2", role="branch",
          scope="set", board="STAR", ctype="weighted_voting", group_no=1,
          law_id="sse_star_2026", article=src_wv, doc=star, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("star_wv_g1_b2_c2_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于人民币5 亿元")])

    # ══════════ 北交所（2.1.2(三) 净资产为全套装 shared + 2.1.3 四套）══════════
    bse = load_doc("bse_2026")
    eq_art, fin_art = "2.1.2", "2.1.3"
    EQ_QUOTE = "最近一年期末净资产不低于5000 万元"

    def bse_shared(gid, gno):
        b.add(clause_id=f"bse_g{gno}_c0", group_id=gid, branch_id=None, role="shared",
              scope="set", board="BSE", ctype="general", group_no=gno,
              law_id="bse_2026", article=eq_art, doc=bse, logic="all",
              display="最近一年期末净资产不低于5000万元（全套装一般条件）",
              leaves=[leaf(f"bse_g{gno}_c0_l1", "equity_latest", "ge", 5e7, "number", "5000 万元",
                           EQ_QUOTE)])

    # 套1：市值2亿 提升 shared；两支路（两年净利各≥1500万+ROE均值 / 一年净利2500万+ROE）
    bse_shared("bse_general_g1", 1)
    b.add(clause_id="bse_g1_c1", group_id="bse_general_g1", branch_id=None, role="shared",
          scope="set", board="BSE", ctype="general", group_no=1,
          law_id="bse_2026", article=fin_art, doc=bse, logic="all",
          display="预计市值不低于2亿元（两支路公共）",
          leaves=[leaf("bse_g1_c1_l1", "mktcap_forecast", "ge", 2e8, "number", "2 亿元",
                       "预计市值不低于2 亿元")])
    b.add(clause_id="bse_g1_b1_c1", group_id="bse_general_g1",
          branch_id="bse_general_g1-b1", role="branch",
          scope="set", board="BSE", ctype="general", group_no=1,
          law_id="bse_2026", article=fin_art, doc=bse, logic="all",
          display="最近两年各年净利润不低于1500万元",
          leaves=[leaf("bse_g1_b1_c1_l1", "np_2y_each", "ge", 1.5e7, "number", "1500 万元",
                       "最近两年净利润均不低于1500 万元")])
    b.add(clause_id="bse_g1_b1_c2", group_id="bse_general_g1",
          branch_id="bse_general_g1-b1", role="branch",
          scope="set", board="BSE", ctype="general", group_no=1,
          law_id="bse_2026", article=fin_art, doc=bse, logic="all",
          display="两年加权平均净资产收益率平均不低于8%",
          leaves=[leaf("bse_g1_b1_c2_l1", "roe_weighted_2y_avg", "ge", 0.08, "percent", "8%",
                       "加权平均净资产收益率平均不低于8%")])
    b.add(clause_id="bse_g1_b2_c1", group_id="bse_general_g1",
          branch_id="bse_general_g1-b2", role="branch",
          scope="set", board="BSE", ctype="general", group_no=1,
          law_id="bse_2026", article=fin_art, doc=bse, logic="all",
          display="最近一年净利润不低于2500万元",
          leaves=[leaf("bse_g1_b2_c1_l1", "np_latest", "ge", 2.5e7, "number", "2500 万元",
                       "最近一年净利润不低于2500 万元")])
    b.add(clause_id="bse_g1_b2_c2", group_id="bse_general_g1",
          branch_id="bse_general_g1-b2", role="branch",
          scope="set", board="BSE", ctype="general", group_no=1,
          law_id="bse_2026", article=fin_art, doc=bse, logic="all",
          display="最近一年加权平均净资产收益率不低于8%",
          leaves=[leaf("bse_g1_b2_c2_l1", "roe_weighted_latest", "ge", 0.08, "percent", "8%",
                       "加权平均净资产收益率不低于8%")])

    # 套2：市值4亿 + 营收均值1亿 + 增速30% + 现金流为正
    bse_shared("bse_general_g2", 2)
    for cid_suffix, item, op, thr, fmt, text, quote, disp in [
        ("c1", "mktcap_forecast", "ge", 4e8, "number", "4 亿元", "预计市值不低于4 亿元", "预计市值不低于4亿元"),
        ("c2", "rev_2y_avg", "ge", 1e8, "number", "1 亿元", "最近两年营业收入平均不低于1 亿元", "最近两年营业收入平均不低于1亿元"),
        ("c3", "rev_1y_growth", "ge", 0.30, "percent", "30%", "最近一年营业收入增长率不低于30%", "最近一年营业收入增长率不低于30%"),
        ("c4", "ocf_latest", "gt", 0, "number", "为正", "最近一年经营活动产生的现金流量净额为正", "最近一年经营现金流净额为正"),
    ]:
        b.add(clause_id=f"bse_g2_b1_{cid_suffix}", group_id="bse_general_g2",
              branch_id="bse_general_g2-b1", role="branch",
              scope="set", board="BSE", ctype="general", group_no=2,
              law_id="bse_2026", article=fin_art, doc=bse, logic="all",
              display=disp,
              leaves=[leaf(f"bse_g2_b1_{cid_suffix}_l1", item, op, thr, fmt, text, quote)])

    # 套3：市值8亿 + 营收2亿 + 研发强度8%（2年口径）
    bse_shared("bse_general_g3", 3)
    for cid_suffix, item, thr, fmt, text, quote, disp in [
        ("c1", "mktcap_forecast", 8e8, "number", "8 亿元", "预计市值不低于8 亿元", "预计市值不低于8亿元"),
        ("c2", "rev_latest", 2e8, "number", "2 亿元", "最近一年营业收入不低于2亿元", "最近一年营业收入不低于2亿元"),
        ("c3", "rd_intensity_2y", 0.08, "percent", "8%", "最近两年研发投入合计占最近两年营业收入合计比例不低于8%", "两年研发投入占营收比例不低于8%"),
    ]:
        b.add(clause_id=f"bse_g3_b1_{cid_suffix}", group_id="bse_general_g3",
              branch_id="bse_general_g3-b1", role="branch",
              scope="set", board="BSE", ctype="general", group_no=3,
              law_id="bse_2026", article=fin_art, doc=bse, logic="all",
              display=disp,
              leaves=[leaf(f"bse_g3_b1_{cid_suffix}_l1", item, "ge", thr, fmt, text, quote)])

    # 套4：市值15亿 + 两年研发累计5000万
    bse_shared("bse_general_g4", 4)
    for cid_suffix, item, thr, text, quote, disp in [
        ("c1", "mktcap_forecast", 1.5e9, "15 亿元", "预计市值不低于15 亿元", "预计市值不低于15亿元"),
        ("c2", "rd_2y_sum", 5e7, "5000 万元", "最近两年研发投入合计不低于5000 万元", "最近两年研发投入合计不低于5000万元"),
    ]:
        b.add(clause_id=f"bse_g4_b1_{cid_suffix}", group_id="bse_general_g4",
              branch_id="bse_general_g4-b1", role="branch",
              scope="set", board="BSE", ctype="general", group_no=4,
              law_id="bse_2026", article=fin_art, doc=bse, logic="all",
              display=disp,
              leaves=[leaf(f"bse_g4_b1_{cid_suffix}_l1", item, "ge", thr, "number", text, quote)])

    return b.rules


def main() -> int:
    rules = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r in rules:
            f.write(r.model_dump_json() + "\n")
    print(f"写出 {len(rules)} 条候选 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
