# 工单 02：save_enterprise/list_enterprises 提取（ingest 层）

- blockers：无（与 01 并行）
- 决策依据：[ADR-0013 修订 1](../../../docs/adr/0013-enterprise-data-ingestion.md)

## 背景

保存/防覆盖逻辑现在长在 `ingest/__main__.py` 的 main() 里，webui（工单 03）要复用；
新建页下拉和「数据接入」页也需要 enterprises 目录的主体列表。提取为可编程接口。

## 任务

1. 新增 `ipo_eval_lab/ingest/save.py`：
   - `save_enterprise(company_dir, company_id, enterprises_root, overwrite=False) -> Path`
     ——目录已存在且非 overwrite → 抛 `SaveRefused`（消息与 CLI 现文案一致：
     「不可再生数据永不静默覆盖——确认替换请加 --overwrite，或更换 company_id」）；
     overwrite=True → rmtree 后 copytree。`__main__.py` 改调它，**exit 2 语义不变**。
   - `list_enterprises(enterprises_root) -> list[dict]`：每项
     `{company_id, display_name, imported_at, source_sha256, fiscal_years[]}`——
     从 `ingest.json` + `profile.json` 摘要；目录缺失返回 `[]`；坏目录（缺件）跳过不炸。
2. webui 侧使用留到工单 03；CLI e2e 测试不回退。

## TDD

`tests/test_ingest_save.py` 先红：保存成功三件套齐 / 重复保存 SaveRefused 且原目录
字节不变 / overwrite 后替换 / list 字段与排序 / 空根目录返回 []。

## 出界

HTTP API（03）；前端（04/05）。
