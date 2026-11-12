"""
L1a 提取规格 · 批次 2（agent 会话当模型执行者，P7）

范围：
- szse_main_2026#3.1.2   深主板三标准（与沪主板同文镜像：数值集合 22/22 一致，
                          措辞微差 7 处——发行人/企业、3年/三年、或/或者；
                          clause_id 沿用批次 1，board=SZSE-MB，quote 摘深文）
- szse_chinext_2026#2.1.2 创业板四标准（g4 标准四双支路：30亿+CAGR30% 或 40亿+研发双条件）
- sse_main_2026#3.1.4    沪主板红筹已上市（2000亿 或 200亿+技术优势；零公共条文双支路，
                          触发不变量 #6 修订版）
- sse_main_2026#3.1.5    沪主板红筹未上市（三标准 × 营收快速增长子标准 → 展平为 4 支路）
- sse_main_2026#3.1.6    沪主板表决权差异（np_latest>0 提升 shared）

已知缺口（无 item，不建叶，人工核对）：
- 3.1.5 增长子标准第三路径「行业下行期 cagr > 同行业可比公司平均」：需行业对比增长 item
- 3.1.5 尾部豁免「研发阶段红筹 / 国家战略红筹不适用快速增长」（redchip_special）：
  豁免语义 v1 schema 不支持
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
from batch1_sse_mb_star import Builder, leaf, load_doc  # noqa: E402

OUT = Path(__file__).resolve().parent / "output" / "candidates_batch2.jsonl"


def build() -> list:
    b = Builder()

    # ══════════ 深主板 3.1.2 镜像（同文验证通过，quote 摘深文）══════════
    szse = load_doc("szse_main_2026")
    art = "3.1.2"

    b.add(clause_id="cn_main_g1_c1", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SZSE-MB", ctype="general", group_no=1,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近三年净利润均为正",
          leaves=[leaf("cn_main_g1_c1_l1", "np_3y_allpos", "gt", 0, "number", "为正",
                       "最近三年净利润均为正")])
    b.add(clause_id="cn_main_g1_c2", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SZSE-MB", ctype="general", group_no=1,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近三年净利润累计不低于2亿元",
          leaves=[leaf("cn_main_g1_c2_l1", "np_3y_sum", "ge", 2e8, "number", "2 亿元",
                       "最近三年净利润累计不低于2 亿元")])
    b.add(clause_id="cn_main_g1_c3", group_id="cn_main_general_g1", branch_id=None, role="shared",
          scope="set", board="SZSE-MB", ctype="general", group_no=1,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近一年净利润不低于1亿元",
          leaves=[leaf("cn_main_g1_c3_l1", "np_latest", "ge", 1e8, "number", "1 亿元",
                       "最近一年净利润不低于1 亿元")])
    b.add(clause_id="cn_main_g1_b1_c1", group_id="cn_main_general_g1",
          branch_id="cn_main_general_g1-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=1,
          law_id="szse_main_2026", article=art, doc=szse, logic="any",
          display="经营现金流累计2亿元 或 营业收入累计15亿元",
          leaves=[
              leaf("cn_main_g1_b1_c1_l1", "ocf_3y_sum", "ge", 2e8, "number", "2 亿元",
                   "最近三年经营活动产生的现金流量净额累计不低于2 亿元或者营业收入累计不低于15 亿元"),
              leaf("cn_main_g1_b1_c1_l2", "rev_3y_sum", "ge", 1.5e9, "number", "15 亿元",
                   "最近三年经营活动产生的现金流量净额累计不低于2 亿元或者营业收入累计不低于15 亿元"),
          ])

    b.add(clause_id="cn_main_g2_b1_c1", group_id="cn_main_general_g2",
          branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=2,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("cn_main_g2_b1_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "预计市值不低于50 亿元")])
    b.add(clause_id="cn_main_g2_b1_c2", group_id="cn_main_general_g2",
          branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=2,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("cn_main_g2_b1_c2_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="cn_main_g2_b1_c3", group_id="cn_main_general_g2",
          branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=2,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近一年营业收入不低于6亿元",
          leaves=[leaf("cn_main_g2_b1_c3_l1", "rev_latest", "ge", 6e8, "number", "6 亿元",
                       "最近一年营业收入不低于6 亿元")])
    b.add(clause_id="cn_main_g2_b1_c4", group_id="cn_main_general_g2",
          branch_id="cn_main_general_g2-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=2,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近三年经营现金流净额累计不低于2.5亿元",
          leaves=[leaf("cn_main_g2_b1_c4_l1", "ocf_3y_sum", "ge", 2.5e8, "number", "2.5 亿元",
                       "最近三年经营活动产生的现金流量净额累计不低于2.5 亿元")])

    b.add(clause_id="cn_main_g3_b1_c1", group_id="cn_main_general_g3",
          branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=3,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("cn_main_g3_b1_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="cn_main_g3_b1_c2", group_id="cn_main_general_g3",
          branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=3,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("cn_main_g3_b1_c2_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="cn_main_g3_b1_c3", group_id="cn_main_general_g3",
          branch_id="cn_main_general_g3-b1", role="branch",
          scope="set", board="SZSE-MB", ctype="general", group_no=3,
          law_id="szse_main_2026", article=art, doc=szse, logic="all",
          display="最近一年营业收入不低于10亿元",
          leaves=[leaf("cn_main_g3_b1_c3_l1", "rev_latest", "ge", 1e9, "number", "10 亿元",
                       "最近一年营业收入不低于10 亿元")])

    # ══════════ 创业板 2.1.2 四标准 ══════════
    cnx = load_doc("szse_chinext_2026")
    art2 = "2.1.2"

    # 标准一：两年净利均为正 + 累计≥1亿 + 最近一年≥6000万
    b.add(clause_id="chinext_g1_b1_c1", group_id="chinext_general_g1",
          branch_id="chinext_general_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=1,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近两年净利润均为正",
          leaves=[leaf("chinext_g1_b1_c1_l1", "np_2y_allpos", "gt", 0, "number", "为正",
                       "最近两年净利润均为正")])
    b.add(clause_id="chinext_g1_b1_c2", group_id="chinext_general_g1",
          branch_id="chinext_general_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=1,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近两年净利润累计不低于1亿元",
          leaves=[leaf("chinext_g1_b1_c2_l1", "np_2y_sum", "ge", 1e8, "number", "1 亿元",
                       "累计净利润不低于1 亿元")])
    b.add(clause_id="chinext_g1_b1_c3", group_id="chinext_general_g1",
          branch_id="chinext_general_g1-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=1,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近一年净利润不低于6000万元",
          leaves=[leaf("chinext_g1_b1_c3_l1", "np_latest", "ge", 6e7, "number", "6000 万元",
                       "最近一年净利润不低于6000 万元")])

    # 标准二：市值15亿 + 净利正 + 营收4亿
    b.add(clause_id="chinext_g2_b1_c1", group_id="chinext_general_g2",
          branch_id="chinext_general_g2-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=2,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="预计市值不低于15亿元",
          leaves=[leaf("chinext_g2_b1_c1_l1", "mktcap_forecast", "ge", 1.5e9, "number", "15 亿元",
                       "预计市值不低于15 亿元")])
    b.add(clause_id="chinext_g2_b1_c2", group_id="chinext_general_g2",
          branch_id="chinext_general_g2-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=2,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近一年净利润为正",
          leaves=[leaf("chinext_g2_b1_c2_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正且营业收入不低于4 亿元")])
    b.add(clause_id="chinext_g2_b1_c3", group_id="chinext_general_g2",
          branch_id="chinext_general_g2-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=2,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近一年营业收入不低于4亿元",
          leaves=[leaf("chinext_g2_b1_c3_l1", "rev_latest", "ge", 4e8, "number", "4 亿元",
                       "最近一年净利润为正且营业收入不低于4 亿元")])

    # 标准三：市值50亿 + 营收3亿
    b.add(clause_id="chinext_g3_b1_c1", group_id="chinext_general_g3",
          branch_id="chinext_general_g3-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=3,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("chinext_g3_b1_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "预计市值不低于50 亿元")])
    b.add(clause_id="chinext_g3_b1_c2", group_id="chinext_general_g3",
          branch_id="chinext_general_g3-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=3,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近一年营业收入不低于3亿元",
          leaves=[leaf("chinext_g3_b1_c2_l1", "rev_latest", "ge", 3e8, "number", "3 亿元",
                       "最近一年营业收入不低于3 亿元")])

    # 标准四：双支路——(30亿+CAGR30%) 或 (40亿+研发1亿+研发强度15%)；营收2亿为公共 → shared
    b.add(clause_id="chinext_g4_c1", group_id="chinext_general_g4", branch_id=None, role="shared",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近一年营业收入不低于2亿元（两支路公共）",
          leaves=[leaf("chinext_g4_c1_l1", "rev_latest", "ge", 2e8, "number", "2 亿元",
                       "最近一年营业收入不低于2亿元")])
    b.add(clause_id="chinext_g4_b1_c1", group_id="chinext_general_g4",
          branch_id="chinext_general_g4-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="预计市值不低于30亿元",
          leaves=[leaf("chinext_g4_b1_c1_l1", "mktcap_forecast", "ge", 3e9, "number", "30 亿元",
                       "预计市值不低于30 亿元")])
    b.add(clause_id="chinext_g4_b1_c2", group_id="chinext_general_g4",
          branch_id="chinext_general_g4-b1", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近三年营业收入复合增长率不低于30%",
          leaves=[leaf("chinext_g4_b1_c2_l1", "rev_3y_cagr", "ge", 0.30, "percent", "30%",
                       "最近三年营业收入复合增长率不低于30%")])
    b.add(clause_id="chinext_g4_b2_c1", group_id="chinext_general_g4",
          branch_id="chinext_general_g4-b2", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="预计市值不低于40亿元",
          leaves=[leaf("chinext_g4_b2_c1_l1", "mktcap_forecast", "ge", 4e9, "number", "40 亿元",
                       "预计市值不低于40 亿元")])
    b.add(clause_id="chinext_g4_b2_c2", group_id="chinext_general_g4",
          branch_id="chinext_general_g4-b2", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="最近三年累计研发投入不低于1亿元",
          leaves=[leaf("chinext_g4_b2_c2_l1", "rd_3y_sum", "ge", 1e8, "number", "1 亿元",
                       "最近三年累计研发投入不低于1 亿元")])
    b.add(clause_id="chinext_g4_b2_c3", group_id="chinext_general_g4",
          branch_id="chinext_general_g4-b2", role="branch",
          scope="set", board="ChiNext", ctype="general", group_no=4,
          law_id="szse_chinext_2026", article=art2, doc=cnx, logic="all",
          display="研发投入占营收比例不低于15%",
          leaves=[leaf("chinext_g4_b2_c3_l1", "rd_intensity_3y", "ge", 0.15, "percent", "15%",
                       "占最近三年累计营业收入的比例不低于15%")])

    # ══════════ 沪主板 3.1.4 红筹已上市（官方 2 套：2000亿 / 200亿+技术；U6 黄金集对拍锚定）══════════
    sse = load_doc("sse_main_2026")
    art3 = "3.1.4"

    b.add(clause_id="rc_listed_g1_b1_c1", group_id="cn_main_redchip_listed_g1",
          branch_id="cn_main_redchip_listed_g1-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_listed", group_no=1,
          law_id="sse_main_2026", article=art3, doc=sse, logic="all",
          display="市值不低于2000亿元",
          leaves=[leaf("rc_listed_g1_b1_c1_l1", "mktcap_actual", "ge", 2e11, "number", "2000 亿元",
                       "市值不低于2000 亿元")])
    b.add(clause_id="rc_listed_g2_b1_c1", group_id="cn_main_redchip_listed_g2",
          branch_id="cn_main_redchip_listed_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_listed", group_no=2,
          law_id="sse_main_2026", article=art3, doc=sse, logic="all",
          display="市值200亿元以上",
          leaves=[leaf("rc_listed_g2_b1_c1_l1", "mktcap_actual", "ge", 2e10, "number", "200 亿元",
                       "市值200 亿元以上")])
    b.add(clause_id="rc_listed_g2_b1_c2", group_id="cn_main_redchip_listed_g2",
          branch_id="cn_main_redchip_listed_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_listed", group_no=2,
          law_id="sse_main_2026", article=art3, doc=sse, logic="all",
          display="自主研发、国际领先技术，科技创新能力较强，同行业相对优势",
          leaves=[leaf("rc_listed_g2_b1_c2_l1", "self_developed_tech_full", "eq", True, "boolean", "是",
                       "拥有自主研发、国际领先技术，科技创新能力较强，在同行业竞争中处于相对优势地位")])

    # ══════════ 沪主板 3.1.5 红筹未上市（官方 3 套：200亿 / 100亿 / 50亿；U6 黄金集对拍锚定）══════════
    # 增长子标准按套内支路展开：路径A（营收≥5亿→CAGR≥10%）/ 路径B（营收<5亿→CAGR≥20%）；
    # 行业下行期对比路径无 item（已知缺口）；研发阶段/国家战略红筹豁免未编码（已知缺口）。
    art4 = "3.1.5"

    # 官方套1：市值200亿 + 营收30亿
    b.add(clause_id="rc_unlisted_g1_b1_c1", group_id="cn_main_redchip_unlisted_g1",
          branch_id="cn_main_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=1,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="预计市值不低于200亿元",
          leaves=[leaf("rc_unlisted_g1_b1_c1_l1", "mktcap_forecast", "ge", 2e10, "number", "200 亿元",
                       "预计市值不低于200 亿元")])
    b.add(clause_id="rc_unlisted_g1_b1_c2", group_id="cn_main_redchip_unlisted_g1",
          branch_id="cn_main_redchip_unlisted_g1-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=1,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="最近一年营业收入不低于30亿元",
          leaves=[leaf("rc_unlisted_g1_b1_c2_l1", "rev_latest", "ge", 3e9, "number", "30 亿元",
                       "最近一年营业收入不低于30 亿元")])

    # 官方套2：市值100亿 + 技术（提升 shared）+ 增长认定（两支路）
    b.add(clause_id="rc_unlisted_g2_c1", group_id="cn_main_redchip_unlisted_g2",
          branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="预计市值不低于100亿元（两支路公共）",
          leaves=[leaf("rc_unlisted_g2_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="rc_unlisted_g2_c2", group_id="cn_main_redchip_unlisted_g2",
          branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="自主研发、国际领先技术，同行业相对优势（两支路公共）",
          leaves=[leaf("rc_unlisted_g2_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                       "拥有自主研发、国际领先技术，在同行业竞争中处于相对优势地位，且预计市值不低于100 亿元")])
    b.add(clause_id="rc_unlisted_g2_b1_c1", group_id="cn_main_redchip_unlisted_g2",
          branch_id="cn_main_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="营收快速增长·路径A：最近一年营收≥5亿",
          leaves=[leaf("rc_unlisted_g2_b1_c1_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元的")])
    b.add(clause_id="rc_unlisted_g2_b1_c2", group_id="cn_main_redchip_unlisted_g2",
          branch_id="cn_main_redchip_unlisted_g2-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="营收快速增长·路径A：3年复合增长率10%以上",
          leaves=[leaf("rc_unlisted_g2_b1_c2_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近3 年营业收入复合增长率10%以上")])
    b.add(clause_id="rc_unlisted_g2_b2_c1", group_id="cn_main_redchip_unlisted_g2",
          branch_id="cn_main_redchip_unlisted_g2-b2", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="营收快速增长·路径B：最近一年营收低于5亿",
          leaves=[leaf("rc_unlisted_g2_b2_c1_l1", "rev_latest", "lt", 5e8, "number", "5 亿元",
                       "最近一年营业收入低于5 亿元的")])
    b.add(clause_id="rc_unlisted_g2_b2_c2", group_id="cn_main_redchip_unlisted_g2",
          branch_id="cn_main_redchip_unlisted_g2-b2", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=2,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="营收快速增长·路径B：3年复合增长率20%以上",
          leaves=[leaf("rc_unlisted_g2_b2_c2_l1", "rev_3y_cagr", "ge", 0.20, "percent", "20%",
                       "最近3 年营业收入复合增长率20%以上")])

    # 官方套3：市值50亿 + 营收5亿 + 增长路径A + 技术（路径B 与营收≥5亿互斥）
    b.add(clause_id="rc_unlisted_g3_b1_c1", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="预计市值不低于50亿元",
          leaves=[leaf("rc_unlisted_g3_b1_c1_l1", "mktcap_forecast", "ge", 5e9, "number", "50 亿元",
                       "且预计市值不低于50 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c2", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="自主研发、国际领先技术，同行业相对优势",
          leaves=[leaf("rc_unlisted_g3_b1_c2_l1", "self_developed_tech", "eq", True, "boolean", "是",
                       "拥有自主研发、国际领先技术，在同行业竞争中处于相对优势地位，且预计市值不低于50 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c3", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="最近一年营业收入不低于5亿元",
          leaves=[leaf("rc_unlisted_g3_b1_c3_l1", "rev_latest", "ge", 5e8, "number", "5 亿元",
                       "最近一年营业收入不低于5 亿元")])
    b.add(clause_id="rc_unlisted_g3_b1_c4", group_id="cn_main_redchip_unlisted_g3",
          branch_id="cn_main_redchip_unlisted_g3-b1", role="branch",
          scope="set", board="SSE-MB", ctype="redchip_unlisted", group_no=3,
          law_id="sse_main_2026", article=art4, doc=sse, logic="all",
          display="营收快速增长·路径A：3年复合增长率10%以上",
          leaves=[leaf("rc_unlisted_g3_b1_c4_l1", "rev_3y_cagr", "ge", 0.10, "percent", "10%",
                       "最近3 年营业收入复合增长率10%以上")])

    # ══════════ 沪主板 3.1.6 表决权差异（np_latest>0 提升 shared）══════════
    art5 = "3.1.6"

    b.add(clause_id="wv_g1_c1", group_id="cn_main_weighted_voting_g1", branch_id=None, role="shared",
          scope="set", board="SSE-MB", ctype="weighted_voting", group_no=1,
          law_id="sse_main_2026", article=art5, doc=sse, logic="all",
          display="最近一年净利润为正（两支路公共）",
          leaves=[leaf("wv_g1_c1_l1", "np_latest", "gt", 0, "number", "为正",
                       "最近一年净利润为正")])
    b.add(clause_id="wv_g1_b1_c1", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b1", role="branch",
          scope="set", board="SSE-MB", ctype="weighted_voting", group_no=1,
          law_id="sse_main_2026", article=art5, doc=sse, logic="all",
          display="预计市值不低于200亿元",
          leaves=[leaf("wv_g1_b1_c1_l1", "mktcap_forecast", "ge", 2e10, "number", "200 亿元",
                       "预计市值不低于200 亿元")])
    b.add(clause_id="wv_g1_b2_c1", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b2", role="branch",
          scope="set", board="SSE-MB", ctype="weighted_voting", group_no=1,
          law_id="sse_main_2026", article=art5, doc=sse, logic="all",
          display="预计市值不低于100亿元",
          leaves=[leaf("wv_g1_b2_c1_l1", "mktcap_forecast", "ge", 1e10, "number", "100 亿元",
                       "预计市值不低于100 亿元")])
    b.add(clause_id="wv_g1_b2_c2", group_id="cn_main_weighted_voting_g1",
          branch_id="cn_main_weighted_voting_g1-b2", role="branch",
          scope="set", board="SSE-MB", ctype="weighted_voting", group_no=1,
          law_id="sse_main_2026", article=art5, doc=sse, logic="all",
          display="最近一年营业收入不低于10亿元",
          leaves=[leaf("wv_g1_b2_c2_l1", "rev_latest", "ge", 1e9, "number", "10 亿元",
                       "最近一年营业收入不低于10 亿元")])

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
