# ADR-0002：套建模（group/branch）与三段式固定组合树

- 状态：Accepted（2026-11-10，P2/P5/P6/P7 拍板）
- 关联：[设计 0001](../design/0001-top-down-redesign.md) §0.5/§1~§2、[calibration/0001](../calibration/0001-set-inventory.md)、CONTEXT D4

## 背景

v0.1 把 64 个「板块×企业类型×套序号」组合平铺为套，维度沿用 midas UI 四分法，套带 pass_ratio。评审 0002 指控笛卡尔积造假套；种子复核**修正了事实**（64 条目皆真实条文，非叉积；红筹/表决权差异专套真实存在），但确认：①21 处「或」支路被拆成独立条目（主板 sort1/sort2 净利条文逐字相同）；②存在笔误（主板 sort3 市值 350亿，应为 50亿）；③沪深主板同文重复。

## 决策

1. **三段式固定树**：板块结论 = AND(段①发行条件 issuance，段②板块定位 positioning，OR(段③上市标准套 listing_sets))。树形由法规结构决定，**写死在引擎**，不建通用表达式引擎。
2. **四层条件层级**：leaf（`logic ∈ {all, any}`，表达条文内择一）→ clause（条文）→ branch（支路，挂 set_id，与快照行对应）→ group（官方套，group_no）。OR 出现在 group 间、branch 间、clause 内；AND 为 clause 内默认与 branch 内。法规现实示例：主板第一套「现金流≥2亿 或 营收≥15亿」、科创属性研发投入「占比≥5% 或 累计≥8000万」。
3. **适用性**：`applicant_profile`（company_type ∈ 4 枚举 + profit_status 等）+ applicability 谓词（等值/枚举/**in_list** 合取，覆盖行业负面清单）；不匹配 → 套级 `not_applicable`，出分母，保留在事实层。
4. **权威源链**：法规原文（authority）→ 规则库 YAML（人工校准）→ midas 快照（trace，仅作起点与回归对照）。套清单以校准为准：**43 官方套**（沪深同文合并 34）。
5. **删除 pass_ratio**（套是必要条件合取，不存在"83% 上岸"）；五态计数替代；sort 仅官方编号，不参与排序。

> **补注（2026-11-10，[ADR-0007](0007-progress-and-coverage-metrics.md)）**：本条**仍然成立**。恢复的 `progress`（进度）/ `coverage`（覆盖率）**不是 pass_ratio**——`progress` 用 **min 折叠**且与 AND 判定**同源**（100% ⟺ met），「无补偿」的语义反而被强化；pass_ratio 那种「满足项占比可补偿」的形态仍被删除。

## 被否方案

- 维度组合派生套（叉积思维）；通用布尔表达式引擎（为不存在的灵活性付复杂度）；pass_ratio / 维度计分（评审 0002 A2/A5）。

> 补注同上：`pass_ratio` / 维度计分仍然被否（[ADR-0007](0007-progress-and-coverage-metrics.md) 恢复的 `progress` / `coverage` 与二者均不同源）。

## 后果

- 规则库 schema（未决 #3）按 group/branch/clause/leaf 四实体设计。
- 不变量「同 group 各 branch 共享公共条文」成为校准自动检查项（可抓转写噪音）。
- midas standardId（63 规则包）不参与建模，仅 trace。

## 勘误注（2026-11-10，随设计 0002 R2 拍板）

「branch（支路，挂 set_id，与快照行一一对应）」放宽为：**branch 对应官方文本的成组择一路径**；快照的「或」拆行（如主板 sort1/sort2 的现金流/营收两叶）在权威模型中收敛为**同一 branch 内 clause `logic: any`**，两行快照经 `aliases` 追溯到同一 branch。判据：单一指标内联「或」→ clause any；法条并列情形（各自捆绑多个条件）→ branch。样板验证：`rulebook/sets/cn_main_general.yaml`（IPO-01/IPO-02 两行 collapse 到单 branch）与 `rulebook/sets/star_general.yaml`（两条路径各为 branch）。
