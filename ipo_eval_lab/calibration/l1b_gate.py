"""
M1 校准管线 L1b 锚点核对（设计 0003 §4）

确定性三步：引文防编造 / 数值锚点 / 覆盖率扫描
"""

from pathlib import Path
import re
import yaml

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L1bCheckCode,
    CandidateRule, CandidateLeaf,
)


# ── R10: 归一化规则表 ──

def load_anchor_normalization(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}


def _parse_chinese_numeral(text: str) -> float:
    """解析中文数字（十五 / 五十 / 一百 / 五百 / 五千 / 一万 / 五十亿）"""
    if not text:
        raise ValueError("空中文数字")

    total = 0.0
    section = 0.0
    num = 0.0

    for ch in text:
        if ch in _CN_DIGITS:
            num = float(_CN_DIGITS[ch])
        elif ch == "十":
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

    if text.endswith("%") or text.endswith("％") or text.startswith("百分之"):
        num_part = (text.replace("%", "").replace("％", "").replace("百分之", "", 1))
        return normalize_chinese_number(num_part) / 100

    if "亿" in text:
        num_part = text.replace("亿", "").replace("元", "")
        val = normalize_chinese_number(num_part) if num_part else 1.0
        return val * 1e8

    if "万" in text:
        num_part = text.replace("万", "").replace("元", "")
        val = normalize_chinese_number(num_part) if num_part else 1.0
        return val * 1e4

    try:
        return float(text.replace("元", ""))
    except ValueError:
        pass

    return _parse_chinese_numeral(text.replace("元", ""))


_NUM_PATTERNS = [
    r"[\d.]+(?:\s*[亿万]?\s*元?)",                       # 2 亿元 / 5000 万元
    r"[\d.]+\s*%",                                       # 25%
    r"百分之[\d一二三四五六七八九十百千]+",              # 百分之十五
    r"[零一二三四五六七八九十百千][零一二三四五六七八九十百千万亿]*(?:亿|万)?\s*元?",
]


def extract_numbers_from_text(text: str) -> list[float]:
    """从文本中提取所有数值（阿拉伯/中文/百分比，统一归一化）"""
    numbers: list[float] = []
    for pat in _NUM_PATTERNS:
        for m in re.finditer(pat, text):
            try:
                numbers.append(normalize_chinese_number(m.group()))
            except ValueError:
                pass
    return numbers


def numbers_match(candidate_value: float, source_number: float) -> bool:
    """浮点容差比对（相对误差 1e-9 或绝对 1e-6）"""
    if candidate_value == 0 and source_number == 0:
        return True
    return abs(candidate_value - source_number) <= max(1e-6, abs(source_number) * 1e-9)


# ── 1b-1: 引文防编造 ──

def check_quote_verbatim(candidate: CandidateRule) -> list[GateFailure]:
    fails: list[GateFailure] = []
    source_text = candidate.source.text

    for leaf in candidate.clause.leaves:
        quote = leaf.quote.strip()
        if not quote:
            continue  # 0-1 已报空 quote
        if quote not in source_text:
            fails.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.QUOTE_VERBATIM,
                reason=f"leaf {leaf.leaf_id}: quote 未在原文中逐字命中（疑似编造）",
                details={"clause_id": candidate.clause_id, "quote": quote},
            ))
    return fails


# ── 1b-2: 数值锚点 ──

def check_numeric_anchor(
    candidate: CandidateRule, anchor_rules: dict | None = None,
) -> list[GateFailure]:
    """
    候选叶的 threshold_text 归一化后，必须落在「原文数值集合」内。
    引文自身若一个数值都没有（纯定性条件），跳过该叶的数值锚点。
    """
    fails: list[GateFailure] = []
    source_text = candidate.source.text
    source_numbers = extract_numbers_from_text(source_text)

    if not source_numbers:
        return fails

    for leaf in candidate.clause.leaves:
        leaf_numbers = extract_numbers_from_text(leaf.threshold_text)
        if not leaf_numbers:
            continue

        if not any(numbers_match(n, s) for n in leaf_numbers for s in source_numbers):
            fails.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.NUMERIC_ANCHOR,
                reason=(f"leaf {leaf.leaf_id}: 阈值文本 '{leaf.threshold_text}' 归一化 {leaf_numbers} "
                        f"不在原文数值集合内"),
                details={"clause_id": candidate.clause_id,
                         "source_numbers": sorted(source_numbers)[:12]},
            ))
        # 结构值一致性：threshold 数值与 threshold_text 归一化值必须一致
        elif leaf.threshold_format != "percent" and not any(
            numbers_match(float(leaf.threshold), n) for n in leaf_numbers
        ):
            fails.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.NUMERIC_ANCHOR,
                reason=(f"leaf {leaf.leaf_id}: threshold={leaf.threshold} 与 "
                        f"threshold_text '{leaf.threshold_text}' 归一化 {leaf_numbers[0]} 不一致"),
                details={"clause_id": candidate.clause_id},
            ))
    return fails


# ── 1b-3: 覆盖率扫描 ──

THRESHOLD_PATTERNS = [
    r"不低于\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"不少于\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"超过\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"高于\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"大于\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"达到\s*[\d一二三四五六七八九十百千万亿.]+\s*[亿万]?\s*(?:元|股|份)?",
    r"不低于\s*百分之[\d一二三四五六七八九十]+",
    r"不少于\s*百分之[\d一二三四五六七八九十]+",
    r"超过\s*[\d.]+\s*%",
    r"高于\s*[\d.]+\s*%",
    r"\d+\s*%\s*以上",
]


def scan_thresholds(source_text: str) -> list[str]:
    """扫出原文中的阈值型表达（覆盖率扫描的输入）"""
    found: list[str] = []
    for pat in THRESHOLD_PATTERNS:
        for m in re.finditer(pat, source_text):
            found.append(m.group())
    return found


def check_coverage_scan(candidate: CandidateRule) -> list[GateFailure]:
    """单条规则的覆盖率扫描（引文有阈值而候选未提取 → 疑似漏条件）"""
    fails: list[GateFailure] = []

    found = scan_thresholds(candidate.source.text)
    if not found:
        return fails

    leaf_numbers = [
        n for leaf in candidate.clause.leaves
        for n in extract_numbers_from_text(leaf.threshold_text)
    ]

    for thresh_text in found:
        thresh_numbers = extract_numbers_from_text(thresh_text)
        if not thresh_numbers:
            continue
        if not any(numbers_match(th, ln) for th in thresh_numbers for ln in leaf_numbers):
            fails.append(GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.COVERAGE_SCAN,
                reason=f"引文含阈值 '{thresh_text}' 但候选未提取对应数值（疑似漏条件）",
                details={"clause_id": candidate.clause_id, "missed": thresh_text},
            ))
    return fails


def check_coverage_scan_article(rules: list[CandidateRule]) -> dict[str, list[GateFailure]]:
    """
    按「条文」（law_id#article）聚合覆盖率扫描。

    一条条文可产出多个候选（多套/多支路，如 3.1.2 三个标准），漏提取要按条文看
    全部候选的并集，否则每条候选都会被别的标准阈值误报。
    """
    from collections import defaultdict

    by_article: dict[str, list[CandidateRule]] = defaultdict(list)
    for r in rules:
        by_article[f"{r.source.law_id}#{r.source.article}"].append(r)

    out: dict[str, list[GateFailure]] = {}
    for key, group in by_article.items():
        found = scan_thresholds(group[0].source.text)
        if not found:
            continue
        leaf_numbers = [
            n for r in group for leaf in r.clause.leaves
            for n in extract_numbers_from_text(leaf.threshold_text)
        ]
        missing = []
        for thresh_text in found:
            thresh_numbers = extract_numbers_from_text(thresh_text)
            if not thresh_numbers:
                continue
            if not any(numbers_match(th, ln) for th in thresh_numbers for ln in leaf_numbers):
                missing.append(thresh_text)
        if missing:
            out[key] = [GateFailure(
                gate=GateName.L1B, check_code=L1bCheckCode.COVERAGE_SCAN,
                reason=(f"条文 {key} 引文含阈值 {missing} 但该条文的候选未提取对应数值"
                        f"（疑似漏条件，需人工核对）"),
                details={"article": key, "missed": missing,
                         "candidates": [r.clause_id for r in group]},
            )]
    return out


# ── 主入口 ──

def run_l1b_gate(
    candidates: list[CandidateRule],
    anchor_normalization_path: Path,
) -> list[GateResult]:
    anchor_rules = load_anchor_normalization(anchor_normalization_path)
    article_warnings = check_coverage_scan_article(candidates)
    results: list[GateResult] = []

    for c in candidates:
        hard: list[GateFailure] = []
        hard.extend(check_quote_verbatim(c))
        hard.extend(check_numeric_anchor(c, anchor_rules))
        warnings = article_warnings.get(f"{c.source.law_id}#{c.source.article}", [])

        if hard:
            results.append(GateResult(
                clause_id=c.clause_id, gate=GateName.L1B, status=GateStatus.FAIL,
                failure=hard[0],
                payload={"all_failures": [f.model_dump() for f in hard]},
            ))
        elif warnings:
            results.append(GateResult(
                clause_id=c.clause_id, gate=GateName.L1B, status=GateStatus.PASS,
                payload={"warnings": [f.reason for f in warnings],
                         "checks": ["1b-1", "1b-2", "1b-3"]},
            ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id, gate=GateName.L1B, status=GateStatus.PASS,
                payload={"checks": ["1b-1", "1b-2", "1b-3"]},
            ))
    return results


__all__ = [
    "run_l1b_gate", "check_quote_verbatim", "check_numeric_anchor",
    "check_coverage_scan", "check_coverage_scan_article", "scan_thresholds",
    "normalize_chinese_number", "extract_numbers_from_text", "numbers_match",
    "load_anchor_normalization",
]
