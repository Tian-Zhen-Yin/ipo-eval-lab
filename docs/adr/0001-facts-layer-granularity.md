# ADR-0001：结果事实层采用 item / check 双层结构

- 状态：Accepted
- 日期：2026-11-09
- 关联：CONTEXT.md R2（事实层粒度）、R3（三态）、R4（差距口径）；grilling 问题 #1

## 背景

结果 JSON 要同时服务四层分析（差距量化 / 最优路径 / 归因诊断 / 叙述报告）。必须满足：

1. 四层不得各自保存一份实测值、阈值、判定和 evidence（用户明确要求"避免冗余"）。
2. 同一个 `item` 在不同"标准套"下阈值不同，但实测值只由公式计算一次、与套无关。
3. 层③要区分"数据缺失/不可计算"与"真实不达标"，而 midas 的 `isSatisfied` 在 `value == null` 时直接返回 0（未知与不达标被合并）。
4. 法规 evidence 必须有一等位置，可被层④逐句引用。
5. 规模：61 个测评项；227 条阈值；62 个（板块×企业类型×套序号）组合，套内 1~11 项，展开约 250 条判定。

## 决策

`facts` 是唯一事实源，分三个数组：

- `facts.items[]`：item 级实测（实测值、期间、可算性、数据质量、可选数据溯源 `inputs`）。实测值只存这一份。
- `facts.checks[]`：`item × 标准套` 的判定，字段含阈值、比较符、`status`、`diff`、`gap_ratio`、规则 id 与 `evidence`；通过 `item_id` 引用实测，不复制实测值。
- `facts.sets[]`：标准套身份与成员（板块、企业类型、套序号、成员/必选项）。

约束：

- `layers.gap / path / attribution` 只引用 id；`distance` 归 `path`，`eta` 归 `gap`，均不写入 `sets`。
- `evidence` 只出现在 `checks[].evidence`（法规）与 `items[].inputs`（数据溯源）两处。

## 理由

- **无口径漂移**：一个营收值只计算/存储一次；若按套平铺，同一值会重复约 4 倍，任何口径修正都要同步多行。
- **层③天然可按 item 聚合**：`data_quality` 挂在 item 上，不会被某个套的判定副本污染。
- **三态可落地**：`unknown` 是 check 的状态，与 `fail` 并列；层②枚举时把 unknown 视为 blocking，层③把 unknown 归到数据质量。
- **evidence 位置正确**：法规约束的是"阈值要求"，天然属于 check（同一套内同一项的判定），而非实测。
- **规模可控**：约 250 条 check，双层 join 的复杂度对本地项目完全可接受。

## 代价

- 消费方（含 LLM agent）需做一次 join：`check.item_id → items.measurement`。缓解手段：check 可带 `item_name` 之类纯展示标签，但**实测值仍只认 items**。
- 规则库必须在评测前把"套→成员项→阈值"解析成 checks（依赖 #3 的规则库 schema）。

## 被否方案

1. **单层 `evaluations[]`（每行 item×套，行内内嵌实测值）**：LLM 最友好，但实测值重复约 4 倍；层③需按 item 去重聚合；口径修正要同步多行，易漂移。
2. **三层 `items[] + thresholds[] + checks[]`**：阈值跨板块复用（如 618 号规则包挂 5 板块），最省空间；但阈值与 check 实际 1:1，独立成表收益很小，个人项目属过度设计。

## 后果

- pydantic 契约需实现 CONTEXT.md §4 的五条不变量（外键存在、计数守恒、fail 必带差距与 evidence、层内不得出现实测值、叙述数字必须带引用）。
- 若未来某层确实需要"扁平视图"，只能作为**派生产物**（由 `facts` 生成、不落契约），不得反向写入事实层。
