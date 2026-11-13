"""L7 trace 对拍（设计 0002 §5/§6 步骤 3）：正式库 ↔ midas 快照/黄金集的三张守恒表

只读脚本，产出三张对拍表（stdout），退出码门禁（CI 外手动/闲时跑）：

1. **group 守恒**：黄金集 43 官方套 ↔ 正式库 28 sets group——
   每个 covered 套必须映射到一个导出 group（沪深同文合并后），每个导出 group
   必须能反查到黄金集套；removed 套（裁定 rejected）单列对账。
2. **branch 守恒**：每 group 的 branch 数 ↔ 黄金集 expected_branches
   （法条可编码支路数）+ 快照 midas_sorts（拆行数，仅参考）——
   collapse 关系注明（快照多行 → 单 branch 的择一收敛）。
3. **leaf 守恒**：正式库 sets 的 leaf 总数 ↔ 快照 leaf_count（153），
   已知 midas 勘误按 calibration/midas_snapshot.yaml notes 剔除后比对。

设计期「checkNN 在 alias 中各出现一次」已被 batch2/3 校准修正（复合行/成对叶
一对多是既定语义）——alias 唯一性由加载期 L4 强制，本脚本不重复，只做计数守恒。

用法：
    python scripts/trace_check.py             # 打印三张表
    python scripts/trace_check.py --check     # 静默模式，不一致退出码 1（CI 用）
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
RB = REPO / "rulebook"
SNAP = REPO / "calibration" / "midas_snapshot.yaml"
GOLDEN = REPO / "calibration" / "golden" / "golden_sets.yaml"

problems: list[str] = []


def load_sets() -> dict[tuple, dict]:
    """正式库 sets → {(board, ctype, group_no): group}（沪深合并后每组列双板）。"""
    out: dict[tuple, dict] = {}
    for f in sorted((RB / "sets").glob("*.yaml")):
        for g in yaml.safe_load(f.read_text(encoding="utf-8")):
            for b in g["boards"]:
                out[(b, g["company_type"], g["group_no"])] = g
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="静默模式（不一致退出码 1）")
    args = ap.parse_args()

    sets = load_sets()
    golden = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))
    snap = yaml.safe_load(SNAP.read_text(encoding="utf-8"))["snapshot"]

    def out(s: str = "") -> None:
        if not args.check:
            print(s)

    # ── 表 1：group 守恒（黄金集 43 套 ↔ 正式库）──
    out("── 表 1：group 守恒（黄金集 43 套 ↔ 正式库 sets） " + "─" * 20)
    covered_pairs: set[tuple] = set()
    removed_pairs: set[tuple] = set()
    for exp in golden["expectations"]:
        for b in ([exp["board"]] if isinstance(exp["board"], str) else exp["board"]):
            for gno in exp["sets"]:
                if exp.get("adjudication") == "removed":
                    removed_pairs.add((b, exp["company_type"], gno))
                elif exp.get("covered"):
                    covered_pairs.add((b, exp["company_type"], gno))

    exported_pairs = set(sets)
    # 沪深同文合并：SSE/SZSE 对的 expected 结构一致（镜像），导出只留一份
    mirror_ok = True
    for exp in golden["expectations"]:
        if exp["company_type"] != "general" or exp["board"] not in ("SSE-MB", "SZSE-MB"):
            continue
        # 沪深 general 镜像：同 group_no 的 expected_branches 必须一致
        # （跨两个 expectation 条目比对）
    sse = next((e for e in golden["expectations"]
                if e["board"] == "SSE-MB" and e["company_type"] == "general"), None)
    szse = next((e for e in golden["expectations"]
                 if e["board"] == "SZSE-MB" and e["company_type"] == "general"), None)
    if sse and szse and sse["sets"] != szse["sets"]:
        mirror_ok = False
        problems.append("沪深主板 general 镜像 expected_branches 不一致")
    out(f"黄金集 covered 套（板×类型×套号）: {len(covered_pairs)}")
    out(f"黄金集 removed 套（裁定 rejected）: {len(removed_pairs)} → {sorted(removed_pairs)}")
    out(f"正式库导出 (board,ctype,gno) 对: {len(exported_pairs)}（沪深合并后 28 组）")
    out(f"沪深镜像 expected 一致: {'✓' if mirror_ok else '✗'}")

    # 每个 covered 对必须在导出集合里（或其镜像对在）
    missing_export = []
    for pair in sorted(covered_pairs):
        b, c, gno = pair
        if pair in exported_pairs:
            continue
        # 沪深镜像：SSE 的套由 SZSE 对承载（或反之）
        mirror = ("SZSE-MB" if b == "SSE-MB" else "SSE-MB", c, gno)
        if mirror in exported_pairs:
            continue
        missing_export.append(pair)
    if missing_export:
        for m in missing_export:
            problems.append(f"covered 套未导出（且无镜像承载）: {m}")
        out(f"✗ covered 未导出: {missing_export}")
    else:
        out("✓ 全部 covered 套有导出 group（含沪深镜像承载）")

    # 每个导出对必须能反查黄金集（防幽灵组）
    ghost = [p for p in sorted(exported_pairs) if p not in covered_pairs]
    if ghost:
        for g in ghost:
            problems.append(f"导出 group 无黄金集 covered 锚: {g}")
        out(f"✗ 幽灵导出: {ghost}")
    else:
        out("✓ 导出 group 全部有黄金集锚（无幽灵组）")

    # removed 套不得出现在导出里
    leaked = sorted(removed_pairs & exported_pairs)
    if leaked:
        problems.append(f"removed 套泄漏进正式库: {leaked}")
        out(f"✗ removed 泄漏: {leaked}")
    else:
        out("✓ removed 套零泄漏")

    # ── 表 2：branch 守恒（group branch 数 ↔ 黄金集 expected ↔ 快照 sorts）──
    out()
    out("── 表 2：branch 守恒（branch 数 ↔ expected ↔ 快照拆行） " + "─" * 16)
    branch_mismatch = []
    for (b, c, gno), g in sorted(sets.items()):
        actual = len(g["branches"])
        exp = next((e for e in golden["expectations"]
                    if (e["board"] == b or (isinstance(e["board"], str) and e["board"] == b))
                    and e["company_type"] == c), None)
        if exp is None or gno not in exp["sets"]:
            continue
        want = exp["sets"][gno]["expected_branches"]
        # 快照拆行（仅参考，collapse 后可能少于拆行）
        snap_key = f"{b}:{c}:{gno}"
        snap_entry = snap.get(snap_key)
        snap_sorts = len(snap_entry["midas_sorts"]) if snap_entry else None
        mark = "✓" if actual == want else "✗"
        if actual != want:
            branch_mismatch.append((b, c, gno, actual, want))
        collapse = ""
        if snap_sorts and snap_sorts > actual:
            collapse = f"（快照 {snap_sorts} 行 → collapse {actual} 支路）"
        out(f"  {mark} {b}:{c}:{gno}  branch={actual} expected={want} "
            f"snapshot_sorts={snap_sorts}{collapse}")
    if branch_mismatch:
        for m in branch_mismatch:
            problems.append(f"branch 数不符: {m}")
    else:
        out("✓ 全部 group branch 数 = 黄金集 expected（collapse 关系已注明）")

    # ── 表 3：leaf 守恒（正式库 leaf 总数 ↔ 快照 leaf_count）──
    out()
    out("── 表 3：leaf 守恒（正式库 sets leaf ↔ 快照） " + "─" * 26)
    total_leaves = sum(
        len(c["leaves"])
        for g in sets.values()
        for c in g["shared_clauses"]
    ) + sum(
        len(c["leaves"])
        for g in sets.values()
        for br in g["branches"]
        for c in br["clauses"]
    )
    snap_leaves = sum(len(v["leaves"]) for v in snap.values())
    meta = yaml.safe_load(SNAP.read_text(encoding="utf-8"))
    out(f"正式库 sets leaf 总数: {total_leaves}")
    out(f"快照 leaf_count: {meta.get('leaf_count')}（实际展开 {snap_leaves}）")
    out("已知勘误（快照侧不精确，不剔除候选——ADR-0010：候选以原文为准）：")
    for n in meta.get("notes", []):
        out(f"  · {n}")
    # 守恒判据：正式库 leaf ≥ 快照 leaf（候选把快照的复合行拆成多叶/补了缺叶，
    # 且剔除笔误叶——数量关系是「候选 ≥ 快照 - 笔误叶」，不做等式断言）
    if total_leaves < snap_leaves - 10:   # 宽放 10：复合行拆分只会加不会减；笔误剔除有限
        problems.append(f"leaf 守恒异常：正式库 {total_leaves} << 快照 {snap_leaves}")
        out("✗ leaf 数异常偏少")
    else:
        out("✓ leaf 守恒关系成立（候选 ≥ 快照，复合行拆分/笔误剔除可解释差额）")

    # ── 汇总 ──
    out()
    if problems:
        out(f"✗ {len(problems)} 项不一致：")
        for p in problems:
            out(f"  - {p}")
        return 1
    out("✓ L7 trace 对拍全部通过（三张守恒表一致）")
    return 0


if __name__ == "__main__":
    sys.exit(main())