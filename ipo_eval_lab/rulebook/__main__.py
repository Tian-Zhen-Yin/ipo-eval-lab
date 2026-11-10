"""CLI：规则库 lint 入口。

用法：python -m ipo_eval_lab.rulebook [path] [--strict]
"""
from __future__ import annotations

import argparse
import sys

from pydantic import ValidationError

from .loader import RulebookLintError, load_rulebook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ipo_eval_lab.rulebook", description="规则库 lint（设计 0002）"
    )
    parser.add_argument("path", nargs="?", default="rulebook", help="规则库目录（默认 ./rulebook）")
    parser.add_argument(
        "--strict", action="store_true", help="全局严格模式：L2 组合覆盖缺口视为错误"
    )
    args = parser.parse_args(argv)

    try:
        result = load_rulebook(args.path, strict_global=args.strict)
    except RulebookLintError as e:
        print("❌ lint 失败：")
        for m in e.messages:
            print(f"  - {m}")
        return 1
    except ValidationError as e:
        print("❌ lint 失败（模型断言）：")
        print(e)
        return 1

    rb = result.rulebook
    n_branches = sum(len(g.branches) for g in rb.groups)
    n_clauses = sum(len(g.shared_clauses) + len(b.clauses) for g in rb.groups for b in g.branches)
    print(f"✅ {rb.meta.rulebook_version}：metrics {len(rb.metrics)} / items {len(rb.items)} "
          f"/ laws {len(rb.laws)} / groups {len(rb.groups)} / branches {n_branches} / clauses {n_clauses}")
    if result.warnings:
        print("⚠️ 警告（strict 模式下将报错）：")
        for m in result.warnings:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
