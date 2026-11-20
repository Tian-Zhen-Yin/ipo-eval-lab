# 工单 04：load_company 企业模式 + run meta 打 data_source

- blockers：02
- 决策依据：[ADR-0013](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

ADR-0013：勾稽⑥只属 mock 卫生参数。`load_company()` 见 `company_dir/ingest.json`
存在 → 企业模式（①~⑤留、⑥跳）——**目录自描述驱动，签名与调用方零改动**。
run 结果 JSON meta 顶层打 `data_source: fixture | session | enterprise`。

## 任务

1. `fixtures/loader.py`：`load_company()` 检测 `company_dir/"ingest.json"` 存在 →
   跳过⑥（实现方式自选：`check_profile(profile, sanity, skip_growth=...)` 或
   `sanity=None` 语义化处理；**fixtures 现有测试必须全绿不回退**）。
2. data_source 判定函数（建议放 `ingest/` 或 `fixtures/`，两处调用方共用）：
   目录含 `ingest.json` → `enterprise`；路径位于 `.scratch` 下 → `session`
   （webui 补录目录 `ui-runs` 先例，见 `webui.py` api_run）；否则 `fixture`。
3. `webui.py` 落盘处与 `cli.py` 落盘处：run JSON meta 顶层加 `data_source`。

## TDD

`tests/test_loader_enterprise_mode.py` 先红：企业目录（用工单 02 产出的样例目录
或手工构造含 `ingest.json` 的 tmp 目录 + 一个⑥超界但①~⑤自洽的 profile）→
`load_company()` 不抛；同数据⑥正常区间外但①违例 → 仍抛①。
fixtures 目录全部既有测试不回退。`tests/test_webui.py` 补 data_source 断言。

## 出界

不改 `sanity.yaml`；不做 run JSON 其他字段变更。
