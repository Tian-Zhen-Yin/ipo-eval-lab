# 工单 01：模板底稿与字段坐标（含 openpyxl 引入）

- blockers：无（首张工单）
- 决策依据：[ADR-0013](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

企业数据接入的唯一入口是标准模板 Excel（客户财务填写）。模板双 sheet：
「财务三年一期」（必填主表行 + 可选勾稽行，3 个完整年度列 + 可选 1 期 stub 列）
与「申报口径」（documentary/declared 约 25 字段，留空合法 → null → indeterminate）。
字段坐标常量是 importer 与模板的**单一事实源**——两边不得各写一份。

## 任务

1. `.venv/bin/pip install openpyxl`（项目首个第三方运行时依赖，ADR-0013 已拍板；
   项目无 pyproject，依赖直接装进 `.venv`）。
2. 新建包 `ipo_eval_lab/ingest/`：
   - `template.py`：坐标常量（sheet 名、表头行、年度列、字段行 ↔ `CompanyProfile`
     字段映射，字段带中文名供违例报告用）；`build_blank_template(path)`（空白模板，
     财务友好：中文列头、说明行）；`build_sample_template(path)`（填好样例）。
   - 样例数字**手写小数字**（如营收 100/120/150 百万级，勾稽自洽），便于 golden
     期望 profile 可读；不从 `fixtures/companies/base_co_2029` 抄。
     勾稽①~⑤必须自洽；⑥对企业模式已跳过，不要求。
3. 样例模板的申报口径 sheet 填一半留一半（验证「留空合法」路径）。

## TDD

`tests/test_ingest_template.py` 先红：模板可被 openpyxl 重开、坐标常量命中的
必填格在样例模板中非空、空白模板对应格为空 → 实现 → 绿。

## 出界

不做 importer（工单 02）；不做 webui；不做样式美化 beyond 中文表头+说明行。
