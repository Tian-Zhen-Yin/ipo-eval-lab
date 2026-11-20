"""save_enterprise / list_enterprises（ADR-0013 修订 1；工单 02）。

保存/防覆盖从 CLI 提取为可编程接口（webui 复用）；列表供新建页下拉与
「数据接入」页展示。防覆盖语义与 CLI 现行为一致（exit 2 文案归 CLI）。
"""
import json
from pathlib import Path

import pytest

from ipo_eval_lab.ingest.importer import import_profile
from ipo_eval_lab.ingest.save import SaveRefused, list_enterprises, save_enterprise
from ipo_eval_lab.ingest.template import build_sample_template


@pytest.fixture(scope="module")
def session_dir(tmp_path_factory) -> Path:
    """导入样例得到一个含三件套的会话目录。"""
    root = tmp_path_factory.mktemp("ing")
    xlsx = root / "s.xlsx"
    build_sample_template(xlsx)
    r = import_profile(xlsx, "acme_01", out_root=root / "out")
    assert r.status == "ok" and r.company_dir is not None
    return r.company_dir


def test_save_copies_three_pieces(session_dir: Path, tmp_path: Path) -> None:
    ent = tmp_path / "enterprises"
    dest = save_enterprise(session_dir, "acme_01", ent)
    assert dest == ent / "acme_01"
    assert sorted(p.name for p in dest.iterdir()) == ["ingest.json", "profile.json", "source.xlsx"]


def test_save_refused_preserves_existing(session_dir: Path, tmp_path: Path) -> None:
    ent = tmp_path / "enterprises"
    save_enterprise(session_dir, "acme_01", ent)
    before = (ent / "acme_01" / "profile.json").read_bytes()

    with pytest.raises(SaveRefused, match="已存在"):
        save_enterprise(session_dir, "acme_01", ent)
    assert (ent / "acme_01" / "profile.json").read_bytes() == before  # 拒绝时原样


def test_save_overwrite_replaces(session_dir: Path, tmp_path: Path) -> None:
    ent = tmp_path / "enterprises"
    save_enterprise(session_dir, "acme_01", ent)
    # 在副本上改一个可辨识值后覆盖保存（不动共享的 session_dir 夹具）
    import shutil

    mutated = tmp_path / "mutated_session"
    shutil.copytree(session_dir, mutated)
    prof = json.loads((mutated / "profile.json").read_text(encoding="utf-8"))
    prof["display_name"] = "新名称股份有限公司"
    (mutated / "profile.json").write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")

    save_enterprise(mutated, "acme_01", ent, overwrite=True)
    after = json.loads((ent / "acme_01" / "profile.json").read_text(encoding="utf-8"))
    assert after["display_name"] == "新名称股份有限公司"


def test_list_enterprises_fields(session_dir: Path, tmp_path: Path) -> None:
    ent = tmp_path / "enterprises"
    save_enterprise(session_dir, "acme_01", ent)

    items = list_enterprises(ent)
    assert len(items) == 1
    it = items[0]
    assert it["company_id"] == "acme_01"
    assert it["display_name"] == "样例实业股份有限公司"
    assert it["imported_at"] and len(it["source_sha256"]) == 64
    assert it["fiscal_years"] == [2023, 2024, 2025]


def test_list_empty_and_broken(session_dir: Path, tmp_path: Path) -> None:
    assert list_enterprises(tmp_path / "nope") == []  # 根不存在不炸
    ent = tmp_path / "enterprises"
    save_enterprise(session_dir, "acme_01", ent)
    broken = ent / "bad_co"  # 缺 ingest.json 的残缺目录：跳过不炸
    broken.mkdir()
    (broken / "profile.json").write_text("{}", encoding="utf-8")

    assert [i["company_id"] for i in list_enterprises(ent)] == ["acme_01"]
