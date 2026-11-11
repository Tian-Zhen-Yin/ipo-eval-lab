"""
M1 校准管线 L1b 锚点核对（设计 0003 §4）

确定性三步：引文防编造 / 数值锚点 / 覆盖率扫描
"""

from pathlib import Path
from typing import Any
import re
import yaml

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L1bCheckCode,
    CandidateRule, CandidateLeaf
)


# ── R10: 锚点归一化规则表（YAML 配置） ──

def load_anchor_normalization(path: Path) -> dict:
    """加载 R10 归一化规则表"""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _parse_chinese_numeral(text: str) -> float:
    """解析中文数字（支持 十五 / 五十 / 一百 / 五百 / 五千 / 一万 等）"""
    digits = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}

    if not text:
        raise ValueError("空中文数字")

    total = 0.0   # 已结算的大单位累计（万/亿以上）
    section = 0.0  # 当前小段累计（万以下）
    num = 0.0      # 当前数字

    for ch in text:
        if ch in digits:
            num = float(digits[ch])
        elif ch == "十":
            # "十五" → 1×10；"五十" 前有 5 → 5×10
            section += (num if num else 1.0) * 10
            num = 0.0
        elif ch == "百":
            section += (num if num else 1.0) * 100
            num = 0.0
        elif ch == "千":
            section += (num if num else 1.0) * 1000
            num = 0.0
        elif ch == "万":
            section = (section + num) * 10000
            total += section
            section = 0.0
            num = 0.0
        elif ch == "亿":
            section = (section + num) * 100000000
            total += section
            section = 0.0
            num = 0.0
        else:
            raise ValueError(f"非法中文数字字符：{ch}")

    return total + section + num


def normalize_chinese_number(text: str) -> float:
    """中文数字归一化：五十亿 → 5e9、5000万 → 5e7、15% → 0.15"""
    text = text.strip().replace(",", "").replace("，", "").replace(" ", "")

    # 百分比
    if text.endswith("%") or text.endswith("％") or text.startswith("百分之"):
        num_part = (text.replace("%", "").replace("％", "")
                    .replace("百分之", "", 1))
        return normalize_chinese_number(num_part) / 100

    # 亿
    if "亿" in text:
        num_part = text.replace("亿", "").replace("元", "")
        scale = 1e8
        val = normalize_chinese_number(num_part) if num_part else 1.0
        return val * scale

    # 万
    if "万" in text:
        num_part = text.replace("万", "").replace("元", "")
        scale = 1e4
        val = normalize_chinese_number(num_part) if num_part else 1.0
        return val * scale

    # 纯阿拉伯数字
    try:
        return float(text.replace("元", ""))
    except ValueError:
        pass

    # 中文数字（注意：先去掉可能的"元"后缀）
    return _parse_chinese_numeral(text.replace("元", ""))


def extract_numbers_from_text(text: str) -> list[float]:
    """从文本中提取所有数值（含中文、百分比、单位）"""
    numbers = []
    
    # 模式：数字+单位（亿/万/元/%）或纯数字或中文数字
    patterns = [
        r'[\d.]+(?:\s*[亿万]?\s*元?)',  # 50亿元、5000万、2亿
        r'[\d.]+\s*%',                  # 15%
        r'百分之[\d一二三四五六七八九十百千万亿]+',  # 百分之十五
        r'[零一二三四五六七八九十百千][零一二三四五六七八九十百千万亿]*(?:亿|万)?\s*元?',  # 五十亿
    ]
    
    for pat in patterns:
        for m in re.finditer(pat, text):
            try:
                numbers.append(normalize_chinese_number(m.group()))
            except (ValueError, IndexError):
                pass
    
    return numbers


# ── 1b-1: 引文防编造（quote 必须在原文中逐字命中）──

def check_quote_verbatim(candidate: CandidateRule) -> list[GateFailure]:
    """1b-1: 引文逐字命中检查"""
    failures = []
    source_text = candidate.source.text
    
    for leaf in candidate.candidate.leaves:
        quote = leaf.quote.strip()
        if quote and quote not in source_text:
            failures.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.QUOTE_VERBATIM,
                reason=f"leaf {leaf.leaf_id}: quote 未在原文中逐字命中",
                details={"quote": quote, "source_preview": source_text[:200]}
            ))
    return failures


# ── 1b-2: 数值锚点（候选规则用到的每个数值 ∈ 引文归一化数值集合）──

def check_numeric_anchor(
    candidate: CandidateRule,
    anchor_rules: dict
) -> list[GateFailure]:
    """1b-2: 数值锚点检查"""
    failures = []
    source_text = candidate.source.text
    
    # 从引文提取归一化数值集合
    source_numbers = set(extract_numbers_from_text(source_text))
    
    for leaf in candidate.candidate.leaves:
        # threshold 归一化
        thresh_norm = leaf.threshold
        thresh_format = leaf.threshold_format
        
        # 用 threshold_format 反推归一化值（更准）
        format_numbers = extract_numbers_from_text(thresh_format)
        
        # 检查候选数值是否在引文数值集合内
        for num in format_numbers:
            # 允许微小浮点误差
            matched = any(abs(num - sn) < 1e-6 for sn in source_numbers)
            if not matched and source_numbers:
                failures.append(GateFailure(
                    gate=GateName.L1B, check_code=L1bCheckCode.NUMERIC_ANCHOR,
                    reason=f"leaf {leaf.leaf_id}: 数值 {num} (来自 '{thresh_format}') 不在引文归一化集合内",
                    details={"candidate_value": num, "source_numbers": sorted(source_numbers)}
                ))
    return failures


# ── 1b-3: 覆盖率扫描（抓漏条件）──

THRESHOLD_PATTERNS = [
    r"不低于\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"不少于\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"超过\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"高于\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"大于\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"达到\s*[\d一二三四五六七八九十百千万亿.]+(?:\s*[亿万]?\s*元?)?",
    r"不低于\s*百分之[\d一二三四五六七八九十]+",
    r"不少于\s*百分之[\d一二三四五六七八九十]+",
    r"超过\s*[\d.]+\s*%",
    r"高于\s*[\d.]+\s*%",
]

def check_coverage_scan(candidate: CandidateRule) -> list[GateFailure]:
    """1b-3: 覆盖率扫描 - 引文有阈值模式而候选未使用 → 警告"""
    failures = []
    source_text = candidate.source.text
    
    # 提取引文中的所有阈值型模式
    found_thresholds = []
    for pat in THRESHOLD_PATTERNS:
        for m in re.finditer(pat, source_text):
            found_thresholds.append(m.group())
    
    if not found_thresholds:
        return failures  # 引文无阈值模式，无需检查
    
    # 检查每个阈值模式是否有对应的 leaf
    for thresh_text in found_thresholds:
        thresh_nums = extract_numbers_from_text(thresh_text)
        if not thresh_nums:
            continue
        
        # 看候选里是否有匹配的数值
        matched = False
        for leaf in candidate.candidate.leaves:
            leaf_nums = extract_numbers_from_text(leaf.threshold_format)
            for ln in leaf_nums:
                for tn in thresh_nums:
                    if abs(ln - tn) < 1e-6:
                        matched = True
                        break
                if matched:
                    break
            if matched:
                break
        
        if not matched:
            failures.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.COVERAGE_SCAN,
                reason=f"引文含阈值模式 '{thresh_text}' 但候选规则未提取对应条件",
                details={"missed_pattern": thresh_text, "candidate_leaves": len(candidate.candidate.leaves)}
            ))
    
    return failures


# ── L1b 闸门主入口 ──

def run_l1b_gate(
    candidates: list[CandidateRule],
    anchor_normalization_path: Path,
) -> list[GateResult]:
    """
    L1b 锚点核对主函数
    - 确定性，零 AI
    - 三步全过 → PASS，任一失败 → FAIL
    """
    anchor_rules = load_anchor_normalization(anchor_normalization_path)
    results: list[GateResult] = []
    
    for c in candidates:
        all_failures = []
        
        # 1b-1 引文防编造
        all_failures.extend(check_quote_verbatim(c))
        
        # 1b-2 数值锚点
        all_failures.extend(check_numeric_anchor(c, anchor_rules))
        
        # 1b-3 覆盖率扫描（警告级，不直接 FAIL，但记录）
        coverage_warnings = check_coverage_scan(c)
        all_failures.extend(coverage_warnings)
        
        if all_failures:
            # 区分：quote/数值锚点 = 硬拦截；覆盖率 = 警告
            hard_failures = [f for f in all_failures 
                           if f.check_code in (L1bCheckCode.QUOTE_VERBATIM, L1bCheckCode.NUMERIC_ANCHOR)]
            if hard_failures:
                results.append(GateResult(
                    clause_id=c.clause_id,
                    gate=GateName.L1B,
                    status=GateStatus.FAIL,
                    failure=hard_failures[0],
                ))
            else:
                # 只有覆盖率警告，标记为 PASS 但带警告
                results.append(GateResult(
                    clause_id=c.clause_id,
                    gate=GateName.L1B,
                    status=GateStatus.PASS,
                    payload={"warnings": [f.reason for f in coverage_warnings]}
                ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L1B,
                status=GateStatus.PASS,
                payload={"checks": ["1b-1", "1b-2", "1b-3"]}
            ))
    
    return results


__all__ = [
    "run_l1b_gate",
    "check_quote_verbatim", "check_numeric_anchor", "check_coverage_scan",
    "normalize_chinese_number", "extract_numbers_from_text", "load_anchor_normalization",
]