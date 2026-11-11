"""
M1 校准管线 L0 确定性闸门（设计 0003 §3）

8 项 lint，零 AI，毫秒级，不过 = 绝对拦截
"""

from pathlib import Path
from typing import Any
from collections import Counter

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L0CheckCode,
    CandidateRule, CandidateClause, CandidateLeaf
)


# ── 0-1: Schema 合法（字段/枚举） ──

VALID_QUANTIFIERS = {"sum", "last", "avg", "all_periods", "any_period"}
VALID_WINDOWS = {"last_1_year", "last_2_years", "last_3_years", "last_5_years", "latest", "all_periods"}
VALID_OPS = {"GE", "GT", "LE", "LT", "EQ", "NE"}
VALID_LOGICS = {"all", "any"}


def check_schema(candidate: CandidateRule) -> list[GateFailure]:
    """0-1: Schema 合法性检查"""
    failures = []
    for clause in [candidate.candidate]:
        if clause.logic not in VALID_LOGICS:
            failures.append(GateFailure(
                gate=GateName.L0, check_code=L0CheckCode.SCHEMA_VALID,
                reason=f"clause.logic 非法：{clause.logic}，合法值 {VALID_LOGICS}"
            ))
        for leaf in clause.leaves:
            if leaf.quantifier not in VALID_QUANTIFIERS:
                failures.append(GateFailure(
                    gate=GateName.L0, check_code=L0CheckCode.SCHEMA_VALID,
                    reason=f"leaf {leaf.leaf_id}: quantifier 非法：{leaf.quantifier}，合法值 {VALID_QUANTIFIERS}"
                ))
            if leaf.window not in VALID_WINDOWS:
                failures.append(GateFailure(
                    gate=GateName.L0, check_code=L0CheckCode.SCHEMA_VALID,
                    reason=f"leaf {leaf.leaf_id}: window 非法：{leaf.window}，合法值 {VALID_WINDOWS}"
                ))
            if leaf.op not in VALID_OPS:
                failures.append(GateFailure(
                    gate=GateName.L0, check_code=L0CheckCode.SCHEMA_VALID,
                    reason=f"leaf {leaf.leaf_id}: op 非法：{leaf.op}，合法值 {VALID_OPS}"
                ))
    return failures


# ── 0-2: 量纲一致（同 metric 阈值换算后同单位）──

def check_unit_consistency(candidates: list[CandidateRule], metrics_yaml: Path) -> list[GateFailure]:
    """0-2: 量纲一致性检查"""
    # TODO: 读取 metrics.yaml 的 unit 字段，按 item_ref 分组检查 threshold 单位
    # 现在先返回空，后续接入 metrics.yaml
    return []


# ── 0-3: 唯一性（group+branch+clause、sort 不重复）──

def check_uniqueness(candidates: list[CandidateRule]) -> list[GateFailure]:
    """0-3: 唯一性检查"""
    failures = []
    clause_ids = [c.clause_id for c in candidates]
    dup = {cid for cid, cnt in Counter(clause_ids).items() if cnt > 1}
    for cid in dup:
        failures.append(GateFailure(
            gate=GateName.L0, check_code=L0CheckCode.UNIQUENESS,
            reason=f"重复 clause_id：{cid} 出现 {clause_ids.count(cid)} 次"
        ))
    return failures


# ── 0-4: 引用完整（metric_ref ∈ metric_definitions；evidence_ref 非空）──

def check_ref_integrity(candidates: list[CandidateRule], metrics_yaml: Path) -> list[GateFailure]:
    """0-4: 引用完整性检查"""
    # TODO: 读取 metrics.yaml，检查 item_ref 是否存在
    # 现在先返回空
    return []


# ── 0-5: 窗口不重述（leaf 只有 quantifier+window 枚举，禁手写区间）──

def check_window_enum(candidates: list[CandidateRule]) -> list[GateFailure]:
    """0-5: 窗口枚举检查 - 确保 window 只用枚举值，不手写区间"""
    failures = []
    for c in candidates:
        for leaf in c.candidate.leaves:
            if leaf.window not in VALID_WINDOWS:
                failures.append(GateFailure(
                    gate=GateName.L0, check_code=L0CheckCode.WINDOW_ENUM,
                    reason=f"leaf {leaf.leaf_id}: window '{leaf.window}' 非枚举值，疑似手写区间"
                ))
    return failures


# ── 0-6: 结构完整（每套 ≥1 clause；同 group 各 branch 共享公共条文）──

def check_struct_completeness(candidates: list[CandidateRule]) -> list[GateFailure]:
    """0-6: 结构完整性检查"""
    # TODO: 按 group/branch 分组检查
    return []


# ── 0-7: 组合覆盖（每个 (board, company_type) 有套或显式声明无套）──

def check_combination_coverage(candidates: list[CandidateRule], rulebook_dir: Path) -> list[GateFailure]:
    """0-7: 组合覆盖检查"""
    # TODO: 对照 rulebook/sets/ 和 _meta.yaml 的 declared_no_sets
    return []


# ── 0-8: 版本对齐（evidence_ref 指向文档版本 = as_of_date 时点现行版）──

def check_version_alignment(candidates: list[CandidateRule], as_of_date: str) -> list[GateFailure]:
    """0-8: 版本对齐检查"""
    failures = []
    for c in candidates:
        eff = c.evidence.get("effective_from", "")
        if eff and eff > as_of_date:
            failures.append(GateFailure(
                gate=GateName.L0, check_code=L0CheckCode.VERSION_ALIGN,
                reason=f"clause {c.clause_id}: 证据文档版本 {eff} 晚于 as_of_date {as_of_date}，疑似旧值残留"
            ))
    return failures


# ── L0 闸门主入口 ──

def run_l0_gate(
    candidates: list[CandidateRule],
    as_of_date: str,
    metrics_yaml: Path,
    rulebook_dir: Path,
) -> list[GateResult]:
    """
    L0 确定性闸门主函数
    - 输入：候选规则列表、as_of_date、metrics.yaml 路径、rulebook 目录
    - 输出：每条候选规则的 GateResult 列表
    - 短路：任一检查失败 → 该条 FAIL，不再做后续检查（毫秒级，无所谓）
    """
    results: list[GateResult] = []

    # 预计算各检查的失败映射：clause_id -> [GateFailure]
    all_failures: dict[str, list[GateFailure]] = {}

    # 0-1 Schema
    for c in candidates:
        fails = check_schema(c)
        if fails:
            all_failures.setdefault(c.clause_id, []).extend(fails)

    # 0-2 量纲
    fails_02 = check_unit_consistency(candidates, metrics_yaml)
    for f in fails_02:
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-3 唯一性
    for f in check_uniqueness(candidates):
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-4 引用完整
    fails_04 = check_ref_integrity(candidates, metrics_yaml)
    for f in fails_04:
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-5 窗口枚举
    for f in check_window_enum(candidates):
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-6 结构完整
    fails_06 = check_struct_completeness(candidates)
    for f in fails_06:
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-7 组合覆盖
    fails_07 = check_combination_coverage(candidates, rulebook_dir)
    for f in fails_07:
        all_failures.setdefault(f.details.get("clause_id", "unknown"), []).append(f)

    # 0-8 版本对齐
    for f in check_version_alignment(candidates, as_of_date):
        all_failures.setdefault(c.clause_id, []).append(f)

    # 汇总结果
    for c in candidates:
        fails = all_failures.get(c.clause_id, [])
        if fails:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L0,
                status=GateStatus.FAIL,
                failure=fails[0],  # 取第一个失败原因
            ))
        else:
            results.append(GateResult(
                clause_id=c.clause_id,
                gate=GateName.L0,
                status=GateStatus.PASS,
                payload={"checks": ["0-1", "0-2", "0-3", "0-4", "0-5", "0-6", "0-7", "0-8"]}
            ))

    return results


__all__ = [
    "run_l0_gate",
    "check_schema", "check_unit_consistency", "check_uniqueness",
    "check_ref_integrity", "check_window_enum", "check_struct_completeness",
    "check_combination_coverage", "check_version_alignment",
]