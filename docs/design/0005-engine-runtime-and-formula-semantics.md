# 设计 0005：测评引擎运行时与公式语义

- 日期：2026-11-10
- 性质：**伞形收官第 ② 步**——M4/M5 的运行时与判定语义；**吸收未决 #4（公式引擎边界语义 / G-B）**
- 输入：[设计 0001](0001-top-down-redesign.md)（契约 v0.2、五态、判定矩阵、四层）、[设计 0002](0002-rulebook-yaml-schema.md)（window token / item 宇宙 / measures）、[设计 0004](0004-system-architecture.md)（十步运行时序、AR1~AR5）、CONTEXT D5（责任链与 `FormulaFactory` 对齐）
- 决策点：E1~E9（§9，**2026-11-10 已拍板：全部按推荐**）。编号前缀 **E**（Engine），与 0001-P / 0002·0003-R / 0004-A 区分；引用带文档号（如「设计 0005-E2」）。注意与评审 0002 的发现编号 E1~E6 无关。
- **v0.2（2026-11-10）**：新增 §5.2「进度与覆盖率」（E9 / [ADR-0007](../adr/0007-progress-and-coverage-metrics.md)）——**第六个语义单点**，反转设计 0001 A5 与 CONTEXT #6「删除计分」；恢复的不是总分，而是「进度 + 覆盖率」双指标，**判定与展示分离**。
- 贯穿算例：甲公司（设计 0001 附录 A）——净利 1.5 / 0.3 / 0.4 亿（2022/2023/2024），营收累计 16 亿，经营现金流累计 1.8 亿，归母净资产 10 亿，三年研发 7000 万（强度 6%）。

---

## 0. 本文回答什么

引擎收到（规则库, 企业数据, run 坐标）后到产出 result.json 之间的**全部确定性语义**：怎么解析窗口、缺数怎么处理、每个量词怎么算、状态怎么折叠、层①②③怎么算。一句话原则：**每个语义只有一个定义点**（G-B 的教训：midas 把窗口语义散在 check 配置里，check04/11 才会互相矛盾）。

## 1. 运行时：五节点责任链（E1）

设计 0004 §4 的十步归并为五个节点，共享一个 Context，**单向遍历、节点 append-only、无回边**：

| 节点 | 吸收 0004 十步 | 职责 | 出口契约 |
|---|---|---|---|
| **Init** | ① ~ ④ | 坐标装配；规则加载（as_of 过滤 + 全量 lint，AR4）；企业数据加载（七条勾稽断言，AR4）；适用性判定 | `run` 定型；适用集 + not_applicable 集 |
| **Fetch** | ⑤ | facts 构建：三表 → drivers / metrics（measures 两维）/ items 实测值 | `facts.{drivers,metric_definitions,items}` 填充 |
| **Calc** | ⑥ | 叶判定：窗口解析（§3）→ 量词公式（§4）→ 五态 + 差距三分列 | `facts.checks[]` |
| **Fold** | ⑦ | 折叠：clause(logic) → branch → group → 段③ OR → 三段 AND → 板块结论（§5） | `facts.sets[].outcome`；**facts 冻结**（Result 只读，AR5 的强制点） |
| **Result** | ⑧ ~ ⑩ | 层①②③计算（§6/§7）+ 出口汇编 result.json（narrative_handoff 内嵌） | `layers.*` + result.json |

- **Context 形态**：`{run, rulebook, company, facts, layers, issues[]}`；节点只追加不回写；lint / 勾稽失败 → run 即刻中止（fail fast，不带病出数）。
- **适用套为空 → 显式报错**（兑现设计 0003 的 0-7 承诺），不是静默空报告。
- **与 midas 四节点的关系**：复用的是**模式**（有序节点遍历 + 共享 Context），不照搬其 Init→Calc→Fetch→Result 顺序——我们把 Fetch 放在 Calc 之前（公式依赖实测值与口径，先取数后计算，消除 midas「Calc 先行」的二次扫描）。
- 段①（issuance）每 run 算一次；段②（positioning）按目标板块各算一次；段③按 (板块, 主体类型) 的适用集算。

## 2. 取数语义（Fetch 内部）

| 口径问题 | 规则 |
|---|---|
| 净利润 measures | 申报值 `as_reported` 与扣非值 `excl_nonrecurring` **逐年各自持有**；判定口径 `lower_of_both` = **逐年孰低后聚合**（对齐法规「扣非前后孰低」的逐年语义） |
| 扣非缺某年 | **整叶 indeterminate**（原因：缺 YYYY 年扣非值）——不用申报值顶替（会高估），不猜 |
| 归母口径 | 净利 / 净资产类一律 `attrib_parent`（指标层已绑定，取数上不可能拿错，G4） |
| 研发 | `rd_investment_total = rd_expensed + rd_capitalized`（两源相加，缺任一源 → 该指标缺值） |
| ROE | `roe_weighted_avg` 派生：加权平均法（按净资产变动时间加权），分母 ≤ 0 → 指标缺值 |
| 市值 / 预计市值 | documentary，`basis: self_estimate`；mock 无值 → indeterminate（G-C），永不静默留空 |
| 未审计年度 | 该年数据可入库展示，但**涉及该年的叶 → indeterminate**（依据 0001 §3.2 矩阵） |

## 3. 窗口解析：引擎单点（E2）

锚点 = `fiscal_years` 的**最后一个完整会计年度** `FY_end`（甲公司 = 2024）。解析表：

| window token | 解析规则 | 甲公司（FY_end=2024） |
|---|---|---|
| `{kind: latest}` | `{FY_end}` | {2024} |
| `{kind: last_n_years, n}` | `{FY_end−n+1, …, FY_end}`，需 n 个**连续**年度 | n=3 → {2022, 2023, 2024} |
| `{kind: nth_year, n}` | `{FY_end−n+1}` | n=3 → {2022} |

三条边界规则：

1. **解析出的每个年度必须 ∈ fiscal_years 且连续**；需求年数 > 实有（或中间断年）→ 该叶 **indeterminate**，原因写明「窗口需 {2021..2023}，实有 {2022..2024}」——**不缩窗、不外推、不补零**（midas check04/11 的病灶就是窗口区间手写在配置里且缺数无定义）。
2. **stub（申报期一期）不进任何窗口**：法定窗口 = 完整会计年度；stub 数据只入 facts 供叙述展示，永不参与判定。
3. **渲染器同源**：本表同时是设计 0003 L2 回译渲染器的窗口措辞来源（`last_n_years 3` ↔「最近三个会计年度」）——写出来的中文和算出来的窗口出自同一张表，校准管线回译与引擎判定不可能各说各话。

## 4. 判定语义：量词公式 + 缺数三原则（E3 / E4）

### 4.1 判定矩阵（0001 §3.2）+ 审计覆盖

| nature × basis | 计算可达态 | 覆盖降级 |
|---|---|---|
| quantitative × calc | met / not_met / indeterminate | 非标审计意见年涉及的涉财叶 → **needs_review**（矩阵之上的一层覆盖，矩阵不重复写） |
| documentary × worksheet | 按底稿值判，可达四态；无值 indeterminate | 口径存疑（如专利是否授权 / 应用于主营）→ needs_review |
| judgment × declared | **恒 needs_review**，永不 met | —（记 declared_value 为证据，输出 pending_evidence） |

### 4.2 六量词公式表（E4 核心；`x[y]` = 指标 y 年实测，窗口 W）

| quantifier | 公式 | 边界 → indeterminate 的情形 | 甲公司 |
|---|---|---|---|
| `latest` | v = x[FY_end]，判 op | x[FY_end] 缺 | np_latest = 0.4 亿 |
| `sum` | v = Σ_{y∈W} x[y] | 任一年缺 | np_3y_sum = 2.2 亿 |
| `all_periods` | ∀y∈W: x[y] op thr | 任一年缺（无法证明「均为正」） | 净利 1.5/0.3/0.4 全 > 0 ✓ |
| `avg` | v = Σ x[y] / n | 任一年缺 | — |
| `cagr` | v = (x[末年]/x[首年])^(1/(n−1)) − 1，**n = 窗口年数** | 首年值 ≤ 0（增长率无定义）；窗口 < 2 年 | 3 年复合 = (x₂₀₂₄/x₂₀₂₂)^(1/2)−1；1 年增长率（rev_1y_growth）= 窗口 n=2、指数 1 |

> **勘误（2026-11-10，评审 0004 V1）**：本式原写 `(x[首年]/x[末年])^(1/(n−1)) − 1`，**分子分母颠倒**——与 §6 的 window_roll cagr 式（`首年′ × (1+thr)^(n−1)`）互推不自洽，且与「复合增长率」标准定义相反。甲公司算例：2022 营收 4.2 亿 / 2024 营收 6.8 亿，正确值 (6.8/4.2)^(1/2)−1 = **+27.3%**，原式得 **−21.4%**（符号与量级皆反）。已改正为上式，§6 的 window_roll 式即本式的反解（`末年′ = 首年′ × (1+thr)^(n−1)`），两处现已自洽；[ADR-0006](../adr/0006-engine-runtime-and-formula-semantics.md) 第 4 条同步勘误。
| `ratio` | v = Σnum[W] / Σden[W]（3 年研发强度 = 7000 万 / 三年营收） | 分母合计 = 0；任一年分子或分母缺 | 6% |

### 4.3 比较与差距三分列

| op | met 条件 | diff 公式 |
|---|---|---|
| GE / GT | v ≥ thr / v > thr | diff = thr − v |
| LE / LT | v ≤ thr / v < thr | diff = v − thr |
| EQ | v = thr | diff = \|v − thr\| |

- 数值叶：`gap_ratio = diff / |thr|`（thr = 0 时只报 diff，不造无穷大）。
- 计数叶：`required_delta = thr − v`（整数）。
- 布尔 / 动作叶：`required_action` = 条文动作文案（引自 evidence 原文措辞，不自由发挥）。
- 甲公司：np_latest 对 thr 1 亿 → diff = 0.6 亿，gap_ratio = 0.6。

### 4.4 缺数三原则（E3）

1. **叶级隔离**：缺某年只杀「窗口含该年的叶」（缺 2022 → np_3y_sum / np_3y_allpos 均杀，np_latest 只看 2024 照常判）；**套级传染只经折叠规则**，不做任何「缺一年杀整套」的特殊逻辑。
2. **无静默回退**：任何缺值 → indeterminate + 显式原因（缺哪年、缺哪个口径）；**null 永不进比较**（midas `null→0` 的修复，`ResultEvalServiceImpl.java:149` 对照）。
3. **审计覆盖降级**：见 §4.1——非标意见 → needs_review；未审计年度 → indeterminate。两者都发生在叶级，之后按普通状态参与折叠。

## 5. 折叠语义：Kleene 三值、AND/OR 双规则（E5，**含 0001 §2.3 勘误**）

> **勘误**：设计 0001 §2.3 写「折叠（AND 与 OR 同规则）」，按字面执行会错杀——甲公司现金流条文（OR：现金流 1.8 亿 ✗ / 营收 16 亿 ✓）会折成 not_met，恰是附录 A 要修的病。正解是三值逻辑（Kleene）按连接词**分别定义**：

| 连接词 | 折叠规则（not_applicable 先剔除；needs_review 视同 unknown） |
|---|---|
| **AND**（clause all / branch / 三段） | any **not_met** → not_met；else any (indeterminate \| needs_review) → indeterminate；else all met → met |
| **OR**（clause any / group 间 / branch 间） | any **met** → met；else any (indeterminate \| needs_review) → indeterminate；else all not_met → not_met |

| 场景（clause any：现金流叶, 营收叶） | Kleene OR（**正确**） | 0001 §2.3 字面（同规则） |
|---|---|---|
| (not_met 1.8<2, met 16≥15) | **met**（条文满足） | not_met —— 错杀 |
| (met, indeterminate) | met | indeterminate —— 过度保守 |
| (not_met, indeterminate) | indeterminate | not_met |

- **P3 相容性**：judgment 叶位于 AND 路径（绝大多数：定性条文独立成 clause 后进 branch 合取）→ 必传染 indeterminate 到套终态，P3 兑现；OR 兄弟叶已满足时条文真值已定，unknown 被吸收是**正确**语义，且套终态仍带 needs_review 计数与 pending_judgments 清单（层②候选强制携带）。
- not_applicable **只存在于套级**（适用性谓词，Init 节点），叶级无此态；出分母、留事实层。
- 层级链：leaf → clause(logic) → branch(AND) → group(OR branches) → 段③(OR groups) → 板块 = AND(段①, 段②, 段③)。

### 5.2 进度与覆盖率（E9，**含 ADR-0007**）

> 本节是**第六个语义单点**（前五个：窗口解析 §3 / 量词公式 §4.2 / 缺数三原则 §4.4 / Kleene 折叠 §5 / 情景推演 §6）。它与 §5 的折叠**共用同一套 Kleene 逻辑**，因此进度与判定不可能各说各话。

**为什么需要**：midas 给了一个总分，本项目设计 0001 A5 / CONTEXT #6 曾判「删除计分」。用户复盘后要求保留量化锚点——但保留的**不是总分**，而是**双指标**（进度 + 覆盖率），且判定与展示分离。完整论证见 [ADR-0007](../adr/0007-progress-and-coverage-metrics.md)。

#### 叶分数

```
s_leaf:
  met                                  → 1
  not_met 且有 gap_ratio（数值/计数叶） → 1 − gap_ratio
  not_met 且 thr = 0                   → 0       ← gap_ratio 无定义，不硬凑
  not_met 且为布尔/动作叶               → 0       ← 无「差多少」概念
  indeterminate / needs_review          → 未定义   ← 不是 0
```

**未定义叶绝不进聚合**——缺数据算成 0 分正是 midas `isSatisfied(null)→0` 的病灶（§4.4-2），不得重犯。

#### 折叠（与 §5 双规则同向）

| 层级 | 连接 | 进度聚合 |
|---|---|---|
| clause | logic=all | min(子叶) |
| clause | logic=any | max(子叶) |
| branch | AND | min(子 clause) |
| group | OR | max(子 branch) |
| 套 | AND | min(全部 clause 与 branch) |

- `min` 不是「每项权重相同」，而是「整体强度 = 最弱环强度」——AND 约束系统的正确语义，且**不需要任何外部权重表**（权重在 AND 约束里无法律依据，在展示层无数据来源）。
- `max` 用于 OR 条款：落败支路不构成约束，不拉低分数（与 Kleene OR「任一 met 先满足」同向）。
- **同向性保证**：无未定义叶时 `progress = 100% ⟺ 套 met`。

#### 覆盖率

```
coverage = 可判叶数 / 适用叶总数
```

可判 = met / not_met；未定义叶计入分母、不计入分子。

#### 甲公司算例（主板第一套）

| 叶 | 状态 | gap_ratio | s_leaf |
|---|---|---|---|
| c1 三年净利均为正 | met | — | 1.0 |
| c2 三年净利累计 2.14 亿 ≥ 2 亿 | met | — | 1.0 |
| c3 最近一年净利 0.4 亿 < 1 亿 | not_met | 0.6 | **0.4** |
| b1_c1（any）现金流 1.8 亿 / 营收 16 亿 | met（营收胜出） | — | **1.0** |

```
b1_c1 = max(0.9, 1.0) = 1.0        ← OR 取最优支路
套 progress = min(1.0, 1.0, 0.4, 1.0) = 40 分
套 coverage = 4/4 = 100%
```

读法「40 分 · 覆盖 100%」→ 卡点唯一明确：最近一年净利差 60%。

对照均值：`mean(1.0, 1.0, 0.4, 1.0) = 85 分`——not_met 的套拿 85 分，与 AND 判定脱钩，读者第一反应是「到底过没过」。**这就是不用均值的原因。**

科创板第一套（市值未自估 → 未定义叶）：`progress = 100 分`，`coverage = 4/5 = 80%` → **「100 分 · 覆盖 80%」**。

#### 边界规则

| 情形 | 处理 | 理由 |
|---|---|---|
| thr = 0 的叶（三年净利均为正、净利 > 0） | met → 1；not_met → 0 | gap_ratio 分母为 0，无比例可言 |
| `all_periods` 量词（三年均为正） | 叶级二值（0 或 1） | 一个叶覆盖三年，逐年拆分会改变 item 语义 |
| 计数叶（专利数等） | gap_ratio = diff/thr；thr = 0 时同 thr=0 规则 | 有阈值就有比例 |
| 布尔/动作叶 | 恒 0（未做）或 1（已做） | 无「差多少」概念 |
| OR 落败支路 | 不计入次弱约束 | Kleene OR 下不构成约束 |
| 未定义叶 | 不进 progress 聚合，只进 coverage 分母 | 缺数据不得算成 0 分（midas 病灶） |

#### 次弱约束与措辞禁令

- `binding_clause_id` = 达成最小叶分数的 clause（卡点）；`next_binding_clause_id` = 排序后第 2 小的 clause——**min 的颗粒度补强**，直接回答「补完这个下一个是谁」。
- **coverage < 100% 时硬禁「可达标 / 预计能过」表述**，进度一律限定为「已评估部分」。
- **跨期自比较是进度最值钱的用法**（同一套、同一批叶、同一口径）；**跨套排序不合法**（叶集不同 → 不可比），跨套排序仍走层②帕累托四轴。
- 进度**不进 narrative**（叙述层只复述 facts 与 layers 的数字，且不得表述为「得分高所以能过」）。

## 6. 层①：差距画像 + 情景（E7）

- **blockers**：逐套叶级清单（not_met / indeterminate + diff 三分列 + 口径分类），套排序按官方 sort 仅展示。
- **window_roll**（确定性、零假设；P8 兑现）——窗口滚动一年（FY_end+1 进入、FY_end−n+1 滑出），按 quantifier 给**进入年所需值**：

| quantifier | required_entering_year_value | 甲公司（np_3y_sum，thr 2.0 亿） |
|---|---|---|
| sum | thr − Σ(窗口剩余年) | 2.0 − (0.3+0.4) = **1.3 亿** |
| all_periods | 满足 op 所需（GT 0 → 「进入年需为正」） | — |
| cagr | 首年′ × (1+thr)^(n−1)（首年′ = 滚动后新窗口首年值） | — |
| latest / avg / ratio | 不适用（无窗口滚动语义），跳过 | — |

  滚动风险标注：required > 最近年实际 × k → 高风险；k 入规则库配置（`_meta.yaml`），缺省 2。甲公司：1.3 > 0.4×2=0.8 → 高风险。
- **growth**（F5 终案的降级形态）：v1 只算两点情景 r ∈ {0（零增长）, historical_cagr}，输出 years_low / years_high；一律 `is_forecast: true`；**无来源不编数**——假设仅 historical_cagr（ADR-0004 残点就此关闭）。套级区间仅当套内无 act/adjust 阻塞叶（P4）。

## 7. 层②③：gate × 帕累托 + 归因枚举（E6）

### 7.1 hard gate 与帕累托的关系（E6）

- **帕累托前沿在全部适用套上计算**（四轴：not_met 叶数 / max gap_ratio / years_high（缺省 +∞）/ data_uncertainty）——含未过闸套，四轴保有区分度；
- **recommendation = 前沿 ∩ 过闸套**；过闸 = 套内无 not_met 的定量/documentary 硬叶（judgment/needs_review 不挡，P3）；
- `excluded[]` 分 reason：`hard_leaf_not_met`（含硬叶未满足）/ `dominated`（被支配，附被谁支配）。
- 备选方案（只在过闸套上算前沿）会导致轴 1 恒为 0 而退化，须删轴——推翻 0001 已拍板的四轴，不取。

### 7.2 层③归因枚举（正交双字段，只计数不合成标量）

| verifiability（可核验性） | substantive_obstacle（实质障碍） |
|---|---|
| `verified` / `missing_data`（缺年/缺口径）/ `pending_worksheet`（底稿未填）/ `pending_judgment`（需专业意见）/ `pending_audit`（非标意见） | `none` / `numeric_gap`（数值差）/ `boolean_gap`（动作未做） |

逐 blocker 出一对（如「缺 2022 年数据」= missing_data × none；「净利差 0.6 亿」= verified × numeric_gap）；层内只做组合计数，交叉空格自然为空。

## 8. midas 对齐锚点（trace only，不作为对拍基准）

| midas 锚点 | midas 行为 | 本设计 |
|---|---|---|
| `ResultEvalServiceImpl.isSatisfied` | null → 0 参与比较 | 缺值 → indeterminate，null 永不进比较（§4.4-2） |
| `CAGRFormula` + check 配置 | 窗口区间手写在各 check 配置 | window token 单点解析（§3，E2） |
| `FormulaFactory` | 公式语义分散在各 Formula 类 | 六量词公式表单点（§4.2，E4） |
| diff（阈值−实测） | 单一公式不分类 | 三分列 diff / required_delta / required_action（§4.3） |

## 9. 决策点（E1~E9）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| E1 | 责任链五节点 Init/Fetch/Calc/Fold/Result（十步归并如 §1）；Context append-only 无回边；Fetch 先于 Calc（不照搬 midas 顺序） | 五节点 / 四节点（⑦~⑨ 合并 Result）/ 十步平铺 | **五节点**——Fold 出口 = facts 冻结点，AR5「层只读 facts」在节点边界上强制成立 |
| E2 | 窗口解析单点：§3 解析表 + 三条边界（不足/断年→indeterminate 不缩窗；stub 不进窗口；渲染器同源） | 此 / 允许短窗口回退 | **此**——G-B 的正面兑现；短窗口回退就是 check04/11 的错法 |
| E3 | 缺数三原则（叶级隔离 / 无静默回退 / 审计覆盖降级）+ measures 逐年孰低、扣非缺→整叶 indeterminate | 此 / 扣非缺用申报值顶替 | **此**——顶替即系统性高估，宁可 indeterminate |
| E4 | 六量词公式表 + diff 三分列公式（§4.2/§4.3） | 此 | **此** |
| E5 | 折叠 = Kleene 三值按 AND/OR 双规则；**勘误 0001 §2.3「同规则」表述** | 双规则 / 维持同规则 | **双规则**——同规则会错杀甲公司现金流条文（OR 择一已满足），与 G1/P7 的立法动机自相矛盾 |
| E6 | 帕累托前沿算全部适用套，recommendation = 前沿 ∩ 过闸套，excluded 分 reason | 此 / 只在过闸套上算 | **此**——保住四轴区分度，不动 0001 已拍板的轴定义 |
| E7 | 情景语义：window_roll 分量词公式 + 风险 k 配置（缺省 2）；growth 两点 r∈{0, hist_cagr} 一律 is_forecast | 此 / growth 用连续区间 | **此**——两点情景零编造（r_high=1.5×cagr 之类的系数才是编数） |
| E8 | 数值表示：金额整数元存储、float64 计算、比较不带 ε（阈值皆整数，<2^53 精确）；Decimal 缓 | 此 / 全程 Decimal | **此**——边界族 ±1 元测试在 float64 下精确；Decimal 留给未来出现非整阈值时 |
| **E9** | **恢复量化指标，但形态 = 进度 + 覆盖率双指标（§5.2）；判定与展示分离；套级聚合 min；不恢复总分；不引入权重表；补次弱约束** | ① 双指标（进度+覆盖）② 只恢复总分③ 不恢复量化 ④ 双指标但用加权平均 | **①**——midas「100 才通过」是 AND 约束的正确表达（保留），问题在门旁那个数；权重进判定是改法律语义、进展示是无来源装饰，两条都不成立；min 与 AND 判定同源 → 达标 ⟺ 100%，不会出「85 分却 not_met」 |

> **拍板记录：2026-11-10 —— E1~E8 全部按推荐通过。** 随拍板动作：#4 关闭；[ADR-0006](../adr/0006-engine-runtime-and-formula-semantics.md) 落盘；设计 0001 §2.3 加勘误注（E5，Kleene 双规则）；甲公司端到端自检链定为实现期首个回归用例。
>
> **拍板记录（补，2026-11-10）—— E9 按推荐通过**（用户「按照推荐的来调整」）。随拍板动作：[ADR-0007](../adr/0007-progress-and-coverage-metrics.md) 落盘；**反转设计 0001 A5 与 CONTEXT #6「删除计分」**（恢复的不是总分，是双指标；#6 的原始判据——避免恢复 midas 式总分——仍成立）；设计 0006 golden 增进度与覆盖率期望值；设计 0007 UI 增进度条与覆盖徽章。

## 10. 与既有决策 / 未决问题的对账

| 项 | 关系 |
|---|---|
| #4（公式引擎边界语义 / G-B） | 本文 §3/§4 即其全部内容；拍板后 **#4 关闭**（E2 窗口单点 + E3 缺数 + E4 公式表） |
| 0001 §2.3 | E5 勘误（AND/OR 双规则），拍板后随 ADR-0006 回写勘误注 |
| 0001 §3.2 判定矩阵 | §4.1 继承 + 补审计覆盖降级层 |
| 0004 十步 / AR1~AR5 | §1 五节点映射；facts 冻结在 Fold 出口（AR5）；fail fast（AR4） |
| 设计 0003 L2 渲染器 | E2-3 渲染器同源（窗口中文措辞与解析同表） |
| 设计 0002 window token / measures | §3 解析表与 §2 取数是其在引擎侧的消费面 |
| ADR-0004 残点（growth 假设来源） | E7 关闭：仅 historical_cagr 两点情景 |
| **0001 A5 / CONTEXT #6「删除计分」** | **E9 反转**——恢复量化指标但形态为双指标（进度 + 覆盖率），非总分；判定与展示分离；见 ADR-0007 |
| 拍板后动作（E1~E8） | 出 ADR-0006（引擎运行时与公式语义，含 0001 §2.3 勘误）；CONTEXT #4 关闭；剩 0006《mock 数据契约》（伞形第③步）收官 |
| 拍板后动作（E9） | 出 ADR-0007（进度与覆盖率）；CONTEXT #6 状态反转 + §2.8 拍板记录；设计 0006 golden 增期望值；设计 0007 UI 增进度条与覆盖徽章 |

> 甲公司端到端自检（供实现期回归用）：适用性→主板+创业板一般企业套；主板第一套 = 均为正 ✓ / 累计 2.2≥2 ✓ / 最近年 0.4<1 ✗（diff 0.6 亿）/ 现金流条文 any→met（E5 双规则）/ 套终态 not_met / 层② excluded{hard_leaf_not_met} / window_roll 进入年需 1.3 亿 vs 0.4 亿（k=2 → 高风险）。
>
> **进度与覆盖率自检（E9）**：主板第一套 = progress 40 分 / coverage 100% / binding_clause = 最近一年净利条款（gap 0.6）/ 次弱 = 净利累计条款（gap 7%）。
