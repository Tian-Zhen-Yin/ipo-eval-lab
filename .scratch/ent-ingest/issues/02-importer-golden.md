# 工单 02：import_profile 主链路 + golden 对拍

- blockers：01（模板与坐标常量）
- 决策依据：[ADR-0013](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

`ipo_eval_lab/ingest/` 对外唯一入口
`import_profile(xlsx_path, company_id, out_root=None) -> IngestResult`。
本工单只做 happy path（全必填齐、可选行填齐或按规则推导），违例收集是工单 03。

## 任务

1. `ingest/importer.py`：
   - 按工单 01 的坐标常量解析 → 构造 pydantic `CompanyProfile`
     （schema 见 `ipo_eval_lab/fixtures/models.py`，`extra=forbid`）。
   - 推导规则（缺可选勾稽行时）：`minority = total_equity − attrib_parent`；
     `reconciliation.adjustments = ocf − net_profit_total`（np/ocf 取主表值）；
     `equity_roll.closing = 资产负债表归母`，中间年 `opening = 上年 closing`，
     分红/增资只缺一项 → 该项取残差；两项都缺 → `dividends = 残差`、
     `capital_injection = 0`，入 derived 清单披露；
     **首年 `opening` 缺 = 推导不可行 = 违例**（工单 03 落地报错，本工单先抛
     NotImplementedError 亦可）。
   - 落盘三件套到 `out_root`（默认 `.scratch/ingest/<company_id>_<YYYYmmdd_HHMMSS>/`）：
     `profile.json`（indent=2 UTF-8，与 CLI 同约定）+ `source.xlsx`（原件字节拷贝）+
     `ingest.json`（`data_source: "enterprise"`、`derived_fields[]`、`template_version`、
     `source_sha256`、`imported_at`、`company_id`）。
   - `company_id` 必须由调用方传入（运营方分配），**不得取自 Excel 内客户自填名**。

## TDD（golden 对拍）

`tests/test_ingest_golden.py` 先红：`build_sample_template()` 生成样例 →
`import_profile()` → 产出 `profile.json` 与 `tests/fixtures/ingest/expected_profile.json`
深度比对（含推导字段的期望值）；`ingest.json` 字段齐全；`source.xlsx` 与原件同字节。

## 出界

违例收集与报错（03）；`load_company` 企业模式分支（04）；CLI（05）。
