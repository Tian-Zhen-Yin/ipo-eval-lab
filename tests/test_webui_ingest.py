"""webui 企业数据接入 API（ADR-0013 修订 1；工单 03）。

UiApp 纯方法直调（不起 socket，沿 test_webui.py 惯例）。覆盖：上传好/坏件、
护栏（后缀/大小/文件名/company_id）、保存与 409 指纹、越权 session_dir、
预填下载、api_run 直跑企业主体、/api/enterprises 列表。
"""
import json
import shutil
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ipo_eval_lab.webui import UiApp

REPO = Path(__file__).resolve().parents[1]
AS_OF = "2025-06-30"


@pytest.fixture()
def app(tmp_path: Path) -> UiApp:
    return UiApp(
        rulebook_dir=REPO / "rulebook",
        fixtures_root=REPO / "fixtures",
        results_dir=tmp_path / "results",
        ui_dir=REPO / "ui" / "app",
        scratch_root=tmp_path / "scratch",
        enterprises_root=tmp_path / "ent",
    )


def _sample_bytes(tmp_path: Path, broken: bool = False) -> bytes:
    from ipo_eval_lab.ingest.template import build_sample_template

    p = tmp_path / ("broken.xlsx" if broken else "ok.xlsx")
    build_sample_template(p)
    if broken:
        wb = load_workbook(p)
        wb["财务三年一期"]["C2"] = None
        wb.save(p)
    return p.read_bytes()


def _upload_ok(app: UiApp, tmp_path: Path, company_id: str | None = None) -> dict:
    status, payload = app.api_ingest_upload(_sample_bytes(tmp_path), "客户回填.xlsx", company_id)
    assert status == 200 and payload["status"] == "ok", payload
    return payload


# -- 上传 --


def test_upload_ok_returns_preview_and_session(app: UiApp, tmp_path: Path) -> None:
    p = _upload_ok(app, tmp_path)

    assert p["company_id"].startswith("ent_")  # 自动生成
    assert p["violations"] == [] and p["derived"]
    assert p["upload_id"]
    assert p["preview"]["display_name"] == "样例实业股份有限公司"
    assert p["preview"]["fiscal_years"] == [2023, 2024, 2025]
    assert len(p["preview"]["revenue"]) == 3
    d = Path(p["session_dir"])
    assert sorted(x.name for x in d.iterdir()) == ["ingest.json", "profile.json", "source.xlsx"]


def test_upload_custom_company_id(app: UiApp, tmp_path: Path) -> None:
    p = _upload_ok(app, tmp_path, company_id="acme_01")
    assert p["company_id"] == "acme_01"
    assert Path(p["session_dir"]).name.startswith("acme_01_")


def test_upload_violations_structured_no_disk(app: UiApp, tmp_path: Path) -> None:
    status, p = app.api_ingest_upload(_sample_bytes(tmp_path, broken=True), "坏数据.xlsx", None)
    assert status == 200 and p["status"] == "violations"
    v = p["violations"][0]
    assert set(v) == {"sheet", "coord", "label", "reason"}
    assert v["coord"] == "C2" and "营业收入" in v["label"]
    assert p.get("session_dir") is None
    assert not list((tmp_path / "scratch" / "ingest").glob("ent_*"))  # 未落盘


def test_upload_guards(app: UiApp, tmp_path: Path) -> None:
    ok = _sample_bytes(tmp_path)
    assert app.api_ingest_upload(ok, "客户数据.exe", None)[0] == 400        # 后缀
    assert app.api_ingest_upload(ok, "../evil.xlsx", None)[0] == 400        # 路径
    assert app.api_ingest_upload(ok, "客户/回填.xlsx", None)[0] == 400      # 分隔符
    assert app.api_ingest_upload(b"x" * (10 * 1024 * 1024 + 1), "大.xlsx", None)[0] == 413
    assert app.api_ingest_upload(ok, "好.xlsx", "Bad-Id")[0] == 400         # company_id


# -- 保存 --


def test_save_conflict_409_with_fingerprint(app: UiApp, tmp_path: Path) -> None:
    p = _upload_ok(app, tmp_path, company_id="acme_01")
    status, out = app.api_ingest_save(
        {"company_id": "acme_01", "session_dir": p["session_dir"]}
    )
    assert status == 200 and (tmp_path / "ent" / "acme_01" / "ingest.json").exists()

    status, out = app.api_ingest_save(
        {"company_id": "acme_01", "session_dir": p["session_dir"]}
    )
    assert status == 409
    assert out["existing"]["imported_at"] and len(out["existing"]["source_sha256"]) == 64

    status, out = app.api_ingest_save(
        {"company_id": "acme_01", "session_dir": p["session_dir"], "overwrite": True}
    )
    assert status == 200


def test_save_rejects_foreign_session_dir(app: UiApp, tmp_path: Path) -> None:
    status, out = app.api_ingest_save({"company_id": "x", "session_dir": str(tmp_path)})
    assert status == 400 and "session_dir" in out["error"]


# -- 预填 --


def test_prefill_download(app: UiApp, tmp_path: Path) -> None:
    status, p = app.api_ingest_upload(_sample_bytes(tmp_path, broken=True), "坏数据.xlsx", None)
    assert p["status"] == "violations"

    status, ctype, data = app.api_ingest_prefill(p["upload_id"])
    assert status == 200 and "spreadsheet" in ctype
    out = tmp_path / "dl.xlsx"
    out.write_bytes(data)
    ws = load_workbook(out)["财务三年一期"]
    assert ws["C2"].value is None  # 错误格已清空（等客户填回）

    assert app.api_ingest_prefill("no_such_id")[0] == 404


# -- 测评联动与列表 --


def test_api_run_with_enterprise_subject(app: UiApp, tmp_path: Path) -> None:
    p = _upload_ok(app, tmp_path, company_id="acme_01")
    status, _ = app.api_ingest_save({"company_id": "acme_01", "session_dir": p["session_dir"]})
    assert status == 200

    status, out = app.api_run({"company": "acme_01", "as_of": AS_OF})
    assert status == 200, out
    raw = json.loads((tmp_path / "results" / out["file"]).read_text(encoding="utf-8"))
    assert raw["data_source"] == "enterprise"

    status, idx = app.api_results()   # 历史索引带 data_source（徽标数据源；旧 JSON → None）
    assert status == 200 and idx[0]["data_source"] == "enterprise"

    status, out = app.api_run({"company": "no_such", "as_of": AS_OF})
    assert status == 400 and "不存在" in out["error"]


def test_api_enterprises_listing(app: UiApp, tmp_path: Path) -> None:
    status, out = app.api_enterprises()
    assert status == 200 and out == []  # 空根目录

    p = _upload_ok(app, tmp_path, company_id="acme_01")
    app.api_ingest_save({"company_id": "acme_01", "session_dir": p["session_dir"]})
    status, out = app.api_enterprises()
    assert status == 200 and out[0]["company_id"] == "acme_01"
    assert out[0]["fiscal_years"] == [2023, 2024, 2025]


# -- 走查修复：模板下载 / 预填持久化 / 申报口径计数 --


def test_template_download(app: UiApp) -> None:
    """P1-1：空白模板与填写示例可从 webui 获取（xlsx zip 头 + 三 sheet）。"""
    import io

    from openpyxl import load_workbook

    for kind in ("blank", "sample"):
        st, ctype, data = app.api_ingest_template(kind)
        assert st == 200 and data[:2] == b"PK" and "spreadsheet" in ctype
        assert load_workbook(io.BytesIO(data)).sheetnames == ["主体信息", "财务三年一期", "申报口径"]
    assert app.api_ingest_template("evil")[0] == 400


def test_prefill_survives_restart(app: UiApp, tmp_path: Path) -> None:
    """P2-3：upload 记录落盘——新 UiApp 实例（同目录、零内存）仍可下载预填。"""
    status, p = app.api_ingest_upload(_sample_bytes(tmp_path, broken=True), "坏数据.xlsx", None)
    assert p["status"] == "violations"

    app2 = UiApp(
        rulebook_dir=REPO / "rulebook",
        fixtures_root=REPO / "fixtures",
        results_dir=tmp_path / "results",
        ui_dir=REPO / "ui" / "app",
        scratch_root=tmp_path / "scratch",
        enterprises_root=tmp_path / "ent",
    )
    st, ctype, data = app2.api_ingest_prefill(p["upload_id"])
    assert st == 200 and data[:2] == b"PK"
    assert app2.api_ingest_prefill("no_such_id")[0] == 404


def test_preview_declared_stat(app: UiApp, tmp_path: Path) -> None:
    """P3-5：预览带申报口径已填计数（样例填一半 → filled < total）。"""
    p = _upload_ok(app, tmp_path)
    d = p["preview"]["declared"]
    assert 0 < d["filled"] < d["total"] and d["total"] == 30


# -- 勾稽误伤/异常未捕获修复（用户实测反馈：企业主体 + 补录 → Failed to fetch）--


def _wild_bytes(tmp_path: Path) -> bytes:
    """⑥违例但①~⑤自洽的企业数据（营收 1.2亿 → 15亿 → 1.8亿，+1150%/−88%）。"""
    from openpyxl import load_workbook

    from ipo_eval_lab.ingest.template import build_sample_template

    src = tmp_path / "wild.xlsx"
    build_sample_template(src)
    wb = load_workbook(src)
    ws = wb["财务三年一期"]
    ws["C2"] = 1_500_000_000  # 2024 营收 ×10
    wb.save(src)
    return src.read_bytes()


def test_api_run_enterprise_with_overrides_keeps_enterprise_mode(app: UiApp, tmp_path: Path) -> None:
    """企业主体 + 补录：overlay 会话目录必须带 ingest.json（⑥不误伤），200 且来源=enterprise。"""
    status, p = app.api_ingest_upload(_wild_bytes(tmp_path), "野数据.xlsx", "wild_co")
    assert status == 200 and p["status"] == "ok"
    app.api_ingest_save({"company_id": "wild_co", "session_dir": p["session_dir"]})

    status, out = app.api_run(
        {"company": "wild_co", "as_of": AS_OF, "overrides": {"documentary": {"operating_years": 20}}}
    )
    assert status == 200, out
    raw = json.loads((tmp_path / "results" / out["file"]).read_text(encoding="utf-8"))
    assert raw["data_source"] == "enterprise"
    sessions = list((tmp_path / "scratch" / "ui-runs").glob("wild_co_*/ingest.json"))
    assert sessions, "overlay 会话目录缺 ingest.json——企业模式丢失"


def test_fixture_data_error_returns_400_not_crash(tmp_path: Path) -> None:
    """勾稽红必须 400 可读，不能穿透成网络层失败（Failed to fetch）。"""
    import shutil as _sh

    fx = tmp_path / "fx"
    fx.mkdir(parents=True)
    _sh.copy(REPO / "fixtures" / "sanity.yaml", fx / "sanity.yaml")
    _sh.copytree(REPO / "fixtures" / "companies" / "base_co_2029", fx / "companies" / "bad_co")
    prof = json.loads((fx / "companies" / "bad_co" / "profile.json").read_text(encoding="utf-8"))
    last = max(prof["statements"], key=lambda s: s["fiscal_year"])
    last["balance"]["total_assets"] += 1  # ① 破坏
    (fx / "companies" / "bad_co" / "profile.json").write_text(
        json.dumps(prof, ensure_ascii=False), encoding="utf-8"
    )
    app = UiApp(
        rulebook_dir=REPO / "rulebook",
        fixtures_root=fx,
        results_dir=tmp_path / "results",
        ui_dir=REPO / "ui" / "app",
        scratch_root=tmp_path / "scratch",
        enterprises_root=tmp_path / "ent",
    )
    status, out = app.api_run({"company": "bad_co", "as_of": AS_OF})
    assert status == 400 and "勾稽①" in out["error"], out
