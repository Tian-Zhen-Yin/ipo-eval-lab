# 第二步：自顶向下重设计（v0.2 骨架）

- 日期：2026-11-09
- 性质：兑现 [0002 §5](../reviews/0002-professional-gap-audit.md) 预告的第二步；本文档是 CONTEXT v0.2 与 ADR-0002/0003/0004 的**底稿**，经 §9 拍板后回写
- 输入：CONTEXT v0.1（已冻结于 tag `context-v0.1`）、[评审 0001](../reviews/0001-gap-layer-design-review.md)（F5-R）、[评审 0002](../reviews/0002-professional-gap-audit.md)（34 条发现）、种子数据全量复核（见 §0）
- 修订：**v2（2026-11-09）按专家复核意见修订六处**——①§2.2 套内/条文内 OR（group/branch 层级 + clause logic）②§0.5 权威源链 ③§2.4 负面清单 `in_list` ④§3.4 口径补丁（归母后缀、prune、市值自估、同行比依赖）⑤§5.1 新增 `window_roll` 情景与 `data_uncertainty` 轴改名 ⑥§5.2 边界声明三条；新增 G1~G6 处置行、P7/P8 拍板点、附录 A（甲公司白话示例）
- 拍板：**2026-11-10，P1~P8 全部按推荐通过**；已回写 CONTEXT v0.2 与 ADR-0001（Amendment 1）/0002/0003/0004

---

## 0. 事实底座修正（双向纠偏）

对种子 JSON 全量复核后，**CONTEXT §5 与 0002 的部分事实指控都需要修正**。本节是后续所有设计的取数依据。

### 0.1 计数修正

| 对象 | CONTEXT §5 记载 | 实测（2026-11-09 快照） | 差异 |
|---|---|---|---|
| 规则原文条文 | 178 | **185**（`mt_ipo_listing_standard.json` 行数） | +7 |
| 板块×企业类型×套序号组合 | 62 | **64**（按 board+type+asset_name+sort 去重） | +2 |
| 阈值 | 227 | **234**（`mt_ipo_eval_thresold.json` 行数） | +7 |
| 规则表单 | 61 | **63**（`mt_ipo_evaluation_standard.json` 行数） | +2 |
| 板块 / 企业类型 | — | **5 / 4**（一般企业、红筹已境外上市、红筹未境外上市、表决权差异） | — |
| 底稿自填项（`RAW()`） | — | **32 / 61**（check01,07,32~61） | — |

阈值结构：`{eval_item_id, std_id, op, val, format, suffix}`；op 实际只出现 3 个码（`1`×61、`7`×58、`8`×115），format 4 个码（`0`×61、`2`×134、`3`×32、`1`×7）。**码值→语义映射待校准（归 #3/#5），本节只记分布。**

### 0.2 对 0002 两项指控的修正（事实层面）

| 0002 指控 | 复核结论 | 保留什么、修正什么 |
|---|---|---|
| A1「62 套是笛卡尔积，会造出现实中不存在的套」 | **不成立**。64 套 = `listing_standard` 的真实行组合，每套 1~5 条条文，无交叉膨胀 | 修正事实；**保留精神**：套成员与适用性仍必须由条文+主体类型重建（midas 的 `std_id` 规则包被 234 条阈值挂在 63 个包上，它不是套） |
| A6「红筹/未盈利/特殊主体专套缺失」 | **专套在数据中存在**：红筹（已/未境外上市）与表决权差异各有专套（上交所主板红筹未上市 6 套、科创板表决权差异 2 套等） | 修正事实；**真问题换位**：专套引用的 3 类定性条件（见 0.3）在 61 个 UI 项里**没有可判定载体**，v0.1 契约算不了它们 |

### 0.3 条文条件型全集（item 宇宙重建的依据）

185 条条文引用 **24 种条件型**：

- **定量 21 种**：预计市值(48)、市值(8)、市值/预计市值(3)、最近1年营收(31)、最近3年营收累计(2)、最近2年均值(1)、3年复合增长率(19)、1年增长率(1)、最近1年净利润(16)、3年均为正且累计(4)、2年均为正且累计(2)、2年均正(1)、最近1年净资产(5)、经营现金流 1年(1)/3年累计(5)、研发投入 3年累计(1)、2年累计(1)、研发占营收比 3年(2)/2年(1)、加权 ROE 1年(1)/2年均(1)
- **定性 3 种**：自主研发国际领先+同行业相对优势(26)、研发阶段红筹或国家创新驱动红筹(4)、国家批准/二期临床(1)

**推论：上市标准套的原子条件是一个比 61 小得多的、以口径为纲的宇宙**（21 定量条件型 × 板块/类型/套的阈值差异）。61 个 midas UI 项是"展示项"，不是"条件型"——v0.2 的 item 按条件型重建，旧 `checkNN` 降级为 `alias`（溯源用）。

### 0.4 61 项的构成事实（Q3 的输入）

- 公式计算项 29 个（check02~06、08~31 中的非 RAW 部分）
- 底稿自填项 **32 个**（占 52.5%）：其中可核验的事实型（专利数、经营年限、股本、公开发行比例）约 8~10 个，其余为治理/合规/定位类**实质性判断**项

### 0.5 权威源链（专家复核 G5 补）

快照本身也是**转写件**——其套数与现行规则对不齐：

| 板块 | 快照套数（一般企业） | 现行规则 | 疑点 |
|---|---|---|---|
| 沪深主板 | 4 | 3 | sort1/sort2 疑为第一套「现金流**或**营收」两分支拆行 |
| 科创板 | 6 | 5 | sort1/sort2 疑为第一套两分支拆行；其余待核 |
| 北交所 | 5 | 4 | 待核 |
| 创业板 | 5 | 3 + 未盈利通道 | sort4/5（复合增长率/科研能力）疑为未盈利标准 |

> 「现行规则」列以校准 #5 对照法规原文复核为准，本表是**校准旗标**而非结论。

权威链固定为：

```
法规原文（authority）→ 规则库 YAML（人工校准）→ midas 快照（trace，仅作起点与回归对照）
```

§0.1~0.3 的计数是 **midas 口径**的客观记录，不构成套清单的最终裁定；套清单与套数以规则库校准结果为准（CONTEXT D4 的重申，写进 ADR-0002）。

---

## 1. Q1：决策对象 → 契约主键

真实决策对象一句话：

> 企业 **E**，在板块 **B** 的标准套 **S** 下，按规则时点 **T** 的适用规则，以报告期 **P** 的经审计数据，指标层面是否满足。

### 1.1 映射规则

| 决策坐标 | 契约落点 |
|---|---|
| E | `run.input.company_file / company_id` |
| **T**（新增） | `run.input.as_of_date` → 加载规则时按生效区间过滤 → 结果回写 `run.applied_rule_versions[]`（C5 收入 v1） |
| **P**（扩充） | `run.input.report_period = {fiscal_years[], stub_period?, audit_status, audit_opinion}`；`audit_opinion != unqualified` 时相关财务条件降 `needs_review`（A7 收入 v1） |
| **E 的主体画像**（新增） | `run.input.applicant_profile`：v1 至少 `{company_type ∈ 4 枚举, profit_status ∈ {profitable, loss_making}, ...}`，用于套适用性判定 |
| B × S | `facts.sets[]`，`set_id = {board_code}:{type_code}:{sort}`（如 `SSE-MB:redchip_unlisted:2`），成员由条文重建 |
| 目标范围 | `run.input.target = {boards[]?, sets[]?}`，缺省 = **全部适用套**（applicable，不是全部套） |

### 1.2 结论单元与 run 边界

- **一次 run** = (E, T, P, target)，内部评多个套（层②要跨套比较，不能一 run 一套）。
- **结论单元** = `facts.sets[].outcome`（指标层面 `criteria_met / criteria_not_met / indeterminate`，措辞遵循 E6）；板块级结论 = 固定树折叠（§2），不另存副本。
- `facts` 仍是唯一事实源（ADR-0001 双层结论保留）：items 唯一权威实测 → checks 判定 → sets/boards 折叠。

---

## 2. Q2：三段式评价单元与套的择一

### 2.1 固定组合树（不建通用表达式引擎，D1 的 v1 简化）

```
板块结论 = AND(
  段① issuance_conditions        # L1 四节：主体资格/规范运行/财务与会计/募资运用；板块无关基线
  段② board_positioning(B)       # 板块定位：科创属性（常规4项 AND + 例外 OR）/三创四新/北交所创新性
  OR( 段③ listing_sets(B, E.profile) )   # 套择一
)
```

树形是**法规结构决定的常量**，写死在引擎里；数据驱动的是叶子（条件判定）与成员（哪条文进哪套）。这是 D1「表达式树」在 v1 的正确简化：**只有 AND/OR 两层交替 + 固定形状**，不需要通用布尔引擎。

### 2.2 条件层级（原子化 B2；v2 修订：择一不止在套间）

法规现实：主板第一套含「三年现金流累计≥2亿 **或** 三年营收累计≥15亿」；科创属性研发投入是「占比≥5% **或** 累计≥8000万」。**OR 存在于条文内部与指标内部**，且快照已把套内 OR 分支拆成独立条目（§0.5：主板 sort1/sort2 即第一套的两条支路）。层级修正为：

```
叶子谓词 leaf        ← 原子判定：{metric_ref, quantifier, window, op, threshold}
  ↑ logic ∈ {all, any}     ← 条文 = 叶子合取或择一：「3年净利均为正 ∧ 累计≥2亿」= 2 叶合取；
                              「现金流≥2亿 ∨ 营收≥15亿」= 2 叶择一
条文 clause          ← 对应 listing_standard 一行（或其一分支）
  ↑ AND              ← 支路 = 条文合取
支路 branch          ← branch_no；快照中的"多余套"多为官方套的支路
  ↑ OR               ← 同一官方套内支路择一
官方套 group         ← group_no（官方套号），段③成员
  ↑ OR               ← 同板块同主体画像内官方套间择一
```

- `set_id` 挂在 **branch 层**（与快照行一一对应），同时带 `group_no`；段③折叠 = OR(group) × OR(branch) × AND(clause) × logic(leaf)。仍然只有 AND/OR 交替，**不需要通用表达式树**（P2 维持）。
- `quantifier ∈ {latest, all_periods, sum, avg, cagr, ratio}`（B2 收入 v1）；`all_periods` 独立成叶（"均为正"）。
- **新增不变量**：同一 `group_no` 内各支路必须共享公共条文（如主板两支路共享净利条件）；不满足即转写噪音旗标，交校准（#5）裁决——该不变量可自动抓出 §0.5 表中的快照疑点。
- `checks[]` 增 `scope ∈ {issuance, positioning, set}`；set 作用域的 check 带 `set_id`，其余带 `board_id`。
- `check_id = chk:{set_id|scope:board}:{leaf_no}`。

### 2.3 五态与折叠规则（B7 收入 v1）

状态：`met / not_met / not_applicable / indeterminate / needs_review`。

- `not_applicable`：适用性不匹配（红筹条款对一般企业）——**出分母，不作 not_met**。
- `indeterminate`：数据缺年/不可算（可核验性问题）。
- `needs_review`：需专业判断（法律结论、声明式自填、审计意见非标）。

折叠（AND 与 OR 同规则，not_applicable 先剔除）：

```
any not_met                    → not_met
else any (indeterminate|needs_review) → indeterminate
else all met                   → met
```

`pass_ratio` 删除（A2）；仅保留 `met_count / not_met_count / indeterminate_count / needs_review_count / not_applicable_count`。

### 2.4 适用性（A6/D3 收入 v1，谓词受限）

`set.applicability`：v1 限定为 `applicant_profile` 字段的**等值 / 枚举 / in_list 合取**（如 `company_type == 红筹未境外上市`、`industry NOT IN 科创板负面清单`——行业负面清单是板块定位的**硬筛**，等值合取表达不了清单成员关系，专家复核 G3）。不做通用谓词语言。不匹配 → 套级 `not_applicable`，不出现在候选里但保留在事实层（审计可见）。

---

## 3. Q3：硬指标与实质性判断分家

### 3.1 item 双字段分类

| 字段 | 取值 | 说明 |
|---|---|---|
| `nature` | `quantitative` / `documentary` / `judgment` | 条件的本性：可计算 / 可核验事实（专利数、年限、股本）/ 需专业意见 |
| `basis` | `calc` / `worksheet` / `declared` | 取数方式（沿用 v0.1） |

### 3.2 判定矩阵（引擎能输出什么）

| nature × basis | 可输出状态 | 约束 |
|---|---|---|
| quantitative × calc | met / not_met / indeterminate | 走公式引擎 + 阈值 |
| documentary × worksheet | met / not_met / indeterminate / needs_review | 底稿有值按值判；无值 indeterminate；**口径存疑**（如专利是否授权、是否应用于主营）needs_review |
| judgment × declared | **只能 needs_review** | 自报值记为 `declared_value`（证据），**永不产生 met**；输出 `pending_evidence[]`（所需核查材料清单） |
| judgment × 任何 | needs_review | 同上（B6/B9 收入 v1；check07 同行 CAGR 归此类） |

### 3.3 对层② 与套终态的作用（关键裁决）

- judgment 项**不构成层②的 hard gate**（引擎无权因"未核查无违法证明"把一套筛掉），但计入套终态的 `indeterminate`——即：**推荐可以带 uncertainty，终态必须留待人工清除**。
- 层②候选上强制带 `pending_judgments[]` 清单，agent 叙述时逐条转述为"待核查事项"，不得转述为"已满足"。

### 3.4 口径拆分（B1~B5 收入 v1）

| 项 | v1 做法 |
|---|---|
| 净利润（B1） | `measures[]` v1 两维：`deduction ∈ {as_reported, excl_nonrecurring}` × `audit ∈ {audited, unaudited}`；判定口径 `lower_of_both` 作为 check 的取数规则字段 |
| 量词（B2） | §2.2，`all_periods` 独立成叶 |
| ROE（B3） | 指标命名强制 `roe_weighted_avg`，只实现加权平均 |
| 研发（B4） | v1 拆 `rd_expense`（费用化）/ `rd_investment_total`（含资本化）；科创属性判定用 total；资本化明细与归集依据 v2 |
| 专利（B5） | `invention_patents_granted` + `applied_to_main_business: bool` 两叶合取 |
| **归母口径（G4）** | 口径后缀强制**不止 ROE**：净利、净资产类指标一律绑定归母口径（`attrib_parent`，剔除少数股东权益；ADS 源字段本即如此），杜绝拿合并总净资产比门槛 |
| **预计市值（G4）** | documentary 项，取值必须带 `basis: self_estimate`（发行后股本 × 预估价）；输出与叙述强制"企业自估"限定，禁止复述为"市值已达标" |
| **同行比条件（G4）** | 红筹「3年复合增长率高于同行」依赖可比公司集合——基准库（Phase 2）对此类叶是**前置依赖**而非增强；未建库前一律 `indeterminate` + 显式原因，不得静默留空 |
| measures 维度（C1） | v1 两维如上；第三维（报表编制主体：合并/母公司）v2，v1 默认归母 |

**prune 原则（G4）**：61 项不照单全收——已退出评价指标体系的项（如「研发人员占比」，科创属性指引修订后只剩披露要求）在校准 #5 中删除，仅在 alias 表留痕。

---

## 4. Q4：mock 数据勾稽约束 → 可校验 fixture

### 4.1 结构

```
fixtures/
  companies/            # 每公司一个 CompanyProfile JSON（#2 契约的字段全集在此落地）
    base_co_2029/       # 基准样本：接近上交所主板 sort=1 的"差一点"企业
      profile.json
      statements/       # 三表 + 权益变动，按年
      expected/         # 期望结果 golden（哪些套 met/not_met/差距数字）
    boundary_epsilon/   # 阈值 ±ε 参数化族（"刚好差 1 元"）
  conftest.py           # 七条勾稽约束全部实现为 fixture 加载期断言
```

### 4.2 七条约束的落法（F1 收入 v1）

| # | 约束 | 校验实现 |
|---|---|---|
| ① | 资产 = 负债 + 权益（逐年） | 加载期断言 |
| ② | 利润表↔现金流量表（间接法调节表存在且平） | 断言：净利 + 调节项序列 = 经营现金流 |
| ③ | 权益变动勾稽：期末 = 期初 + 净利 − 分红 + 增资 | 断言 |
| ④ | 三年一期连续无缺口 | 年份连续性检查 |
| ⑤ | 审计意见字段逐年存在；基准样本 = unqualified，另设一 fixture = qualified（测降级路径） | schema 必填 + 用例 |
| ⑥ | 增长率落合理区间（如 −50%~+200%） | 加载期 sanity 断言 |
| ⑦ | 边界族：每个数值型叶子生成 threshold ± ε 两变体 | 参数化生成器 |

### 4.3 v1/v2 切

- v1：一套干净账（original）+ 边界族 + 一个非标审计意见样本。
- v2（F2 推迟）：`original / restated` 双套账 + 差异说明（测追溯调整与归因路径）。

---

## 5. Q5：四层结论边界与措辞禁令

### 5.1 层定位定案（合并 0001 F5-R 与 0002 E1~E4/E6）

| 层 | 结论本体 | 能说 | 不能说 |
|---|---|---|---|
| ① gap | **差距画像**：逐套 blockers（叶子级 not_met/indeterminate 清单 + diff + 口径分类） | "在 S 套下，条件 c 差 x（gap_ratio r），属数据缺失/真实缺口"；"窗口滚动后，进入年需≥v 才能保住达标"（window_roll，确定性） | 跨套比较；"还差 N 年"（只可作为 scenario） |
| ② path | hard gate 筛选 → **帕累托前沿** | "在给定维度下，套 X 不被任何套支配；推荐 X，理由…；备选 Y" | 单一 distance 排序；"最优"；推荐含 not_met 硬叶的套 |
| ③ attribution | 归因：`verifiability × substantive_obstacle` 正交双字段（C3 收入 v1） | "该 indeterminate 源于缺 2022 年数据" | "数据造假/粉饰" |
| ④ narrative | 叙述 handoff + 免责 | 复述 facts/layers 数字（必带 refs） | 任何 forbidden_claims |

层①时间维度（0001 F5-R 与 0002 E2 的合并终态；v2 修订新增 window_roll）：

- `lever` 分类（grow/derived/wait/adjust/act）与 `facts.drivers[]`（6 驱动）**保留**（0001 的贡献）。
- `scenario_projection[]` 分两类：
  - `growth`（原 eta 降级）：`{driver_id, assumptions[], r_low, r_high, years_low, years_high, is_forecast: true, basis: historical_cagr}`；**无来源不编数**（0001 §3.1 结论维持）。
  - **`window_roll`（G2 新增，确定性、零增长率假设）**：报告期滚动一年后旧年滑出窗口——对每个窗口型定量叶（`sum / all_periods / cagr`），输出**进入年所需值** `required_entering_year_value = 阈值 − 窗口剩余年值合计`，并与最近一年实际对照标注滚动风险（如所需值 > 最近一年实际 × 2 → 高风险，阈值入规则库配置）。这回答的是"晚一年申报，结论会不会反转"，是无需编造假设的结构性风险。例见附录 A。
- 套级时间仅当套内无 act/adjust 阻塞叶时给区间（0001-P5 维持），且必须标 `is_forecast`。

层②帕累托维度（F6 的替代终案；v2 修订：轴改名）：

```
轴 = [not_met 叶数, max(gap_ratio)（数值叶）, 时间上界 years_high（scenario 缺省 +∞）,
      data_uncertainty（indeterminate + needs_review 计数）]
```

- 轴名从「不确定性计数」改为 **`data_uncertainty`**（G6）：它度量的是**数据完整度**，不表征审核通过概率——板块通过率、问询强度、政策窗口属监管判断，工具无数据也无权下结论。`metric` 块须声明此限定，防止叙述层滑向"推荐 X 板块因为确定性高"。
- 不压成单值；`best` 改为 `recommendation + alternatives + excluded{reason}`，比较维度与权重（若用于 tiebreak）在 `metric` 块显式声明（E3/E4 收入 v1）。

### 5.2 措辞禁令（E5/E6 收入 v1，进契约 `narrative_handoff`）

- 统一判定措辞：`criteria_met / criteria_not_met / indeterminate`，一律附限定语"**基于所提供数据与 as_of_date 规则版本，指标层面的满足情况**"。
- `forbidden_claims[]`（agent 硬约束）：「符合发行条件」「能够/即将上市」「保证过会」「不符合上市条件」（只能说"指标层面不满足 X 套的 Y 条件"）「预计 N 年达标」（除非逐字转述 scenario 且带 is_forecast 标注）「本报告可替代专业意见」。
- `disclaimers[]`：数据来源与审计状态、规则版本与 as_of_date、judgment 项未核查清单、"上市资格由交易所/证监会认定"，外加三条固定边界（专家复核补）：
  1. **段①是抽样核查**：发行条件部分只覆盖保荐人核查清单的子集（募集资金运用等节零覆盖），"指标层面满足"≠ 尽调通过；
  2. **甜区声明**：64 套中 40 套为特殊画像套（红筹/表决权差异），定性条文密集、needs_review 必然集中；工具的有效区是**一般企业套（24 套）+ 定位叠加**；
  3. **预计市值依赖自估**：所有市值类结论一律带"企业自估"限定（§3.4）。

---

## 6. 发现处置表（0002 的 34 条 + 专家复核 G1~G6；v1 范围切分的总裁决）

| 组 | 条目 | 处置 | 落点 |
|---|---|---|---|
| A1 套建模 | **v1 收**（事实修正后） | 套=条文重建；std_id 降为 trace | §2 |
| A2 pass_ratio | **v1 收** | 删；五态计数 | §2.3 |
| A3 套排序 | **v1 收** | sort 仅为官方编号，不参与排序 | §1.1 |
| A4 维度三段式 | **v1 收** | §2.1 | §2 |
| A5 计分 | **v1 收** | 总分/维度分/pass_ratio 全删；#6 关闭 | §2 |
| A6 主体画像 | **v1 收**（事实修正后） | applicant_profile + not_applicable | §2.4 |
| A7 报告期 | **v1 收** | report_period 四字段；非标意见降级 | §1.1 |
| B1 扣非孰低 | **v1 收**（简化） | measures 两维 + lower_of_both | §3.4 |
| B2 量词 | **v1 收** | quantifier 六值 | §2.2 |
| B3 加权 ROE | **v1 收** | 命名强制 | §3.4 |
| B4 研发口径 | **v1 简化** | 拆二（expense/total）；资本化明细 v2 | §3.4 |
| B5 专利 | **v1 收** | 两叶合取 | §3.4 |
| B6 check07 | **v1 收** | 降 needs_review | §3.2 |
| B7 五态 | **v1 收** | §2.3 | §2 |
| B8 diff 分列 | **v1 收** | 数值 diff / 计数 required_delta / 布尔 required_action 三列 | 契约 v0.2 |
| B9 合规项 | **v1 收** | judgment 矩阵 | §3.2 |
| C1 measures | **v1 简化** | 两维；合并/母公司 v2 | §3.4 |
| C2 source_ref | **v1 简化** | 结构化 `{statement, line_item, period, audit_report_id?}`，note_no/restated v2 | 契约 v0.2 |
| C3 归因正交 | **v1 收** | verifiability × substantive_obstacle | §5.1 |
| C4 evidence 类型 | **v1 简化** | source_type 三值 {law, exchange_rule, guideline_qa}；case/准则解释 v2 | 契约 v0.2 |
| C5 规则时点 | **v1 简化** | as_of_date + applied_rule_versions；effective_to/过渡期 v2 | §1.1 |
| C6 指标映射 | **v1 简化** | metric_definition 仅覆盖 6 驱动 + 市值；全量 v2 | 契约 v0.2 |
| D1 表达式树 | **v1 简化** | 固定三段树 + AND/OR 交替（§2.1）；通用树永不（法规形状是常量） | §2 |
| D2 生效区间 | **v1 简化** | effective_from 必填；effective_to/过渡期 v2 | §1.1 |
| D3 applicability | **v1 简化** | 等值合取谓词 | §2.4 |
| D4 条文库 | **v1 简化** | YAML 单库 `{law_id, article, version, text}` + evidence_ref 必填校验；独立版本管理 v2 | 规则库 |
| E1~E4 | **v1 收** | §5.1（帕累托/禁"最优"） | §5 |
| E5/E6 | **v1 收** | §5.2 | §5.2 |
| F1 勾稽 | **v1 收** | §4.2 | §4 |
| F2 双套账 | **v2 推迟** | §4.3 | — |
| （0001）参数库/基准库 | **不建/Phase 2** | 0001 §3 结论维持 | §5.1 |
| G1 套内/条文内 OR（专家复核） | **v1 收** | group/branch 层级 + clause `logic` + 共享条文不变量 | §2.2 |
| G2 window_roll 情景（专家复核） | **v1 收** | 确定性重算（进入年所需值），growth 型维持降级地位 | §5.1 |
| G3 负面清单谓词（专家复核） | **v1 收** | applicability 增 `in_list` | §2.4 |
| G4 口径补丁（专家复核） | **v1 收** | 归母后缀强制、prune 过时项、市值自估声明、同行比=基准库前置依赖 | §3.4 |
| G5 权威源链（专家复核） | **v1 收** | 原文→YAML→快照(trace)；套数差异表=校准旗标 | §0.5 |
| G6 data_uncertainty 改名（专家复核） | **v1 收** | 轴更名 + "不表征审核通过概率"声明 | §5.1 |

**v1 规模预估**：item 重建后约 21 定量条件型 + 3 定性 + 段①约 18 + 段②约 12 ≈ **54 叶型**；展开 checks ≈ 64 套 × 平均 3.5 叶 + 板块级 ≈ **260 判定**，与 v0.1 估算同量级，规模成立。

---

## 7. 对两轮评审的合并裁决 + ADR 编号

| 来源 | 裁决 |
|---|---|
| 0001 F5-R | lever/drivers/gap_profile/set 级条件（P5）**采纳**；"eta 作为结论"按 0002-E2 进一步降级为 scenario_projection |
| 0001 P2（drivers 一等数组） | **采纳**（并入 ADR-0001 修订） |
| 0002 A1/A6 | 事实修正（§0.2），精神保留（§2/§2.4） |
| 0002 其余 | 按 §6 处置表 |

**ADR 编号裁决**（解决两轮评审的 0002 编号冲突）：

| ADR | 主题 | 内容来源 |
|---|---|---|
| ADR-0001（修订） | facts 双层 + `measures[]`/五态/drivers 的 amendment | 0002 §3 + 0001 P2 合并 |
| **ADR-0002（新）** | 套建模与三段式固定树（含 applicant_profile、删 pass_ratio、条文重建、**套内/条文内 OR（group/branch/clause logic）与权威源链**） | 本文 §0.5、§1~§2 |
| **ADR-0003（新）** | 口径与五态（measures、扣非孰低、量词、判定矩阵） | 本文 §2.3/§3 |
| **ADR-0004（新）** | 层①差距画像与情景推演（F5 终案，取代旧 F5/F6 问题） | 本文 §5.1 |

---

## 8. 未决问题表重建（替代 CONTEXT §6）

| 编号 | 内容 | 状态 |
|---|---|---|
| ~~F5~~ | 已收敛为 ADR-0004 方向 | **关闭**（残点：scenario 假设来源是否仅 historical_cagr——建议是，随 ADR-0004 拍板） |
| ~~F6~~ | 被帕累托前沿取代 | **关闭**（残点：tiebreak 权重默认值） |
| #2 | mock/CompanyProfile 字段全集 | 待（骨架已定：§4 的 statements/审计字段/measures 两维） |
| #3 | 规则库 YAML schema | 待（骨架已定：条件型/叶子谓词/条文库/applicability/effective_from） |
| #4 | 公式引擎边界语义 | 待（不变；量化语义受 §3.4 口径约束） |
| #5 | 校准工作流 | 待（条文库 YAML + evidence_ref 必填已定；op/format 码值映射、法条来源与人工流程待定） |
| ~~#6~~ | 维度评分 | **关闭**（A5：删除计分） |
| #7 | 工程细节 | 待（不变） |

---

## 9. 需要拍板的决策点

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| P1 | item 宇宙按**条件型**重建（61 UI 项降为 alias），而非沿用 check01~61 | 重建 / 沿用 | **重建**——条文引用 24 条件型，61 项与其不对齐，沿用则 B1~B5 的口径拆分无处安放 |
| P2 | 固定三段树替代通用表达式树（D1 简化） | 固定树 / 通用树 | **固定树**——法规形状是常量，通用树是为不存在的灵活性付复杂度 |
| P3 | judgment 项：不进层② hard gate、但计入套终态 indeterminate | 此 / 全部硬挡 / 全部忽略 | **此**——引擎无权筛掉也未权放行 |
| P4 | 套级时间仅对"无 act/adjust 阻塞"的套给（0001-P5 维持），且一律 is_forecast | 维持 / 放宽 | **维持** |
| P5 | 0002-A1/A6 的事实修正（§0.2）是否接受为最终记录 | 接受 / 复核原始 SQL | **接受**（快照即依据；如需可对照 midas DML 复核） |
| P6 | ADR 编号按 §7 裁决 | 确认 / 重排 | **确认** |
| P7（v2 增） | 套内 OR 建模：`group_no/branch` 层级 + 条文 `logic ∈ {all, any}` + 共享条文不变量 | 此 / 仅 clause logic / 通用表达式树 | **此**——与快照行一一对应、改动最小；通用树仍是为不存在的灵活性付复杂度（P2 的细化） |
| P8（v2 增） | `window_roll` 情景进 v1（确定性重算，输出进入年所需值） | 进 v1 / 推 v2 | **进 v1**——零增长率假设、实现代价一次减法+对照，且是本工具区别于"编年数"的最大专业增值 |

P1 是总开关（决定 #3 规则库 schema 的形态）；P2/P3/P7 是其推论；P4/P5/P6/P8 可一并确认。

> **拍板记录：2026-11-10 —— P1~P8 全部按推荐通过。** 本文升级为定稿底稿；套清单以 [calibration/0001](../calibration/0001-set-inventory.md)（64 条目 → 43 官方套）为 P5/P7 的证据附件。

---

## 10. 拍板后的落地清单（第三步预告）

1. 重写 CONTEXT v0.2（以本文 §1~§5 为骨架，含契约字段级修订）
2. ADR-0001 修订 + 新建 ADR-0002/0003/0004
3. 删除 HANDOFF.md（吸收完毕）
4. 回到 grilling：#2/#3/#4/#5/#7（骨架均已在本文给出，收敛应快于 v0.1 轮）

---

## 附录 A：白话示例（甲公司）

甲公司（一般企业，拟主板），2022~2024：净利润 **1.5 / 0.3 / 0.4 亿**；三年营收累计 **16 亿**、经营现金流累计 **1.8 亿**；归母净资产 **10 亿**（另有少数股东权益 2 亿，合并报表净资产 12 亿）；三年研发投入 7000 万、占营收 6%。

| 复核点 | 规则原文口径 | 错误模型会怎样 | 本设计的处理 |
|---|---|---|---|
| 套内 OR（G1，§2.2） | 主板第一套「三年现金流累计≥2亿 **或** 三年营收累计≥15亿」→ 营收 16 亿，**该条文满足** | AND 模型判现金流 1.8 亿不达标 → **整套错杀** | 条文 `logic: any`，两条支路任一满足即条文满足 |
| 归母口径（G4，§3.4） | 净资产类条件比的是**归母 10 亿** | 拿合并 12 亿比门槛，虚高 2 亿 | 指标绑定 `attrib_parent`，从取数上不可能拿错 |
| window_roll（G2，§5.1） | 「三年净利累计≥2亿」：2024 年报口径 = 1.5+0.3+0.4 = **2.2 亿 ✓**；2025 年报口径窗口滑出 2022 的 1.5 亿 | 静态工具只说"达标"，企业晚一年申报才发现结论反转 | 输出进入年所需值：2025 年需 ≥ 2.0 − 0.7 = **1.3 亿**，而 2024 实际仅 0.4 亿（3 倍以上）→ 滚动风险高 |
| 同行比依赖（G4，§3.4） | 红筹「增长率高于同行」需要可比公司集合 | 没有同行数据就静默空着，或瞎判 | 未建基准库前一律 `indeterminate` + 显式原因 |
| data_uncertainty（G6，§5.1） | 工具只能度量"报表齐不齐、缺哪年" | 轴名叫"确定性"，叙述层会写成"推荐某板块因为确定性高"（审核概率判断，越权） | 轴名 `data_uncertainty` + metric 块声明不表征审核通过概率 |

## 勘误注（2026-11-10，随设计 0005-E5 / ADR-0006 拍板）

§2.3「折叠（AND 与 OR 同规则，not_applicable 先剔除）」表述有误：按字面执行，OR 条文任一叶 not_met 即整条文 not_met——会错杀「三年现金流累计 1.8 亿 ✗ **或** 三年营收累计 16 亿 ✓」这类**已满足的择一条文**（本文附录 A 第一行正是要修的病，其行为与本勘误一致而与 §2.3 字面矛盾）。正解为 **Kleene 三值按连接词分别定义**：AND 任一 not_met → not_met；OR 任一 met → met；其余 unknown（indeterminate / needs_review）传染为 indeterminate。折叠语义以 [设计 0005 §5](0005-engine-runtime-and-formula-semantics.md) / [ADR-0006](../adr/0006-engine-runtime-and-formula-semantics.md) 为准。

## 勘误注二（2026-11-10，随设计 0006-F2/F3 拍板）

附录 A 的数字有两处内部矛盾，随 mock 契约定稿处置（定稿数值表以 [设计 0006](0006-mock-data-contract.md) §5 为准，逐年勾稽平衡）：

1. 「三年研发投入 7000 万、占营收 6%」**不能同时成立**（7000 万 ÷ 三年营收累计 16 亿 = 4.375%）。定稿取 7000 万、强度实算 4.375%（< 5%，甲公司不满足科创属性研发指标——与其主板定位自洽）；「6%」按笔误处理，附录 A 未用该值做任何判定示例，无下游影响。
2. 净利 1.5 → 0.3 亿 = **−80%**，超出 §4.2-⑥ 示例区间 (−50%, +200%)。⑥ 本为数据卫生参数而非法规语义，随 0006-F3 参数化进 `fixtures/sanity.yaml`（净利 (−90%, +300%)），剧情保留。
