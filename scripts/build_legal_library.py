"""原文库 → 法条库（rulebook/legal/*.yaml）

法条库是**规则库的证据底座**：每条 clause 的 `law_ref` 指向某部规则的某个条款，
加载期 lint（L4/L6）要能查得到那个条款的原文，否则「阈值从哪来」无从追溯。

原文库（`rulebook/source_texts/*.yaml`）是 2026-11-11 从官方 PDF 抽取的现行版全文，
含全部条款号与正文；法条库此前只是设计 0002 阶段的 **schema 样板**（3 份，
条文写「（简述）」、`calibration_pending: true`），其中两份（深交所创业板、
北交所）根本没有——候选库导出后 L4 立刻拦下一片「指向未定义法条」。

本脚本把法条库从原文库**机械生成**：不改一个字，只做结构转换
（source_texts 的 article → LawArticle，chapter/section 等抽取元数据不进法条库，
它们属于原文库层）。生成物入 git——法条库是正式库的一部分，与 sets/ 同级。

用法：
    python scripts/build_legal_library.py            # 生成
    python scripts/build_legal_library.py --check    # 只校验是否为最新（CI 用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "rulebook" / "source_texts"
OUT = REPO / "rulebook" / "legal"

HEADER = """# 法条库（由 rulebook/source_texts/ 机械生成，勿手工编辑）
# 生成脚本：scripts/build_legal_library.py
# 原文库含全部条款号与正文；本文件只做结构转换（抽取元数据 chapter/section
# 留在原文库层，不进法条库）。
# 条文内容未经人工校核（原文库为 PDF 抽取），条款号与正文以官方 PDF 为准。
"""


def build() -> dict[str, list]:
    """读原文库 → 返回 {law_id: law 字典}。"""
    laws: dict[str, list] = {}
    for path in sorted(SRC.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        law_id = doc["law_id"]
        articles = [
            {"article": a["article"], "text": a["text"]}
            for a in doc.get("articles", [])
        ]
        laws[law_id] = {
            "law_id": law_id,
            "title": doc["title"],
            "source_type": doc.get("source_type", "exchange_rule"),
            "effective_from": doc["effective_from"],
            "articles": articles,
            "calibration_pending": False,
        }
    return laws


def render(law: dict) -> str:
    """法条 → YAML 文本（一个文件 = 一个文档；loader 用 safe_load 读单文档）。"""
    body = yaml.safe_dump(
        [law], allow_unicode=True, sort_keys=False, default_flow_style=False,
    )
    return HEADER + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="只校验生成物是否最新（不改文件）")
    args = ap.parse_args()

    laws = build()
    if not laws:
        print("原文库为空", file=sys.stderr)
        return 1

    stale: list[str] = []
    OUT.mkdir(parents=True, exist_ok=True)
    for law_id, law in sorted(laws.items()):
        path = OUT / f"{law_id}.yaml"
        text = render(law)
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(law_id)
            continue
        path.write_text(text, encoding="utf-8")
        print(f"写入 {path.relative_to(REPO)}（{len(law['articles'])} 条文）")

    if args.check:
        if stale:
            print(f"法条库不是最新：{stale}（跑 scripts/build_legal_library.py）",
                  file=sys.stderr)
            return 1
        print("法条库与原文库一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
