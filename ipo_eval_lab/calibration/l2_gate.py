"""
M1 校准管线 L2 回译闸门（设计 0003 §5）

结构化候选 → 确定性渲染回中文 → 异构模型做等价判断（NLI，判断题非问答题）
"""

from pathlib import Path
from typing import Any
import json

from .models import (
    GateName, GateStatus, GateResult, GateFailure, EquivalenceJudgment,
    CandidateRule, CandidateClause, CandidateLeaf, L2Judgment
)


# ── 确定性渲染器：候选结构 → 中文文本 ──

QUANTIFIER_CN = {
    "sum": "累计",
    "last": "最近",
    "avg": "平均",
    "all_periods": "各期",
    "any_period": "任一期",
}

WINDOW_CN = {
    "last_1_year": "最近 1 个会计年度",
    "last_2_years": "最近 2 个会计年度",
    "last_3_years": "最近 3 个会计年度",
    "last_5_years": "最近 5 个会计年度",
    "latest": "最新一期",
    "all_periods": "各会计年度",
}

OP_CN = {
    "GE": "不低于",
    "GT": "高于",
    "LE": "不高于",
    "LT": "低于",
    "EQ": "等于",
    "NE": "不等于",
}


def render_leaf(leaf: CandidateLeaf) -> str:
    """单叶渲染：quantifier + window + item + op + threshold"""
    q = QUANTIFIER_CN.get(leaf.quantifier, leaf.quantifier)
    w = WINDOW_CN.get(leaf.window, leaf.window)
    op = OP_CN.get(leaf.op, leaf.op)
    thresh = leaf.threshold_format  # 用原文形态
    
    if leaf.quantifier == "all_periods" and leaf.op == "GT" and leaf.threshold == 0:
        # 特例：均为正
        return f"{w}{leaf.item_ref}均为正"
    
    return f"{q}{w}{leaf.item_ref}{op}{thresh}"


def render_clause(clause: CandidateClause) -> str:
    """条文渲染：logic=all → 同时满足；logic=any → 满足下列条件之一"""
    leaf_texts = [f"({i+1}) {render_leaf(lf)}" for i, lf in enumerate(clause.leaves)]
    
    if clause.logic == "all":
        return "同时满足：" + "，且".join(leaf_texts)
    else:
        return "满足下列条件之一：" + "；或".join(leaf_texts)


def render_candidate(candidate: CandidateClause) -> str:
    """候选规则整体渲染"""
    return render_clause(candidate)


# ── L2 判定提示词模板 ──

L2_SYSTEM_PROMPT = """你是一个严格的语义等价判断器（NLI 任务）。

输入：
1. 原文条款（权威来源，逐字准确）
2. 渲染文本（由结构化候选规则通过确定性模板生成）

任务：判断「渲染文本」在语义上是否与「原文条款」等价。
- 仅输出 JSON，格式：{"equivalent": "yes|no|partial", "differences": ["..."]}
- "yes" = 语义完全一致，无任何信息增减
- "no" = 存在实质性语义差异（如 AND↔OR、量词变更、数值不同、条件增减）
- "partial" = 大体一致但有细微差异（如同义词替换、语序调整但不改变含义）

重点关注：
- AND/OR 嵌套结构（最危险错误类）
- 量词（累计/各期/任一期/平均）
- 数值与单位
- 条件的增减

不要做提取，只做判断。不要输出解释，只输出 JSON。"""

L2_USER_TEMPLATE = """【原文条款】
{source_text}

【渲染文本】
{rendered_text}

请判断语义等价性，仅输出 JSON。"""


def build_l2_prompt(candidate: CandidateRule) -> tuple[str, str]:
    """构建 L2 提示词"""
    rendered = render_candidate(candidate.candidate)
    user = L2_USER_TEMPLATE.format(
        source_text=candidate.source.text,
        rendered_text=rendered
    )
    return L2_SYSTEM_PROMPT, user, rendered


def parse_l2_response(response: str) -> L2Judgment:
    """解析模型返回的 JSON"""
    try:
        data = json.loads(response.strip())
        return L2Judgment(
            equivalent=EquivalenceJudgment(data.get("equivalent", "no")),
            differences=data.get("differences", []),
            rendered_text=""  # 由调用方填入
        )
    except json.JSONDecodeError:
        # 兜底：当作失败
        return L2Judgment(
            equivalent=EquivalenceJudgment.NO,
            differences=["模型返回非 JSON，解析失败"],
            rendered_text=""
        )


# ── L2 闸门主入口（agent 会话执行版）──

def run_l2_gate_agent(
    candidates: list[CandidateRule],
    agent_session,  # 当前 agent 会话，由 CLI 注入
) -> list[GateResult]:
    """
    L2 回译闸门 - 由 agent 会话执行模型调用
    - 输入：候选规则列表
    - 执行：agent 按 prompt 调用异构模型
    - 输出：GateResult 列表
    
    实际模型调用在 CLI 层完成，这里只负责构建 prompt 和解析结果。
    """
    results: list[GateResult] = []
    
    for c in candidates:
        system_prompt, user_prompt, rendered = build_l2_prompt(c)
        
        # 由 agent 会话执行实际调用
        # agent 返回模型原始响应字符串
        response = agent_session.run_l2_judgment(system_prompt, user_prompt)
        
        judgment = parse_l2_response(response)
        judgment.rendered_text = rendered
        
        if judgment.equivalent == EquivalenceJudgment.YES:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L2,
                status=GateStatus.PASS,
                payload={"judgment": judgment.model_dump()}
            ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L2,
                status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L2,
                    check_code="l2-nli",
                    reason=f"回译不等价：{judgment.equivalent.value}",
                    details={"differences": judgment.differences, "rendered": rendered}
                )
            ))
    
    return results


# ── 备选：离线模式（测试用，喂入预跑结果）──

def run_l2_gate_offline(
    candidates: list[CandidateRule],
    precomputed_judgments: dict[str, L2Judgment],  # clause_id -> L2Judgment
) -> list[GateResult]:
    """离线模式：直接用预跑的判定结果（测试/CI 用）"""
    results: list[GateResult] = []
    
    for c in candidates:
        rendered = render_candidate(c.candidate)
        judgment = precomputed_judgments.get(c.clause_id)
        
        if not judgment:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L2,
                status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L2, check_code="l2-missing",
                    reason="无预计算判定结果"
                )
            ))
            continue
        
        judgment.rendered_text = rendered
        
        if judgment.equivalent == EquivalenceJudgment.YES:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L2,
                status=GateStatus.PASS,
                payload={"judgment": judgment.model_dump()}
            ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L2,
                status=GateStatus.FAIL,
                failure=GateFailure(
                    gate=GateName.L2, check_code="l2-nli",
                    reason=f"回译不等价：{judgment.equivalent.value}",
                    details={"differences": judgment.differences, "rendered": rendered}
                )
            ))
    
    return results


__all__ = [
    "run_l2_gate_agent", "run_l2_gate_offline",
    "render_leaf", "render_clause", "render_candidate",
    "build_l2_prompt", "parse_l2_response",
    "L2_SYSTEM_PROMPT", "L2_USER_TEMPLATE",
]