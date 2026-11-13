"""
签核 → 正式库导出（ADR-0005 R3 两级入库的第二级）

ADR-0005：**正式库只能由人工签核产生**。本模块是这条约束的执行点——
导出的每一条都必须有对应的签核记录（accepted 或 amended），未签核的条款
**一律不进正式库**。

「候选库 → 人工签核 → 正式库」这条链路的三个环节各自负责：
- 候选库（calibration/l1a/output/candidates_merged.jsonl）：机器可入；
- 签核队列（本模块的输入，见 signoff.py）：给人看；
- 正式库（rulebook/sets/*.yaml）：**唯一可被引擎加载**。

## 为什么「不完整套」不能静默导出

一条套若只有部分条款签核通过，把已签的那部分导出会得到一个**看起来完整、
实则缺条件**的套——比不导出更危险（引擎会据此判「不达标」，而缺口其实是
未签完导致的）。故本模块：
- 套内条款未全部签核 → 该套**不导出**，并在报告里点名缺哪几条；
- 被签核**打回**（rejected）的条款 → 该套不导出（打回意味着这条要改，
  改了要重新走签核，不是「跳过这一条」）。

## 落盘形态

按 (board, company_type) 分文件：`rulebook/sets/<board>_<company_type>.yaml`。
沪深同文合并（R3）：SSE-MB 与 SZSE-MB 的同一条款共用 clause_id——导出时
合并为一个 group（boards 列两个），镜像条款（若内容不同）不得合并。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .signoff import AUTO_EXEMPT_REVIEWER


class ExportError(Exception):
    """导出前置校验不过——候选库结构有问题，不能导出。

    与「套不完整所以跳过」不同：套不完整是**校准流程没走完**（可继续），
    结构矛盾是**数据自相矛盾**（导出结果必错，必须先修数据）。
    """


@dataclass
class ExportReport:
    """导出结果报告。"""
    exported_files: list[str] = field(default_factory=list)
    exported_clauses: int = 0
    skipped_sets: list[dict[str, Any]] = field(default_factory=list)
    rejected_clauses: list[str] = field(default_factory=list)
    auto_exempt_clauses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exported_files": list(self.exported_files),
            "exported_clauses": self.exported_clauses,
            "skipped_sets": list(self.skipped_sets),
            "rejected_clauses": list(self.rejected_clauses),
            "auto_exempt_clauses": list(self.auto_exempt_clauses),
        }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def _signed_keys(records: list[dict[str, Any]]) -> tuple[set[str], set[str], set[str]]:
    """从签核记录取 (已签核键, 已打回键, 免签键)。

    记录 append-only，同一 key 可多次签核 → 取**最后一次**为准：
    最后一次是 accepted/amended → 算已签；是 rejected → 算打回。

    免签键单列：reviewer=auto-exempt 的记录是 ADR-0009 决策 1 的抽检免签凭据，
    它让免签条款能进正式库（否则其所在的套会被判为不完整而整个不导出），
    但审计报告要能区分「人核通过」与「按规则免签」——两者不是一回事。
    """
    latest: dict[str, dict[str, Any]] = {}
    for r in records:
        latest[r["key"]] = r
    signed = {k for k, r in latest.items() if r["decision"] in ("accepted", "amended")}
    rejected = {k for k, r in latest.items() if r["decision"] == "rejected"}
    auto = {k for k, r in latest.items()
            if r.get("reviewer") == AUTO_EXEMPT_REVIEWER and r["decision"] == "accepted"}
    return signed, rejected, auto


def _clause_to_yaml(cand: dict[str, Any], clause_id: str) -> Optional[dict[str, Any]]:
    """候选 → 正式库 clause 形态（去掉证据字段 quote/threshold_text）。"""
    c = cand["clause"]
    if c["clause_id"] != clause_id:
        return None
    out: dict[str, Any] = {
        "clause_id": clause_id,
        "law_ref": c["law_ref"],
        "logic": c.get("logic", "all"),
    }
    if c.get("display"):
        out["display"] = c["display"]
    # 豁免标注（ADR-0008）随条款进正式库——它是对**本条款**的法定不适用标注，
    # 与阈值同属规则语义，不是证据字段（quote/threshold_text 才是，那些留在候选库）。
    if c.get("exemptions"):
        out["exemptions"] = c["exemptions"]
    leaves = []
    for lf in c.get("leaves", []):
        leaves.append({
            "leaf_id": lf["leaf_id"],
            "item_ref": lf["item_ref"],
            "op": lf["op"],
            "threshold": {"value": lf["threshold"], "format": lf["threshold_format"]},
        })
    out["leaves"] = leaves
    return out


def export_official_rulebook(
    candidates_path: Path,
    records_path: Path,
    out_dir: Path,
    dry_run: bool = False,
) -> ExportReport:
    """把已签核条款导出为正式规则库 YAML。

    candidates_path: 候选库 JSONL。
    records_path: 签核记录 JSONL（append-only）。
    out_dir: 正式库目录（通常 rulebook/sets）。
    dry_run: 只出报告不落盘。
    """
    candidates = _load_jsonl(candidates_path)
    records = _load_jsonl(records_path)
    signed, rejected, auto_exempt = _signed_keys(records)

    # ── 聚合键 = group_id（不是 (company_type, group_no)）──
    # group_id 已由候选库归一好：沪深同文共用 cn_main_*，科创 star_*，创业板
    # chinext_*，北交所 bse_*。用 (company_type, group_no) 当键会把**不同板块**
    # 的同一套号并成一个 group（主板第 1 套 vs 科创板第 1 套），导出的正式库
    # ��是错的——一个 group 里混着几套上市标准，引擎加载即失去意义。
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        gid = c["context"]["group_id"]
        groups.setdefault(gid, []).append(c)

    # 归一一致性校验：group_id 是主键，但它归一得对不对，导出器得自己查一遍。
    # 唯一性不变量 = **(board, company_type, group_no) → 唯一 group_id**：
    # - (company_type, group_no) 跨板块**本就不唯一**（主板第1套 ≠ 科创板第1套），
    #   按它查会把所有板块的同号套误报成冲突；
    # - 真正的错法：同一板块同一套号被两个 group_id 占用（同一套被拆成两个套，
    #   引擎的套级引用与差距画像会指向两个套）。
    # - 同一 group_id 内 (company_type, group_no) 必须一致——一个 group 里混着
    #   不同套号的条款，引擎按「套」判定即失去意义。
    # 沪深同文共用 group_id 是**允许**的（两块板映射到同一 group_id，不冲突）。
    _no_conflicts: list[str] = []
    for gid, cl in groups.items():
        slots = {(c["context"]["company_type"], c["context"].get("group_no")) for c in cl}
        if len(slots) > 1:
            _no_conflicts.append(
                f"group_id {gid} 内含多个套号 {sorted(slots)}（套号应唯一）"
            )
    _seen_slot: dict[tuple[str, str, Any], str] = {}
    for c in candidates:
        ctx = c["context"]
        slot = (ctx["board"], ctx["company_type"], ctx.get("group_no"))
        prev = _seen_slot.get(slot)
        if prev is not None and prev != ctx["group_id"]:
            _no_conflicts.append(
                f"套号 {slot} 被两个 group_id 占用：{prev} / {ctx['group_id']}"
            )
        _seen_slot.setdefault(slot, ctx["group_id"])
    if _no_conflicts:
        raise ExportError(
            "候选库 group_id 归一不一致，导出会得到错乱的套结构：\n  - "
            + "\n  - ".join(_no_conflicts)
        )

    report = ExportReport()

    merged: dict[str, dict[str, Any]] = {}
    for gid, cl in groups.items():
        ctx0 = cl[0]["context"]
        g: dict[str, Any] = {
            "scope": ctx0.get("scope", "set"),
            "group_id": gid,
            "display": None,
            "boards": [],
            "company_type": ctx0["company_type"],
            "group_no": ctx0.get("group_no"),
            "effective_from": None,
            "law_refs": [],
            "shared_clauses": [],
            "branches": [],
            "_clause_ids": set(),       # 同文合并去重用（限本 group 内）
            "_branch_map": {},         # branch_id → branch 草稿
            "_pending": [],             # 未签核条款（跨板合并后的完整清单）
            "_rejected": [],            # 已打回条款
            "_auto": [],                # 按规则免签（抽检未落入）的条款
        }
        merged[gid] = g

        for c in cl:
            ctx = c["context"]
            board = ctx["board"]
            if board not in g["boards"]:
                g["boards"].append(board)
            # 组级硬筛（scope=positioning 专用）：任一候选的 context 携带即提升为组字段
            if ctx.get("hard_filters"):
                g["hard_filters"] = ctx["hard_filters"]

            # 生效日取候选库的 evidence.effective_from（现行版规则的生效日，
            # 随 doc_version 一起落库）。**不硬编码**——硬编码会让所有套在
            # as-of 闸门前被剔除：闸门按 effective_from 与评估基准日比较，
            # 生效日错了，规则库对任何历史评估都不可用。
            eff = (c.get("evidence") or {}).get("effective_from")
            if eff and (g["effective_from"] is None or eff < g["effective_from"]):
                g["effective_from"] = eff

            ckey = f"{board}:{c['clause_id']}"
            if ckey in rejected:
                g["_rejected"].append(ckey)
                continue
            if ckey not in signed:
                g["_pending"].append(ckey)
                continue
            if ckey in auto_exempt:
                g["_auto"].append(ckey)

            # 同文合并：clause_id 相同（沪深镜像同文）→ 只留一份。
            # 去重**限本 group 内**——不同板块的 clause_id 不同，
            # 但若跨 group 同名（如两个板块都用 cn_main_g1_c1），必须各自保留。
            if c["clause_id"] in g["_clause_ids"]:
                continue
            clause = _clause_to_yaml(c, c["clause_id"])
            if clause is None:
                continue
            g["_clause_ids"].add(c["clause_id"])
            if clause["law_ref"] not in g["law_refs"]:
                g["law_refs"].append(clause["law_ref"])

            # role=shared → 公共条文；role=branch → 挂到对应支路。
            # 两者语义不同（不变量 #6）：公共条文写一次，支路是择一路径。
            if ctx.get("role") == "branch":
                bid = ctx.get("branch_id") or f"{gid}-b1"
                br = g["_branch_map"].get(bid)
                if br is None:
                    br = {"set_id": bid, "display": None,
                          "aliases": {"midas": []}, "clauses": []}
                    g["_branch_map"][bid] = br
                br["clauses"].append(clause)
            else:
                g["shared_clauses"].append(clause)

    # 完整性判定：**合并后**再判——沪深镜像里一块签了另一块没签，
    # 合并出的套同样不完整（条款在两块板上是同一条，签一半等于没签）。
    for gid, g in merged.items():
        if g["_rejected"]:
            report.rejected_clauses.extend(g["_rejected"])
        # 未签核 **或** 已打回 → 整个套不导出。
        # 打回 = 这条要改，改完要重走签核；把它跳过等于把「待改」当成「已签」，
        # 导出的套会缺一条条件——比不导出更危险（引擎据此会判主体不达标）。
        if g["_pending"] or g["_rejected"]:
            report.skipped_sets.append({
                "board": ",".join(g["boards"]), "company_type": g["company_type"],
                "group_no": g["group_no"], "group_id": gid,
                "reason": ("条款被打回，须重走签核" if g["_rejected"]
                           else "条款未全部签核"),
                "pending_clause_keys": g["_pending"],
                "rejected_clause_keys": g["_rejected"],
            })
            g["_skip"] = True
            continue
        if not g["shared_clauses"] and not g["_branch_map"]:
            g["_skip"] = True
            continue
        # 只有真正导出的套才把免签条款计入报告：被跳过的套没有入库。
        report.auto_exempt_clauses.extend(g["_auto"])

    # 组装 group：display / effective_from / 支路顺序需要外部信息
    for gid, g in merged.items():
        if g.get("_skip"):
            continue
        boards = sorted(g["boards"])
        g["display"] = g.get("display") or f"{g['company_type']} 标准 {g['group_no']}"
        # 生效日已在上面从候选库 evidence 取到；缺失时不得臆造——
        # 臆造一个日期会让 as-of 闸门误判规则适用性。缺失即导出该套失败。
        if not g["effective_from"]:
            report.skipped_sets.append({
                "board": ",".join(g["boards"]), "company_type": g["company_type"],
                "group_no": g["group_no"], "group_id": gid,
                "reason": "候选库缺 effective_from（无法定生效日）",
                "pending_clause_keys": [], "rejected_clause_keys": [],
            })
            g["_skip"] = True
            continue
        g["law_refs"] = sorted(g["law_refs"])
        # 支路按 branch_id 排序，保证导出结果稳定可复现
        g["branches"] = [g["_branch_map"][bid] for bid in sorted(g["_branch_map"])]
        # 无支路的套：把公共条文并入唯一支路——Branch 模型要求至少 1 个支路，
        # 且引擎按「支路择一」判定；一个没有支路的套无法表达。
        if not g["branches"]:
            g["branches"] = [{
                "set_id": f"{gid}-b1", "display": None,
                "aliases": {"midas": []},
                "clauses": list(g["shared_clauses"]),
            }]
            g["shared_clauses"] = []

    # 按 (板块, 企业类型) 分文件落盘。
    # 板块取 group 的 boards 首板 —— 用 group_id 前缀切不可靠
    # （cn_main_* / cn_redchip_* 的前缀都是 "cn"，切不出板块）。
    files: dict[str, list[dict[str, Any]]] = {}
    for gid, g in merged.items():
        if g.get("_skip"):
            continue
        prefix = sorted(g["boards"])[0].lower()
        if g.get("scope") == "positioning":
            name = f"{prefix}_positioning.yaml"
        else:
            name = f"{prefix}_{g['company_type']}.yaml"
        files.setdefault(name, []).append(g)

    for name, gl in sorted(files.items()):
        path = out_dir / name
        report.exported_files.append(str(path))
        report.exported_clauses += sum(
            len(g["shared_clauses"]) + sum(len(b["clauses"]) for b in g["branches"])
            for g in gl
        )
        if dry_run:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        header = (
            f"# 正式规则库（由签核记录导出，勿手工编辑）\n"
            f"# 来源：{candidates_path.name} + {records_path.name}\n"
            f"# ADR-0005 R3：正式库只能由人工签核产生——本文件只含已签核条款\n"
        )
        # 一个文件 = **一个 YAML 列表文档**（loader 用 safe_load 读单文档，
        # 写成多文档流会直接报 "expected a single document"）。
        body = yaml.safe_dump(
            [_clean(g) for g in gl],
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        )
        path.write_text(header + body, encoding="utf-8")

    return report


def _clean(g: dict[str, Any]) -> dict[str, Any]:
    """去掉内部标记字段，按正式库字段序输出。"""
    order = ["scope", "group_id", "display", "boards", "company_type", "group_no",
             "effective_from", "law_refs", "hard_filters", "shared_clauses", "branches"]
    return {k: g[k] for k in order if k in g}


__all__ = ["export_official_rulebook", "ExportReport"]
