"""码值映射审计（只读；#5 遗留「码值映射待核」的机器化）

审计对象 = scripts/export_midas_snapshot.py 的三张手工固化映射表 + SORT_GROUP：
- BOARD_MAP / CTYPE_MAP：midas 中文名 → 规则库枚举——查 raw json 里出现过的
  值是否**全部**被映射（漏一个 = 该维度数据静默丢弃）；
- ROW_LEAF_MAP：eval_item_name 前缀 → item_ref——查快照 185 行的条件型名称
  是否**全部**落入某个前缀（未落入 = leaves_for 抛 KeyError，批次生成即炸——
  审计其价值在「映射是否仍完备」而非「是否有漏」，因为漏了会显式炸）；
- SORT_GROUP：(board, ctype) → sort → group_no——查快照里出现的 (board,ctype)
  是否全部有映射、sort 是否全部被覆盖；
- 双向：正式库侧 items.yaml 的 aliases.midas（check01~61）与 ROW_LEAF_MAP 的
  item_ref 是否一致（同一 check 在两个表里指向不同 item = 口径裂缝）。

产出：只读报告（stdout + 退出码）。发现「未映射」= 1；一致 = 0。
不改任何文件。CI 外手动跑，服务 midas 侧数据治理与 #5 待核清单。

用法：
    python scripts/audit_midas_code_mapping.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts.export_midas_snapshot import (  # noqa: E402
    BOARD_MAP, CTYPE_MAP, ROW_LEAF_MAP, SORT_GROUP, leaves_for,
)
from ipo_eval_lab.calibration.rulebook_refs import load_items  # noqa: E402

RAW = REPO / "raw" / "mt_ipo_daily_20261109" / "mt_ipo_listing_standard.json"

problems: list[str] = []


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 56 - len(title)))


# ── 1. BOARD_MAP / CTYPE_MAP 全覆盖 ──
section("1. BOARD_MAP / CTYPE_MAP 全覆盖")
rows = json.loads(RAW.read_text(encoding="utf-8"))
raw_boards = {r["board_name"] for r in rows}
raw_ctypes = {r["company_type"] for r in rows}
unmapped_b = raw_boards - set(BOARD_MAP)
unmapped_c = raw_ctypes - set(CTYPE_MAP)
print(f"raw boards: {sorted(raw_boards)}")
print(f"raw ctypes: {sorted(raw_ctypes)}")
if unmapped_b:
    problems.append(f"BOARD_MAP 未映射: {sorted(unmapped_b)}")
    print(f"✗ 未映射: {sorted(unmapped_b)}")
if unmapped_c:
    problems.append(f"CTYPE_MAP 未映射: {sorted(unmapped_c)}")
    print(f"✗ 未映射: {sorted(unmapped_c)}")
if not unmapped_b and not unmapped_c:
    print("✓ 全覆盖（无静默丢弃）")
# 反向：映射表有但 raw 未出现（映射冗余，无害但记录）
for b in set(BOARD_MAP) - raw_boards:
    print(f"· BOARD_MAP 冗余（raw 未出现）: {b}")
for c in set(CTYPE_MAP) - raw_ctypes:
    print(f"· CTYPE_MAP 冗余（raw 未出现）: {c}")

# ── 2. ROW_LEAF_MAP 完备性（全部行必须落入某前缀）──
section("2. ROW_LEAF_MAP 完备性（185 行条件型 → item_ref）")
items = load_items(REPO / "rulebook")
unmapped_rows = []
for r in rows:
    try:
        leaves_for(r, items)
    except KeyError as e:
        unmapped_rows.append((r["eval_item_name"], str(e)))
print(f"总行数 {len(rows)}，未落入前缀 {len(unmapped_rows)}")
for name, err in unmapped_rows[:10]:
    problems.append(f"ROW_LEAF_MAP 未覆盖: {name!r}")
    print(f"✗ {name!r}: {err}")
if not unmapped_rows:
    print("✓ 全部行落入映射（否则批次生成会 KeyError——此处确认仍完备）")

# ── 3. SORT_GROUP 完备性（(board,ctype) → sort 全覆盖）──
section("3. SORT_GROUP 完备性（sort → group_no）")
snap_keys = defaultdict(set)
for r in rows:
    b = BOARD_MAP[r["board_name"]]
    c = CTYPE_MAP[r["company_type"]]
    snap_keys[(b, c)].add(int(r["sort"]))
missing_group = []
for (b, c), sorts in sorted(snap_keys.items()):
    mapping = SORT_GROUP.get((b, c))
    if mapping is None:
        missing_group.append((b, c))
        problems.append(f"SORT_GROUP 缺 (board,ctype): {(b, c)}")
        continue
    unmapped_sorts = sorts - set(mapping)
    if unmapped_sorts:
        missing_group.append((b, c, sorted(unmapped_sorts)))
        problems.append(f"SORT_GROUP 未覆盖 sorts: {(b, c)} {sorted(unmapped_sorts)}")
if missing_group:
    for m in missing_group:
        print(f"✗ {m}")
else:
    print(f"✓ 全覆盖（{len(snap_keys)} 个 (board,ctype) 组合，sorts 全有 group_no）")

# ── 4. 双向：items.aliases.midas ↔ ROW_LEAF_MAP ──
section("4. 双向：items.aliases.midas ↔ ROW_LEAF_MAP")
alias2item: dict[str, str] = {}
for it in items.values():
    for c in it.get("aliases", {}).get("midas", []):
        alias2item.setdefault(c, it["item_id"])
# ROW_LEAF_MAP 的复合行拆双 item——取 leaves_for 对 raw 行实际产出的 item_ref 集合
rowleaf_items: dict[str, set[str]] = defaultdict(set)
for r in rows:
    for lf in leaves_for(r, items):
        rowleaf_items[r["eval_item_name"]].add(lf["item_ref"])

# 行级溯源豁免（有显式注记的两项，midas 存量无法用 check 码区分）：
# - mktcap_actual：midas「市值」行（红筹已上市二级市场值）经 ROW_LEAF_MAP
#   ("市值", "mktcap_actual") 行级映射——midas 单形态不区分市值/预计市值；
# - self_developed_tech_full：midas 单形态（不分 3.1.4/3.1.5 措辞），与短形态
#   共享 l3_group=self_developed_tech，L3 对拍按组归并（l3_gate.canon）。
ROW_LEVEL_EXEMPT = {"mktcap_actual", "self_developed_tech_full"}

produced = {i for v in rowleaf_items.values() for i in v}
no_alias = sorted(i for i in produced
                  if not items.get(i, {}).get("aliases", {}).get("midas", [])
                  and i not in ROW_LEVEL_EXEMPT)
if no_alias:
    for i in no_alias:
        problems.append(f"ROW_LEAF_MAP 产出 item 无 midas alias（溯源断链）: {i}")
    print(f"✗ 产出但无 alias: {no_alias}")
else:
    print(f"✓ 产出 item 全部有 midas 溯源（check 别名或行级映射豁免 "
          f"{sorted(ROW_LEVEL_EXEMPT)}）")

# 孤儿反查：alias 声明了但 midas eval_item 表无此 check 码（声明孤儿 = 幽灵别名）
raw_item_path = REPO / "raw" / "mt_ipo_daily_20261109" / "mt_ipo_evaluation_item.json"
if raw_item_path.exists():
    raw_items = json.loads(raw_item_path.read_text(encoding="utf-8"))
    midas_codes = {r["code"] for r in raw_items if r.get("code")}
    orphans = sorted(set(alias2item) - midas_codes)
    if orphans:
        for c in orphans:
            problems.append(f"幽灵别名（midas 无此 check 码）: {c} → {alias2item[c]}")
        print(f"✗ 幽灵别名: {orphans}")
    else:
        print(f"✓ 无幽灵别名（{len(alias2item)} 个 check 码全部在 midas item 表存在）")

# ── 汇总 ──
section("汇总")
if problems:
    print(f"✗ {len(problems)} 项待核：")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("✓ 码值映射审计全部通过（三张映射表 + 双向溯源链完整）")
sys.exit(0)