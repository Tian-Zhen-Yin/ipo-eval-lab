"""load_company 企业模式与 data_source 判定（ADR-0013；工单 04）。

- 目录含 ingest.json（导入三件套）→ 企业模式：勾稽①~⑤照查、⑥跳（卫生参数不适用）；
- data_source_of：enterprise 优先于 session（.scratch/ingest 下的导入目录是企业数据）。
"""
import json
import shutil
from pathlib import Path

import pytest

from ipo_eval_lab.fixtures import FixtureDataError, load_company, load_sanity
from ipo_eval_lab.ingest.source import data_source_of

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "fixtures" / "companies" / "base_co_2029"


@pytest.fixture(scope="module")
def sanity():
    return load_sanity(REPO / "fixtures" / "sanity.yaml")


def _copy_base(tmp_path: Path) -> Path:
    d = tmp_path / "co"
    shutil.copytree(BASE, d)
    return d


def _mutate(co_dir: Path, field: str, fn) -> None:
    p = json.loads((co_dir / "profile.json").read_text(encoding="utf-8"))
    last = max(p["statements"], key=lambda s: s["fiscal_year"])
    section, key = field.split(".")
    last[section][key] = fn(last[section][key])
    (co_dir / "profile.json").write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def _mark_enterprise(co_dir: Path) -> None:
    (co_dir / "ingest.json").write_text(
        json.dumps({"data_source": "enterprise", "company_id": "co", "derived_fields": [],
                    "template_version": 1, "source_sha256": "x" * 64, "imported_at": "2026-11-21T00:00:00"}),
        encoding="utf-8",
    )


def test_fixture_dir_still_checks_growth(sanity, tmp_path: Path) -> None:
    """mock 目录（无 ingest.json）：⑥照查——营收 ×5（+400% 超 200% 上限）必须拦。"""
    co = _copy_base(tmp_path)
    _mutate(co, "income.operating_revenues", lambda v: v * 5)

    with pytest.raises(FixtureDataError) as ei:
        load_company(co, sanity)
    assert any("勾稽⑥" in m for m in ei.value.messages), ei.value.messages


def test_enterprise_dir_skips_growth(sanity, tmp_path: Path) -> None:
    """企业目录（含 ingest.json）：同一份数据 ⑥不拦，加载成功。"""
    co = _copy_base(tmp_path)
    _mutate(co, "income.operating_revenues", lambda v: v * 5)
    _mark_enterprise(co)

    loaded = load_company(co, sanity)
    assert loaded.profile.company_id  # 正常加载（⑥跳过）


def test_enterprise_dir_keeps_identity_checks(sanity, tmp_path: Path) -> None:
    """企业模式只跳⑥：①资产≠负债+权益 仍拦（搬运错误检测不动摇）。"""
    co = _copy_base(tmp_path)
    _mutate(co, "balance.total_assets", lambda v: v + 1)
    _mark_enterprise(co)

    with pytest.raises(FixtureDataError) as ei:
        load_company(co, sanity)
    assert any("勾稽①" in m for m in ei.value.messages), ei.value.messages


def test_data_source_of_precedence(tmp_path: Path) -> None:
    """enterprise（ingest.json 自描述）> session（调用方 scratch 根之下）> fixture。"""
    ent = tmp_path / "enterprises" / "acme_01"
    ent.mkdir(parents=True)
    (ent / "ingest.json").write_text("{}", encoding="utf-8")
    assert data_source_of(ent) == "enterprise"

    scratch = tmp_path / "scratch0"  # 测试里 scratch 根不叫 .scratch——不按名字猜
    sess = scratch / "ui-runs" / "base_co_2029_20261121_000000"
    sess.mkdir(parents=True)
    assert data_source_of(sess, scratch) == "session"
    assert data_source_of(sess) == "fixture"  # 未告知 scratch 根 → 不臆断

    ingest_scratch = scratch / "ingest" / "acme_01_20261121_000000"
    ingest_scratch.mkdir(parents=True)
    (ingest_scratch / "ingest.json").write_text("{}", encoding="utf-8")
    assert data_source_of(ingest_scratch, scratch) == "enterprise"  # 自描述优先于路径

    assert data_source_of(BASE) == "fixture"
