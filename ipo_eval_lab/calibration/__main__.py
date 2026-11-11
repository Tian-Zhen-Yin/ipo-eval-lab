"""
M1 校准管线 CLI 入口

用法：
    python -m ipo_eval_lab.calibration run --candidates cand.jsonl --as-of 2026-11-11
    python -m ipo_eval_lab.calibration run --candidates cand.jsonl \
        --l2-judgments l2.jsonl --as-of 2026-11-11 --output results/calibration
    python -m ipo_eval_lab.calibration check --candidates cand.jsonl --as-of 2026-11-11
"""

import argparse
import sys
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
