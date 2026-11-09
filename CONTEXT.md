# CONTEXT：ipo-eval-lab

> 本项目**决策与契约的单一入口**。HANDOFF.md 中的已定案内容已吸收于此（HANDOFF 暂留作未决问题索引，待 grilling 全部收敛后删除）。
> 最近更新：2026-11-09（F1/F2/F3/F4 定案）

## 1. 项目定位与边界

| # | 决策 | 内容 |
|---|------|------|
| D1 | 定位 | 本地个人实验项目；企业数据 = mock（只消费本地文件，采集不在范围） |
| D2 | 技术栈 | Python：pydantic 契约 + YAML 规则库 + CLI；代码不复用 midas，只复用设计语义 |
| D3 | AI 接入 | 项目内零 AI 依赖。引擎输出结构化结果 JSON；第四层叙述报告由外部 agent 读 JSON 生成，LLM 只叙述、不碰计算 |
| D4 | 标准校准 | 对照交易所规则原文逐条校准 61 测评项 / 227 阈值，每条补 evidence 法规出处；**上市标准"套"为一等公民**（板块×企业类型×套序号） |
| D5 | 测评链 | 复用 midas 责任链模式：Init→Calc→Fetch→Result 四节点 + Context 有序遍历；公式语义对齐 `FormulaFactory` |
| D6 | 结果分析 | 四层递进：①差距量化（含 CAGR 类"还要几年追上"）②最优路径（枚举 板块×标准套）③归因诊断（数据质量 vs 真实差距）→ 前三层纯规则；④叙述报告（agent） |

## 2. 结果 JSON 契约决策（本轮）

| # | 决策 | 内容 | 备注 |
|---|------|------|------|
| R1 | L4 契约边界 | 引擎只输出 `facts + layers.gap/path/attribution + narrative_handoff`；L4 正文是 agent 产物，引擎不定义叙述字段 | 引擎输出不可变、零 AI |
| R2 | 事实层粒度 | 双层：`facts.items[]`（item 级实测，唯一权威） + `facts.checks[]`（item×标准套 判定，引用 item_id） + `facts.sets[]`（套成员） | 见 ADR-0001 |
| R3 | 判定态 | 三态 `pass / fail / unknown`；`unknown` 不得计为 fail | 修复 midas `null→0` 的语义合并 |
| R4 | 差距口径 | `diff = 实测 − 阈值`；`gap_ratio = (阈值 − 实测) / 阈值`（仅 fail 的数值项）；不采用 midas `diffRate = diff/实测` 作为主口径 | midas 口径仅作 trace，不入契约 |

## 3. 结果 JSON 契约 v0.1（字段全集）

约定：
- 百分比一律存小数（`0.15` 表示 15%）；金额存元；实测值与阈值必须同量纲，`suffix` 仅用于展示。
- 所有 id 全局唯一；`checks` 必须引用已存在的 `item_id` 与 `set_id`；各层只存 id 引用，禁止复制实测值/阈值/evidence。
- `evidence` 只出现在 `checks[].evidence`（法规出处）与 `items[].inputs`（数据溯源）两处。

### 3.1 顶层信封

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_version` | str | 契约版本，如 `"0.1"` |
| `run` | object | 见下 |
| `facts` | object | `items[] / checks[] / sets[]` |
| `layers` | object | `gap / path / attribution` |
| `narrative_handoff` | object | 给 agent 的可叙述单元与引用索引 |

`run`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `run_id` | str | 一次评测的唯一 id |
| `engine_version` / `rulebook_version` | str | 引擎与规则库版本 |
| `created_at` | str | ISO 时间 |
| `input.company_file` / `input.company_id` | str | mock 数据文件与主体 id |
| `input.report_period` | `{start_year,end_year,as_of_year}` | 报告期（period 表达归 #2，此处仅占位） |
| `input.target` | `{board,company_type,sets[]\|"all"}` | 可选；为空表示全枚举（层②需要） |

### 3.2 `facts.items[]`（ItemFact）

| 字段 | 类型 | 说明 |
|---|---|---|
| `item_id` / `code` / `name` | str | `check01`~`check61`（种子实测 61 条） |
| `dimension` | enum | `financial_status` / `subject_qualification` / `governance_operation` / `sector_alignment` |
| `basis` | enum | `calc`（公式取数）/ `worksheet`（底稿）/ `declared`（主观声明，如 check07、check51-61） |
| `formula` / `index_codes` | str? / [str] | 公式串与 `$指标`（如 `CAGR($operating_revenues_ytd_bl_cf,#1,#3,2)`） |
| `measurement.value` | number\|bool\|null | 实测值，**唯一权威副本** |
| `measurement.value_type` | enum | `number` / `integer` / `percent` / `boolean` / `text`（对齐 `DataFormatEnum` 0-4） |
| `measurement.period` | str? | `"2024"` 或 `"2022~2024"`（对齐 `getFormulaCalcYear`） |
| `measurement.computable` | bool | 公式是否可算 |
| `measurement.null_reason` | enum? | `missing_years` / `non_positive_base` / `zero_denominator` / `no_data` |
| `data_quality.source_years` / `missing_years` | [int] | 层③归因依据 |
| `data_quality.completeness` | enum | `complete` / `partial` / `absent` |
| `data_quality.user_adjusted` | bool | 是否经"调整重测" |
| `data_quality.flags` | [enum] | `missing_year` / `negative_base` / `zero_denominator` / `declared_only` 等 |
| `inputs`（可选） | `[{index_code, year, value, source_ref}]` | 数据溯源，供层③与审计 |

### 3.3 `facts.checks[]`（Check，item × 标准套）

| 字段 | 类型 | 说明 |
|---|---|---|
| `check_id` | str | `chk:{set_id}:{item_id}` |
| `set_id` / `item_id` | str | 双外键 |
| `requirement_text` | str | 官方口径文本（如 `≥10亿`） |
| `op` | enum | `GT` / `GE` / `LT` / `LE` / `EQ`（符号化，不用 midas 数字码） |
| `threshold_value` | number\|bool | 阈值 |
| `value_type` / `suffix` | enum / str? | 同 item |
| `status` | enum | **`pass` / `fail` / `unknown`** |
| `diff` | float? | `实测 − 阈值`（数值项） |
| `gap_ratio` | float? | `(阈值 − 实测) / 阈值`（仅 fail 数值项；阈值为 0 时 null） |
| `rule_id` | str | 规则库条目 id |
| `evidence` | `[{doc_title, doc_no, article, quote, source_ref, effective_date}]` | 法规出处（一等多位置） |

### 3.4 `facts.sets[]`（SetAssessment）

| 字段 | 类型 | 说明 |
|---|---|---|
| `set_id` | str | `STAR:general:2` = 板块:企业类型:套序号 |
| `board` / `company_type` / `set_no` / `set_name` | str\|int | 套名取规则原文 `asset_name`，如"市值+净利润+营收" |
| `member_items` / `required_items` | [item_id] | 套内成员/必选项（由 178 条规则条文重建，归 #3） |
| `outcome.status` | enum | `feasible` / `infeasible` / `undetermined` |
| `outcome.pass_count` / `fail_count` / `unknown_count` | int | 计数 |
| `outcome.pass_ratio` | float? | 通过率（仅展示，不作距离） |

> `distance`、`eta` **不放在 sets**：分别归 `layers.path` / `layers.gap`，避免二次冗余（R2 的直接推论）。

### 3.5 `layers.gap`（① 差距量化）

| 字段 | 类型 | 说明 |
|---|---|---|
| `baseline` | `{as_of_year, report_period}` | 基准 |
| `per_set[]` | array | 见下 |
| `closest` | `{set_id, reason}` | 当前最接近可上岸的套 |

`per_set[]`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `set_id` | str | 引用 `facts.sets` |
| `passed_items` / `unknown_items` | [item_id] | 引用 |
| `failed_items[]` | `[{item_id, actual, threshold, diff, gap_ratio}]` | 数值冗余为展示副本，权威仍在 `checks` |
| `eta` | object | 见下（**F5 待定稿**） |

`eta`（v0.1 骨架，语义待 F5）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `assumption` | `{type, value, window, source}` | 增长率假设；`type` ∈ 待定 |
| `per_item[]` | `[{item_id, years_exact, years_int, status, note}]` | `status` 枚举待定（已达标/可达/不可达/不可量化） |
| `set_level` | object | 套级口径（取 max / 投影重算，待定） |

### 3.6 `layers.path`（② 最优路径）

| 字段 | 类型 | 说明 |
|---|---|---|
| `metric` | `{name, version, definition, weights, normalization}` | 距离定义必须自带，保证跨套可比（**F6 待定稿**） |
| `candidates[]` | `[{set_id, distance, rank, feasible, blocking[], required_actions[]}]` | `required_actions` = `[{item_id, from, target, improvement, eta_years}]` |
| `best` | `{set_id, why, tradeoffs}` | 最优套与理由 |
| `alternatives` / `excluded` | array | 次优理由 / 排除原因（不适用、确定不可达） |

### 3.7 `layers.attribution`（③ 归因诊断）

| 字段 | 类型 | 说明 |
|---|---|---|
| `per_failed_check[]` | `[{check_id, item_id, cause, subcause, evidence_refs[], confidence}]` | `cause` ∈ `real_gap` / `data_quality` / `mixed` / `declared_only`；`subcause` ∈ `missing_year` / `non_positive_base` / `user_declared` / `threshold_mismatch` / `none` |
| `summary` | `{by_cause{}, data_gap_items[], real_gap_items[]}` | 汇总 |

### 3.8 `narrative_handoff`（④ 交给 agent）

| 字段 | 类型 | 说明 |
|---|---|---|
| `units[]` | `[{unit_id, topic, refs[], key_figures[], evidence_refs[]}]` | 可叙述单元；`refs` 为 check/item/set id |
| `citation_index` | object | 法规 evidence 汇总，供引用编号 |

## 4. 契约不变量（pydantic 校验器实现）

1. `check.item_id` ∈ `items`；`check.set_id` ∈ `sets`；`set.member_items` ⊆ `items`。
2. `pass_count + fail_count + unknown_count == len(required_items)`。
3. 每个 `fail` 的数值项必有 `diff` 与 `gap_ratio`；每个 `fail` 必有非空 `evidence`。
4. 各层出现的 `item_id` / `set_id` 必须已存在于 `facts`；层内不得出现 `measurement.value` 字段。
5. `narrative_handoff.units[].key_figures` 的每个数字都必须带 `refs`，否则视为契约违规。

## 5. 种子数据核对结果（契约规模依据）

| 对象 | 数量 | 来源 |
|---|---|---|
| 测评项 | 61（check01~check61） | `mt_ipo_evaluation_item` DML |
| 阈值 | 227 | `mt_ipo_eval_thresold` DML |
| 规则表单（含 1~11 项，可跨板块/企业类型复用） | 61 | `mt_ipo_evaluation_standard` DML |
| 规则原文条文 | 178 | `mt_ipo_listing_standard` DML |
| 板块×企业类型×套序号 组合 | 62 | 同规则原文（`sort` 1~6） |

**关键发现**：midas 的 `standardId` 是"规则包"而非"标准套"；"套"只能由规则原文的 `板块×企业类型×套序号` 重建。因此结果契约以本项目的 `set_id` 为主键，midas id 仅作 trace（归 #3 处理）。

## 6. 未决问题

| 编号 | 内容 | 状态 |
|---|---|---|
| F5 | `eta_years` 口径：增长率假设、取整、不可达/已达标表达、套级取 max 还是投影重算 | **grilling 中（当前）** |
| F6 | 最优路径 `distance` 度量：跨板块/套可比 | 待 F5 后 |
| #2 | mock 数据契约 CompanyProfile | 待 |
| #3 | 规则库 YAML schema（拍平为 per-item × per-set 阈值） | 待 |
| #4 | 公式引擎边界语义（对齐 `FormulaFactory`） | 待 |
| #5 | 校准工作流形态 | 待 |
| #6 | 维度评分口径 | 待 |
| #7 | 工程细节（Python 3.12 / uv / CLI / pytest） | 待 |

## 7. 参考锚点

- 代码地图：[docs/midas-code-map.md](docs/midas-code-map.md)
- 判定/差距：[ResultEvalServiceImpl.java](../../midas/midas-service/src/main/java/com/yonyou/midas/ipo/result/service/ResultEvalServiceImpl.java)（`isSatisfied` L148-192，diff L271-281，维度计分 L301-345）
- 链内结果 DTO：[IpoEvalResultDTO.java](../../midas/midas-domain/src/main/java/com/yonyou/midas/ipo/eval/result/dto/IpoEvalResultDTO.java)
- CAGR 语义：[CAGRFormula.java](../../midas/midas-service/src/main/java/com/yonyou/midas/ipo/formula/formula/CAGRFormula.java#L63-L72)
- ADR：[docs/adr/0001-facts-layer-granularity.md](docs/adr/0001-facts-layer-granularity.md)
