"""midas 套号（IPO-xx）→ branch aliases.midas 桥接补丁（G-遗留项落地，2026-11-13 用户拍板）

背景：正式库 branch 的 aliases.midas 一直为空——候选库（L1a）没有套号数据。
本脚本给 candidates_amended.jsonl 的 branch 候选补 context.midas_aliases，
产出 candidates_bridged.jsonl，走 export-official 落正式库。

对号算法（SORT_GROUP 为权威，来源 export_midas_snapshot.py，calibration/0001 归组总表）：
- Excel 规则表（03_standard_rules_table.txt）的 (board, ctype) 组内 IPO 码按出现
  顺序 = midas sort（sort1, sort2, …）；
- SORT_GROUP 把 sort → 官方套号 group_no；
- 每 group：该组的 sorts 升序 ↔ 该组 branches 按 branch_id 升序——
  - 支路数 = sort 数：1:1 对号（k-th 支路 ← k-th sort 的 IPO 码）；
  - 支路数 = 1 且 sort 数 > 1（R2-a collapse，如主板 general 套1 的 sort1+sort2
    收敛为单支路 clause any）：该支路 ← 全部 IPO 码（[IPO-01, IPO-02]）；
  - 支路数 < sort 数（非 collapse）：前 N 支路 1:1，剩余 sort 无支路承接
    （如特殊红筹判断行——豁免语义，已在黄金集 gaps/差异清单），列报告不静默。

IPO-62/63 事实核对（2026-11-13，纠正前期误判）：
- 创业板 general 套4（chinext_general_g4）= 法条 2.1.2(四)（30亿+营收2亿+cagr30%
  ∨ 40亿+营收2亿+研发1亿+15%）；Excel 拆 IPO-62/63 两套（2026-04 新增）；
- DB 快照 ChiNext:general:4 的 sorts [4,5] 数值与 IPO-62/63 **逐值一致**
  （sort4=30亿档、sort5=40亿档）——四方（Excel/快照/法条/正式库）一致，
  **无快照滞后**；前期「快照缺行」的判断系误读，特此更正。

用法：
    python scripts/bridge_midas_aliases.py            # 生成
    python scripts/bridge_midas_aliases.py --check    # 校验幂等（CI 用）
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.export_midas_snapshot import SORT_GROUP, BOARD_MAP, CTYPE_MAP  # noqa: E402

SRC = REPO / "calibration" / "l1a" / "output" / "candidates_amended.jsonl"
OUT = REPO / "calibration" / "l1a" / "output" / "candidates_bridged.jsonl"
XLSX = REPO / "raw" / "preset_xlsx_20261110" / "03_standard_rules_table.txt"


def parse_excel() -> dict[tuple[str, str], list[str]]:
    """Excel 规则表 → {(board, ctype): [IPO-xx 按出现顺序]}（组内序 = midas sort）。"""
    suites: dict[tuple[str, str], list[str]] = {}
    for line in XLSX.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("====="):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        code = parts[1]
        if not code.startswith("IPO-"):
            continue
        boards = [b for b in parts[2].split() if b in BOARD_MAP]
        ctypes = [c for c in parts[3].split() if c in CTYPE_MAP]
        for b in boards:
            for c in ctypes:
                suites.setdefault((BOARD_MAP[b], CTYPE_MAP[c]), []).append(code)
    return suites


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="校验幂等（CI 用）")
    args = ap.parse_args()

    records = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    excel = parse_excel()

    # (board, ctype, group_no) → 该组 sorts 升序（SORT_GROUP 权威）
    group_sorts: dict[tuple[str, str, int], list[int]] = defaultdict(list)
    for (b, c), sort_map in SORT_GROUP.items():
        for sort, gno in sort_map.items():
            group_sorts[(b, c, gno)].append(sort)
    for k in group_sorts:
        group_sorts[k].sort()

    # 每 group 的 branch_id 有序列表（跨板镜像共享 branch_id）
    group_branches: dict[str, list[str]] = {}
    for r in records:
        ctx = r["context"]
        if ctx.get("role") == "branch" and ctx.get("branch_id"):
            bids = group_branches.setdefault(ctx["group_id"], [])
            if ctx["branch_id"] not in bids:
                bids.append(ctx["branch_id"])
    for bids in group_branches.values():
        bids.sort()

    assigned = 0
    unassigned: list[str] = []
    collapse_notes: list[str] = []
    for r in records:
        ctx = r["context"]
        if ctx.get("role") != "branch" or not ctx.get("branch_id"):
            continue
        gno = ctx.get("group_no")
        if gno is None:
            continue
        codes = excel.get((ctx["board"], ctx["company_type"]), [])
        sorts = group_sorts.get((ctx["board"], ctx["company_type"], gno), [])
        ipos = [codes[s - 1] for s in sorts if s <= len(codes)]
        if not ipos:
            continue
        bids = sorted(group_branches.get(ctx["group_id"], []))
        if ctx["branch_id"] not in bids:
            continue
        k = bids.index(ctx["branch_id"])
        if len(bids) == len(ipos):
            ctx["midas_aliases"] = [ipos[k]]
            assigned += 1
        elif len(bids) == 1:
            # R2-a collapse：多 sort 收敛单支路 → 全部 IPO 码挂同一支路
            ctx["midas_aliases"] = list(ipos)
            assigned += 1
            collapse_notes.append(f"{ctx['group_id']}: sorts {sorts} → 单支路，alias {ipos}")
        elif k < len(ipos):
            ctx["midas_aliases"] = [ipos[k]]
            assigned += 1
            extra = ipos[len(bids):]
            if extra:
                unassigned.append(f"{ctx['group_id']}: 支路 {len(bids)} < sort {len(ipos)}，"
                                  f"无支路承接 {extra}（豁免语义/判断行，见黄金集 gaps）")

    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != body:
            print("bridged 候选库不是最新（跑 scripts/bridge_midas_aliases.py）", file=sys.stderr)
            return 1
        print("bridged 候选库与生成器一致")
        return 0

    OUT.write_text(body, encoding="utf-8")
    with_alias = sum(1 for r in records if r["context"].get("midas_aliases"))
    print(f"写入 {OUT.relative_to(REPO)}（{len(records)} 条候选，{with_alias} 条挂 IPO 别名，"
          f"{assigned} 条支路对号）")

    print("\n支路 → IPO 对号表：")
    seen = set()
    for r in records:
        ctx = r["context"]
        if not ctx.get("midas_aliases"):
            continue
        key = (ctx["group_id"], ctx["branch_id"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  {ctx['group_id']:34s} {ctx['branch_id']:36s} → {ctx['midas_aliases']}")
    for n in collapse_notes:
        print(f"  [collapse] {n}")
    for u in unassigned:
        print(f"  [unassigned] {u}")
    return 0


if __name__ == "__main__":
    sys.exit(main())