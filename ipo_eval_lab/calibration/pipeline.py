"""
M1 校准管线主流程编排（设计 0003）

CLI: python -m ipo_eval_lab.calibration run --source rulebook/source_texts --as-of YYYY-MM-DD
"""

from pathlib import Path
from typing import Optional, Any
import json
import yaml
from datetime import datetime

from .models import (
    GateName, GateStatus, GateResult, EvidencePack, ConfidenceTier,
    ConfidenceSynthesis, CalibrationConfig, CalibrationReport, L2Judgment,
    CandidateRule, CandidateClause, CandidateLeaf, SourceClauseRef, L3Diff,
)
from .l0_gate import run_l0_gate
from .l1b_gate import run_l1b_gate
from .l2_gate import run_l2_gate_offline, render_candidate
from .l3_gate import run_l3_gate, generate_midas_diff_report
from .confidence import synthesize_confidence, build_evidence_pack


# ── 输入加载 ──

def load_source_clauses(source_dir: Path) -> list[dict]:
    """加载原文库条文（source_texts/*.yaml）"""
    clauses = []
    for yaml_file in source_dir.glob("*.yaml"):
        if yaml_file.name.startswith("_"):
            continue
        with yaml_file.open("r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        if not doc or "articles" not in doc:
            continue
        
        for art in doc["articles"]:
            clauses.append({
                "law_id": doc.get("law_id", yaml_file.stem),
                "title": doc.get("title", ""),
                "effective_from": doc.get("effective_from", ""),
                "article": art.get("article", ""),
                "chapter": art.get("chapter"),
                "section": art.get("section"),
                "text": art.get("text", ""),
                "source_ref": doc.get("source_ref", ""),
            })
    return clauses


def load_candidates(candidates_path: Path) -> list[CandidateRule]:
    """加载候选规则（L1a 产出 JSONL）"""
    candidates = []
    if not candidates_path.exists():
        return candidates
    with candidates_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            candidates.append(CandidateRule.model_validate(data))
    return candidates


# ── 输出落盘 ──

def write_candidates(candidates: list[CandidateRule], output_dir: Path):
    """写候选库"""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "candidates.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for c in candidates:
            f.write(c.model_dump_json() + "\n")


def write_review_queue(
    evidence_packs: list[EvidencePack],
    diffs: list[L3Diff],
    output_dir: Path,
):
    """写人工队列"""
    queue_dir = output_dir / "review-queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    
    for pack in evidence_packs:
        path = queue_dir / f"{pack.clause_id.replace(':', '_')}.json"
        with path.open("w", encoding="utf-8") as f:
            f.write(pack.model_dump_json(indent=2))
    
    if diffs:
        report = generate_midas_diff_report(diffs)
        (output_dir / "midas-diff-report.md").write_text(report, encoding="utf-8")


def write_report(report: CalibrationReport, output_dir: Path):
    """写批次报告"""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    lines = ["# M1 校准批次报告", ""]
    lines.append(f"- 批次 ID：{report.batch_id}")
    lines.append(f"- as_of：{report.as_of_date}")
    lines.append(f"- 原文库版本：{report.source_version}")
    lines.append(f"- 生成时间：{report.generated_at.isoformat()}")
    lines.append("")
    lines.append("## 闸门统计")
    lines.append("")
    lines.append(f"- 总条文数：{report.total_clauses}")
    lines.append(f"- L0 通过：{report.passed_l0}（{report.passed_l0 / max(report.total_clauses, 1) * 100:.1f}%）")
    lines.append(f"- L1b 通过：{report.passed_l1b}（{report.passed_l1b / max(report.passed_l0, 1) * 100:.1f}%）")
    lines.append(f"- L2 通过：{report.passed_l2}（{report.passed_l2 / max(report.passed_l1b, 1) * 100:.1f}%）")
    lines.append(f"- L3 通过：{report.passed_l3}（{report.passed_l3 / max(report.passed_l2, 1) * 100:.1f}%）")
    lines.append("")
    lines.append("## 置信度分布")
    lines.append("")
    for tier, cnt in report.tier_counts.items():
        lines.append(f"- {tier}: {cnt}")
    lines.append("")
    lines.append("## 产出")
    lines.append("")
    lines.append(f"- 候选库条目：{report.candidates_written}")
    lines.append(f"- 人工队列条目：{report.review_queue_written}")
    lines.append("")
    lines.append("## midas 差异清单摘要")
    lines.append("")
    for cat, cnt in report.midas_diff_summary.items():
        lines.append(f"- {cat}: {cnt}")
    
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


# ── 主流程 ──

def calibrate_run(
    source_dir: Path,
    as_of_date: str,
    candidates_path: Path,
    precomputed_judgments_path: Optional[Path],
    output_dir: Path,
    metrics_yaml: Path,
    anchor_normalization_path: Path,
    snapshot_path: Path,
    rulebook_dir: Path,
) -> CalibrationReport:
    """
    校准管线主入口
    
    L1a 不在管线内执行——候选规则由外部（agent 会话）预先生成，
    管线只读 candidates_path 的 JSONL 做确定性校验。
    
    L2 判定同理：预跑结果存 precomputed_judgments_path。
    """
    # 1. 加载候选
    candidates = load_candidates(candidates_path)
    
    # 2. L0 闸门
    l0_results = {r.clause_id: r for r in run_l0_gate(candidates, as_of_date, metrics_yaml, rulebook_dir)}
    l0_pass_ids = {cid for cid, r in l0_results.items() if r.status == GateStatus.PASS}
    
    # 3. L1b 闸门（只对 L0 通过者）
    l1b_results = {}
    l1b_pass_ids = set()
    for c in candidates:
        if c.clause_id not in l0_pass_ids:
            continue
        # 单条跑
        res = run_l1b_gate([c], anchor_normalization_path)[0]
        l1b_results[c.clause_id] = res
        if res.status == GateStatus.PASS:
            l1b_pass_ids.add(c.clause_id)
    
    # 4. L2 闸门（只对 L1b 通过者）
    l2_results = {}
    l2_pass_ids = set()
    if precomputed_judgments_path and precomputed_judgments_path.exists():
        judgments = {}
        with precomputed_judgments_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    judgments[data["clause_id"]] = L2Judgment(
                        equivalent=data["equivalent"],
                        differences=data.get("differences", []),
                        rendered_text=data.get("rendered_text", ""),
                    )
        l2_candidates = [c for c in candidates if c.clause_id in l1b_pass_ids]
        for res in run_l2_gate_offline(l2_candidates, judgments):
            l2_results[res.clause_id] = res
            if res.status == GateStatus.PASS:
                l2_pass_ids.add(res.clause_id)
    
    # 5. L3 闸门（只对 L2 通过者）
    l3_results = {}
    diffs: list[L3Diff] = []
    l3_candidates = [c for c in candidates if c.clause_id in l2_pass_ids]
    if l3_candidates:
        l3_list, diffs = run_l3_gate(l3_candidates, snapshot_path)
        l3_results = {r.clause_id: r for r in l3_list}
    
    # 6. 置信度合成
    all_syntheses: list[ConfidenceSynthesis] = []
    candidate_entries: list[CandidateRule] = []
    evidence_packs: list[EvidencePack] = []
    
    for c in candidates:
        gate_results = {g: r for g, r in [
            (GateName.L0, l0_results.get(c.clause_id)),
            (GateName.L1B, l1b_results.get(c.clause_id)),
            (GateName.L2, l2_results.get(c.clause_id)),
            (GateName.L3, l3_results.get(c.clause_id)),
        ] if r}
        
        synth = synthesize_confidence(c, gate_results)
        all_syntheses.append(synth)
        
        if synth.auto_decision == "candidates" and c.clause_id in l2_pass_ids:
            candidate_entries.append(c)
        elif synth.auto_decision == "review_queue":
            pack = build_evidence_pack(c, gate_results, synth)
            evidence_packs.append(pack)
    
    # 7. 落盘
    write_candidates(candidate_entries, output_dir)
    write_review_queue(evidence_packs, diffs, output_dir)
    
    # 8. 批次报告
    tier_counts = {}
    for s in all_syntheses:
        tier_counts[s.tier] = tier_counts.get(s.tier, 0) + 1
    
    diff_summary = {}
    for d in diffs:
        diff_summary[d.category] = diff_summary.get(d.category, 0) + 1
    
    report = CalibrationReport(
        batch_id=f"cal-{as_of_date}-{datetime.now().strftime('%H%M%S')}",
        as_of_date=as_of_date,
        source_version="rb-2026.11",
        total_clauses=len(candidates),
        passed_l0=len(l0_pass_ids),
        passed_l1b=len(l1b_pass_ids),
        passed_l2=len(l2_pass_ids),
        passed_l3=len(l3_results),
        tier_counts=tier_counts,
        candidates_written=len(candidate_entries),
        review_queue_written=len(evidence_packs),
        midas_diff_summary=diff_summary,
    )
    write_report(report, output_dir)
    
    return report


__all__ = [
    "calibrate_run", "load_source_clauses", "load_candidates",
    "write_candidates", "write_review_queue", "write_report",
]