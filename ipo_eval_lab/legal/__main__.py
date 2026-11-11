"""
上市法规原文库 CLI（设计 0009 §5.3）

用法：
    python -m ipo_eval_lab.legal extract \
        --pdf-path raw/legal_docs_20261111/sse_star_2026.pdf \
        --law-id sse_star_2026 \
        --title "上海证券交易所科创板股票上市规则" \
        --effective-from 2024-04-30 \
        --output rulebook/source_texts/sse_star_2026.yaml
"""

import argparse
import sys
from pathlib import Path

import yaml

from .extract import ArticleExtractor
from .models import SourceDoc


def main():
    parser = argparse.ArgumentParser(
        description="上市法规原文库 CLI（设计 0009）"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # extract 子命令
    extract_parser = subparsers.add_parser("extract", help="从 PDF 提取条文")
    extract_parser.add_argument(
        "--pdf-path", required=True, type=Path, help="PDF 文件路径"
    )
    extract_parser.add_argument(
        "--law-id", required=True, help="法规唯一标识，如 sse_star_2026"
    )
    extract_parser.add_argument(
        "--title", required=True, help="法规标题"
    )
    extract_parser.add_argument(
        "--effective-from", required=True, help="生效日期，YYYY-MM-DD"
    )
    extract_parser.add_argument(
        "--output", required=True, type=Path, help="输出 YAML 文件路径"
    )

    args = parser.parse_args()

    if args.command == "extract":
        extract_and_save(args)
    else:
        parser.print_help()
        sys.exit(1)


def extract_and_save(args):
    """提取条文并保存为 YAML"""
    print(f"提取条文: {args.pdf_path}")

    # 提取
    extractor = ArticleExtractor(
        pdf_path=args.pdf_path,
        law_id=args.law_id,
        title=args.title,
        effective_from=args.effective_from,
    )
    source_doc, warnings = extractor.extract()

    print(f"提取完成: {len(source_doc.articles)} 条条文, checksum={source_doc.checksum[:20]}...")
    if warnings:
        print(f"⚠ 完整性告警 {len(warnings)} 条:")
        for w in warnings[:10]:
            print(f"  - {w}")
        if len(warnings) > 10:
            print(f"  ... 其余 {len(warnings) - 10} 条略")
    else:
        print("完整性校验: 条款号连续，无告警")

    # 保存 YAML
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        yaml.dump(
            source_doc.model_dump(mode="python"),
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"已保存: {args.output}")


if __name__ == "__main__":
    main()
