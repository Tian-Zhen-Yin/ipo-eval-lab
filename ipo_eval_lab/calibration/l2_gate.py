"""
M1 校准管线 L2 回译闸门（设计 0003 §5）

结构化候选 → 确定性渲染回中文 → 异构模型做等价判断（NLI，判断题非问答题）。
渲染器纯代码模板，不含 LLM；item 的量化口径来自 items.yaml（display/quantifier/window）。
"""

from pathlib import Path
from typing import Optional
import json

from .models import (
    GateName, GateStatus, GateResult, GateFailure, EquivalenceJudgment,
    CandidateRule, CandidateClause, CandidateLeaf, L2Judgment,
)
from .rulebook_refs import load_items

OP_CN = {
    "eq": "等于", "ne": "不等于",
    "gt": "高于", "ge": "不低于",
    "lt": "低于", "le": "不高于",
}

FORMAT_SUFFIX = {
    "percent": "（百分比）",
    "integer": "（整数）",
    "boolean": "（是/否）",
}


def render_leaf(leaf: CandidateLeaf, item: Optional[dict] = None) -> str:
    """单叶渲染：item 的规范名 + 算子 + 原文数值形态"""
    item_display = (item or {}).get("display") or leaf.item_ref

    # 布尔型（judgment item）：display 本身即条件断言
    if leaf.threshold_format == "boolean":
        return item_display if leaf.threshold is True else f"不满足：{item_display}"

    # 「为正」类零阈值：原文无数值形态，按中文习惯渲染（display 已含「为正」则不重复）
    if leaf.threshold_text in ("为正", "正") or (
        leaf.op == "gt" and float(leaf.threshold) == 0 and leaf.threshold_text.strip() == "0"
    ):
        if item_display.endswith("为正") or "均为正" in item_display:
            return item_display
        return f"{item_display}为正"

    op_cn = OP_CN.get(leaf.op, leaf.op)
    return f"{item_display}{op_cn}{leaf.threshold_text}"


def render_clause(clause: CandidateClause, items: Optional[dict[str, dict]] = None) -> str:
    """条文渲染：all → 同时满足；any → 满足下列条件之一"""
    items = items or {}
    texts = [render_leaf(lf, items.get(lf.item_ref)) for lf in clause.leaves]
    if clause.logic == "all":
        return "同时满足：" + "，且".join(texts)
    return "满足下列条件之一：" + "；或".join(texts)


def render_candidate(rule: CandidateRule, items: Optional[dict[str, dict]] = None) -> str:
    return render_clause(rule.clause, items)


# ── L2 提示词 ──

L2_SYSTEM_PROMPT = """你是一个严格的语义等价判断器（NLI 任务）。

输入：
1. 原文条款（权威来源，逐字准确）
2. 候选定位（该候选对应原文的哪个标准/支路，或为跨支路共用条件）
3. 渲染文本（由结构化候选按确定性模板生成）

重要前提：一条条文常含多个「标准/支路」，候选是把其中一个标准（或各标准共用的条件）
抽出来的结构化表示，**不要求**渲染文本复述整条原文的全部标准。因此不要因为「少了别的
标准」而判 no；只判断渲染文本与它所声称对应的那一部分原文是否语义一致。

任务：判断「渲染文本」与原文中「候选定位所指的那部分」是否语义等价。
只输出 JSON，格式：{"equivalent": "yes|no|partial", "differences": ["..."]}

判定口径：
- "yes" = 该部分的条件集合、AND/OR 结构、量词、阈值、单位全部一致
- "no" = 存在实质性语义差异：AND↔OR、量词变更（累计/各期/任一期）、数值或单位错、
  条件增减、适用主体变化、把「或」并列的两条误写成「且」
- "partial" = 大体一致但有不影响判定结果的表述差异

重点核查：
- AND/OR 嵌套结构（最危险的错误类）
- 量词与窗口（累计 / 各期 / 任一期 / 平均 / 复合增长率 / 最近N年 / 最近一年）
- 数值与单位（亿元 / 万元 / %）
- 候选是否把原文中「A 或 B」误写成「A 且 B」，或反之
- 共用条件（如预计市值）是否被按支路阈值的不同值错误合并

不要做提取，只做判断。不要输出解释，只输出 JSON。"""

L2_USER_TEMPLATE = """【原文条款】
{source_text}

【候选定位】
{position}

【渲染文本】
{rendered_text}

请判断语义等价性，仅输出 JSON。"""


def describe_position(rule: CandidateRule) -> str:
    """候选在原文中的位置说明（避免与「少复述别的标准」混为一谈）"""
    ctx = rule.context
    if ctx.role == "shared":
        return (f"套 {ctx.group_id}（group_no={ctx.group_no}）的跨支路共用条件；"
                f"原文可能把同一条件在多条支路各写一遍，合并为一条即可。")
    return (f"套 {ctx.group_id}（group_no={ctx.group_no}）的支路 {ctx.branch_id}；"
            f"只对应原文里可选标准中的一条路径。")


def build_l2_prompt(
    rule: CandidateRule, items: Optional[dict[str, dict]] = None,
) -> tuple[str, str, str]:
    rendered = render_candidate(rule, items)
    user = L2_USER_TEMPLATE.format(
        source_text=rule.source.text,
        position=describe_position(rule),
        rendered_text=rendered,
    )
    return L2_SYSTEM_PROMPT, user, rendered


def parse_l2_response(response: str) -> L2Judgment:
    """解析模型返回的 JSON（容忍 markdown 代码块包裹）"""
    text = response.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text.lstrip("`")
        text = text.lstrip("json").strip()
    try:
        data = json.loads(text)
        return L2Judgment(
            equivalent=EquivalenceJudgment(data.get("equivalent", "no")),
            differences=list(data.get("differences", [])),
        )
    except (json.JSONDecodeError, ValueError):
        return L2Judgment(
            equivalent=EquivalenceJudgment.NO,
            differences=[f"模型返回无法解析：{response[:120]}"],
        )


# ── 闸门入口 ──

def _result_from_judgment(rule: CandidateRule, judgment: L2Judgment) -> GateResult:
    if judgment.equivalent == EquivalenceJudgment.YES:
        return GateResult(
            clause_id=rule.clause_id, gate=GateName.L2, status=GateStatus.PASS,
            payload={"judgment": judgment.model_dump()},
        )
    return GateResult(
        clause_id=rule.clause_id, gate=GateName.L2, status=GateStatus.FAIL,
        failure=GateFailure(
            gate=GateName.L2, check_code="l2-nli",
            reason=f"回译不等价：{judgment.equivalent.value}",
            details={"clause_id": rule.clause_id,
                     "differences": judgment.differences,
                     "rendered": judgment.rendered_text},
        ),
    )


def run_l2_gate_offline(
    rules: list[CandidateRule],
    precomputed_judgments: dict[str, L2Judgment],
    rulebook_dir: Optional[Path] = None,
) -> list[GateResult]:
    """离线模式：判定结果由外部（agent 会话）预跑并落盘，测试/CI 直接回放"""
    items = load_items(rulebook_dir) if rulebook_dir else {}
    results: list[GateResult] = []
    for r in rules:
        judgment = precomputed_judgments.get(r.clause_id)
        if judgment is None:
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L2, status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L2, check_code="l2-missing",
                    reason="无预计算判定结果（L2 未执行）",
                    details={"clause_id": r.clause_id},
                ),
            ))
            continue
        judgment.rendered_text = render_candidate(r, items)
        results.append(_result_from_judgment(r, judgment))
    return results


def run_l2_gate_agent(rules: list[CandidateRule], judge) -> list[GateResult]:
    """
    agent 会话当执行者：judge(system_prompt, user_prompt) -> 模型原始响应字符串
    管线本身不 import 任何模型 SDK（AR2 / D3）。
    """
    results: list[GateResult] = []
    for r in rules:
        system, user, rendered = build_l2_prompt(r)
        judgment = parse_l2_response(judge(system, user))
        judgment.rendered_text = rendered
        results.append(_result_from_judgment(r, judgment))
    return results


__all__ = [
    "run_l2_gate_offline", "run_l2_gate_agent",
    "render_leaf", "render_clause", "render_candidate",
    "build_l2_prompt", "parse_l2_response",
    "L2_SYSTEM_PROMPT", "L2_USER_TEMPLATE",
]
