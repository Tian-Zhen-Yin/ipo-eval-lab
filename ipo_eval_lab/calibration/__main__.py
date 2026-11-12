"""
M1 校准管线 CLI 入口

用法：
    python -m ipo_eval_lab.calibration run --candidates cand.jsonl --as-of 2026-11-11
    python -m ipo_eval_lab.calibration run --candidates cand.jsonl \
        --l2-judgments l2.jsonl --as-of 2026-11-11 --output results/calibration
    python -m ipo_eval_lab.calibration check --candidates cand.jsonl --as-of 2026-11-11
    python -m ipo_eval_lab.calibration signoff --candidates cand.jsonl \
        --l2-judgments l2.jsonl --as-of 2026-11-12 --output results/calibration
    python -m ipo_eval_lab.calibration sign --key SSE-MB:cn_main_g1_c1 \
        --decision accepted --reviewer zhang --reason "原文逐字核对一致"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def cmd_run(args) -> int:
    from .pipeline import calibrate_run

    root = Path(args.root)
    report = calibrate_run(
        as_of_date=args.as_of,
        candidates_path=Path(args.candidates),
        l2_judgments_path=Path(args.l2_judgments) if args.l2_judgments else None,
        output_dir=Path(args.output),
        rulebook_dir=root / "rulebook",
        anchor_normalization_path=root / "config" / "anchor_normalization.yaml",
        snapshot_path=root / "calibration" / "midas_snapshot.yaml",
    )

    print(f"批次 {report.batch_id} 完成")
    print(f"  候选条文：{report.total_clauses}")
    print(f"  L0 通过：{report.passed_l0}  L1b：{report.passed_l1b}  "
          f"L2：{report.passed_l2}  L3：{report.passed_l3}")
    print(f"  候选库：{report.candidates_written} 条   人工队列：{report.review_queue_written} 条")
    print(f"  报告：{args.output}/report.md")
    return 0


def cmd_check(args) -> int:
    from .pipeline import load_candidates
    from .l0_gate import run_l0_gate

    candidates = load_candidates(Path(args.candidates))
    if not candidates:
        print("无候选规则（文件为空或不存在）", file=sys.stderr)
        return 1

    results = run_l0_gate(candidates, args.as_of, Path(args.root) / "rulebook")
    passed = [r for r in results if r.status.value == "pass"]
    failed = [r for r in results if r.status.value == "fail"]

    print(f"L0 检查：{len(results)} 条 | 通过 {len(passed)} | 拦截 {len(failed)}")
    for r in failed:
        print(f"  ✗ {r.clause_id} [{r.failure.check_code}] {r.failure.reason}")
    return 0 if not failed else 1


def _run_gates(args) -> tuple:
    """跑四道闸，返回 (candidates, l0, l1b, l2, l3) 结果表。

    与 pipeline.calibrate_run 同一套闸门——签核队列的分层依据必须与校准批次
    的判定完全一致（同一份 L0/L1b/L2/L3 结果），否则会出现「批次说通过、
    队列说必核」的口径分裂。故此处复用同一实现，不另写一套。
    """
    from .pipeline import load_candidates, load_l2_judgments
    from .l0_gate import run_l0_gate
    from .l1b_gate import run_l1b_gate
    from .l2_gate import run_l2_gate_offline
    from .l3_gate import run_l3_gate
    from .models import GateStatus

    root = Path(args.root)
    candidates = load_candidates(Path(args.candidates))

    def key(c):
        return (c.context.board, c.clause_id)

    l0 = {key(c): r for c, r in zip(candidates, run_l0_gate(candidates, args.as_of, root / "rulebook"))}
    l0_pass = [c for c in candidates if l0[key(c)].status == GateStatus.PASS]

    l1b = {}
    if l0_pass:
        for c, res in zip(l0_pass, run_l1b_gate(l0_pass, root / "config" / "anchor_normalization.yaml")):
            l1b[key(c)] = res
    l1b_pass = [c for c in l0_pass if l1b.get(key(c)) and l1b[key(c)].status == GateStatus.PASS]

    l2 = {}
    if l1b_pass and args.l2_judgments:
        judgments = load_l2_judgments(Path(args.l2_judgments))
        for c, res in zip(l1b_pass, run_l2_gate_offline(l1b_pass, judgments, root / "rulebook")):
            l2[key(c)] = res

    l3 = {}
    if l1b_pass:
        l3_list, _ = run_l3_gate(l1b_pass, root / "calibration" / "midas_snapshot.yaml", root / "rulebook")
        l3 = {key(c): r for c, r in zip(l1b_pass, l3_list)}

    return candidates, l0, l1b, l2, l3


def cmd_signoff(args) -> int:
    """构造签核队列（黄金集必核 + 风险分层抽检）。"""
    from .signoff import (
        build_signoff_queue, extract_gate_facts, load_golden, write_queue,
    )

    root = Path(args.root)
    candidates, l0, l1b, l2, l3 = _run_gates(args)
    gate_status, l3_by_set = extract_gate_facts(candidates, l0, l1b, l2, l3)

    golden = load_golden(root / "calibration" / "golden" / "golden_sets.yaml")
    # 候选转回原始 dict（build_signoff_queue 按 dict 读 context/clause/source）
    raw = [c.model_dump(mode="json") for c in candidates]
    items, adjudications = build_signoff_queue(
        raw, golden, gate_status, l3_by_set,
        spot_check_rate=args.spot_check_rate, seed=args.seed,
    )

    out_dir = Path(args.output)
    stats = write_queue(items, adjudications, out_dir, args.as_of)

    print("签核队列已生成")
    print(f"  候选条款：{stats['total']}")
    print(f"  条款级待签：{stats['pending']}")
    for tier, n in sorted(stats["by_tier"].items()):
        print(f"  档 {tier}：{n} 条")
    print(f"  套级裁定待办：{stats['adjudications']} 项")
    print(f"  队列目录：{stats['queue_dir']}")
    return 0


def cmd_sign(args) -> int:
    """记录一次签核或裁定（append-only）。"""
    from .signoff import SignoffRecord, SignoffStatus, append_record

    decision = SignoffStatus(args.decision)
    if decision is SignoffStatus.PENDING:
        print("决策不能是 pending", file=sys.stderr)
        return 1

    amendment = json.loads(args.amendment) if args.amendment else None
    if amendment is not None and not isinstance(amendment, dict):
        print("--amendment 须为 JSON 对象", file=sys.stderr)
        return 1

    record = SignoffRecord(
        key=args.key,
        decision=decision,
        reviewer=args.reviewer,
        at=datetime.now().isoformat(timespec="seconds"),
        reason=args.reason,
        amendment=amendment,
        tier=args.tier,
    )
    path = Path(args.records)
    append_record(record, path)
    print(f"已记录签核：{args.key} → {decision.value}（记录于 {path}）")
    return 0


def cmd_adjudicate(args) -> int:
    """记录一次套级裁定（append-only）。

    裁定结论用 amendment 承载（confirmed → 记法律依据；rejected → 记移除理由）。
    """
    from .signoff import SignoffRecord, SignoffStatus, SetAdjudicationStatus, append_record

    status = SetAdjudicationStatus(args.status)
    record = SignoffRecord(
        key=args.key,
        decision=SignoffStatus("amended" if status is SetAdjudicationStatus.CONFIRMED
                               else "rejected"),
        reviewer=args.reviewer,
        at=datetime.now().isoformat(timespec="seconds"),
        reason=args.reason,
        amendment={"adjudication_status": status.value},
        tier="B",
    )
    path = Path(args.records)
    append_record(record, path)
    print(f"已记录套级裁定：{args.key} → {status.value}（记录于 {path}）")
    return 0


def cmd_export_official(args) -> int:
    """把已签核条款导出为正式规则库（ADR-0005：正式库只能由人工签核产生）。"""
    from .export_official import export_official_rulebook

    report = export_official_rulebook(
        candidates_path=Path(args.candidates),
        records_path=Path(args.records),
        out_dir=Path(args.out),
        dry_run=args.dry_run,
    )
    prefix = "[试运行] " if args.dry_run else ""
    print(f"{prefix}已导出 {report.exported_clauses} 条已签核条款")
    for f in report.exported_files:
        print(f"  {f}")
    if report.skipped_sets:
        print(f"  跳过 {len(report.skipped_sets)} 个套（条款未全部签核）：")
        for s in report.skipped_sets:
            print(f"    {s['board']}/{s['company_type']} 套 {s['group_no']}："
                  f"待签 {len(s['pending_clause_keys'])} 条")
    if report.rejected_clauses:
        print(f"  含被打回条款的套 {len(report.rejected_clauses)} 条（须重走签核）：")
        for k in report.rejected_clauses:
            print(f"    {k}")
    return 0


def cmd_signoff_status(args) -> int:
    """查签核进度（队列 vs 记录）。"""
    from .signoff import apply_records, load_records

    root = Path(args.root)
    out_dir = Path(args.output)
    items_path = out_dir / "signoff-queue" / "items.jsonl"
    if not items_path.exists():
        print(f"未找到队列：{items_path}（先跑 signoff 子命令）", file=sys.stderr)
        return 1

    import json
    from .signoff import SignoffItem, SignoffStatus, SignoffTier

    items = []
    with items_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                it = SignoffItem(
                    clause_id=d["clause_id"], board=d["board"],
                    company_type=d["company_type"], group_no=d.get("group_no"),
                    tier=SignoffTier(d["tier"]), status=SignoffStatus(d["status"]),
                    reasons=d.get("reasons", []),
                    source_article=d.get("source_article", ""),
                    quote=d.get("quote", ""), rendered=d.get("rendered", ""),
                    l3_category=d.get("l3_category", ""),
                    gates=d.get("gates", {}), notes=d.get("notes", ""),
                )
                items.append(it)

    records = load_records(Path(args.records))
    apply_records(items, records)

    by_tier: dict[str, dict[str, int]] = {}
    for it in items:
        b = by_tier.setdefault(it.tier.value, {"total": 0, "pending": 0, "accepted": 0,
                                                "rejected": 0, "amended": 0, "auto": 0})
        b["total"] += 1
        if it.status is SignoffStatus.ACCEPTED and "自动免签" in it.notes:
            # 自动免签 ≠ 人工通过：抽检未落中的 C 档条款。混进「通过」会让
            # 「已签多少」看起来比真实人工签核量高——那是审核工作量口径的失真。
            b["auto"] += 1
            continue
        b[it.status.value] = b.get(it.status.value, 0) + 1

    print("签核进度")
    for tier in sorted(by_tier):
        b = by_tier[tier]
        print(f"  档 {tier}：共 {b['total']}｜待签 {b['pending']}｜人核通过 {b['accepted']}"
              f"｜修改通过 {b['amended']}｜打回 {b['rejected']}｜自动免签 {b['auto']}")
    pend = sum(b["pending"] for b in by_tier.values())
    print(f"  合计待签：{pend}／{len(items)}")

    # 套级裁定进度
    adj_path = out_dir / "signoff-queue" / "adjudications.jsonl"
    if adj_path.exists():
        ads = []
        with adj_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    ads.append(json.loads(line))
        adj_status: dict[str, str] = {}
        for r in records:
            if r.tier == "B" and r.amendment:
                adj_status[r.key] = r.amendment.get("adjudication_status", "")
        pending_adj = [a for a in ads if a["key"] not in adj_status]
        print(f"  套级裁定：共 {len(ads)}｜待裁 {len(pending_adj)}")
        for a in ads:
            st = adj_status.get(a["key"], "pending")
            mark = "✓" if st != "pending" else "·"
            print(f"    {mark} {a['key']} → {st}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ipo_eval_lab.calibration")
    parser.add_argument("--root", default=".", help="仓库根目录")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行完整校准批次")
    p_run.add_argument("--candidates", required=True, help="候选规则 JSONL（L1a 产出）")
    p_run.add_argument("--l2-judgments", help="L2 预计算判定 JSONL（agent 会话产出）")
    p_run.add_argument("--as-of", required=True, help="as_of 日期 YYYY-MM-DD")
    p_run.add_argument("--output", default="results/calibration", help="输出目录")
    p_run.set_defaults(func=cmd_run)

    p_check = sub.add_parser("check", help="只跑 L0 闸门")
    p_check.add_argument("--candidates", required=True)
    p_check.add_argument("--as-of", required=True)
    p_check.set_defaults(func=cmd_check)

    p_signoff = sub.add_parser("signoff", help="构造人工签核队列（黄金集必核 + 风险分层抽检）")
    p_signoff.add_argument("--candidates", required=True)
    p_signoff.add_argument("--l2-judgments")
    p_signoff.add_argument("--as-of", required=True)
    p_signoff.add_argument("--output", default="results/calibration")
    p_signoff.add_argument("--spot-check-rate", type=float, default=0.20,
                           help="C 档（闸门全绿且 midas 一致）抽检比例，默认 0.20")
    p_signoff.add_argument("--seed", default="2026-11-12",
                           help="抽检随机种子（同 seed 必得同一批；换 seed 换批）")
    p_signoff.set_defaults(func=cmd_signoff)

    p_sign = sub.add_parser("sign", help="记录一次签核（append-only）")
    p_sign.add_argument("--key", required=True, help="条目键：board:clause_id")
    p_sign.add_argument("--decision", required=True,
                        choices=["accepted", "rejected", "amended"])
    p_sign.add_argument("--reviewer", required=True, help="签核人")
    p_sign.add_argument("--reason", default="", help="签核理由（可追）")
    p_sign.add_argument("--tier", default="", help="档位（A/B/C，留档用）")
    p_sign.add_argument("--amendment", help="修改内容 JSON（decision=amended 时用）")
    p_sign.add_argument("--records", default="results/calibration/signoff-records.jsonl",
                        help="签核记录文件（append-only）")
    p_sign.set_defaults(func=cmd_sign)

    p_adj = sub.add_parser("adjudicate", help="记录一次套级裁定（B 档，append-only）")
    p_adj.add_argument("--key", required=True,
                       help="套级裁定键：board:company_type:group_no:question")
    p_adj.add_argument("--status", required=True, choices=["confirmed", "rejected"])
    p_adj.add_argument("--reviewer", required=True)
    p_adj.add_argument("--reason", default="", help="裁定理由与法律依据（可追）")
    p_adj.add_argument("--records", default="results/calibration/signoff-records.jsonl")
    p_adj.set_defaults(func=cmd_adjudicate)

    p_status = sub.add_parser("signoff-status", help="查签核进度")
    p_status.add_argument("--output", default="results/calibration")
    p_status.add_argument("--records", default="results/calibration/signoff-records.jsonl")
    p_status.set_defaults(func=cmd_signoff_status)

    p_exp = sub.add_parser("export-official",
                           help="把已签核条款导出为正式规则库（未签核一律不导出）")
    p_exp.add_argument("--candidates", required=True, help="候选库 JSONL")
    p_exp.add_argument("--records", default="results/calibration/signoff-records.jsonl",
                       help="签核记录 JSONL")
    p_exp.add_argument("--out", default="rulebook/sets", help="正式库输出目录")
    p_exp.add_argument("--dry-run", action="store_true", help="只出报告不落盘")
    p_exp.set_defaults(func=cmd_export_official)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
