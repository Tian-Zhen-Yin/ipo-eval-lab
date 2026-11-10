# ADR-0003：指标口径强制与判定五态

- 状态：Accepted（2026-11-10，P1/P3 拍板 + 专家复核 G4）
- 关联：[设计 0001](../design/0001-top-down-redesign.md) §2.3/§3、[ADR-0001 Amendment 1](0001-facts-layer-granularity.md)

## 决策

1. **五态**：`met / not_met / not_applicable / indeterminate / needs_review`。
   折叠（AND 与 OR 同规则，not_applicable 先剔除）：any not_met → not_met；else any (indeterminate|needs_review) → indeterminate；else met。
2. **判定矩阵**（nature × basis）：
   - quantitative × calc → met / not_met / indeterminate
   - documentary × worksheet → met / not_met / indeterminate / needs_review（口径存疑如专利授权与主营应用，→ needs_review）
   - **judgment × 任何 → 只能 needs_review**：自报值记 `declared_value`（证据），输出 `pending_evidence[]`，**永不产生 met**。judgment 项不进层② hard gate，但计入套终态 indeterminate（P3）——引擎无权放行，也无权毙掉。
3. **口径强制**：
   - 净利类判定取扣非前后**孰低**（measures 两维：deduction × audit）；
   - 指标命名带口径后缀：`roe_weighted_avg`（仅加权平均实现）、归母 `attrib_parent`（净利/净资产类默认，剔除少数股东权益）；
   - 研发拆 `rd_expense` / `rd_investment_total`（科创属性判定用 total）；
   - 专利 = `invention_patents_granted` + `applied_to_main_business` 两叶合取；
   - 预计市值必带 `basis: self_estimate`，叙述强制"企业自估"限定；
   - 同行比条件：基准库未建前一律 indeterminate + 显式原因（基准库是该类叶的前置依赖，Phase 2）。
4. **量词六值**：latest / all_periods / sum / avg / cagr / ratio；`all_periods` 独立成叶（"均为正"是逐期全称量词，与累计求和是两个量词）。
5. **差距三分列**：数值叶 diff + gap_ratio；计数叶 required_delta；布尔叶 required_action；禁止跨项聚合。
6. **prune 原则**：已退出评价体系的指标（如研发人员占比，科创属性修订后只剩披露要求）校准时删除，alias 表留痕。

## 理由

评审 0002 B1~B9；专家复核 G4。核心：修复 midas 三态把 not_applicable / indeterminate / needs_review 语义合并的问题，以及"一个指标一个值"无法表达扣非孰低的问题。

## 被否方案

- 三态（R3 推翻）；单值 measurement；总分 / 维度分 / pass_ratio（A5）。

> **补注（2026-11-10，[ADR-0007](0007-progress-and-coverage-metrics.md)）**：A5 的「总分 / 维度分 / pass_ratio 全删」**仍然成立**——`progress` **不是** `pass_ratio` 的复活：
>
> | | `pass_ratio`（仍删） | `progress`（恢复） |
> |---|---|---|
> | 语义 | 「满足项占比」——暗示可补偿 | 「距达标的程度」——**无补偿**，最弱环决定整体 |
> | 与判定关系 | 与判定**脱钩**（83% 上岸是 midas 病灶） | 与判定**同源**：100% ⟺ met |
> | 聚合 | 计数占比 | **min 折叠**（+ `coverage` 配对披露完整度） |
>
> 权重表不引入（进判定 = 改法律语义；进展示 = 无来源装饰）。
