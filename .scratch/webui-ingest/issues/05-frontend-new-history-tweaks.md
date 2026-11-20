# 工单 05：新建页分组下拉 + 历史页来源徽标

- blockers：03（/api/companies 分组与 /api/enterprises 数据就绪）
- 决策依据：[ADR-0013 修订 1](../../../docs/adr/0013-enterprise-data-ingestion.md)

## 任务（ui/app/）

1. `page-new.js`：主体下拉改 `<optgroup>` 分组——「示例主体」（fixtures，现行为
   不变）与「企业主体」（enterprises：显示 display_name + company_id）；默认仍选
   第一个示例主体（不改变现有用户习惯）。
2. `page-history.js`：结果行按 `data_source` 加徽标——`enterprise`（蓝「企业」）/
   `session`（灰「补录」）/ `fixture` 或字段缺失（不显示，历史 JSON 兼容）。
   徽标只标识来源，不可点击、不改变既有行交互。

## 验证

browser-use 截图走查：下拉分组渲染、选企业主体跑一次、历史页徽标（含旧 JSON
无 data_source 时不炸不显示）。

## 出界

数据接入页（04）；徽标不做筛选功能（有人要再说）。
