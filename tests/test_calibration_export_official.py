"""签核 → 正式库导出回归（ADR-0005 R3 第二级入库）。

钉住一条不可让步的约定：

**未签核的条款一律不进正式库；条款未签完的套整个不导出。**

理由：导出半套比不导更危险——引擎会据「缺条件」的套判不达标，而缺口其实是
未签完导致的，看起来像主体不达标。缺条件是校准流程问题，不该由引擎承担。
"""
import json
from pathlib import Path

import yaml

from ipo_eval_lab.calibration.export_official import export_official_rulebook


def _cand(clause_id, board="SSE-MB", ctype="general", gno=1):
    return {
        "clause_id": clause_id,
        "context": {
            "board": board, "company_type": ctype, "group_no": gno,
            "group_id": f"{board}_{ctype}_g{gno}", "branch_id": None,
            "role": "shared", "scope": "set",
        },
        "clause": {
            "clause_id": clause_id, "law_ref": "sse_main_2026#3.1.2", "logic": "all",
            "display": "条款",
            "leaves": [{
                "leaf_id": f"{clause_id}_l1", "item_ref": "np_3y_sum",
                "op": "ge", "threshold": 200000000, "threshold_format": "number",
                "threshold_text": "2 亿元", "quote": "最近3 年净利润累计不低于2 亿元",
            }],
        },
        "source": {"law_id": "sse_main_2026", "article": "3.1.2", "chapter": None,
                   "section": None, "text": "（测试用占位条文）"},
    }


def _write_cands(path: Path, cands):
    with path.open("w", encoding="utf-8") as f:
        for c in cands:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def _write_records(path: Path, records):
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rec(key, decision, at="2026-11-12T10:00:00"):
    return {"key": key, "decision": decision, "reviewer": "t", "at": at,
            "reason": "", "tier": "A"}


def test_only_signed_clauses_are_exported(tmp_path: Path):
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1"), _cand("c2")])
    _write_records(recs, [_rec("SSE-MB:c1", "accepted")])

    report = export_official_rulebook(cands, recs, out)

    # c2 未签 → 该套不完整 → 整个套不导出
    assert report.exported_clauses == 0
    assert report.skipped_sets
    assert "SSE-MB:c2" in report.skipped_sets[0]["pending_clause_keys"]
    assert not list(out.glob("*.yaml")) or all(
        "c2" not in p.read_text(encoding="utf-8") for p in out.glob("*.yaml")
    )


def test_fully_signed_set_is_exported(tmp_path: Path):
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1"), _cand("c2")])
    _write_records(recs, [_rec("SSE-MB:c1", "accepted"), _rec("SSE-MB:c2", "amended")])

    report = export_official_rulebook(cands, recs, out)
    assert report.exported_clauses == 2
    assert not report.skipped_sets

    files = list(out.glob("*.yaml"))
    assert len(files) == 1
    groups = list(yaml.safe_load_all(files[0].read_text(encoding="utf-8")))
    assert len(groups) == 1
    g = groups[0]
    assert g["group_id"] == "SSE-MB_general_g1"
    assert len(g["shared_clauses"]) == 2
    # 证据字段不进正式库（属证据层，由 calibration 产出物承担）
    leaf = g["shared_clauses"][0]["leaves"][0]
    assert "quote" not in leaf
    assert "threshold_text" not in leaf
    assert leaf["threshold"] == {"value": 200000000, "format": "number"}


def test_rejected_clause_blocks_its_set(tmp_path: Path):
    """打回 = 要改，改完要重走签核——不是「跳过这一条」。"""
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1"), _cand("c2")])
    _write_records(recs, [_rec("SSE-MB:c1", "accepted"), _rec("SSE-MB:c2", "rejected")])

    report = export_official_rulebook(cands, recs, out)
    assert report.exported_clauses == 0
    assert "SSE-MB:c2" in report.rejected_clauses


def test_latest_record_wins(tmp_path: Path):
    """改判留痕：先打回后通过 → 算通过。"""
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1")])
    _write_records(recs, [
        _rec("SSE-MB:c1", "rejected", at="2026-11-12T09:00:00"),
        _rec("SSE-MB:c1", "accepted", at="2026-11-12T11:00:00"),
    ])
    report = export_official_rulebook(cands, recs, out)
    assert report.exported_clauses == 1


def test_mirror_boards_merge_into_one_group(tmp_path: Path):
    """沪深同文合并（R3）：同一 (company_type, group_no) 只导出一个 group。"""
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1", board="SSE-MB"), _cand("c1", board="SZSE-MB")])
    _write_records(recs, [_rec("SSE-MB:c1", "accepted"), _rec("SZSE-MB:c1", "accepted")])

    report = export_official_rulebook(cands, recs, out)
    files = list(out.glob("*.yaml"))
    groups = list(yaml.safe_load_all(files[0].read_text(encoding="utf-8")))
    assert len(groups) == 1
    assert sorted(groups[0]["boards"]) == ["SSE-MB", "SZSE-MB"]
    # 同文合并 → 同一条款只出现一次（两个 clause_id 相同会去重）
    assert len(groups[0]["shared_clauses"]) == 1


def test_dry_run_writes_nothing(tmp_path: Path):
    cands = tmp_path / "c.jsonl"
    recs = tmp_path / "r.jsonl"
    out = tmp_path / "sets"
    _write_cands(cands, [_cand("c1")])
    _write_records(recs, [_rec("SSE-MB:c1", "accepted")])
    report = export_official_rulebook(cands, recs, out, dry_run=True)
    assert report.exported_clauses == 1
    assert not out.exists() or not list(out.glob("*.yaml"))
