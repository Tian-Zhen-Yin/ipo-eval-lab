"""M7 CLI（设计 0004 §5 三命令的逻辑面；#7-E3：`-m` 模块调用形态）。

T1 交付 `eval run`；`rulebook lint` 已有独立入口（python -m ipo_eval_lab.rulebook），
`calibrate run` 随 M1 实现期加入。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .engine import RunContext
from .engine import EngineError, RunTarget, run_eval


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

    _print_summary(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
