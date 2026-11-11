"""
M1 校准管线主流程编排（设计 0003）

管线自身零 AI：
- 候选规则（L1a 产出）与 L2 判定由外部 agent 会话预跑、落 JSONL
- 本文件只做确定性校验、合成与落盘

CLI: python -m ipo_eval_lab.calibration run --candidates ... --as-of YYYY-MM-DD
"""

from pathlib import Path
from typing import Optional
import json
import yaml
from datetime import datetime

from .models import (
    GateName, GateStatus, GateResult, EvidencePack, ConfidenceTier,
    ConfidenceSynthesis, CalibrationReport, L2Judgment, L3Diff, CandidateRule,
)
from .l0_gate import run_l0_gate
from .l1b_gate import run_l1b_gate
from .l2_gate import run_l2_gate_offline
from .l3_gate import run_l3_gate, generate_midas_diff_report
from .confidence import synthesize_confidence, build_evidence_pack


# ── 输入 ──

def load_source_clauses(source_dir: Path) -> list[dict]:
    """加载原文库条文（rulebook/source_texts/*.yaml）"""
    clauses: list[dict] = []
    for yaml_file in sorted(source_dir.glob("*.yaml")):
        if yaml_file.name.startswith("_"):
            continue
        with yaml_file.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        for art in doc.get("articles", []):
            clauses.append({
                "law_id": doc.get("law_id", yaml_file.stem),
                "title": doc.get("title", ""),
                "effective_from": str(doc.get("effective_from", "")),
                "article": str(art.get("article", "")),
                "chapter": art.get("chapter"),
                "section": art.get("section"),
                "text": art.get("text", ""),
                "source_ref": doc.get("source_ref", ""),
            })
    return clauses


def load_candidates(candidates_path: Path) -> list[CandidateRule]:
    rules: list[CandidateRule] = []
    if not candidates_path.exists():
        return rules
    with candidates_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rules.append(CandidateRule.model_validate_json(line))
    return rules


def load_l2_judgments(path: Path) -> dict[str, L2Judgment]:
    judgments: dict[str, L2Judgment] = {}
    if not path.exists():
        return judgments
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            judgments[data["clause_id"]] = L2Judgment(
                equivalent=data["equivalent"],
                differences=data.get("differences", []),
                rendered_text=data.get("rendered_text", ""),
            )
    return judgments


# ── 输出 ──

def write_candidates(rules: list[CandidateRule], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "candidates.jsonl").open("w", encoding="utf-8") as f:
        for r in rules:
            f.write(r.model_dump_json() + "\n")


def write_review_queue(
    packs: list[EvidencePack], diffs: list[L3Diff], output_dir: Path, as_of: str,
) -> None:
    queue_dir = output_dir / "review-queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    for pack in packs:
        safe = pack.clause_id.replace(":", "_").replace("/", "_")
        (queue_dir / f"{safe}.json").write_text(pack.model_dump_json(indent=2), encoding="utf-8")
    if diffs:
        (output_dir / "midas-diff-report.md").write_text(
            generate_midas_diff_report(diffs, as_of), encoding="utf-8")


def write_report(report: CalibrationReport, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    total = max(report.total_clauses, 1)
    lines = [
        "# M1 校准批次报告", "",
        f"- 批次 ID：{report.batch_id}",
        f"- as_of：{report.as_of_date}",
        f"- 原文库版本：{report.source_version}",
        f"- 生成时间：{report.generated_at.isoformat()}",
        "",
        "## 闸门漏斗", "",
        f"- 候选条文总数：{report.total_clauses}",
        f"- L0 通过：{report.passed_l0}（{report.passed_l0 / total * 100:.1f}%）",
        f"- L1b 通过：{report.passed_l1b}（占 L0 通过 {report.passed_l1b / max(report.passed_l0,1) * 100:.1f}%）",
        f"- L2 通过：{report.passed_l2}（占 L1b 通过 {report.passed_l2 / max(report.passed_l1b,1) * 100:.1f}%）",
        f"- L3 通过：{report.passed_l3}（占 L2 通过 {report.passed_l3 / max(report.passed_l2,1) * 100:.1f}%）",
        "",
        "## 置信度分布", "",
    ]
    for tier, cnt in sorted(report.tier_counts.items()):
        lines.append(f"- {tier}: {cnt}")
    lines += [
        "",
        "## 产出", "",
        f"- 候选库：{report.candidates_written} 条",
        f"- 人工队列：{report.review_queue_written} 条",
        "",
        "## midas 差异清单摘要", "",
    ]
    for cat, cnt in sorted(report.midas_diff_summary.items()):
        lines.append(f"- {cat}: {cnt}")
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


# ── 主流程 ──

def calibrate_run(
    as_of_date: str,
    candidates_path: Path,
    l2_judgments_path: Optional[Path],
    output_dir: Path,
    rulebook_dir: Path,
    anchor_normalization_path: Path,
    snapshot_path: Path,
    source_version: str = "rb-2026.11",
) -> CalibrationReport:
    candidates = load_candidates(candidates_path)

    # L0
    l0 = {r.clause_id: r for r in run_l0_gate(candidates, as_of_date, rulebook_dir)}
    l0_pass = [c for c in candidates if l0[c.clause_id].status == GateStatus.PASS]

    # L1b（只对 L0 通过者）
    l1b: dict[str, GateResult] = {}
    if l0_pass:
        for res in run_l1b_gate(l0_pass, anchor_normalization_path):
            l1b[res.clause_id] = res
    l1b_pass = [c for c in l0_pass
                if l1b.get(c.clause_id, None) and l1b[c.clause_id].status == GateStatus.PASS]

    # L2（只对 L1b 通过者；判定由外部预跑）
    l2: dict[str, GateResult] = {}
    if l1b_pass and l2_judgments_path:
        judgments = load_l2_judgments(l2_judgments_path)
        for res in run_l2_gate_offline(l1b_pass, judgments, rulebook_dir):
            l2[res.clause_id] = res
    l2_pass = [c for c in l1b_pass
               if l2.get(c.clause_id, None) and l2[c.clause_id].status == GateStatus.PASS]

    # L3（只对 L2 通过者）
    l3: dict[str, GateResult] = {}
    diffs: list[L3Diff] = []
    if l2_pass:
        l3_list, diffs = run_l3_gate(l2_pass, snapshot_path, rulebook_dir)
        l3 = {r.clause_id: r for r in l3_list}

    # 置信度合成
    syntheses: list[ConfidenceSynthesis] = []
    to_candidates: list[CandidateRule] = []
    to_queue: list[EvidencePack] = []

    for c in candidates:
        gates = {g: r for g, r in (
            (GateName.L0, l0.get(c.clause_id)),
            (GateName.L1B, l1b.get(c.clause_id)),
            (GateName.L2, l2.get(c.clause_id)),
            (GateName.L3, l3.get(c.clause_id)),
        ) if r}
        synth = synthesize_confidence(c, gates)
        syntheses.append(synth)
        if synth.auto_decision == "candidates":
            to_candidates.append(c)
        else:
            to_queue.append(build_evidence_pack(c, gates, synth))

    write_candidates(to_candidates, output_dir)
    write_review_queue(to_queue, diffs, output_dir, as_of_date)

    tier_counts: dict[str, int] = {}
    for s in syntheses:
        tier_counts[s.tier.value] = tier_counts.get(s.tier.value, 0) + 1
    diff_summary: dict[str, int] = {}
    for d in diffs:
        diff_summary[d.category.value] = diff_summary.get(d.category.value, 0) + 1

    report = CalibrationReport(
        batch_id=f"cal-{as_of_date}-{datetime.now().strftime('%H%M%S')}",
        as_of_date=as_of_date,
        source_version=source_version,
        total_clauses=len(candidates),
        passed_l0=len(l0_pass),
        passed_l1b=len(l1b_pass),
        passed_l2=len(l2_pass),
        passed_l3=sum(1 for r in l3.values() if r.status == GateStatus.PASS),
        tier_counts=tier_counts,
        candidates_written=len(to_candidates),
        review_queue_written=len(to_queue),
        midas_diff_summary=diff_summary,
    )
    write_report(report, output_dir)
    return report


__all__ = [
    "calibrate_run", "load_source_clauses", "load_candidates", "load_l2_judgments",
    "write_candidates", "write_review_queue", "write_report",
]
