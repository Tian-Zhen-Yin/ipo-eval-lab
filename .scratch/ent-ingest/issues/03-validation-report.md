# 工单 03：违例收集式校验报告

- blockers：02
- 决策依据：[ADR-0013](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

ADR-0013：违例**收集式**（一次报全，风格对齐 `fixtures/loader.py` 的
`FixtureDataError`——「一次收集全部违例再抛」），逐条带 sheet/行号（或单元格）+
字段中文名+原因/勾稽号；`status = "violations"` 时**不落盘**、`company_dir = None`。

## 任务

`ingest/importer.py` 扩两层校验：

1. **解析层**：缺必填（含首年期初归母权益）、类型错（非整数）、枚举非法
   （audit status/opinion、documentary/declared 布尔）；此层违例则 profile 构造不出，
   逐格报告。
2. **profile 层**：构造成功后跑勾稽**①②③④⑤（跳⑥）**——优先参数化复用
   `fixtures/loader.py` 的 `check_profile`（如 `skip_growth=True`），不改其现有
   fixtures 侧行为；违例带勾稽号映射回 sheet/行。

## TDD

`tests/test_ingest_violations.py` 先红，逐类坏样例（基于样例模板改格）：
缺一个必填格 / total_assets ≠ 负债+权益 / 年份断档（③链断）/ 首年 opening 缺 →
各自命中预期违例条目；违例时目标目录不存在（未落盘）；多错并存时**一次报全**。

## 出界

`load_company` 分支（04）；CLI 打印格式（05，本工单只保证 `violations[]` 数据结构）。
