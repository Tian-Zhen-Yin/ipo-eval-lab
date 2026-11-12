"""口径定义索引：从法规原文提取口径定义句，供 L2 回译按作用域核查（ADR-0010 §2）。

**为什么需要它**：渲染文本带口径后缀（「最近1年净利润（扣非前后孰低）」「最近1年净资产（归母）」），
L2 判定模型此前按「本条文字自足口径」理解，把有依据的口径后缀判成「来源外补充」。
实际上口径定义在原文中有**两级作用域**：

- **规则级**：各规则的**释义条**（「本规则下列用语的具体含义」）对整部规则生效。
  例：沪主板释义条「净利润：指上市公司利润表列报的净利润；上市公司编制合并财务报表的，
  为合并利润表列报的归属于母公司所有者的净利润，不包括少数股东损益。」
- **节级**：「**本节**所称 X」的定义对同一节内全部条文生效。
  例：沪主板 3.1.2 与 3.1.6 同属「第一节 首次公开发行股票上市」，故 3.1.2 的
  「本节所称净利润以扣除非经常性损益前后的孰低者为准」对 3.1.6 同样生效。

本模块只做**机械提取与装配**——作用域的法律判断由人核（ADR-0010 §3），
落到本模块的是「哪条属哪一节」「哪条是释义条」这类结构性事实。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

# 释义条识别：章节名含「释义」「用语」「定义」或「附则」
_DEFINITION_CHAPTER = re.compile(r"释\s*义|用\s*语|定\s*义|附\s*则")

# 节级定义句：「本节所称 X」「本条所称 X」
_SECTION_DEF = re.compile(
    r"本[节条]所称[^。]{0,200}?。"
)

# 规则级定义句：「净利润，指 …」「净资产：指 …」
# 分隔符有三种：逗号、顿号、冒号；且释义条的定义常跨分号分句
# （「净利润，指上市公司利润表列报的净利润；上市公司编制合并财务报表的，为合并利润表
#   列报的归属于母公司所有者的净利润，不包括少数股东损益。」），故分号也要断句。
_TERM_DEF = re.compile(
    r"(?<![。；])([^，。；、]{2,12}?)[，：]?(?:是指|指)[^。；]{0,220}(?:。|；)"
)

# 只有这些术语的口径需要索引——渲染后缀只可能落在这几个上
_CALIBER_TERMS = ("净利润", "净资产", "营业收入", "预计市值", "经营活动产生的现金流量净额")


@dataclass
class CaliberDefinition:
    """一条口径定义及其作用域"""

    text: str                      # 定义句原文
    term: str                      # 所定义的术语
    scope: str                     # "rule"（规则级）| "section"（节级）
    law_id: str
    article: str
    section: Optional[str] = None

    @property
    def anchor(self) -> str:
        """人读锚点：哪条文的哪一节"""
        if self.scope == "section" and self.section:
            return f"{self.law_id}#{self.article}（{self.section}）"
        return f"{self.law_id}#{self.article}"


@dataclass
class CaliberIndex:
    """某部规则的口径定义索引"""

    law_id: str
    rule_level: list[CaliberDefinition] = field(default_factory=list)
    by_section: dict[str, list[CaliberDefinition]] = field(default_factory=dict)
    article_sections: dict[str, str] = field(default_factory=dict)

    def section_of(self, article: str) -> Optional[str]:
        """条文 → 节归属（候选 source.section 全空，需回原文库查）"""
        return self.article_sections.get(article)

    def applicable(self, section: Optional[str]) -> list[CaliberDefinition]:
        """取适用于「某节」的全部口径定义（规则级 + 该节级）。

        section 为 None 时只给规则级——条文无节归属时不得臆断节级作用域。
        """
        out = list(self.rule_level)
        if section:
            out.extend(self.by_section.get(section, []))
        return out

    def render(self, section: Optional[str]) -> str:
        """装配成给 L2 判定模型看的「口径定义依据」段。"""
        defs = self.applicable(section)
        if not defs:
            return "（本规则未检出适用于该条文的口径定义。）"
        lines = []
        for d in defs:
            kind = "规则级（释义条，对整部规则生效）" if d.scope == "rule" else \
                   f"节级（本节，对同节全部条文生效）"
            lines.append(f"- [{kind}] {d.anchor}：{d.text}")
        return "\n".join(lines)


def _iter_articles(doc: dict[str, Any]):
    arts = doc.get("articles")
    if isinstance(arts, dict):
        arts = list(arts.values())
    return arts or []


def _is_definition_article(article: dict[str, Any]) -> bool:
    """释义条：章节名含「释义/用语/定义/附则」，或条文号落在末尾章节。"""
    chapter = (article.get("chapter") or "")
    return bool(_DEFINITION_CHAPTER.search(chapter))


def _section_def_terms(text: str) -> list[tuple[str, str]]:
    """从「本节所称 X…。」中抽出 (术语, 定义句)。"""
    out = []
    for m in _SECTION_DEF.finditer(text):
        s = m.group(0)
        for term in _CALIBER_TERMS:
            if term in s:
                out.append((term, s))
                break
    return out


def _term_defs(text: str) -> list[tuple[str, str]]:
    """从释义条中抽出 (术语, 定义句)。

    释义条的结构是「（N）术语：指 定义；补充。补充。」——**限定语常在补充分句里**：
    沪主板「（十三）净利润：指上市公司利润表列报的净利润；上市公司编制合并财务报表的，
    为合并利润表列报的**归属于母公司所有者的净利润**，不包括少数股东损益。」
    只取第一分句会漏掉「归母」这个正是渲染后缀要表达的东西，故取**整项**（从
    「（N）术语」到下一个「（N+1）」之前）。
    """
    out = []
    # 先切成「（N）…项」
    items = re.split(r"(?=（[一二三四五六七八九十百]+）)", text)
    for it in items:
        m = re.match(r"（[一二三四五六七八九十百]+）([^，：；。]{2,12}?)[，：]?(?:是指|指)", it)
        if not m:
            continue
        head = m.group(1)
        for term in _CALIBER_TERMS:
            # 精确匹配——前缀匹配会把「净资产收益率」当成「净资产」，
            # 那是另一个术语，口径完全不同（前者是收益率，后者是所有者权益）。
            if head == term:
                body = it[m.end():].strip()
                if body:
                    out.append((term, f"{term}：{body}"))
                break
    return out


def build_index_from_doc(doc: dict[str, Any]) -> CaliberIndex:
    """从一份 source_texts 文档构建口径定义索引。"""
    law_id = doc.get("law_id", "?")
    idx = CaliberIndex(law_id=law_id)
    for a in _iter_articles(doc):
        text = a.get("text") or ""
        article = a.get("article", "")
        section = a.get("section")
        if section:
            idx.article_sections[article] = section
        if _is_definition_article(a):
            for term, s in _term_defs(text):
                idx.rule_level.append(CaliberDefinition(
                    text=s, term=term, scope="rule",
                    law_id=law_id, article=article, section=section))
            # 释义条里也可能有「本规则所称以上含本数…」这类全局规则
            for m in re.finditer(r"本规则所称[^。]{0,120}?。", text):
                s = m.group(0)
                idx.rule_level.append(CaliberDefinition(
                    text=s, term="（通用表述规则）", scope="rule",
                    law_id=law_id, article=article, section=section))
        else:
            if not section:
                continue
            for term, s in _section_def_terms(text):
                idx.by_section.setdefault(section, []).append(CaliberDefinition(
                    text=s, term=term, scope="section",
                    law_id=law_id, article=article, section=section))
    return idx


def load_index(source_texts_dir: Path) -> dict[str, CaliberIndex]:
    """从 source_texts 目录加载全部规则的口径索引。"""
    out: dict[str, CaliberIndex] = {}
    for path in sorted(Path(source_texts_dir).glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or "law_id" not in doc:
            continue
        idx = build_index_from_doc(doc)
        out[idx.law_id] = idx
    return out


def article_section(source_texts_dir: Path, law_id: str, article: str) -> Optional[str]:
    """查某条文的节归属（候选 source.section 全空，需回填）。"""
    path = Path(source_texts_dir) / f"{law_id}.yaml"
    if not path.exists():
        return None
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    for a in _iter_articles(doc):
        if a.get("article") == article:
            return a.get("section")
    return None


__all__ = [
    "CaliberDefinition", "CaliberIndex",
    "build_index_from_doc", "load_index", "article_section",
]
