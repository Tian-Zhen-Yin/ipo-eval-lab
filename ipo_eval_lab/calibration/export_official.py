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


@dataclass
class ExportReport:
    """导出结果报告。"""
    exported_files: list[str] = field(default_factory=list)
    exported_clauses: int = 0
    skipped_sets: list[dict[str, Any]] = field(default_factory=list)
    rejected_clauses: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exported_files": list(self.exported_files),
            "exported_clauses": self.exported_clauses,
            "skipped_sets": list(self.skipped_sets),
            "rejected_clauses": list(self.rejected_clauses),
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


def _signed_keys(records: list[dict[str, Any]]) -> tuple[set[str], set[str]]:
    """从签核记录取 (已签核键, 已打回键)。

    记录 append-only，同一 key 可多次签核 → 取**最后一次**为准：
    最后一次是 accepted/amended → 算已签；是 rejected → 算打回。
    """
    latest: dict[str, str] = {}
    for r in records:
        latest[r["key"]] = r["decision"]
    signed = {k for k, d in latest.items() if d in ("accepted", "amended")}
    rejected = {k for k, d in latest.items() if d == "rejected"}
    return signed, rejected


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
    signed, rejected = _signed_keys(records)

    # 按 (board, company_type, group_no) 聚成套
    sets: dict[tuple[str, str, Optional[int]], list[dict[str, Any]]] = {}
    for c in candidates:
        ctx = c["context"]
        k = (ctx["board"], ctx["company_type"], ctx.get("group_no"))
        sets.setdefault(k, []).append(c)

    report = ExportReport()

    # 同一 (company_type, group_no) 的沪深镜像 → 合并为一个 group（R3）
    merged: dict[tuple[str, Optional[int]], dict[str, Any]] = {}
    for (board, ctype, gno), cl in sets.items():
        key = (ctype, gno)
        g = merged.setdefault(key, {
            "scope": "set",
            "group_id": None,
            "display": None,
            "boards": [],
            "company_type": ctype,
            "group_no": gno,
            "effective_from": None,
            "law_refs": [],
            "shared_clauses": [],
            "branches": [],
            "_clause_ids": set(),       # 同文合并去重用
            "_pending": [],             # 未签核条款（跨板合并后的完整清单）
            "_rejected": [],            # 已打回条款
        })
        if board not in g["boards"]:
            g["boards"].append(board)

        for c in cl:
            ckey = f"{board}:{c['clause_id']}"
            if ckey in rejected:
                g["_rejected"].append(ckey)
                continue
            if ckey not in signed:
                g["_pending"].append(ckey)
                continue
            # 同文合并：clause_id 相同（沪深镜像同文）→ 只留一份
            if c["clause_id"] in g["_clause_ids"]:
                continue
            clause = _clause_to_yaml(c, c["clause_id"])
            if clause is None:
                continue
            g["_clause_ids"].add(c["clause_id"])
            g["shared_clauses"].append(clause)
            if clause["law_ref"] not in g["law_refs"]:
                g["law_refs"].append(clause["law_ref"])

    # 完整性判定：**合并后**再判——沪深镜像里一块签了另一块没签，
    # 合并出的套同样不完整（条款在两块板上是同一条，签一半等于没签）。
    for (ctype, gno), g in merged.items():
        if g["_rejected"]:
            report.rejected_clauses.extend(g["_rejected"])
        # 未签核 **或** 已打回 → 整个套不导出。
        # 打回 = 这条要改，改完要重走签核；把它跳过等于把「待改」当成「已签」，
        # 导出的套会缺一条条件——比不导出更危险（引擎据此会判主体不达标）。
        if g["_pending"] or g["_rejected"]:
            report.skipped_sets.append({
                "board": ",".join(g["boards"]), "company_type": ctype, "group_no": gno,
                "reason": ("条款被打回，须重走签核" if g["_rejected"]
                           else "条款未全部签核"),
                "pending_clause_keys": g["_pending"],
                "rejected_clause_keys": g["_rejected"],
            })
            g["_skip"] = True
            continue
        if not g["shared_clauses"]:
            g["_skip"] = True

    # 组装 group：group_id / display / effective_from 需要外部信息
    for (ctype, gno), g in merged.items():
        if g.get("_skip"):
            continue
        boards = sorted(g["boards"])
        # group_id：沪深合并时取第一块板的 id（R3 同文合并）
        gid = None
        for (b, ct, gn), cl in sets.items():
            if ct == ctype and gn == gno and b == boards[0]:
                gid = cl[0]["context"]["group_id"]
                break
        g["group_id"] = gid or f"{boards[0].lower()}_{ctype}_g{gno}"
        g["display"] = g.get("display") or f"{ctype} 标准 {gno}"
        g["effective_from"] = g.get("effective_from") or "2026-04-30"
        g["law_refs"] = sorted(g["law_refs"])

    # 按 (board, company_type) 分文件落盘
    files: dict[str, list[dict[str, Any]]] = {}
    for (ctype, gno), g in merged.items():
        if g.get("_skip"):
            continue
        # 文件名按 boards 首个板块
        name = f"{g['boards'][0].lower()}_{ctype}.yaml"
        files.setdefault(name, []).append(g)

    for name, groups in sorted(files.items()):
        path = out_dir / name
        report.exported_files.append(str(path))
        report.exported_clauses += sum(len(g["shared_clauses"]) for g in groups)
        if dry_run:
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        header = (
            f"# 正式规则库（由签核记录导出，勿手工编辑）\n"
            f"# 来源：{candidates_path.name} + {records_path.name}\n"
            f"# ADR-0005 R3：正式库只能由人工签核产生——本文件只含已签核条款\n"
        )
        body = yaml.safe_dump_all(
            [_clean(g) for g in groups],
            allow_unicode=True, sort_keys=False, default_flow_style=False,
        )
        path.write_text(header + body, encoding="utf-8")

    return report


def _clean(g: dict[str, Any]) -> dict[str, Any]:
    """去掉内部标记字段，按正式库字段序输出。"""
    order = ["scope", "group_id", "display", "boards", "company_type", "group_no",
             "effective_from", "law_refs", "shared_clauses", "branches"]
    return {k: g[k] for k in order if k in g}


__all__ = ["export_official_rulebook", "ExportReport"]
