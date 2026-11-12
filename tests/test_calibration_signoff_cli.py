"""签核 CLI 的端到端行为（重建不复活已签）。

关键回归：重建队列时**必须**回填签核记录。
不做的后果——pending.jsonl 会把「已签 8 条」重新列成待签：审核人白看一遍，
digest 也把已签条款混进审阅底稿，签核工作量口径失真。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.calibration import __main__ as cli

ROOT = Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "calibration" / "l1a" / "output" / "candidates_merged.jsonl"
L2 = ROOT / "calibration" / "l1a" / "output" / "l2_judgments_merged.jsonl"


def _read_pending(out_dir: Path) -> list[dict]:
    p = out_dir / "signoff-queue" / "pending.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


@pytest.mark.skipif(not CANDIDATES.exists() or not L2.exists(),
                    reason="需真实候选库与 L2 判定文件")
def test_rebuild_does_not_revive_signed_items(tmp_path, monkeypatch):
    """签过的条款在重建后不得回到待签清单。"""
    # 隔离签核记录：临时文件，先空后写一条
    # 真实实现读的是 <root>/calibration/signoff-records.jsonl——用临时 root 隔离
    fake_root = tmp_path / "repo"
    (fake_root / "calibration").mkdir(parents=True)
    (fake_root / "calibration" / "signoff-records.jsonl").write_text("", encoding="utf-8")
    (fake_root / "calibration" / "golden").mkdir()
    (fake_root / "calibration" / "golden" / "golden_sets.yaml").write_text(
        (ROOT / "calibration" / "golden" / "golden_sets.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    (fake_root / "calibration" / "midas_snapshot.yaml").write_text(
        (ROOT / "calibration" / "midas_snapshot.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    (fake_root / "rulebook").mkdir()
    for name in ("items.yaml", "metrics.yaml"):
        (fake_root / "rulebook" / name).write_text(
            (ROOT / "rulebook" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (fake_root / "config").mkdir()
    (fake_root / "config" / "anchor_normalization.yaml").write_text(
        (ROOT / "config" / "anchor_normalization.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")

    out = tmp_path / "out"
    argv = ["--root", str(fake_root), "signoff",
            "--candidates", str(CANDIDATES), "--l2-judgments", str(L2),
            "--as-of", "2026-11-12", "--output", str(out)]
    assert cli.main(argv) == 0

    pending = _read_pending(out)
    assert pending, "队列不应为空"

    # 挑一条待签的，签掉，重建
    target = pending[0]
    key = target["key"]
    rec = fake_root / "calibration" / "signoff-records.jsonl"
    rec.write_text(json.dumps({
        "key": key, "decision": "accepted", "reviewer": "yt",
        "at": "2026-11-12T10:00:00", "reason": "测试",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    assert cli.main(argv) == 0
    pending2 = _read_pending(out)
    assert key not in {p["key"] for p in pending2}, \
        f"已签条款 {key} 在重建后复活成待签"


@pytest.mark.skipif(not CANDIDATES.exists() or not L2.exists(),
                    reason="需真实候选库与 L2 判定文件")
def test_pending_and_status_agree(tmp_path, monkeypatch, capsys):
    """pending.jsonl 的条数必须与 signoff-status 报的「待签」一致。

    两者不一致说明重建时没回填记录——审核人看到的清单和进度表对不上。
    """
    fake_root = tmp_path / "repo"
    (fake_root / "calibration" / "golden").mkdir(parents=True)
    (fake_root / "calibration" / "golden" / "golden_sets.yaml").write_text(
        (ROOT / "calibration" / "golden" / "golden_sets.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    (fake_root / "calibration" / "midas_snapshot.yaml").write_text(
        (ROOT / "calibration" / "midas_snapshot.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")
    (fake_root / "calibration" / "signoff-records.jsonl").write_text("", encoding="utf-8")
    (fake_root / "rulebook").mkdir()
    for name in ("items.yaml", "metrics.yaml"):
        (fake_root / "rulebook" / name).write_text(
            (ROOT / "rulebook" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (fake_root / "config").mkdir()
    (fake_root / "config" / "anchor_normalization.yaml").write_text(
        (ROOT / "config" / "anchor_normalization.yaml").read_text(encoding="utf-8"),
        encoding="utf-8")

    out = tmp_path / "out"
    argv = ["--root", str(fake_root), "signoff",
            "--candidates", str(CANDIDATES), "--l2-judgments", str(L2),
            "--as-of", "2026-11-12", "--output", str(out)]
    assert cli.main(argv) == 0
    n_pending = len(_read_pending(out))

    capsys.readouterr()
    assert cli.main(["--root", str(fake_root), "signoff-status",
                     "--output", str(out),
                     "--records", str(fake_root / "calibration" / "signoff-records.jsonl")]) == 0
    out_text = capsys.readouterr().out
    line = [l for l in out_text.splitlines() if "合计待签" in l][0]
    n_status = int(line.split("：")[1].split("／")[0])
    assert n_pending == n_status, f"pending={n_pending} 与 status={n_status} 不一致"
