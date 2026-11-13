"""ADS mock 数据再造生成器（2026-11-13）：基于 raw/ads_daily_20261109 快照造 8 个新主体。

用途（用户拍板 P1/P2/P3）：补充演示/测试用 mock 底稿池——新开
raw/ads_synth_20261113/ 落 4 张同 schema CSV，原快照一字不动。

造数方法（克隆形态 + 重构数值）：
- donor（科商科技物流仓储公司）只提供「列形态」模板：列顺序照抄源 header；
  未映射数值列按 donor 多数形态置 '0E-8' 或 ''（源数据本就大量稀疏）。
- 数值不用 donor 值：每个主体带 2022~2026 年度锚点（营收/归母净利等），
  月度 ytd 沿季节权重曲线推进（营收型/净利型两套权重），12 月强制落锚点；
  ptd = ytd 差分 → 比 ytd/ptd 互不勾稽的源数据更干净。
- 信号列自身勾稽：净利 = 税前−所得税（营业成本做塞子回归净利锚点，税率≈25%）；
  所得税 ytd 由税前−净利恒等式导出；funds 净额 = 收−支、现金余额滚动；
  equity 构成和 = 归母权益、pe/pb 跨月衔接、equity_avg 与 profitability 表同值；
  比率列全部由分子/分母重算。
- 元数据确定性：id = uuid5、all_dimension_md5 = md5(租户|主体|表|期间)、
  create_time 固定批次 '2026-11-13 10:00:00'——同 seed 重跑逐字节一致。

覆盖形态（对齐真实分布，P3）：
- 形态A（6 主体）= 源科商集团形态：2021-12 + 2022-01~2026-03 + 2026-10
  （2026-04~09 缺；equity 表从 2022-01 起、无 2021-12，同源）。
- 形态B（2 主体）= 源电商/科创形态：只到 2026-03；S08 另挖 2023-05、2024-02。

用法：
  python -I scripts/generate_ads_synth.py            # 生成
  python -I scripts/generate_ads_synth.py --check    # 只跑一致性校验
"""
from __future__ import annotations

import csv
import hashlib
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "raw" / "ads_daily_20261109"
DST = PROJECT_ROOT / "raw" / "ads_synth_20261113"

TENANT_ID = "0000MMCSL4RK60WM270000"  # 与源一致
CREATE_TIME = "2026-11-13 10:00:00"  # 合成批次时间戳（源为 2026-11-01）

_TABLES = {
    "profitability": "mt_ads_profitability_cf.csv",
    "funds": "mt_ads_funds_cash_analysis.csv",
    "equity": "mt_ads_equity_analysis.csv",
    "innovation": "ads_mt_ads_innovation_capability.csv",
}

# 月度季节权重（营收型 / 净利型——净利更偏年末集中），12 月强制校准到锚点
_SEASON_REV = [0.6, 0.7, 0.9, 0.95, 1.0, 1.1, 1.05, 1.0, 1.1, 1.15, 1.2, 1.25]
_SEASON_NP = [0.4, 0.5, 0.8, 0.8, 0.9, 1.0, 0.9, 0.9, 1.1, 1.2, 1.3, 2.0]

YEARS = [2022, 2023, 2024, 2025, 2026]
MINORITY = 0.05  # 少数股东损益占净利总额比例


# ── 8 个画像（P2）：年度锚点 2022→2026，单位=元 ──────────────────────────
# 字段：rev 年营收 | np 归母净利 | xr 扣非/归母 | cfr 经营现金流/归母（年末）
#       gm 毛利率 | rd 研发投入/营收 | cap 研发资本化率 | rdp 研发人员占比
#       emp 员工数（2026 年末） | lev 资产负债率 | div 年末分红/归母
#       cov 覆盖形态 | gaps 额外挖缺期间 | cfr_seq 逐年现金流比（可选）
P = lambda *xs: list(xs)  # noqa: E731  锚点列表简写


def _profiles() -> list[dict]:
    return [
        dict(org_id="9900000000000000001", org_name="演示主体-S01-盈利成长型", cov="A", gaps=[],
             rev=P(2.4e8, 2.9e8, 3.5e8, 4.2e8, 5.0e8), np=P(3.2e7, 4.1e7, 5.2e7, 6.6e7, 8.2e7),
             xr=0.95, cfr=0.8, gm=0.32, rd=0.045, cap=0.12, rdp=0.12, emp=1200, lev=0.45, div=0.2),
        dict(org_id="9900000000000000002", org_name="演示主体-S02-持续亏损型", cov="A", gaps=[],
             rev=P(1.6e8, 1.9e8, 2.2e8, 2.4e8, 2.6e8), np=P(-9.0e7, -7.5e7, -6.0e7, -4.2e7, -2.6e7),
             xr=1.12, cfr=0.6, gm=0.26, rd=0.15, cap=0.08, rdp=0.28, emp=900, lev=0.62, div=0.0),
        dict(org_id="9900000000000000003", org_name="演示主体-S03-净利临界型", cov="A", gaps=[],
             rev=P(1.8e8, 1.8e8, 1.85e8, 1.9e8, 1.9e8), np=P(-4.0e6, 9.0e5, -1.2e6, 6.0e5, 1.2e6),
             xr=0.6, cfr=1.5, gm=0.30, rd=0.05, cap=0.0, rdp=0.10, emp=650, lev=0.50, div=0.0),
        dict(org_id="9900000000000000004", org_name="演示主体-S04-扣非倒挂型", cov="A", gaps=[],
             rev=P(3.2e8, 3.4e8, 3.6e8, 3.8e8, 4.0e8), np=P(6.2e7, 6.3e7, 6.4e7, 6.5e7, 6.6e7),
             xr=0.08, cfr=0.7, gm=0.35, rd=0.04, cap=0.0, rdp=0.08, emp=1500, lev=0.42, div=0.3),
        dict(org_id="9900000000000000005", org_name="演示主体-S05-现金流恶化型", cov="A", gaps=[],
             rev=P(2.2e8, 2.5e8, 2.7e8, 2.9e8, 3.0e8), np=P(4.0e7, 4.4e7, 4.8e7, 5.2e7, 5.5e7),
             xr=0.9, cfr=0.0, gm=0.28, rd=0.05, cap=0.0, rdp=0.10, emp=1100, lev=0.55, div=0.0,
             cfr_seq=P(0.5, 0.2, -0.4, -0.8, -1.0)),  # 经营现金流逐年恶化（占归母比）
        dict(org_id="9900000000000000006", org_name="演示主体-S06-研发高强度型", cov="A", gaps=[],
             rev=P(1.2e8, 1.5e8, 1.8e8, 2.1e8, 2.4e8), np=P(-1.5e7, -4.0e6, 3.0e6, 1.0e7, 1.8e7),
             xr=0.85, cfr=0.4, gm=0.40, rd=0.16, cap=0.25, rdp=0.32, emp=780, lev=0.48, div=0.0),
        dict(org_id="9900000000000000007", org_name="演示主体-S07-小规模北交所型", cov="A", gaps=[],
             rev=P(1.1e8, 1.2e8, 1.35e8, 1.5e8, 1.6e8), np=P(1.8e7, 2.0e7, 2.2e7, 2.4e7, 2.6e7),
             xr=0.92, cfr=0.9, gm=0.34, rd=0.06, cap=0.0, rdp=0.14, emp=420, lev=0.38, div=0.3),
        dict(org_id="9900000000000000008", org_name="演示主体-S08-缺口滞后型", cov="B", gaps=["2023-05", "2024-02"],
             rev=P(1.9e8, 2.0e8, 2.1e8, 2.2e8, 2.3e8), np=P(2.5e7, 2.7e7, 2.8e7, 3.0e7, 3.1e7),
             xr=0.9, cfr=0.75, gm=0.31, rd=0.055, cap=0.10, rdp=0.11, emp=700, lev=0.47, div=0.1),
    ]


def _coverage(cov: str, gaps: list[str]) -> list[str]:
    """期间清单：形态A 到 2026-10（缺 2026-04~09）、形态B 到 2026-03；含 2021-12。"""
    ps = ["2021-12"] + [f"{y}-{m:02d}" for y in range(2022, 2027) for m in range(1, 13)]
    if cov == "A":
        ps = [p for p in ps if not ("2026-04" <= p <= "2026-09")] + ["2026-10"]
    else:  # B
        ps = [p for p in ps if p <= "2026-03"]
    return sorted(set(ps) - set(gaps))


def _periods_table(table: str, prof: dict) -> set[str]:
    ps = _coverage(prof["cov"], prof["gaps"])
    return {p for p in ps if not (table == "equity" and p == "2021-12")}


# ── 数值工具 ─────────────────────────────────────────────────────────────


def f8(v):
    """源风格：零写 '0E-8'，非零 8 位小数；None → 空串。"""
    if v is None:
        return ""
    if abs(v) < 5e-9:
        return "0E-8"
    return f"{v:.8f}"


def season_ytd(anchor: float, month: int, weights: list[float]) -> float:
    """年度锚点沿季节权重的累计值；12 月精确 = 锚点。"""
    if month == 12:
        return anchor
    return anchor * sum(weights[:month]) / sum(weights)


def _pv(state: "OrgState", key: str, month: int) -> float:
    """上月 ytd 缓存；月=1 时跨年重置 → 0（否则一月 ptd 会减掉上年 12 月）。"""
    return state.prev_ytd.get(key, 0.0) if month > 1 else 0.0


def _anchor(seq: list, year: int) -> float:
    return seq[min(year - 2022, len(seq) - 1)]


# ── 财务推导（年度层）：费用栈 → 塞子校准到净利锚点 ────────────────────────


def year_layer(prof: dict, year: int) -> dict:
    """年度锚点 → 全套年度推导量；月度层只做季节展开。

    塞子代数：先按画像费用栈算出 pre_tax_raw 与 tax_raw=25%·pre_tax_raw，
    delta = (pre_tax_raw − tax_raw) − np_total_target；营业成本 += delta 后
    pre_tax_new = tax_raw + np_total_target → tax 保持 tax_raw、税率仍 ≈25%，
    净利精确落锚点，毛利率仅小幅偏移（重算比率列所以恒自洽）。
    """
    i = min(year - 2022, len(YEARS) - 1)
    rev = _anchor(prof["rev"], year)
    np_parent = _anchor(prof["np"], year)
    np_total = np_parent / (1 - MINORITY)
    rd_inv = rev * prof["rd"]
    rd_exp = rd_inv * (1 - prof["cap"])
    taxes = rev * 0.008
    sales = rev * 0.06
    mgmt = rev * 0.09
    fin = rev * 0.012
    gross = rev * prof["gm"]
    pre_tax_raw = rev - (rev - gross) - taxes - sales - mgmt - rd_exp - fin
    tax_raw = 0.25 * pre_tax_raw if pre_tax_raw > 0 else 0.0
    delta = (pre_tax_raw - tax_raw) - np_total
    costs = (rev - gross) + delta
    gross = rev - costs
    pre_tax = rev - costs - taxes - sales - mgmt - rd_exp - fin
    income_tax = pre_tax - np_total
    if income_tax < 0:
        income_tax = 0.0
    cfr = (prof.get("cfr_seq") or [prof["cfr"]] * len(YEARS))[i]
    oper_cf = np_parent * cfr
    excl = np_parent * prof["xr"]
    emp = prof["emp"] - (len(YEARS) - 1 - i) * prof["emp"] // 8  # 前些年约每年少 1/8
    return dict(
        rev=rev, costs=costs, gross=gross, taxes=taxes, sales=sales, mgmt=mgmt, fin=fin,
        rd_inv=rd_inv, rd_exp=rd_exp, cap_ratio=prof["cap"], pre_tax=pre_tax,
        income_tax=income_tax, np_total=np_total, np_parent=np_parent, excl=excl,
        nonrec=np_parent - excl, oper_cf=oper_cf, emp=emp,
        rd_person=round(emp * prof["rdp"]), lev=prof["lev"], div_ratio=prof["div"],
    )


# ── 跨期滚动状态 ─────────────────────────────────────────────────────────


class OrgState:
    """单主体滚动量：权益/资产/现金/未分配利润 + 上月 ytd 缓存（差分用）。"""

    def __init__(self, prof: dict):
        self.prof = prof
        self.equity_parent_pe = 0.0
        self.total_equity_pe = 0.0
        self.assets_pe = 0.0
        self.cash_pe = 2.0e7  # 期初货币资金
        self.undist = 0.0
        # 股本基数派生：4× 历年最大净利、下限 6000 万——否则成长型 ROE 会虚高到 60%+
        base = max(6.0e7, 4 * max(abs(x) for x in prof["np"]))
        self.capital = base * 0.7
        self.cap_reserve = base * 0.3
        self.surplus = 0.0
        self._prev_assets = 0.0
        self.prev_undist = 0.0
        self.prev_equity_parent = 0.0
        self.prev_ytd: dict[str, float] = {}

    def advance(self, layer: dict, month: int, np_parent_ptd: float) -> None:
        """按月推进滚动量（各表写行前调用；年末扣分红、提盈余公积）。"""
        self.prev_undist = self.undist  # pb 列要的是「扣分红/提公积前」的上月期末
        self.prev_equity_parent = self.equity_parent_pe
        self.undist += np_parent_ptd
        if month == 12 and layer["np_parent"] > 0:  # 亏损年不提公积、不分红
            self.undist -= layer["np_parent"] * layer["div_ratio"]
            self.surplus += layer["np_parent"] * 0.10
        parent = self.capital + self.cap_reserve + self.surplus + self.undist
        prev = self.equity_parent_pe
        self.equity_parent_pe = parent
        self.equity_avg = (prev + parent) / 2 if prev else parent
        total = parent / (1 - MINORITY)
        self.total_equity_avg = ((self.total_equity_pe + total) / 2) if self.total_equity_pe else total
        self.total_equity_pe = total
        self.assets_pe = total / (1 - layer["lev"])
        self.assets_avg = ((self._prev_assets + self.assets_pe) / 2) if self._prev_assets else self.assets_pe
        self._prev_assets = self.assets_pe  # noqa: B010  首期后才有值


# ── 各表行构造（返回 信号列→数值 的 dict；空值表缺失比率）────────────────


def _funds_quant(layer: dict, month: int) -> dict:
    """funds 表期间量（ytd 口径单点计算，构造行与缓存共用一份，保证一致）。"""
    cf = season_ytd(layer["oper_cf"], month, _SEASON_NP)
    inv = season_ytd(layer["rev"] * -0.03, month, _SEASON_REV)  # 投资净流出 ≈ 营收 3%
    fin_k = 0.04 if (layer["np_parent"] < 0 or layer["div_ratio"] == 0) else -0.01
    fin = season_ytd(layer["rev"] * fin_k, month, _SEASON_REV)  # 亏损/扩张期筹资净流入
    inflow = season_ytd(layer["rev"] * 1.02, month, _SEASON_REV)
    outflow = inflow - cf
    if outflow <= 0:
        outflow = inflow * 0.8
    return dict(cf=cf, inv=inv, fin=fin, inflow=inflow, outflow=outflow, inc=cf + inv + fin)


def row_profitability(state: OrgState, layer: dict, month: int) -> dict:
    rev_y = season_ytd(layer["rev"], month, _SEASON_REV)
    rev_p = rev_y - _pv(state, "rev", month)
    y = lambda k: season_ytd(layer[k], month, _SEASON_REV)  # noqa: E731  营收驱动科目
    p = lambda k: y(k) - _pv(state, k, month)  # noqa: E731
    np_y = lambda k: season_ytd(layer[k], month, _SEASON_NP)  # noqa: E731  净利块（年末集中）
    np_p = lambda k: np_y(k) - _pv(state, k + "_np", month)  # noqa: E731
    fq = _funds_quant(layer, month)
    pre_tax_y, np_total_y = y("pre_tax"), np_y("np_total")
    income_tax_y = pre_tax_y - np_total_y  # 恒等式导出（两曲线年度合计仍精确闭合）
    income_tax_p = income_tax_y - _pv(state, "income_tax", month)
    npa = np_y("np_parent")

    return {
        # 收入
        "operating_revenues_ytd_bl_cf": rev_y, "operating_revenues_ptd_bl_cf": rev_p,
        "main_operating_revenues_ytd_bl_cf": rev_y, "main_operating_revenues_ptd_bl_cf": rev_p,
        "other_operating_revenues_ytd_bl_cf": 0.0, "other_operating_revenues_ptd_bl_cf": 0.0,
        # 成本与利润（源表无成本/毛利/营业利润的 ptd 口径，只给 ytd）
        "operating_costs_ytd_bl_cf": y("costs"),
        "gross_profit_ytd_bl_cf": y("gross"),
        "operating_profit_ytd_bl_cf": pre_tax_y,
        "net_profit_ytd_bl_cf": np_total_y, "net_profit_ptd_bl_cf": np_p("np_total"),
        "net_profit_attrib_parent_ytd_cf": npa,
        "net_profit_attrib_parent_excl_extra_ytd_cf": np_y("excl"),
        "non_recurring_net_amount": np_y("nonrec"),
        # 费用（营收驱动）
        "sales_expenses_ytd_bl_cf": y("sales"), "sales_expenses_ptd_bl_cf": p("sales"),
        "management_expenses_ytd_bl_cf": y("mgmt"), "management_expenses_ptd_bl_cf": p("mgmt"),
        "financial_expenses_ytd_bl_cf": y("fin"), "financial_expenses_ptd_bl_cf": p("fin"),
        "taxes_and_additions_ytd_bl_cf": y("taxes"), "taxes_and_additions_ptd_bl_cf": p("taxes"),
        "research_expenses_ytd_cf": y("rd_exp"), "research_expenses_ptd_cf": p("rd_exp"),
        "income_tax_ytd_bl_cf": income_tax_y, "income_tax_ptd_bl_cf": income_tax_p,
        # 资产/权益（与 equity 表同源滚动）
        "assets_pe_bl_cf": state.assets_pe, "asset_avg_cf": state.assets_avg,
        "equity_pe_bl_cf": state.total_equity_pe, "equity_avg_cf": state.equity_avg,
        "total_equity_attr_to_parent_co_pe_bl_cf": state.equity_parent_pe,
        "total_equity_attr_to_parent_co_avg_cf": state.equity_avg,
        "accumulated_depreciation_ytd_cf": state.assets_pe * 0.12,
        # 现金流（与 funds 表同源量）
        "net_cash_flow_from_oper_ytd_cf": fq["cf"],
        "cash_rec_from_sell_ytd_consolidated": fq["inflow"],
        "cash_pay_for_employees_ytd_cf": fq["outflow"] * 0.30,
        "cash_pay_for_taxs_ytd_cf": y("taxes") + income_tax_y,
        "cash_pay_for_ph_goods_ytd_cf": y("costs") * 0.8,
        # 比率（除零 → 空）
        "operating_gross_profit_margin_cf": (y("gross") / rev_y) if rev_y else None,
        "operating_net_profit_margin_cf": (pre_tax_y / rev_y) if rev_y else None,
        "roe_attri_ytd_cf": (npa / state.equity_avg) if state.equity_avg else None,
        "roe_attri_excl_extra_ytd_cf": (np_y("excl") / state.equity_avg) if state.equity_avg else None,
        "roa_ratio_cf": (np_total_y / state.assets_avg) if state.assets_avg else None,
        "revenue_cash_ratio_cf": (fq["cf"] / rev_y) if rev_y else None,
        "surplus_cash_cover_multiple_cf": (fq["cf"] / np_total_y) if np_total_y else None,
    }


def row_funds(state: OrgState, layer: dict, fq: dict, month: int) -> dict:
    g = lambda k, m: season_ytd(layer[k], month, m)  # noqa: E731
    npy = season_ytd(layer["np_total"], month, _SEASON_NP)
    cf_p = fq["cf"] - _pv(state, "fq_cf", month)
    inc_p = fq["inc"] - _pv(state, "fq_inc", month)
    inflow_p = fq["inflow"] - _pv(state, "fq_inflow", month)
    outflow_p = fq["outflow"] - _pv(state, "fq_outflow", month)
    cash_yb = state.cash_pe
    state.cash_pe = cash_yb + inc_p  # 现金余额滚动
    return {
        "cash_inflows_from_oper_ytd_cf": fq["inflow"], "cash_inflows_from_oper_cf": inflow_p,
        "cash_outflows_from_oper_ytd_cf": fq["outflow"], "cash_outflows_from_oper_cf": outflow_p,
        "net_cash_flow_from_oper_ytd_cf": fq["cf"], "net_cash_flow_from_oper_cf": cf_p,
        "net_cash_flow_from_invest_ytd_cf": fq["inv"], "net_cash_flow_from_invest_cf": fq["inv"] - _pv(state, "fq_inv", month),
        "net_cash_flow_from_fin_ytd_cf": fq["fin"], "net_cash_flow_from_fin_cf": fq["fin"] - _pv(state, "fq_fin", month),
        "net_increase_cash_cash_equiv_current_ytd_cf": fq["inc"], "net_increase_cash_cash_equiv_current_cf": inc_p,
        "cash_and_equivalents_yb_bl_cf": cash_yb, "cash_and_equivalents_pe_bl_cf": state.cash_pe,
        "cash_and_equivalents_pb_bl_cf": cash_yb,
        "net_profit_ytd_bl_cf": npy, "net_profit_ptd_bl_cf": npy - _pv(state, "np_total_np", month),
        "cash_rec_from_sell_ytd_consolidated": fq["inflow"],
        "cash_pay_for_ph_goods_ytd_cf": g("costs", _SEASON_REV) * 0.8,
        "cash_pay_for_ph_goods_cf": (g("costs", _SEASON_REV) - _pv(state, "costs", month)) * 0.8,
        "cash_pay_for_employees_ytd_cf": fq["outflow"] * 0.30,
        "cash_pay_for_taxs_cf": g("taxes", _SEASON_REV) + (g("pre_tax", _SEASON_REV) - npy),
        "net_profit_cash_cov_mult_cf": (fq["cf"] / npy) if npy else None,
    }


def row_equity(state: OrgState, layer: dict, month: int) -> dict:
    surplus_yb = layer["np_parent"] * 0.10 if (month == 12 and layer["np_parent"] > 0) else 0.0
    return {
        "capital_pe_bl_cf": state.capital, "capital_yb_bl_cf": 0.0,
        "capital_reserve_pe_bl_cf": state.cap_reserve, "capital_reserve_yb_bl_cf": 0.0,
        "surplus_reserve_pe_bl_cf": state.surplus, "surplus_reserve_yb_bl_cf": surplus_yb,
        "undistributed_profits_pe_bl_cf": state.undist,
        "undistributed_profits_pb_bl_cf": state.prev_undist,  # = 上月期末（advance 已含分红/公积）
        "other_comprehensive_income_pe_bl_cf": 0.0,
        "equity_pe_bl_cf": state.total_equity_pe, "equity_yb_bl_rf": 0.0,
        "equity_avg_cf": state.equity_avg,
        "total_equity_attr_to_parent_co_pe_bl_cf": state.equity_parent_pe,
        "total_equity_attr_to_parent_co_yb_bl_cf": state.equity_parent_pe - state.prev_equity_parent,
        "total_equity_attr_to_parent_co_avg_cf": state.equity_avg,
    }


def row_innovation(state: OrgState, layer: dict, month: int) -> dict:
    rev_y = season_ytd(layer["rev"], month, _SEASON_REV)
    rd_y = season_ytd(layer["rd_inv"], month, _SEASON_REV)
    exp_y = rd_y * (1 - layer["cap_ratio"])
    return {
        "rd_investment_ytd_bl_cf": rd_y,
        "rd_expensed_costs_ytd_bl_cf": exp_y,
        "rd_capitalized_costs_ytd_bl_cf": rd_y - exp_y,
        "research_expenses_ytd_cf": exp_y,  # 与 profitability 表 research_expenses 同源
        "operating_revenues_ytd_bl_cf": rev_y,
        "main_operating_revenues_ytd_bl_cf": rev_y,
        "other_operating_revenues_ytd_bl_cf": 0.0,
        "intensity_develop_invest_cf": (rd_y / rev_y) if rev_y else None,
        "number_of_employees_pe_bl_cf": float(layer["emp"]),
        "number_of_rd_personnel_pe_bl_cf": float(layer["rd_person"]),
        "rd_personnel_ratio_pe_bl_cf": (layer["rd_person"] / layer["emp"]) if layer["emp"] else None,
    }


# ── 元数据与合成 ─────────────────────────────────────────────────────────


def _meta(table: str, prof: dict, period: str) -> dict:
    h = hashlib.md5(f"{TENANT_ID}|{prof['org_id']}|{table}|{period}".encode()).hexdigest()
    y, m = period.split("-")
    return dict(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"ads-synth|{table}|{prof['org_id']}|{period}")),
        ytenant_id=TENANT_ID, all_dimension_md5=h, dw_data_from="",
        dim_y_rpt_org=prof["org_id"], dim_y_rpt_org_name=prof["org_name"],
        year=y, month=str(int(m)), period_code=period, dim_y_ana_month=period,
        create_time=CREATE_TIME,
    )


def _compose(table: str, signals: dict, meta: dict, header: list[str], donor_default: dict) -> dict:
    """元数据 + 信号列 + 未映射列的 donor 形态兜底；拼写错误 fail-fast。"""
    row = {c: donor_default[table][c] for c in header}
    row.update(meta)
    for k, v in signals.items():
        assert k in header, f"{table} 信号列不在 header: {k}"
        row[k] = f8(v)
    return row


def _cache_profit_prev(state: OrgState, layer: dict, month: int) -> None:
    """profitability 表 ytd 缓存：营收驱动科目走 _SEASON_REV，净利块另存 *_np 键。"""
    for k in ["rev", "costs", "gross", "pre_tax", "sales", "mgmt", "fin", "taxes", "rd_exp"]:
        state.prev_ytd[k] = season_ytd(layer[k], month, _SEASON_REV)
    for k in ["np_total", "np_parent"]:
        state.prev_ytd[f"{k}_np"] = season_ytd(layer[k], month, _SEASON_NP)
    state.prev_ytd["income_tax"] = (
        season_ytd(layer["pre_tax"], month, _SEASON_REV) - season_ytd(layer["np_total"], month, _SEASON_NP)
    )


def generate() -> None:
    src_headers = {t: _read_header(f) for t, f in _TABLES.items()}
    donor_default = _donor_defaults(src_headers)  # 未映射列的稀疏形态
    tables: dict[str, list[dict]] = {t: [] for t in _TABLES}

    for prof in _profiles():
        state = OrgState(prof)
        periods = _coverage(prof["cov"], prof["gaps"])
        cov = {t: _periods_table(t, prof) for t in _TABLES}
        for period in periods:
            year, month = int(period[:4]), int(period[5:])
            layer = year_layer(prof, year)
            np_y = season_ytd(layer["np_parent"], month, _SEASON_NP)
            np_ptd = np_y - _pv(state, "np_parent_np", month)
            state.advance(layer, month, np_ptd)
            fq = _funds_quant(layer, month)

            if period in cov["profitability"]:
                tables["profitability"].append(_compose(
                    "profitability", row_profitability(state, layer, month),
                    _meta("profitability", prof, period), src_headers["profitability"], donor_default))
            if period in cov["funds"]:
                tables["funds"].append(_compose(
                    "funds", row_funds(state, layer, fq, month),
                    _meta("funds", prof, period), src_headers["funds"], donor_default))
            if period in cov["equity"]:
                tables["equity"].append(_compose(
                    "equity", row_equity(state, layer, month),
                    _meta("equity", prof, period), src_headers["equity"], donor_default))
            if period in cov["innovation"]:
                tables["innovation"].append(_compose(
                    "innovation", row_innovation(state, layer, month),
                    _meta("innovation", prof, period), src_headers["innovation"], donor_default))

            # 当期 ytd → 缓存（下月差分用）；funds 量与行构造同一份 fq
            _cache_profit_prev(state, layer, month)
            for k, v in [("fq_cf", fq["cf"]), ("fq_inv", fq["inv"]), ("fq_fin", fq["fin"]),
                         ("fq_inc", fq["inc"]), ("fq_inflow", fq["inflow"]), ("fq_outflow", fq["outflow"])]:
                state.prev_ytd[k] = v

    DST.mkdir(parents=True, exist_ok=True)
    for t, fname in _TABLES.items():
        rows = sorted(tables[t], key=lambda r: (r["dim_y_rpt_org"], r["period_code"]))
        with (DST / fname).open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=src_headers[t], extrasaction="raise")
            w.writeheader()
            w.writerows(rows)
        print(f"{fname}: {len(rows)} 行 × {len(src_headers[t])} 列")
    print(f"输出目录: {DST}")


def _read_header(fname: str) -> list[str]:
    with (SRC / fname).open(encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def _donor_defaults(headers: dict[str, list[str]]) -> dict[str, dict[str, str]]:
    """donor（科商科技物流仓储公司）各列多数形态：'0E-8' / ''。"""
    donor = "2486610460541976584"
    out = {}
    for t, fname in _TABLES.items():
        with (SRC / fname).open(encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh) if r["dim_y_rpt_org"] == donor]
        out[t] = {}
        for col in headers[t]:
            zeros = sum(1 for r in rows if r.get(col) == "0E-8")
            empties = sum(1 for r in rows if r.get(col) == "")
            out[t][col] = "" if empties > zeros else "0E-8"
    return out


# ── 一致性校验 ───────────────────────────────────────────────────────────


def check() -> None:
    """schema 对齐、无 org 碰撞、期间覆盖、ytd 累计、和式与比率勾稽。"""
    src_headers = {t: _read_header(f) for t, f in _TABLES.items()}
    problems: list[str] = []

    def load(t: str) -> list[dict]:
        with (DST / _TABLES[t]).open(encoding="utf-8", newline="") as fh:
            r = csv.DictReader(fh)
            if r.fieldnames != src_headers[t]:
                problems.append(f"{t}: header 与源不一致")
            return list(r)

    def n(v):
        return float(v) if v not in ("", None) else None

    src_orgs: set[str] = set()
    for t in _TABLES:
        with (SRC / _TABLES[t]).open(encoding="utf-8", newline="") as fh:
            src_orgs |= {r["dim_y_rpt_org"] for r in csv.DictReader(fh)}

    data = {t: load(t) for t in _TABLES}
    for t, rows in data.items():
        collide = {r["dim_y_rpt_org"] for r in rows} & src_orgs
        if collide:
            problems.append(f"{t}: org 与源碰撞 {collide}")
        for r in rows:
            if r["period_code"] != r["dim_y_ana_month"] or r["create_time"] != CREATE_TIME:
                problems.append(f"{t} {r['period_code']}: 元数据异常")

    for prof in _profiles():
        org, want = prof["org_id"], set(_coverage(prof["cov"], prof["gaps"]))
        by = {t: sorted((r for r in data[t] if r["dim_y_rpt_org"] == org), key=lambda r: r["period_code"]) for t in _TABLES}
        got = {r["period_code"] for r in by["profitability"]}
        if got != want:
            problems.append(f"{org}: 覆盖不符 缺{sorted(want - got)} 多{sorted(got - want)}")
        for t in _TABLES:
            expect_eq = {p for p in want if not (t == "equity" and p == "2021-12")}
            if {r["period_code"] for r in by[t]} != expect_eq:
                problems.append(f"{org} {t}: 期间覆盖与规划不符")

        prev: dict = {}
        for r in by["profitability"]:
            y, m = r["year"], int(r["month"])
            for c in ["operating_revenues", "net_profit"]:
                ytd_, ptd_ = n(r[f"{c}_ytd_bl_cf"]), n(r[f"{c}_ptd_bl_cf"])
                exp = ptd_ + (prev.get((y, c), 0.0) if m > 1 else 0.0)
                if ytd_ is None or ptd_ is None or abs(ytd_ - exp) > 0.01:
                    problems.append(f"{org} {r['period_code']} {c}: ytd {ytd_} != prev+ptd {exp}")
                prev[(y, c)] = ytd_ or 0.0
            rev, gp, op = n(r["operating_revenues_ytd_bl_cf"]), n(r["gross_profit_ytd_bl_cf"]), n(r["operating_profit_ytd_bl_cf"])
            if rev and abs(gp / rev - n(r["operating_gross_profit_margin_cf"])) > 1e-6:
                problems.append(f"{org} {r['period_code']}: 毛利率不符")
            if rev and abs(op / rev - n(r["operating_net_profit_margin_cf"])) > 1e-6:
                problems.append(f"{org} {r['period_code']}: 营业利润率不符")
            npa, eqv = n(r["net_profit_attrib_parent_ytd_cf"]), n(r["total_equity_attr_to_parent_co_avg_cf"])
            if eqv and abs(npa / eqv - n(r["roe_attri_ytd_cf"])) > 1e-6:
                problems.append(f"{org} {r['period_code']}: roe 不符")
            par, exl, nn = npa, n(r["net_profit_attrib_parent_excl_extra_ytd_cf"]), n(r["non_recurring_net_amount"])
            if None not in (par, exl, nn) and abs(par - exl - nn) > 0.01:
                problems.append(f"{org} {r['period_code']}: 非经常勾稽不符")
            # 利润恒等式：营业利润 − 所得税 = 净利总额（跨曲线年度闭合）
            op_y, tax_y, npy = op, n(r["income_tax_ytd_bl_cf"]), n(r["net_profit_ytd_bl_cf"])
            if None not in (op_y, tax_y, npy) and abs(op_y - tax_y - npy) > 0.02:
                problems.append(f"{org} {r['period_code']}: 利润恒等式不符")

        for r in by["equity"]:
            comp = sum(n(r[k]) or 0 for k in ["capital_pe_bl_cf", "capital_reserve_pe_bl_cf",
                                              "surplus_reserve_pe_bl_cf", "undistributed_profits_pe_bl_cf",
                                              "other_comprehensive_income_pe_bl_cf"])
            if abs(comp - (n(r["total_equity_attr_to_parent_co_pe_bl_cf"]) or 0)) > 0.01:
                problems.append(f"{org} {r['period_code']}: equity 构成和不符")
            twin = next((x for x in by["profitability"] if x["period_code"] == r["period_code"]), None)
            if twin and abs((n(twin["equity_avg_cf"]) or 0) - (n(r["equity_avg_cf"]) or 0)) > 0.01:
                problems.append(f"{org} {r['period_code']}: equity_avg 跨表不一致")
        # equity pb 衔接：本月期初 = 上月期末（同年内及跨年）
        for i in range(1, len(by["equity"])):
            pb_cur = n(by["equity"][i]["undistributed_profits_pb_bl_cf"])
            pe_prev = n(by["equity"][i - 1]["undistributed_profits_pe_bl_cf"])
            if None not in (pb_cur, pe_prev) and abs(pb_cur - pe_prev) > 0.01:
                problems.append(f"{org} {by['equity'][i]['period_code']}: 未分配利润 pb≠上月 pe")
        # 未分配利润逐月增量 = 归母净利当期（12 月另扣分红；盈余公积单独成科目不动未分配）
        # ——能抓住「一月误减上年全年净利」这类跨年重置 bug
        npa_by_period = {r["period_code"]: n(r["net_profit_attrib_parent_ytd_cf"]) for r in by["profitability"]}
        prev_npa = 0.0
        prev_year = None
        for r in by["equity"]:
            period, m = r["period_code"], int(r["month"])
            npa = npa_by_period.get(period)
            npa_ptd = (npa - (prev_npa if r["year"] == prev_year else 0.0)) if None not in (npa, prev_npa) else None
            pb_, pe_ = n(r["undistributed_profits_pb_bl_cf"]), n(r["undistributed_profits_pe_bl_cf"])
            if None not in (npa_ptd, pb_, pe_):
                expect_delta = npa_ptd
                if m == 12 and npa and npa > 0:
                    expect_delta = npa_ptd - npa * prof["div"]
                if abs(pe_ - pb_ - expect_delta) > 0.02:
                    problems.append(f"{org} {period}: 未分配利润增量 {pe_ - pb_:.0f} != 归母净利当期 {expect_delta:.0f}")
            prev_npa, prev_year = npa if npa is not None else prev_npa, r["year"]

        prev_cash = 2.0e7
        for r in by["funds"]:
            fin_, out_, net_ = n(r["cash_inflows_from_oper_ytd_cf"]), n(r["cash_outflows_from_oper_ytd_cf"]), n(r["net_cash_flow_from_oper_cf"])
            inc_ = n(r["net_increase_cash_cash_equiv_current_cf"])
            cash_pe = n(r["cash_and_equivalents_pe_bl_cf"])
            if None not in (fin_, out_) and abs(fin_ - out_ - n(r["net_cash_flow_from_oper_ytd_cf"])) > 0.01:
                problems.append(f"{org} {r['period_code']}: funds 净额 != 收-支")
            if abs(prev_cash + inc_ - cash_pe) > 0.01:
                problems.append(f"{org} {r['period_code']}: 现金滚动不符")
            prev_cash = cash_pe

        for r in by["innovation"]:
            inv, rev = n(r["rd_investment_ytd_bl_cf"]), n(r["operating_revenues_ytd_bl_cf"])
            if rev and inv is not None and abs(inv / rev - n(r["intensity_develop_invest_cf"])) > 1e-6:
                problems.append(f"{org} {r['period_code']}: 研发强度不符")
            emp, rdp = n(r["number_of_employees_pe_bl_cf"]), n(r["number_of_rd_personnel_pe_bl_cf"])
            if emp and rdp is not None:
                if abs(rdp / emp - n(r["rd_personnel_ratio_pe_bl_cf"])) > 1e-6:
                    problems.append(f"{org} {r['period_code']}: 研发人员比不符")
                if rdp > emp:
                    problems.append(f"{org} {r['period_code']}: 研发人数 > 员工数（源病态不复刻）")
            # 跨表同源：研发费用化 = profitability.research_expenses_ytd
            twin = next((x for x in by["profitability"] if x["period_code"] == r["period_code"]), None)
            if twin and abs((n(twin["research_expenses_ytd_cf"]) or 0) - (n(r["research_expenses_ytd_cf"]) or 0)) > 0.01:
                problems.append(f"{org} {r['period_code']}: 研发费用跨表不一致")

    if problems:
        print(f"校验失败 {len(problems)} 条：")
        for p_ in problems[:40]:
            print("  -", p_)
        sys.exit(1)
    print("校验通过（全部一致）", {t: len(rows) for t, rows in data.items()})


def main() -> None:
    if "--check" in sys.argv:
        check()
    else:
        generate()


if __name__ == "__main__":
    main()
