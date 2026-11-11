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
2. 渲染文本（由结构化候选规则通过确定性模板生成）

任务：判断「渲染文本」在语义上是否与「原文条款」等价。
只输出 JSON，格式：{"equivalent": "yes|no|partial", "differences": ["..."]}

判定口径：
- "yes" = 语义完全一致（条件集合、AND/OR 结构、量词、阈值、单位均一致）
- "no" = 存在实质性语义差异（AND↔OR、量词变更、数值不同、条件增减、主体范围变化）
- "partial" = 大体一致但存在表述差异（不改变判定结果的同义表述）

重点核查：
- AND/OR 嵌套结构（最危险的错误类）
- 量词（累计 / 各期 / 任一期 / 平均 / 复合增长率）
- 数值与单位（亿元 / 万元 / %）
- 条件的增减与适用主体（发行人 / 红筹企业 / 表决权差异安排）

不要做提取，只做判断。不要输出解释，只输出 JSON。"""

L2_USER_TEMPLATE = """【原文条款】
{source_text}

【渲染文本】
{rendered_text}

请判断语义等价性，仅输出 JSON。"""


def build_l2_prompt(rule: CandidateRule, items: Optional[dict[str, dict]] = None) -> tuple[str, str, str]:
    rendered = render_candidate(rule, items)
    user = L2_USER_TEMPLATE.format(source_text=rule.source.text, rendered_text=rendered)
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
