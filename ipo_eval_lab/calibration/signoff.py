"""
签核队列（ADR-0005 R3 两级入库的「人工签核」环节）

两级入库：**候选库（机器可入）──人工签核──→ 正式库（唯一可被引擎加载）**。
本模块负责签核这一环节的**队列构造、签核记录落盘、状态查询**三件事，不做判定——
判定是人做的（ADR-0005：正式库只能由人工签核产生）。

## 分层（为什么不全签、也不全不签）

ADR-0005 首批要求 100% 人核；用户 2026-11-12 拍板「黄金集先签 + 风险分层抽检」。
本模块把这句话落成**可复算的分层规则**——分层依据全部来自可验证事实（黄金集
covered 标记 / 闸门结果 / midas 差异类别），不来自模型自报置信度。

三档（**两档在条款级、一档在套级**——混在一起会让人去签不存在的东西）：

- **A 必核（条款级）**：条款本身有异常——校准闸门失败，或 midas 快照非 exact
  （value_diff / structure_diff）。按设计 0003 §6，midas 是「证人不是法官」，
  不一致必有人看一眼。
- **B 必核（套级裁定）**：黄金集 covered=false 的套（无法律锚点，如创业板/科创板
  redchip_listed——原文只覆盖「尚未在境外上市」红筹），以及黄金集 gaps 里点名的
  未编码项。**这类不是「机器可信」问题，而是法律适用性问题**，必须有人裁定，
  不得靠抽样稀释。裁定的对象是**套**（「这个套该不该存在、依据在哪」），不是
  条款——一个套若根本无法律依据，签它的每一条条款都没有意义。
- **C 抽检（条款级）**：闸门全绿且 L3 exact 的条款。按比例抽样，
  抽检比例与随机种子入档（可复现、可审计）。

## 为什么「黄金集覆盖」本身不构成必核

黄金集 `covered` 标记核的是**套结构**（43 套的支路数对不对、该套该不该存在），
不是**条款内容**（某条阈值抄对没有）。若把「落在黄金集组合内」直接当必核，
结果是 133 条全进 A 档、抽检档永远为空——「黄金集先签 + 风险分层抽检」就退化
成「全部先签」，分层名存实亡。

故分层只按**内容风险**切：闸门红 / midas 不一致 → 必核；两闸皆绿 → 抽样。
黄金集覆盖信息作为落档依据留在 reasons 里，供审核人参考，不单独决定档位。

实测当前批次（as_of 2026-11-12）：133 条中 53 条落 A 档（闸门红或 midas 差异），
80 条落 C 档。

## 为什么 B 档必须是套级

实测 133 条候选里，ChiNext/STAR 的 `redchip_listed` **一条都没有**——那两套在候选库
里根本没有条款。把 B 档打在条款上会出现两种荒谬结果：要么「裁定一个空套」，
要么因无条款而把 B 档悄悄抹掉（正好丢掉最需要裁的那几套）。故 B 档独立成
**套级裁定清单**（`SetAdjudication`），与条款级队列并列产出。


## 抽样的可复现性

抽样用**确定性哈希**（blake2b(clause_id + board + seed)）而非随机数——同一 seed
必得同一批抽检条款，重跑不改结果；换 seed 换批（可做第二轮抽检而不重叠）。

## 签核记录

每次签核落一条记录：谁、何时、对哪条、给了什么结论、附了什么依据。
记录是**追加**的（append-only）：同一条款可多次签核（改判留痕），取最后一次为准，
但历史不可删——「谁在什么时候把这条从通过改成了打回」必须查得到。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml


class SignoffTier(str, Enum):
    """签核档位（**条款级**）。

    分层只按**内容风险**，不按「是否落在黄金集组合内」——黄金集的 covered 核的是
    套结构，不是条款内容；把它当必核依据会让全部候选落 A 档、抽检档恒为空
    （ADR-0009 决策 1）。法律适用性裁定是**套级**的，不占条款档位。
    """
    A = "A"          # 必核：闸门失败 或 midas 快照非 exact
    C = "C"          # 抽检：闸门全绿且 midas 一致


class SetAdjudicationStatus(str, Enum):
    """套级裁定状态。"""
    PENDING = "pending"        # 未裁定
    CONFIRMED = "confirmed"    # 裁定成立（须补齐依据与条款）
    REJECTED = "rejected"      # 裁定不成立（该套不入规则库）


class SignoffStatus(str, Enum):
    """单条签核状态。"""
    PENDING = "pending"        # 未签
    ACCEPTED = "accepted"      # 签核通过 → 进正式库
    REJECTED = "rejected"      # 签核打回 → 不可进正式库
    AMENDED = "amended"        # 签核通过但有修改（修改内容随记录存）


class LegalQuestion(str, Enum):
    """B 档的裁定问句类型——裁定的是「法律适用性」，不是「抽取对不对」。"""
    NO_ANCHOR = "no_anchor"            # 原文库无对应标准条款
    UNENCODED_GAP = "unencoded_gap"    # 黄金集 gaps 点名的未编码项


@dataclass
class SignoffItem:
    """队列中的一条签核任务。"""
    clause_id: str
    board: str
    company_type: str
    group_no: Optional[int]
    tier: SignoffTier
    status: SignoffStatus = SignoffStatus.PENDING
    reasons: list[str] = field(default_factory=list)   # 为什么落这一档（可复算）
    source_article: str = ""                           # 原文条款号
    quote: str = ""                                    # 支撑引文（逐字）
    rendered: str = ""                                 # 渲染回中文（审阅用）
    l3_category: str = ""                              # midas 差异类别
    gates: dict[str, str] = field(default_factory=dict)  # 各闸状态
    notes: str = ""

    @property
    def key(self) -> str:
        """队列内唯一键：沪深镜像共享 clause_id，须带 board（R3 同文合并）。"""
        return f"{self.board}:{self.clause_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "clause_id": self.clause_id,
            "board": self.board,
            "company_type": self.company_type,
            "group_no": self.group_no,
            "tier": self.tier.value,
            "status": self.status.value,
            "reasons": list(self.reasons),
            "source_article": self.source_article,
            "quote": self.quote,
            "rendered": self.rendered,
            "l3_category": self.l3_category,
            "gates": dict(self.gates),
            "notes": self.notes,
        }


@dataclass
class SetAdjudication:
    """套级裁定项——B 档，独立于条款级队列。

    裁定的对象是「一个 (board, company_type, group_no) 套该不该进正式规则库」：
    - covered=false → 原文库无对应标准条款，须裁定法律依据是否存在；
    - gaps 点名的未编码项 → 须裁定豁免/例外语义如何编码。
    """
    board: str
    company_type: str
    group_no: Optional[int]
    question: LegalQuestion
    question_text: str
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    candidate_clause_count: int = 0     # 候选库里该套的条款数（0 = 候选库中无此套）
    snapshot_branches: Optional[int] = None   # midas 快照行数（仅供裁定参考）
    status: SetAdjudicationStatus = SetAdjudicationStatus.PENDING

    @property
    def key(self) -> str:
        """套级裁定键：套号 + 问句类型——同一套可能有多个待裁定点
        （如 ChiNext/redchip_unlisted 的套3 豁免 与 增长认定第三路径），
        只用套号会撞键。"""
        return f"{self.board}:{self.company_type}:{self.group_no}:{self.question.value}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "board": self.board,
            "company_type": self.company_type,
            "group_no": self.group_no,
            "question": self.question.value,
            "question_text": self.question_text,
            "reasons": list(self.reasons),
            "gaps": list(self.gaps),
            "candidate_clause_count": self.candidate_clause_count,
            "snapshot_branches": self.snapshot_branches,
            "status": self.status.value,
        }


@dataclass
class SignoffRecord:
    """一条签核记录（append-only 落盘单元）。"""
    key: str
    decision: SignoffStatus
    reviewer: str
    at: str
    reason: str = ""
    amendment: Optional[dict[str, Any]] = None   # AMENDED 时的修改内容
    tier: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {
            "key": self.key,
            "decision": self.decision.value,
            "reviewer": self.reviewer,
            "at": self.at,
            "reason": self.reason,
            "tier": self.tier,
        }
        if self.amendment is not None:
            d["amendment"] = self.amendment
        return d


# ── 黄金集读取 ──

def load_golden(path: Path) -> dict[str, Any]:
    """读黄金集 YAML。"""
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _golden_index(golden: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(board, company_type) → 该组合的黄金集条目。"""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for exp in golden.get("expectations", []) or []:
        out[(exp["board"], exp["company_type"])] = exp
    return out


# ── 队列构造 ──

def _hash_rank(key: str, seed: str) -> float:
    """确定性哈希排序键——同 seed 必得同一抽样结果。"""
    h = hashlib.blake2b(f"{seed}:{key}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "big") / float(1 << 64)


def build_signoff_queue(
    candidates: list[dict[str, Any]],
    golden: dict[str, Any],
    gate_results: dict[tuple[str, str], dict[str, str]],
    l3_by_set: dict[tuple[str, str, Optional[int]], str],
    spot_check_rate: float = 0.20,
    seed: str = "2026-11-12",
) -> tuple[list[SignoffItem], list[SetAdjudication]]:
    """构造签核队列 + 套级裁定清单。

    返回 (条款级队列, 套级裁定清单)。

    candidates: L1a 候选（含 context / clause / source）——每条一个 clause。
    gate_results: (board, clause_id) → {gate_name: status}。
    l3_by_set: (board, company_type, group_no) → midas 差异类别
              （exact / value_diff / structure_diff / snapshot_only / source_only）。
    spot_check_rate: C 档抽样比例（0~1）；A 档不受影响。
    """
    idx = _golden_index(golden)
    items: list[SignoffItem] = []

    # 候选库中每个套实际有几条条款（供套级裁定参考——0 = 候选库里根本没这个套）
    set_clause_count: dict[tuple[str, str, Optional[int]], int] = {}
    for c in candidates:
        ctx = c["context"]
        k = (ctx["board"], ctx["company_type"], ctx.get("group_no"))
        set_clause_count[k] = set_clause_count.get(k, 0) + 1

    for c in candidates:
        ctx = c["context"]
        board, ctype = ctx["board"], ctx["company_type"]
        gno = ctx.get("group_no")
        clause_id = c["clause_id"]
        gates = gate_results.get((board, clause_id), {})
        l3_cat = l3_by_set.get((board, ctype, gno), "")

        reasons: list[str] = []
        tier: Optional[SignoffTier] = None

        # ── 闸门失败 → A 档 ──
        failed = [g for g, s in gates.items() if s != "pass"]
        if failed:
            reasons.append(f"闸门未通过：{'、'.join(sorted(failed))}")
            tier = SignoffTier.A

        # ── midas 非 exact → A 档（证人不是法官：不一致必有人看一眼）──
        if l3_cat and l3_cat != "exact":
            reasons.append(f"midas 快照差异：{l3_cat}")
            if tier is None:
                tier = SignoffTier.A

        # ── 黄金集覆盖 → 记入依据（但本身不构成必核）──
        # 关键区分：黄金集的 covered 标记核的是**套结构**（43 套的支路数对不对），
        # 不是**条款内容**。条款内容未被人工核过的，同样该按风险抽样——
        # 否则「黄金集先签」会退化成「全部先签」，抽检档永远为空。
        g = idx.get((board, ctype))
        golden_covered = g is not None and g.get("covered") is True
        if golden_covered:
            reasons.append(f"黄金集覆盖（{board}/{ctype} 套 {gno}）")

        # ── 都没命中 → C 档（闸门全绿 + midas 一致）──
        if tier is None:
            tier = SignoffTier.C
            reasons.append("闸门全绿且 midas 一致（低风险）"
                           + ("；黄金集已核套结构" if golden_covered else ""))

        leaves = c["clause"].get("leaves", [])
        items.append(SignoffItem(
            clause_id=clause_id,
            board=board,
            company_type=ctype,
            group_no=gno,
            tier=tier,
            reasons=reasons,
            source_article=c["source"].get("article", ""),
            quote="；".join(lf.get("quote", "") for lf in leaves if lf.get("quote")),
            rendered=c["clause"].get("display", ""),
            l3_category=l3_cat,
            gates=gates,
        ))

    # ── C 档抽样 ──
    c_items = [it for it in items if it.tier is SignoffTier.C]
    n = round(len(c_items) * spot_check_rate)
    # 确定性抽样：按哈希排序取前 n 条；n=0 时全不抽（全签）
    picked = {it.key for it in sorted(c_items, key=lambda it: _hash_rank(it.key, seed))[:n]}
    for it in c_items:
        if it.key in picked:
            it.reasons.append(f"抽检命中（seed={seed}，比例 {spot_check_rate:.0%}）")
        else:
            it.status = SignoffStatus.ACCEPTED   # 未抽中 = 视为免签（仍留档）
            it.reasons.append(f"未落入抽检（seed={seed}，比例 {spot_check_rate:.0%}）——免签")
            it.notes = "自动免签（非人工签核）"

    return items, build_set_adjudications(golden, set_clause_count)


def build_set_adjudications(
    golden: dict[str, Any],
    set_clause_count: dict[tuple[str, str, Optional[int]], int],
) -> list[SetAdjudication]:
    """从黄金集构造套级裁定清单（B 档）。

    两类来源：
    1. covered=false 的套 —— 原文库无对应标准条款，须裁定法律依据是否存在；
    2. gaps 点名的未编码项（豁免语义、增长认定第三路径等）——须裁定如何编码。

    注意 covered=false 且候选库里一条都没有的套（如 ChiNext/STAR 的 redchip_listed）
    照样列出——那正是「规则库缺套」的信号，不该因为无条款而消失。
    """
    out: list[SetAdjudication] = []
    for exp in golden.get("expectations", []) or []:
        board, ctype = exp["board"], exp["company_type"]
        gaps = exp.get("gaps") or []

        if exp.get("covered") is False:
            # covered=false 的组合：逐套列（黄金集 sets 里每个套号各是一条裁定）
            for gno in sorted((exp.get("sets") or {}).keys(), key=lambda x: str(x)):
                snap_br = ((exp.get("sets") or {}).get(gno) or {}).get("snapshot_branches")
                out.append(SetAdjudication(
                    board=board, company_type=ctype, group_no=gno,
                    question=LegalQuestion.NO_ANCHOR,
                    question_text=(
                        f"{board} {ctype} 套 {gno}：黄金集标注 covered=false——"
                        f"现行规则原文库无对应「上市标准」条款"
                        f"（原文仅覆盖「尚未在境外上市」红筹）。"
                        f"请裁定："
                        f"(1) 该套是否存在法律依据？依据出自哪份文件、哪一条？"
                        f"(2) 若存在，凭 midas 快照补条款是否合规"
                        f"（快照是 trace，不是权威源）？"
                        f"(3) 若不存在，应从规则库移除该套——请明示。"
                    ),
                    reasons=[f"黄金集 covered=false（{board}/{ctype} 套 {gno}）"],
                    candidate_clause_count=set_clause_count.get((board, ctype, gno), 0),
                    snapshot_branches=snap_br,
                ))

        for gi, gap in enumerate(gaps, start=1):
            gno = _gap_group_no(gap)
            if gno == "?":
                # 推不出套号时不猜——用序号占位，保证同一组合的多条 gap 不撞键
                gno = f"?{gi}"
            out.append(SetAdjudication(
                board=board, company_type=ctype, group_no=gno,
                question=LegalQuestion.UNENCODED_GAP,
                question_text=(
                    f"{board} {ctype}：黄金集记录「{gap}」。"
                    f"请裁定该条目的法律依据与适用条件，并确认应如何编码："
                    f"(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；"
                    f"(b) 作为独立条款（需有可取数的 item）；"
                    f"(c) 属 midas 侧冗余，不进规则库。"
                    f"请给出结论与依据。"
                ),
                reasons=[f"黄金集 gaps：{gap}"],
                gaps=[gap],
                candidate_clause_count=sum(
                    n for (b, t, _), n in set_clause_count.items()
                    if b == board and t == ctype
                ),
            ))
    return out


def _gap_group_no(gap: str) -> str:
    """从 gap 文本推套号（「套3 …」→ "3"）；推不出则 "?"（不猜）。"""
    m = re.search(r"套\s*(\d+)", gap)
    return m.group(1) if m else "?"



# ── 队列落盘 ──

def write_queue(
    items: list[SignoffItem],
    adjudications: list[SetAdjudication],
    out_dir: Path,
    as_of: str,
) -> dict[str, Any]:
    """队列落盘：签核任务单（JSON）+ 套级裁定清单 + 汇总（Markdown）。

    out_dir 布局：
      signoff-queue/items.jsonl        全部条款级任务（含免签条目，状态留档）
      signoff-queue/pending.jsonl      待签条款（人工只看这个）
      signoff-queue/adjudications.jsonl 套级裁定清单（B 档）
      signoff-queue/summary.md         分档统计与裁定问句清单
    """
    qdir = out_dir / "signoff-queue"
    qdir.mkdir(parents=True, exist_ok=True)
    # 清场：上一轮残留会误导审核人（与 pipeline.write_review_queue 同一原则）
    for stale in ("items.jsonl", "pending.jsonl", "summary.md", "adjudications.jsonl"):
        p = qdir / stale
        if p.exists():
            p.unlink()

    with (qdir / "items.jsonl").open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it.to_dict(), ensure_ascii=False) + "\n")

    pending = [it for it in items if it.status is SignoffStatus.PENDING]
    with (qdir / "pending.jsonl").open("w", encoding="utf-8") as f:
        for it in pending:
            f.write(json.dumps(it.to_dict(), ensure_ascii=False) + "\n")

    with (qdir / "adjudications.jsonl").open("w", encoding="utf-8") as f:
        for ad in adjudications:
            f.write(json.dumps(ad.to_dict(), ensure_ascii=False) + "\n")

    by_tier: dict[str, list[SignoffItem]] = {}
    for it in items:
        by_tier.setdefault(it.tier.value, []).append(it)

    lines = [
        "# 人工签核队列", "",
        f"- as_of：{as_of}",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 候选条款总数：{len(items)}",
        f"- 条款级待签：{len(pending)}",
        f"- 套级裁定待办：{len(adjudications)}",
        "", "## 条款级分档统计", "",
        "| 档 | 含义 | 条数 | 待签 |",
        "|---|---|---|---|",
        f"| A | 必核：闸门失败 / midas 快照非 exact | {len(by_tier.get('A', []))} | "
        f"{sum(1 for it in by_tier.get('A', []) if it.status is SignoffStatus.PENDING)} |",
        f"| C | 抽检：闸门全绿且 midas 一致 | {len(by_tier.get('C', []))} | "
        f"{sum(1 for it in by_tier.get('C', []) if it.status is SignoffStatus.PENDING)} |",
        "",
        "> 分层只按**内容风险**：黄金集 covered 核的是套结构、不是条款内容，"
        "故只作为落档依据写进 reasons，不单独决定档位（ADR-0009 决策 1）。",
        "",
    ]
    if adjudications:
        lines += ["## 套级裁定清单（法律适用性，与条款级并列，不得互相替代）", ""]
        for ad in adjudications:
            lines += [
                f"### {ad.key}", "",
                f"- 落档原因：{'；'.join(ad.reasons)}",
                f"- 候选库中该套条款数：{ad.candidate_clause_count}"
                f"（0 表示候选库无此套——这本身是「规则库缺套」信号）",
                f"- midas 快照行数（仅参考）：{ad.snapshot_branches}",
                f"- 裁定问句：{ad.question_text}",
                "",
            ]
    (qdir / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    return {
        "total": len(items),
        "pending": len(pending),
        "by_tier": {k: len(v) for k, v in by_tier.items()},
        "adjudications": len(adjudications),
        "queue_dir": str(qdir),
    }


def load_records(path: Path) -> list[SignoffRecord]:
    """读签核记录（append-only JSONL）。"""
    out: list[SignoffRecord] = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(SignoffRecord(
                key=d["key"],
                decision=SignoffStatus(d["decision"]),
                reviewer=d["reviewer"],
                at=d["at"],
                reason=d.get("reason", ""),
                amendment=d.get("amendment"),
                tier=d.get("tier", ""),
            ))
    return out


def append_record(record: SignoffRecord, path: Path) -> None:
    """追加签核记录（append-only）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def apply_records(items: list[SignoffItem], records: Iterable[SignoffRecord]) -> list[SignoffItem]:
    """把签核记录回填到队列条目状态（取最后一次签核为准）。"""
    latest: dict[str, SignoffRecord] = {}
    for r in records:
        latest[r.key] = r
    for it in items:
        r = latest.get(it.key)
        if r is not None:
            it.status = r.decision
            if r.amendment:
                it.notes = json.dumps(r.amendment, ensure_ascii=False)
    return items


# ── 从闸门产物提取签核所需事实 ──

def extract_gate_facts(
    candidates: list[Any],
    l0: dict, l1b: dict, l2: dict, l3: dict,
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[tuple[str, str, Optional[int]], str]]:
    """从四道闸的结果提取两样签核要用的东西。

    返回：
      gate_status[(board, clause_id)] = {gate_name: "pass"/"fail"}
      l3_by_set[(board, company_type, group_no)] = midas 差异类别

    L3 是**套级**判定（一条候选继承其所属套的结果），但 GateResult 里存的是套内
    首条的 clause_id——不能拿它反查套（首条不唯一、且同套多条的 clause_id 不同）。
    因此套→类别的映射**从候选自己的 context 建**：L3 对同套所有候选给同一结果，
    按 (board, clause_id) 取到结果后写回该候选所属的套键。
    """
    gate_status: dict[tuple[str, str], dict[str, str]] = {}
    l3_by_set: dict[tuple[str, str, Optional[int]], str] = {}

    tables = (("L0", l0), ("L1b", l1b), ("L2", l2), ("L3", l3))
    for c in candidates:
        k = (c.context.board, c.clause_id)
        status: dict[str, str] = {}
        for name, table in tables:
            res = table.get(k)
            if res is None:
                continue
            status[name] = res.status.value
            if name == "L3":
                cat = ""
                if res.failure is not None:
                    diffs = (res.failure.details or {}).get("diffs") or []
                    if diffs:
                        cat = diffs[0].get("category", "")
                elif res.payload:
                    cat = res.payload.get("diff_category", "")
                if cat:
                    set_key = (c.context.board, c.context.company_type,
                               c.context.group_no)
                    l3_by_set[set_key] = cat
        gate_status[k] = status

    return gate_status, l3_by_set


# ── 审阅摘要（digest）：pending 条款 → 分组三方对照 ──

_QUANT_CN = {"sum": "合计", "avg": "平均", "latest": "最新", "each": "逐年"}


def _fmt_val(v: Any, fmt: str) -> str:
    """阈值人读格式：1e8→亿、1e4→万、percent→%；g 去尾零（2.5亿 不写 2.5000亿）。

    v 为 None（定性条件，无数值阈值）→「—」，不参与数值比较。
    """
    if v is None:
        return "—"
    if fmt == "percent":
        return f"{v * 100:g}%"
    if v >= 1e8:
        return f"{v / 1e8:g}亿"
    if v >= 1e4:
        return f"{v / 1e4:g}万"
    return f"{v:g}"


def _fmt_leaf(lf: dict[str, Any]) -> str:
    s = f"{lf.get('item_ref')} {lf.get('op')} {_fmt_val(lf.get('threshold', '?'), lf.get('format', 'number'))}"
    q = lf.get("quantifier")
    if q:
        s += f"（{_QUANT_CN.get(q, q)}"
        w = lf.get("window") or {}
        if w.get("kind") == "last_n_years":
            s += f"{w.get('n')}年"
        s += "）"
    return s


def write_review_digest(queue_dir: Path, snapshot_path: Path) -> dict[str, Any]:
    """pending 条款 → review-digest.md：按异常分组的**三方对照**审阅清单。

    三方 = 原文引文（quote）/ 候选渲染（rendered）/ midas 快照行（按
    board:company_type:group_no 关联）。审核人目标：单条一分钟——
    看三方是否语义一致，拍 accepted / rejected / amended。

    分组按**首要异常**归一（value_diff > structure_diff > L2 回译 > C 抽检）；
    次要异常仍在「闸门」行里可见，不丢信息。
    """
    import yaml

    pending_path = queue_dir / "pending.jsonl"
    items: list[dict[str, Any]] = []
    if pending_path.exists():
        with pending_path.open("r", encoding="utf-8") as f:
            items = [json.loads(l) for l in f if l.strip()]

    rows: dict[str, Any] = {}
    if snapshot_path.exists():
        snap = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
        rows = snap.get("snapshot") or {}

    sections: list[tuple[str, str, list[str]]] = [  # (id, 标题, 归入本组的 item key)
        ("value_diff", "A 档 · midas 数值差异（逐条对数）", []),
        ("structure_diff", "A 档 · midas 结构差异（对结构，不是对数）", []),
        ("l2_fail", "A 档 · 回译不一致（L2 说候选与原文语义有出入）", []),
        ("spot", "C 档 · 抽检（两闸皆绿，快扫确认）", []),
    ]
    for it in items:
        l3 = it.get("l3_category") or "exact"
        gates = it.get("gates") or {}
        if l3 == "value_diff":
            sections[0][2].append(it["key"])
        elif l3 == "structure_diff":
            sections[1][2].append(it["key"])
        elif gates.get("L2") == "fail":
            sections[2][2].append(it["key"])
        else:
            sections[3][2].append(it["key"])
    by_key = {it["key"]: it for it in items}

    def _mark(ok: bool) -> str:
        return "✓" if ok else "✗"

    lines = [
        "# 签核审阅摘要（条款级 pending）", "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 待签条款：{len(items)}",
        "- 审法：三方对照（原文 / 候选渲染 / midas 现值）——语义一致 → accepted；"
        "候选错 → rejected；候选要改 → amended（附改法）。",
        "- 逐条记录："
        "`python -m ipo_eval_lab.calibration sign --key <key> --decision … --reviewer <你> --reason \"…\"`",
        "",
    ]
    for sid, title, keys in sections:
        if not keys:
            continue
        lines += [f"## {title}（{len(keys)} 条）", ""]
        for k in keys:
            it = by_key[k]
            gates = it.get("gates") or {}
            gate_s = " ".join(f"{g}{_mark(v == 'pass')}" for g, v in sorted(gates.items()))
            lines.append(f"- [ ] **`{k}`**（{it.get('company_type')} 套 {it.get('group_no')}"
                         f" · 原文 {it.get('source_article')}）｜闸门：{gate_s}")
            lines.append(f"  - 原文：「{it.get('quote', '')}」")
            lines.append(f"  - 候选：「{it.get('rendered', '')}」")
            row_key = f"{it.get('board')}:{it.get('company_type')}:{it.get('group_no')}"
            row = rows.get(row_key)
            if row and row.get("leaves"):
                leaves = " · ".join(_fmt_leaf(lf) for lf in row["leaves"])
                lines.append(f"  - midas 行 `{row_key}`：{leaves}")
            else:
                lines.append(f"  - midas 行 `{row_key}`：无对应行")
            for r in it.get("reasons", []):
                lines.append(f"  - 落档：{r}")
        lines.append("")

    out = queue_dir / "review-digest.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"path": str(out), "total": len(items),
            "sections": {sid: len(keys) for sid, _, keys in sections}}


__all__ = [
    "SignoffTier", "SignoffStatus", "SetAdjudicationStatus", "LegalQuestion",
    "SignoffItem", "SetAdjudication", "SignoffRecord",
    "load_golden", "build_signoff_queue", "build_set_adjudications", "write_queue",
    "load_records", "append_record", "apply_records",
    "extract_gate_facts", "write_review_digest",
]
