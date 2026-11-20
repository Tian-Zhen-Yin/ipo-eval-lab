"""ingest CLI（ADR-0013；工单 05）：导入三态 + --save 防覆盖 + 企业目录端到端。

退出码契约：0 = 成功；1 = 违例（报告一次报全、不落盘）；2 = --save 防覆盖拒绝。
端到端：⑥违例（营收 +400%）的企业数据经 --save 入 enterprises/ 后，
run_eval 直接跑通——企业模式（目录自描述 ingest.json）不被卫生区间误伤。
"""
from pathlib import Path

from openpyxl import load_workbook

from ipo_eval_lab.engine import RunTarget, run_eval
from ipo_eval_lab.ingest.__main__ import main as ingest_main
from ipo_eval_lab.ingest.source import data_source_of
from ipo_eval_lab.ingest.template import FIN_ROWS, build_sample_template
from tests.fixture_rulebook import fixture_rulebook_dir

REPO = Path(__file__).resolve().parents[1]
ROW = {r.key: r.row for r in FIN_ROWS}


def _sample(tmp_path: Path, name: str = "客户.xlsx") -> Path:
    p = tmp_path / name
    build_sample_template(p)
    return p


def _run(tmp_path: Path, xlsx: Path, *extra: str, company_id: str = "acme_01") -> int:
    return ingest_main(
        [str(xlsx), "--company-id", company_id, "--out-root", str(tmp_path / "out"), *extra]
    )


def test_cli_ok_prints_dir_and_derived(tmp_path: Path, capsys) -> None:
    xlsx = _sample(tmp_path)
    rc = _run(tmp_path, xlsx, "--save", "--enterprises-root", str(tmp_path / "ent"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "acme_01_" in out and "已导入" in out
    assert "推导" in out and "少数股东权益" in out  # derived 清单用人读中文
    assert (tmp_path / "ent" / "acme_01" / "ingest.json").exists()


def test_cli_violations_reported_exit1_no_disk(tmp_path: Path, capsys) -> None:
    xlsx = _sample(tmp_path)
    wb = load_workbook(xlsx)
    wb["财务三年一期"][f"C{ROW['income.operating_revenues']}"] = None  # 2024 营收缺
    wb.save(xlsx)

    rc = _run(tmp_path, xlsx)
    assert rc == 1
    out = capsys.readouterr().out
    assert "C2" in out and "营业收入" in out and "未落盘" in out
    out_root = tmp_path / "out"
    assert not out_root.exists() or not list(out_root.glob("acme_01_*"))


def test_cli_save_refuses_existing_until_overwrite(tmp_path: Path, capsys) -> None:
    """不可再生数据永不静默覆盖：重复 --save 须 exit 2 并点名 --overwrite。"""
    xlsx = _sample(tmp_path)
    ent = tmp_path / "ent"
    args = ("--save", "--enterprises-root", str(ent))

    assert _run(tmp_path, xlsx, *args) == 0
    first = (ent / "acme_01" / "profile.json").read_bytes()

    rc = _run(tmp_path, xlsx, *args)
    assert rc == 2
    assert "--overwrite" in capsys.readouterr().err
    assert (ent / "acme_01" / "profile.json").read_bytes() == first  # 拒绝时原目录不动

    assert _run(tmp_path, xlsx, *args, "--overwrite") == 0
    assert (ent / "acme_01" / "profile.json").exists()


def test_gitignore_covers_enterprises() -> None:
    """客户真实财务数据不入 git（ADR-0013：与 fixtures/ 物理分离 + gitignore）。"""
    assert "enterprises/" in (REPO / ".gitignore").read_text(encoding="utf-8")


def test_saved_enterprise_dir_runs_eval_without_growth_trap(tmp_path: Path) -> None:
    """端到端：⑥违例（末年营收 ×5 = +400%）企业数据 → 导入保存 → run_eval 跑通。"""
    xlsx = _sample(tmp_path)
    wb = load_workbook(xlsx)
    ws = wb["财务三年一期"]
    ws[f"D{ROW['income.operating_revenues']}"] = ws[f"D{ROW['income.operating_revenues']}"].value * 5
    wb.save(xlsx)

    ent = tmp_path / "ent"
    rc = _run(tmp_path, xlsx, "--save", "--enterprises-root", str(ent))
    assert rc == 0
    co = ent / "acme_01"
    assert data_source_of(co) == "enterprise"

    with fixture_rulebook_dir() as rb_dir:
        ctx = run_eval(
            company_dir=co,
            rulebook_dir=rb_dir,
            fixtures_root=REPO / "fixtures",
            as_of="2025-06-30",
            target=RunTarget(boards=None, sets=None),
        )
    assert ctx.result  # ⑥误伤会在 load_company 抛 FixtureDataError
