"""M7 CLI（设计 0004 §5 三命令的逻辑面；#7-E3：`-m` 模块调用形态）。

T1 交付 `eval run`；`rulebook lint` 已有独立入口（python -m ipo_eval_lab.rulebook），
`calibrate run` 随 M1 实现期加入。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .engine import RunContext
from .engine import EngineError, RunTarget, run_eval
from .engine.result import state_counts
from .ingest.source import data_source_of


def _print_summary(ctx: RunContext) -> None:
    run = ctx.run
    rp = run["report_period"]
    years = rp["fiscal_years"]
    ap = run["applicant_profile"]
    industry = f"/{ap['industry']}" if ap["industry"] else ""
    print("run 坐标")
    print(f"  company={run['company_id']}  as_of={run['as_of_date']}")
    print(f"  report_period=FY{years[0]}-{years[-1]}  audit={rp['audit_status']}/{rp['audit_opinion']}")
    print(f"  applicant={ap['company_type']}/{ap['profit_status']}{industry}")
    print(f"  target={'全部适用套' if run['target']['boards'] is None and run['target']['sets'] is None else run['target']}")

    versions = run["applied_rule_versions"]
    rb_version = versions[0]["rulebook_version"] if versions else "（无生效套）"
    print(f"规则版本 {rb_version}（生效 {len(versions)} 套）")

    sel = ctx.selection
    print(f"适用套（{len(sel.applicable)}）：")
    for g in sel.applicable:
        print(f"  - {g.group_id}  {g.display}  effective_from={g.effective_from.isoformat()}")
    if sel.not_applicable:
        print(f"不适用（{len(sel.not_applicable)}，出分母保留）：")
        for n in sel.not_applicable:
            print(f"  - {n['group_id']}  {n['reason']}")
    if sel.excluded_by_asof:
        print(f"as_of 排除（{len(sel.excluded_by_asof)}）：")
        for n in sel.excluded_by_asof:
            print(f"  - {n['group_id']}  {n['reason']}")


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",")] if value else None


def _print_result_summary(ctx: RunContext) -> None:
    """终端摘要（票 08）：五态计数 + 每套一行结论 + blockers。

    呈现禁令（CONTEXT §2.8 / 设计 0007 §3.1）：不出现总分 / 维度分 / 雷达图；
    progress/coverage 成对展示（双指标），coverage<100 时标注「已评估部分」。
    """
    result = ctx.result
    gap = result["layers"]["gap"]
    path = result["layers"]["path"]
    counts = state_counts(ctx.facts)
    print("―― 测评摘要 ――")
    print(
        "检查叶计数："
        + " ".join(f"{s}={counts[s]}" for s in ("met", "not_met", "indeterminate", "needs_review", "not_applicable"))
    )
    sets_by_gid = {s["group_id"]: s for s in gap["sets"]}
    rec = set(path["recommendation"]) | set(path["alternatives"])
    for s in gap["sets"]:
        line = (
            f"  {s['group_id']}  {s['outcome']}  blockers={','.join(s['blockers']) or '无'}"
            f"  progress {s['progress']}/coverage {s['coverage']}%"
        )
        if s["coverage"] < 100:
            line += "（进度代表已评估部分）"
        if s["group_id"] in rec:
            line += "  ★" if s["group_id"] in path["recommendation"] else "  ☆(备选)"
        print(line)
    if path["recommendation"]:
        print(f"推荐：{'、'.join(path['recommendation'])}")
    elif path["alternatives"]:
        print(f"推荐：无；备选（带不确定）：{'、'.join(path['alternatives'])}")
    else:
        print("推荐：无——工具宁可说清差在哪，不硬推一个套（理由见 excluded）")


def _write_report(ctx: RunContext, path: Path) -> None:
    """result.json 落盘（票 08：--report；results/ 不入 git，#7-E5）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ctx.result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"result.json → {path}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ipo-eval-lab", description="IPO 条件测评（本地实验）")
    sub = parser.add_subparsers(dest="command", required=True)

    eval_p = sub.add_parser("eval", help="测评")
    eval_run = eval_p.add_subparsers(dest="action", required=True)
    run_p = eval_run.add_parser("run", help="一次测评 run")
    run_p.add_argument("--company", required=True, help="公司 ID（fixtures/companies/ 下目录名）")
    run_p.add_argument("--as-of", default=None, help="YYYY-MM-DD；缺省=当日（写入 run.as_of_date）")
    run_p.add_argument("--boards", default=None, help="逗号分隔板块过滤；缺省=全部适用套")
    run_p.add_argument("--sets", default=None, help="逗号分隔 group_id 过滤；缺省=全部适用套")
    run_p.add_argument("--rulebook", default="rulebook")
    run_p.add_argument("--fixtures", default="fixtures")
    run_p.add_argument(
        "--report",
        nargs="?",
        const=None,
        default=False,
        help="落 result.json；不带值 → results/<company>_<asof>.json（results/ 不入 git，#7-E5）",
    )

    args = parser.parse_args(argv)

    fixtures = Path(args.fixtures)
    company_dir = fixtures / "companies" / args.company
    try:
        ctx = run_eval(
            company_dir=company_dir,
            rulebook_dir=Path(args.rulebook),
            fixtures_root=fixtures,
            as_of=args.as_of,
            target=RunTarget(boards=_csv(args.boards), sets=_csv(args.sets)),
        )
    except (EngineError, FileNotFoundError) as e:
        print(f"[eval run] 失败：{e}", file=sys.stderr)
        raise SystemExit(2) from e

    ctx.result["data_source"] = data_source_of(company_dir)  # ADR-0013 来源打标
    _print_summary(ctx)
    _print_result_summary(ctx)
    if args.report is not False:  # False=未给 --report；None=给了但没带值 → 缺省路径
        report_path = (
            Path(args.report)
            if args.report
            else Path("results") / f"{args.company}_{ctx.run['as_of_date']}.json"
        )
        _write_report(ctx, report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
