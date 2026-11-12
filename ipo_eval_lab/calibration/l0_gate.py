"""
M1 校准管线 L0 确定性闸门（设计 0003 §3）

8 项 lint，零 AI，毫秒级，不过 = 绝对拦截。
判据来自规则库白名单（rulebook_refs.py），不在本文件重写业务口径。
"""

from pathlib import Path
from collections import Counter, defaultdict
from typing import Any

from .models import (
    GateName, GateStatus, GateResult, GateFailure, L0CheckCode, CandidateRule,
)
from .rulebook_refs import (
    load_metrics, load_items, item_window_token_ok, item_required_format,
    board_company_types, declared_no_sets,
)

VALID_OPS = {"eq", "ne", "gt", "ge", "lt", "le"}
VALID_LOGICS = {"all", "any"}
VALID_FORMATS = {"number", "percent", "integer", "boolean"}
VALID_SCOPES = {"set", "issuance", "positioning"}
VALID_ROLES = {"shared", "branch"}


def _fail(rule: CandidateRule, code: L0CheckCode, reason: str, **details) -> GateFailure:
    return GateFailure(
        gate=GateName.L0, check_code=code, reason=reason,
        details={"clause_id": rule.clause_id, **details},
    )


# ── 0-1: Schema 合法 ──

def check_schema(rule: CandidateRule) -> list[GateFailure]:
    fails: list[GateFailure] = []
    clause = rule.clause

    if clause.logic not in VALID_LOGICS:
        fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                           f"logic 非法：{clause.logic}，合法值 {sorted(VALID_LOGICS)}"))

    # board 合法性由 0-7 对照 _meta.yaml 校验（单点，不在 0-1 重复硬编码——
    # 大小写如 ChiNext 以 _meta 为准，曾因硬编码 CHINEXT 误拦）

    if rule.context.scope not in VALID_SCOPES:
        fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                           f"scope 非法：{rule.context.scope}"))

    if rule.context.role not in VALID_ROLES:
        fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                           f"role 非法：{rule.context.role}"))

    if not clause.law_ref or "#" not in clause.law_ref:
        fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                           f"law_ref 格式应为 law_id#article：{clause.law_ref!r}"))

    for leaf in clause.leaves:
        if leaf.op not in VALID_OPS:
            fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                               f"leaf {leaf.leaf_id}: op 非法 {leaf.op}"))
        if leaf.threshold_format not in VALID_FORMATS:
            fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                               f"leaf {leaf.leaf_id}: threshold_format 非法 {leaf.threshold_format}"))
        if not leaf.quote.strip():
            fails.append(_fail(rule, L0CheckCode.SCHEMA_VALID,
                               f"leaf {leaf.leaf_id}: quote 为空（evidence 必填）"))

    return fails


# ── 0-2: 量纲一致（item → metric.unit → 允许的 threshold.format）──

def check_unit_consistent(
    rule: CandidateRule, items: dict[str, dict], metrics: dict[str, dict]
) -> list[GateFailure]:
    fails: list[GateFailure] = []
    for leaf in rule.clause.leaves:
        item = items.get(leaf.item_ref)
        if not item:
            continue  # 0-4 负责报悬空引用
        required = item_required_format(item, metrics)
        if required and leaf.threshold_format != required:
            fails.append(_fail(
                rule, L0CheckCode.UNIT_CONSISTENT,
                f"leaf {leaf.leaf_id}: item {leaf.item_ref} 量纲要求 format={required}，"
                f"候选给 {leaf.threshold_format}（metric={item.get('metric_ref')}）",
            ))
        if leaf.threshold_format == "percent" and not (0 < float(leaf.threshold) <= 1):
            fails.append(_fail(
                rule, L0CheckCode.UNIT_CONSISTENT,
                f"leaf {leaf.leaf_id}: percent 阈值应归一为小数 (0,1]，候选 {leaf.threshold}",
            ))
    return fails


# ── 0-3: 唯一性 ──

def check_uniqueness(rules: list[CandidateRule]) -> list[GateFailure]:
    """
    0-3：唯一性。按 (board, clause_id) 判——沪深同文合并共享 group（R3）意味着
    同一 clause_id 会在两个 board 各有一条转写（quote 各摘各的原文），这是设计
    而非重复；同一 board 内重复才是转写重复。
    """
    fails: list[GateFailure] = []
    keys = [(r.context.board, r.clause_id) for r in rules]
    dup_keys = {k for k, n in Counter(keys).items() if n > 1}
    for board, cid in dup_keys:
        rule = next(r for r in rules if r.context.board == board and r.clause_id == cid)
        fails.append(_fail(rule, L0CheckCode.UNIQUENESS,
                           f"同一 board 内 clause_id 重复：{board}:{cid} 出现 {keys.count((board, cid))} 次"))

    for r in rules:
        leaf_ids = [lf.leaf_id for lf in r.clause.leaves]
        dup_leaves = {lid for lid, n in Counter(leaf_ids).items() if n > 1}
        for lid in dup_leaves:
            fails.append(_fail(r, L0CheckCode.UNIQUENESS, f"leaf_id 重复：{lid}"))
    return fails


# ── 0-4: 引用完整 ──

def check_ref_integrity(
    rule: CandidateRule, items: dict[str, dict], metrics: dict[str, dict],
) -> list[GateFailure]:
    fails: list[GateFailure] = []
    for leaf in rule.clause.leaves:
        item = items.get(leaf.item_ref)
        if not item:
            fails.append(_fail(
                rule, L0CheckCode.REF_INTEGRITY,
                f"leaf {leaf.leaf_id}: item_ref '{leaf.item_ref}' 不在 items.yaml 白名单（{len(items)} 项）",
            ))
            continue
        metric_ref = item.get("metric_ref")
        if metric_ref and metric_ref not in metrics:
            fails.append(_fail(
                rule, L0CheckCode.REF_INTEGRITY,
                f"leaf {leaf.leaf_id}: item {leaf.item_ref} 的 metric_ref '{metric_ref}' 不在 metrics.yaml",
            ))
    if not rule.source.text.strip():
        fails.append(_fail(rule, L0CheckCode.REF_INTEGRITY, "source.text 为空（原文引用缺失）"))
    return fails


# ── 0-5: 窗口不重述 ──

def check_window_enum(rule: CandidateRule, items: dict[str, dict]) -> list[GateFailure]:
    fails: list[GateFailure] = []
    for leaf in rule.clause.leaves:
        item = items.get(leaf.item_ref)
        if not item:
            continue
        ok, why = item_window_token_ok(item)
        if not ok:
            fails.append(_fail(rule, L0CheckCode.WINDOW_ENUM,
                               f"item {leaf.item_ref} 窗口不合规：{why}"))
    return fails


# ── 0-6: 结构完整 ──

def check_struct_complete(rules: list[CandidateRule]) -> list[GateFailure]:
    """
    0-6：结构完整。不变量 #6 修订版（batch2 校准勘误，2026-11-12）：
    - 旧版「多 branch 必须有 shared_clauses」会误拦零公共条文的多支路套
      （如主板 3.1.4 红筹：2000亿 或 200亿+技术优势，两支路无交集）。
    - 修订为：**全部**支路都含相同叶签名（item_ref, op, threshold）而未提升到
      shared → 拦（这才是「公共条文该写一次」要抓的转写噪音）；部分支路重叠
      或零重叠 → 放行。
    """
    fails: list[GateFailure] = []
    for r in rules:
        if len(r.clause.leaves) < 1:
            fails.append(_fail(r, L0CheckCode.STRUCT_COMPLETE, "条文无叶"))

    by_group: dict[str, list[CandidateRule]] = defaultdict(list)
    for r in rules:
        by_group[r.context.group_id].append(r)

    for group_id, group_rules in by_group.items():
        first = group_rules[0]
        branch_rules = defaultdict(list)   # branch_id -> rules
        shared_leaf_sigs: set[tuple] = set()
        for r in group_rules:
            if r.context.role == "branch" and r.context.branch_id:
                branch_rules[r.context.branch_id].append(r)
            elif r.context.role == "shared":
                shared_leaf_sigs.update(
                    (lf.item_ref, lf.op, lf.threshold) for lf in r.clause.leaves
                )

        if not branch_rules:
            fails.append(_fail(first, L0CheckCode.STRUCT_COMPLETE,
                               f"套 {group_id} 没有任何 branch（至少 1 条支路）"))
            continue

        # 各支路叶签名集合（单支路无「共有」可言，跳过提升检查）
        sigs_per_branch = [
            {(lf.item_ref, lf.op, lf.threshold)
             for r in rs for lf in r.clause.leaves}
            for rs in branch_rules.values()
        ]
        common = (set.intersection(*sigs_per_branch)
                  if len(sigs_per_branch) > 1 else set())
        unhoisted = common - shared_leaf_sigs
        if unhoisted:
            fails.append(_fail(first, L0CheckCode.STRUCT_COMPLETE,
                               f"套 {group_id} 全部支路共有叶 {sorted(unhoisted)} "
                               f"未提升到 shared_clauses（不变量 #6：公共条文写一次）"))
    return fails


# ── 0-7: 组合覆盖 ──

def check_combination_coverage(
    rules: list[CandidateRule], rulebook_dir: Path,
) -> list[GateFailure]:
    """
    每个 (board, company_type) 有套或被显式声明无套。
    只对候选里出现的组合做正向校验（反向漏配由 rulebook lint L2 管）。
    """
    fails: list[GateFailure] = []
    boards, company_types = board_company_types(rulebook_dir)
    if not boards or not company_types:
        return fails  # 无元数据时不臆断

    declared = {tuple(x) for x in declared_no_sets(rulebook_dir)}
    present = {(r.context.board, r.context.company_type) for r in rules}

    for board, ctype in present:
        rule = next(r for r in rules if r.context.board == board
                    and r.context.company_type == ctype)
        if board not in boards:
            fails.append(_fail(rule, L0CheckCode.COMBINATION_COVERAGE,
                               f"board '{board}' 不在 _meta.yaml boards"))
        if ctype not in company_types:
            fails.append(_fail(rule, L0CheckCode.COMBINATION_COVERAGE,
                               f"company_type '{ctype}' 不在 _meta.yaml company_types"))
        if (board, ctype) in declared:
            fails.append(_fail(rule, L0CheckCode.COMBINATION_COVERAGE,
                               f"({board},{ctype}) 已声明无套，候选不应出现该组合"))
    return fails


# ── 0-8: 版本对齐 ──

def check_version_alignment(rule: CandidateRule, as_of_date: str) -> list[GateFailure]:
    fails: list[GateFailure] = []
    effective_from = str(rule.evidence.get("effective_from", "") or "")
    if not effective_from:
        fails.append(_fail(rule, L0CheckCode.VERSION_ALIGN,
                           "evidence 缺 effective_from，无法校验版本对齐"))
    elif effective_from > as_of_date:
        fails.append(_fail(rule, L0CheckCode.VERSION_ALIGN,
                           f"证据文档生效日 {effective_from} 晚于 as_of {as_of_date}"))

    doc_version = str(rule.evidence.get("doc_version", "") or "")
    as_of_version = str(rule.evidence.get("as_of_doc_version", "") or "")
    if doc_version and as_of_version and doc_version != as_of_version:
        fails.append(_fail(rule, L0CheckCode.VERSION_ALIGN,
                           f"证据版本 {doc_version} ≠ as_of 时点现行版 {as_of_version}"))
    return fails


# ── 主入口 ──

def run_l0_gate(
    rules: list[CandidateRule],
    as_of_date: str,
    rulebook_dir: Path,
) -> list[GateResult]:
    items = load_items(rulebook_dir)
    metrics = load_metrics(rulebook_dir)

    failures: dict[str, list[GateFailure]] = defaultdict(list)
    for r in rules:
        for f in check_schema(r):
            failures[r.clause_id].append(f)
        for f in check_unit_consistent(r, items, metrics):
            failures[r.clause_id].append(f)
        for f in check_ref_integrity(r, items, metrics):
            failures[r.clause_id].append(f)
        for f in check_window_enum(r, items):
            failures[r.clause_id].append(f)
        for f in check_version_alignment(r, as_of_date):
            failures[r.clause_id].append(f)

    for f in check_uniqueness(rules):
        failures[f.details.get("clause_id", "")].append(f)
    for f in check_struct_complete(rules):
        failures[f.details.get("clause_id", "")].append(f)
    for f in check_combination_coverage(rules, rulebook_dir):
        failures[f.details.get("clause_id", "")].append(f)

    results: list[GateResult] = []
    for r in rules:
        fails = failures.get(r.clause_id, [])
        if fails:
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L0, status=GateStatus.FAIL,
                failure=fails[0],
                payload={"all_failures": [f.model_dump() for f in fails]},
            ))
        else:
            results.append(GateResult(
                clause_id=r.clause_id, gate=GateName.L0, status=GateStatus.PASS,
                payload={"checks": [c.value for c in L0CheckCode]},
            ))
    return results


__all__ = [
    "run_l0_gate", "check_schema", "check_unit_consistent", "check_uniqueness",
    "check_ref_integrity", "check_window_enum", "check_struct_complete",
    "check_combination_coverage", "check_version_alignment",
]
