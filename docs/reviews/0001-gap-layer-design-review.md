# 评审：层①「差距量化 / 还要几年追上」能力定位与 F5 方案

- 日期：2026-11-09
- 对象：F5 的 D 方案（A 历史 CAGR 优先 + 参数兜底）及其加严版（A + 行业基准 + not_quantifiable）
- 结论：**部分合理 → 需改**
- 关联：[CONTEXT.md](../../CONTEXT.md) §3.5、[ADR-0001](../adr/0001-facts-layer-granularity.md)

---

## 1. 结论先行

**分层架构（facts → gap → path → attribution）站得住；但把「eta_years（还要几年）」当成一层的一等结论不成立，应降级为「驱动级可达性区间」，层①的结论本体改为「差距画像」。**

判断依据不是偏好，而是 61 项的构成：能回答"几年"的只有 6 个底层驱动，其余 55 项要么不该问时间、要么问不出可信数字。

---

## 2. 证据：61 项按「杠杆类型」分类

分类依据：种子 `mt_ipo_evaluation_item` 的 `formula` / `index_source` / `default_value` 与 `type` 字段（61 条全量核对）。

| 杠杆类型 | 定义 | 覆盖项 | 数量 | 能否给年数 |
|---|---|---|---|---|
| `grow` | 存量/流量金额，可按增长率累积 | check02-06 营收（5）、check08-12 净利（5）、check13-17 扣非（5）、check18-19 现金流（2）、check20 净资产（1）、check26-28 研发投入（3）、check31 研发投入 CAGR（1） | **22** | 能，但仅 6 个底层驱动 |
| `derived` | 比率，分子分母各自变化 | check21-24 ROE（4）、check25 研发人员占比（1）、check29-30 研发投入占营收比（2） | **7** | 不能直接外推；须拆解为"分子增速需高于分母" |
| `wait` | 时钟，随时间自然满足 | check36 经营年限 | **1** | 能，且**唯一无需增长率假设的硬年数**：`max(0, 阈值 − 当前)` |
| `adjust` | 由发行/股本/定价决策决定，非经营趋势 | check01 市值/预计市值、check37 发行后股本、check38 公开发行股份比例 | **3** | 不能（mock 无估值历史，也无定价参数） |
| `act` | 定性动作 / 布尔声明 | check07（同行 CAGR，底稿自填）、check32-34（3）、check35（1）、check39-49 治理（11）、check50 专利数、check51-55 科创属性（5）、check56-61 板块定位（6） | **28** | 不能；差距是"做什么"，不是"等多久" |

合计 22 + 7 + 1 + 3 + 28 = **61**。

### 2.1 三个直接推论

1. **46%（28/61）的项与时间无关。** 把这 28 项塞进时间轴，只能得到空值或编造值。原方案"每项一个 `eta_years`"必然产生大面积 `not_quantifiable`，但这不是覆盖率缺陷，是**问题模型错误**——它们的差距应表达为"动作幅度"。
2. **时间可算域收敛到 6 个驱动**：`operating_revenues_ytd_bl_cf`、`net_profit_attrib_parent_ytd_cf`、`net_profit_attrib_parent_excl_extra_ytd_cf`、`net_cash_flow_from_oper_ytd_cf`、`total_equity_attr_to_parent_co_pe_bl_cf`、`rd_investment_ytd_bl_cf`。22 个 `grow` 项只是这 6 个驱动的不同切片（DB/AVG/SUM/CAGR），**在 item 级重复算同一年数本身就是冗余**（与 ADR-0001 的去冗余精神冲突）。
3. **`adjust` 三项恰好是多个标准套的首要门槛。** 例如 check01 市值是上交所主板、科创板多套的唯一或首个条件。若层①的结论依赖年数，则这些套"还要几年"**永远无法回答**——而它们往往正是"能不能上岸"的关键套。

### 2.2 敏感性：单点年数是伪精确

以"营收从 1 亿到 3 亿"为例，年数 = `ln(3)/ln(1+r)`：

| 年增长率 r | 所需年数 |
|---|---|
| 10% | 11.5 年 |
| 15% | 7.6 年 |
| 20% | 6.0 年 |
| 25% | 5.0 年 |
| 30% | 4.2 年 |

增长率假设每差 5 个百分点，年数差 1.4~2.1 年；差 10 个百分点，年数差 3 年以上。一个不带区间、不带来源的单点数字（原 D 的 `years_int`）在决策上是**假精确**，写进叙述报告会被读者当作确定事实。

---

## 3. 逐条评三个已暴露的软点

### 3.1 软点一：固定参数兜底无财务依据 —— **成立，应删除而非加严**

- 加严方向（"参数必须带来源，否则 `not_quantifiable`"）方向正确，但**结论是 D 退化为「A + 区间/不可量化」，兜底实际被取消了**。既然如此，不如显式删掉 `config_rate` 这条路径，避免留下一个"总能给出数字"的诱惑。
- 关键区别：**"有来源的参数"不等于"适用于该企业"**。行业增速来自行业报告，与企业自身增速是两回事；把它当兜底，等于把行业平均强加给个体。若要用，只能作为**区间的上/下界参照**，不能作为中值。
- 结论：v1 不建参数库；`reachability` 的 `basis` 只允许 `historical_cagr`（有足够历史年）与 `none`。

### 3.2 软点二：基准库是第三类数据资产且会过期 —— **成立，应降为可选、不进 v1 关键路径**

- 已核实 midas 无任何行业均值/中位数计算（仅 `baia` 模块有"可比公司池"配置，不做聚合），基准库需完全自建。
- 基准库有三个持续成本：样本采集、分层口径（板块/二级行业/规模档）、逐年失效复核。它**不影响层①能否成立**，只影响"参照系好不好"。
- 结论：基准库移出 v1，标记为 Phase 2 可选增强。它的正确用途是给 `r_low/r_high` 提供外部参照（`basis=industry_benchmark`），而不是替代企业自身历史。

### 3.3 软点三：「层①变成子集结论（约 20 项永远没年数）」—— **前提不成立，是分类问题不是覆盖率问题**

- 该软点默认"每项都应有年数"，但 28 项 `act` + 3 项 `adjust` + 7 项 `derived` 本就不属于时间问题。把它们从"缺年数"重新表达为 `lever` 分类后，**不存在"20 项永远没有年数"这种缺陷**，而是"55 项以其他方式表达差距"。
- 真正需要承认的是：**"最快 N 年上岸"这类全局结论，在含 `act`/`adjust` 阻塞项的套上无法给出**。这不是缺陷，是诚实的边界——一个套若卡在"是否有 50 项发明专利"，任何年数都是假的。

---

## 4. 替代方案：F5-R「驱动级可达性 + 差距画像」

### 4.1 层①的新定位

| | 原（D 方案） | 新（F5-R） |
|---|---|---|
| 层①结论本体 | 每项 / 每套的"还要几年" | **差距画像**：谁卡住、差多少、属哪类问题、需要多大动作 |
| 年数地位 | 一等结论字段 | **驱动的附属区间**（`years_low ~ years_high` + `basis`） |
| 不可算项 | `not_quantifiable`（视为空缺） | `lever` 分类 + 动作幅度（视为另一种表达） |
| 增长率来源 | 历史 CAGR + 参数兜底 | 仅历史 CAGR（带窗口与来源）；无则只给差距 |
| 基准库 | 关键路径 | Phase 2 可选 |

### 4.2 核心结构变化：eta 从 item 级搬到 driver 级

```
facts.drivers[]                      ← 新增：6 个驱动，各自年序列
  driver_id = index_code
  series[] = [{year, value, source_ref}]
  growth   = {window, cagr, cagr_basis: {source, computed_at}}
  used_by_items[] = [check02, check03, ...]

layers.gap.per_set[]
  gap_profile:                       ← 新增：层①的结论本体
    blockers[]   = [{item_id, lever, actual, threshold, diff, gap_ratio, severity}]
    by_lever     = {grow: n, derived: n, wait: n, adjust: n, act: n}
    severity_histogram = {critical: n, major: n, minor: n}
  reachability[]:                    ← 替代原 eta.per_item[]
    {driver_id, basis, r_low, r_high, years_low, years_high, years_mid|null, confidence}
  wait_items[] = [{item_id, years_exact}]      ← 唯一无假设的硬年数
  derived_items[] = [{item_id, decomposition, required_condition}]  ← 如"净利增速需>净资产增速"
  action_items[] = [{item_id, required_change}]                     ← act/adjust 的动作幅度
  set_level_eta: {available: bool, years_low, years_high, blocked_by[]}
```

### 4.3 `set_level_eta` 何时给、何时不给

仅在**该套内无 `act` / `adjust` / `derived` 阻塞项**时给区间年数，且取所有 `grow` 驱动区间的并集上限：

- 可给：某套仅由 `市值 + 近1年净利润` 构成，且市值已达标 → 年数由净利润驱动区间决定。
- 不给：套内含任一 `act` 项（如治理、专利、板块定位）→ 输出 `available: false` + `blocked_by: [item_id]` + 动作清单。

这条规则让"最快上岸"在能给时给，在不能给时明确说明原因，而不是用参数硬凑。

### 4.4 覆盖了什么

| 原方案问题 | F5-R 如何解决 |
|---|---|
| 固定参数无财务依据 | 删除参数路径；无历史 CAGR 就只给差距，不编年数 |
| 基准库是易过期资产 | 移出 v1；需要时只作为 `r_low/r_high` 的外部参照 |
| 20 项永远没年数 | 改为 `lever` 分类 + 动作幅度，不存在"缺年数" |
| item 级年数冗余（22 项共享 6 驱动） | eta 归 driver，天然去重 |
| 单点年数伪精确 | 输出区间 + `basis` + `confidence` |
| 比率项被强行外推 | `derived` 拆解为"分子增速需高于分母"的条件式 |
| 市值项无法给年数却被要求给 | `adjust` 明确为发行决策问题，给所需发行规模/定价而非年数 |
| F6 distance 依赖不可靠年数 | distance 用 `gap_ratio` + `lever` 权重，输入全部确定性 |

### 4.5 放弃了什么（必须承认）

| 放弃项 | 影响 | 是否可接受 |
|---|---|---|
| "每项一个年数"的整齐表格 | LLM 拿不到"逐项追赶时间"这种直观表 | 可接受——原表格靠假设填充，属于编造 |
| 单一"最快 N 年上岸"的营销式结论 | 部分套只能给"动作清单 + 条件式时间" | 可接受——含 `act` 阻塞的套本来无确定年数 |
| 固定参数兜底 | 覆盖率下降：无 3 年以上历史的项不给年数 | 可接受——mock 数据本就不足以支撑 |
| 基准库进 v1 | 失去"与行业比"的参照 | 可接受——Phase 2 补；不影响层①成立 |
| 比率项的直接年数 | ROE 等只能给"需净利增速 > 净资产增速"这类条件 | 可接受——这才是财务上正确的表述 |

---

## 5. 改动代价（可决策粒度）

### 5.1 契约字段增删

| 位置 | 动作 | 具体变化 |
|---|---|---|
| `facts` | **新增数组** | `drivers[]`（driver_id、series、growth、used_by_items） |
| `facts.items[]` | **增 2 字段** | `lever`（枚举）、`driver_ids`（[driver_id]，`derived` 项为分子/分母两个驱动） |
| `layers.gap.per_set[]` | **删 1 增 5** | 删 `eta.per_item[]`；增 `gap_profile`、`reachability[]`、`wait_items[]`、`derived_items[]`、`action_items[]` |
| `layers.gap.per_set[].eta` | **替换** | 由 `set_level_eta{available, years_low, years_high, blocked_by[]}` 取代 |
| `layers.path.candidates[].required_actions[]` | **改 1 字段** | `eta_years` → `reachability`（引用 driver 区间）或 `required_change`（act/adjust 项） |
| `layers.attribution` | **不变** | 该层设计本就正确 |
| `narrative_handoff.units[]` | **增 1 字段** | `claim_type`（`gap` / `range` / `action`），防止 agent 把区间写成年数 |
| CONTEXT.md §4 不变量 | **增 2 条** | ①`grow` 项必须映射到已存在的 driver；②`set_level_eta.available=true` 时套内不得有 `act/adjust/derived` 阻塞项 |

### 5.2 规则库 YAML 结构变化

| 变化 | 内容 | 规模 |
|---|---|---|
| 新增 per-item `lever` | 61 项逐项标注；可由 `formula`/`type`/`index_source` 脚本推导约 80%，人工复核 61 项 | 61 条 |
| 新增 per-item `driver_ids` | `grow` 项从公式串 `$指标` 直接抽取；`derived` 项需人工指定分子/分母驱动 | 22 + 7 条 |
| 删除全局 `default_growth_rate` | 不再允许无来源的兜底率 | 1 处 |
| 新增可选 `rate_basis` | `{driver_id, value, source, reviewed_at}`；v1 允许为空 | 0~6 条 |
| 不变 | `checks` 的阈值/op/format/evidence 结构完全不变 | — |

### 5.3 是否新建数据资产

| 资产 | 原设计 | F5-R | 净变化 |
|---|---|---|---|
| 参数库（增长率 + 来源 + 复核） | 必需（兜底依赖它） | **不建**（v1） | 省 1 个库 + 审批流程 |
| 行业基准库（分层 + 样本门槛 + 清单） | 必需（加严后） | **Phase 2 可选** | 省 v1 工作量，保留未来入口 |
| 驱动序列 | 无（隐含在 items.inputs） | `facts.drivers[]`，由现有 mock 年数据直接生成 | 无新采集成本 |

### 5.4 已落地文档是否要改

| 文档 | 是否改 | 改什么 |
|---|---|---|
| [CONTEXT.md](../../CONTEXT.md) §3.5（gap 层） | **重写** | `eta` 段整体替换为 `gap_profile + reachability + 分类数组` |
| CONTEXT.md §3.3（checks） | 不改 | 阈值/evidence 结构不受影响 |
| CONTEXT.md §3.2（items） | **增 2 字段** | `lever`、`driver_ids` |
| CONTEXT.md §3.6（path） | **小改** | `required_actions.eta_years` → `reachability` / `required_change` |
| CONTEXT.md §4（不变量） | **增 2 条** | 见 5.1 |
| CONTEXT.md R4（差距口径） | 不改 | `diff`/`gap_ratio` 被完整继承 |
| [ADR-0001](../adr/0001-facts-layer-granularity.md) | **加 Amendment 段** | facts 新增 `drivers[]`；不改双层结论，只补一层"驱动序列"作为 items 的规范化视图 |
| 新 ADR-0002 | **新建** | 记录"eta 从 item 级降为 driver 级、层①定位改为差距画像"这一不可回退决策 |

### 5.5 工作量估算（人天，含自测；个人项目口径）

| 阶段 | 内容 | F5-R | 原 D 加严版 | 差异 |
|---|---|---|---|---|
| 契约改造 | pydantic 模型 + 6 条不变量校验 | 1.5 | 1.5 | 0 |
| 驱动抽象 | 6 驱动抽取 + 公式串反解 item↔driver | 2.0 | 0 | +2.0 |
| 求解器 | 时点/累计/均值/比率分解 + 区间求解 | 3.0 | 2.0（单点，简单） | +1.0 |
| 规则库标注 | 61 项 `lever` + `driver_ids`（脚本 + 复核） | 1.5 | 1.0 | +0.5 |
| 层②适配 | 去 eta 排序键，改 gap_ratio + lever 权重 | 1.0 | 0.5 | +0.5 |
| 基准库 / 参数库 | 建库 + 分层 + 样本门槛 + 清单 | **0（Phase 2）** | 6.0 | **−6.0** |
| 文档 | CONTEXT 重写 + ADR-0001 修订 + ADR-0002 | 0.5 | 0.3 | +0.2 |
| 回归 | 样例跑通 + 边界用例（负基数、缺年、比率） | 1.0 | 1.0 | 0 |
| **合计（v1）** | | **10.5** | **12.3**（不含基准库运维） | **−1.8** |

持续成本：

| 项 | 原 D 加严版 | F5-R |
|---|---|---|
| 基准库年度复核 | 1~2 人天/年 | Phase 2 起才有 |
| 参数复核流程 | 0.5 人天/次变更 | 无 |

**净判断：F5-R 首次交付更省（−1.8 人天），且去掉一个会持续失效的数据资产；代价是求解器更复杂（+1 人天）和一次性的驱动抽象（+2 人天）。**

---

## 6. 需要拍板的决策点

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| P1 | 是否接受「层①定位改为差距画像，年数降级为驱动级区间」 | 接受 / 保留单点年数 | **接受** |
| P2 | `facts.drivers[]` 是否升为一等数组（需修订 ADR-0001） | 一等数组 / 塞进 `items[].inputs` | **一等数组**（去重 + 有 `growth` 的天然归属） |
| P3 | 基准库是否移出 v1 | 移出 / 保留 | **移出**（Phase 2） |
| P4 | 参数库是否彻底不建 | 不建 / 建带来源版 | **不建** |
| P5 | `set_level_eta` 是否只对"无 act/adjust/derived 阻塞"的套给年数 | 是 / 否 | **是** |

P1 是总开关；P2/P3/P4/P5 是它的推论，可一并确认。
