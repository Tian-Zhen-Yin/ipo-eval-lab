# -*- coding: utf-8 -*-
"""
M8 midas 桥：raw/mt_ipo_daily_20261109/mt_ipo_listing_standard.json
        → calibration/midas_snapshot.yaml（L3 第三证人的快照基线）

确定性代码，零 AI。三张手工固化、可审计的映射表：
1. BOARD_MAP / CTYPE_MAP   —— midas 中文名 → 规则库枚举
2. ROW_LEAF_MAP            —— 24 条件型（含复合行拆双叶）→ item_ref
3. SORT_GROUP              —— midas sort(支路号) → 官方套号 group_no
                              （来源：docs/calibration/0001 归组总表，2026-11-10 已拍板）

已知勘误随导出一并落盘（notes 段），供 L3 差异清单交叉引用：
- 沪/深主板 一般企业 sort3 预计市值 ≥350亿 —— 笔误，正确 50亿（0001 §3-1）
- 北交所 sort1 最近2年净利润均 ＞1500万 —— op 与法条「不低于」不一致（gt vs ge）
- midas 红筹定性条件单形态（含「科技创新能力较强」），不区分 3.1.4/3.1.5 措辞
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RAW = REPO / "raw" / "mt_ipo_daily_20261109" / "mt_ipo_listing_standard.json"
OUT = REPO / "calibration" / "midas_snapshot.yaml"

BOARD_MAP = {
    "上交所主板": "SSE-MB", "深交所主板": "SZSE-MB", "科创板": "STAR",
    "创业板": "ChiNext", "北交所": "BSE",
}
CTYPE_MAP = {
    "一般企业": "general",
    "红筹企业（已境外上市）": "redchip_listed",
    "红筹企业（未境外上市）": "redchip_unlisted",
    "表决权差异企业": "weighted_voting",
}

# eval_item_name 前缀 → 叶模式；None = 复合行，由专门函数拆
ROW_LEAF_MAP = [
    ("最近3年净利润均为正，且累计值", "compound_np3y"),
    ("最近2年净利润均为正，且累计值", "compound_np2y"),
    ("最近2年净利润均", "np_2y_each"),
    ("主要业务或产品需经国家有关部门批准", "product_approved_clinical"),
    ("处于研发阶段的红筹企业", "redchip_special"),
    ("拥有自主研发、国际领先技术", "self_developed_tech_full"),  # midas 单形态，不分 3.1.4/3.1.5
    ("市值/预计市值", "mktcap_forecast"),
    ("市值", "mktcap_actual"),          # 已上市红筹的二级市场市值
    ("预计市值", "mktcap_forecast"),
    ("最近1年净利润", "np_latest"),
    ("最近1年净资产", "equity_latest"),
    ("最近1年加权平均净资产收益率", "roe_weighted_latest"),
    ("最近2年加权平均净资产收益率平均", "roe_weighted_2y_avg"),
    ("最近1年经营活动产生的现金流量净额", "ocf_latest"),
    ("最近3年经营活动产生的现金流量净额累计", "ocf_3y_sum"),
    ("最近1年营业收入增长率", "rev_1y_growth"),
    ("最近3年营业收入复合增长率", "rev_3y_cagr"),
    ("最近2年营业收入平均值", "rev_2y_avg"),
    ("最近1年营业收入", "rev_latest"),
    ("最近3年营业收入累计", "rev_3y_sum"),
    ("最近2年研发投入金额累计", "rd_2y_sum"),
    ("最近3年累计研发投入占最近3年累计营业收入的比例", "rd_intensity_3y"),
    ("最近2年累计研发投入占最近2年累计营业收入比例", "rd_intensity_2y"),
    ("最近3年累计研发投入", "rd_3y_sum"),
]

# sort（支路号）→ group_no（官方套号）；来源 0001 §1 归组总表
_MB_GENERAL = {1: 1, 2: 1, 3: 2, 4: 3}
SORT_GROUP = {
    ("SSE-MB", "general"): _MB_GENERAL,
    ("SZSE-MB", "general"): _MB_GENERAL,
    ("STAR", "general"): {1: 1, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5},
    ("ChiNext", "general"): {1: 1, 2: 2, 3: 3, 4: 4, 5: 4},
    ("BSE", "general"): {1: 1, 2: 1, 3: 2, 4: 3, 5: 4},
}
_RC_LISTED = {1: 1, 2: 2}
_MB_RC_UNLISTED = {1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3}
_GEM_RC_UNLISTED = {1: 1, 2: 1, 3: 1, 4: 2, 5: 3, 6: 3}
for _b in BOARD_MAP.values():
    SORT_GROUP[(_b, "redchip_listed")] = _RC_LISTED
    SORT_GROUP[(_b, "weighted_voting")] = {1: 1, 2: 1}
for _b in ("SSE-MB", "SZSE-MB"):
    SORT_GROUP[(_b, "redchip_unlisted")] = _MB_RC_UNLISTED
for _b in ("STAR", "ChiNext"):
    SORT_GROUP[(_b, "redchip_unlisted")] = _GEM_RC_UNLISTED

OP_MAP = {"≥": "ge", "＞": "gt", ">": "gt", "≤": "le", "＜": "lt", "是": "eq"}


def parse_requirement(req: str):
    """'≥200亿' → (ge, 2e10, number)；'＞10%' → (gt, 0.10, percent)；'是' → (eq, True, boolean)"""
    req = req.strip()
    if req == "是":
        return "eq", True, "boolean"
    m = re.match(r"^(≥|＞|>|≤|＜|<)\s*(.+)$", req)
    if not m:
        return None, None, None   # 如「高于同行业可比公司同期平均增长水平」
    op = OP_MAP[m.group(1)]
    rest = m.group(2)
    if "%" in rest:
        return op, round(float(rest.replace("%", "")) / 100, 6), "percent"
    # 亿/万 → 元（与 L1b 归一化同口径）
    sys.path.insert(0, str(REPO))
    from ipo_eval_lab.calibration.l1b_gate import normalize_chinese_number
    return op, float(normalize_chinese_number(rest)), "number"


def item_enrich(item_ref: str, items: dict) -> dict:
    it = items.get(item_ref, {})
    return {"quantifier": it.get("quantifier"), "window": it.get("window")}


def leaves_for(row: dict, items: dict) -> list[dict]:
    name, req = row["eval_item_name"], row["requirement"]
    op, val, fmt = parse_requirement(req)
    for prefix, target in ROW_LEAF_MAP:
        if not name.startswith(prefix):
            continue
        if target == "compound_np3y":
            return [
                {"item_ref": "np_3y_allpos", "op": "gt", "threshold": 0,
                 "format": "number", **item_enrich("np_3y_allpos", items)},
                {"item_ref": "np_3y_sum", "op": op, "threshold": val,
                 "format": "number", **item_enrich("np_3y_sum", items)},
            ]
        if target == "compound_np2y":
            return [
                {"item_ref": "np_2y_allpos", "op": "gt", "threshold": 0,
                 "format": "number", **item_enrich("np_2y_allpos", items)},
                {"item_ref": "np_2y_sum", "op": op, "threshold": val,
                 "format": "number", **item_enrich("np_2y_sum", items)},
            ]
        leaf = {"item_ref": target, "op": op, "threshold": val,
                "format": fmt, **item_enrich(target, items)}
        if val is None:
            leaf["note"] = f"无量值阈值：{req}（判断型/行业对比）"
        return [leaf]
    raise KeyError(f"未映射的条件型：{name!r}")


def main() -> int:
    sys.path.insert(0, str(REPO))
    from ipo_eval_lab.calibration.rulebook_refs import load_items
    items = load_items(REPO / "rulebook")

    rows = json.loads(RAW.read_text(encoding="utf-8"))
    snapshot: dict[str, dict] = defaultdict(lambda: {"leaves": [], "_sorts": set()})

    for r in rows:
        board = BOARD_MAP[r["board_name"]]
        ctype = CTYPE_MAP[r["company_type"]]
        sort = int(r["sort"])
        gno = SORT_GROUP[(board, ctype)][sort]
        key = f"{board}:{ctype}:{gno}"
        entry = snapshot[key]
        entry["_sorts"].add(sort)
        for leaf in leaves_for(r, items):
            sig = (leaf["item_ref"], leaf["op"], leaf["threshold"])
            if sig not in {(l["item_ref"], l["op"], l["threshold"]) for l in entry["leaves"]}:
                entry["leaves"].append(leaf)

    # 落盘（剔除工作键）
    out = {k: {"leaves": v["leaves"], "midas_sorts": sorted(v["_sorts"])}
           for k, v in sorted(snapshot.items())}
    n_leaves = sum(len(v["leaves"]) for v in out.values())

    anomalies = [
        "SSE-MB/SZSE-MB general g2 预计市值 ≥350亿 —— 笔误，正确 50亿（0001 §3-1）",
        "BSE general g1 最近2年净利润 ＞1500万 —— 法条为「不低于」（gt vs ge 口径差）",
        "midas 红筹定性条件单形态（含科技创新能力较强），不区分 3.1.4/3.1.5 措辞",
        "行业下行期对比路径（高于同行业平均）无量值阈值，以 note 记录",
    ]

    doc = {
        "version": "mt_ipo_daily_20261109",
        "exported_at": str(Path(__file__).stem),
        "source": "raw/mt_ipo_daily_20261109/mt_ipo_listing_standard.json",
        "row_count": len(rows),
        "entry_count": len(out),
        "leaf_count": n_leaves,
        "notes": anomalies,
        "snapshot": out,
    }
    OUT.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"导出 {len(out)} 个套键 / {n_leaves} 叶 → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
