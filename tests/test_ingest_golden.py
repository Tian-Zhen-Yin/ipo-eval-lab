"""企业数据导入·golden 对拍（ADR-0013；工单 02）。

样例模板（坐标常量的样例值，少数股东权益/调节项两行故意留空）→
import_profile() → profile.json 必须与 expected_profile.json 深度一致——
schema 加字段而模板/导入器没跟上时，本测试红（「模板↔schema 不脱钩」闸门）。
三件套契约（profile.json + source.xlsx + ingest.json）同时锁定。
"""
import hashlib
import json
from pathlib import Path

from ipo_eval_lab.ingest.importer import IngestResult, import_profile
from ipo_eval_lab.ingest.template import build_sample_template

GOLDEN = Path(__file__).parent / "fixtures" / "ingest" / "expected_profile.json"

# 样例里两行留空 → 推导；equity_roll 的 np/closing 无模板行 → 恒推导
EXPECTED_DERIVED = {
    "balance.minority_interests",
    "reconciliation.adjustments",
    "equity_roll.net_profit_attrib_parent",
    "equity_roll.closing_attrib_parent",
}


def test_import_sample_matches_golden(tmp_path: Path) -> None:
    xlsx = tmp_path / "客户样例.xlsx"
    build_sample_template(xlsx)

    result = import_profile(xlsx, "sample_co_01", out_root=tmp_path)

    assert isinstance(result, IngestResult)
    assert result.status == "ok"
    assert result.company_dir is not None
    profile = json.loads((result.company_dir / "profile.json").read_text(encoding="utf-8"))
    assert profile == json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_import_artifacts_three_pieces(tmp_path: Path) -> None:
    """三件套：profile.json / source.xlsx（原件字节拷贝）/ ingest.json（契约字段）。"""
    xlsx = tmp_path / "客户样例.xlsx"
    build_sample_template(xlsx)

    result = import_profile(xlsx, "sample_co_01", out_root=tmp_path)
    assert result.company_dir is not None
    d = result.company_dir

    assert (d / "source.xlsx").read_bytes() == xlsx.read_bytes()

    meta = json.loads((d / "ingest.json").read_text(encoding="utf-8"))
    assert meta["data_source"] == "enterprise"
    assert meta["company_id"] == "sample_co_01"
    assert meta["display_name"] == "样例实业股份有限公司"
    assert meta["template_version"] == 1
    assert meta["source_sha256"] == hashlib.sha256(xlsx.read_bytes()).hexdigest()
    assert meta["imported_at"]
    assert set(meta["derived_fields"]) == EXPECTED_DERIVED
    assert set(result.derived_fields) == EXPECTED_DERIVED
