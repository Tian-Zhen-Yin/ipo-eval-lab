# 设计 0006：mock 数据契约（CompanyProfile 字段全集）

- 日期：2026-11-10
- 性质：**伞形收官第 ③ 步（收官件）**——M3 企业数据契约；吸收未决 **#2**
- 输入：[设计 0001](0001-top-down-redesign.md) §4（fixtures 结构 / 七条勾稽 / v1-v2 切）、[设计 0005](0005-engine-runtime-and-formula-semantics.md) §2（Fetch 取数面：逐年扣非 / 逐年审计 / 权益变动序列）、[设计 0002](0002-rulebook-yaml-schema.md)（7 metric 的字段需求）、[设计 0004](0004-system-architecture.md)（M3 职责 / AR4 断言前置）
- 决策点：F1~F6（§8，**2026-11-10 已拍板：全部按推荐**）。编号前缀 **F**（Fixture），与 0001-P / 0002·0003-R / 0004-A / 0005-E 区分；引用带文档号（如「设计 0006-F2」）。与评审文档的历史 F5/F6 发现编号无关。
- **v0.2（2026-11-10）**：§6.1 增补 golden 的进度与覆盖率期望值（E9 / [ADR-0007](../adr/0007-progress-and-coverage-metrics.md)）；§6 golden 套 ID 改用实物 `group_id`（`cn_main_general_g1` / `star_general_g1`），不引入短名别名层。

---

## 0. 本文回答什么

引擎的输入数据长什么样：**一份 profile.json 就够引擎跑完五节点**（设计 0005）。本文定：文件形态、字段全集、勾稽断言落法、expected golden 格式、边界/缺数生成器族、基准样本数值定稿。

## 1. 目录与文件形态（F1）

```
fixtures/
  sanity.yaml                # 勾稽⑥增长率区间的参数配置（见 §4）
  companies/
    base_co_2029/            # 基准样本（甲公司，数值定稿见 §5）
      profile.json           # 单文件：applicant_profile + statements[] + documentary + declared
      expected/              # golden（§6）
    qualified_audit/         # 非标审计意见变体（2023 意见改 qualified，测 E3 降级路径）
  generators/                # 实现期：±ε 边界族 + knockout 缺数族（§7，动态生成不落盘）
```

- **单文件 profile.json**（statements 内嵌为年度数组），不用「按年拆文件」——加载与断言一次完成，拆文件没有消费方。0001 §4.1 草图的 `statements/` 目录就此收敛为单文件。
- 金额一律**整数元**（与 E8 一致）；百分比不存（全部派生）；JSON 格式。
- 加载器 = `fixtures` loader（引擎 Init 节点与测试共用同一实现，AR4：坏数据起不了 run）。

## 2. CompanyProfile 字段全集（F2）

### 2.1 顶层

| 字段 | 类型 | 说明 |
|---|---|---|
| `company_id` | str | = 目录名 |
| `display_name` | str | 展示名 |
| `applicant_profile` | obj | `{company_type ∈ 4 枚举, profit_status ∈ {profitable, loss_making}, industry: str\|null}`——适用性谓词的输入（industry 供 in_list 负面清单） |
| `statements[]` | list | 逐年财务（§2.2），年份连续 |
| `stub_period` | obj\|null | 申报期一期数据；**展示用，永不进判定**（E2-2） |
| `documentary` | obj | 底稿事实项（§2.3） |
| `declared` | obj | judgment 项自报值（§2.4，只作证据） |

### 2.2 statements[]（每年一条）

| 块 | 字段 | 供给谁 |
|---|---|---|
| `fiscal_year` | int | 窗口解析（E2） |
| `audit` | `{status: audited\|unaudited, opinion: unqualified\|qualified\|disclaimer\|adverse\|null, report_id: str\|null}` | E3 审计覆盖降级；勾稽⑤（逐年必填） |
| `income` | `operating_revenues: int`；`net_profit_total: int`；`net_profit_attrib_parent: {as_reported: int, excl_nonrecurring: int\|null}`；`rd_expensed: int\|null`；`rd_capitalized: int\|null` | 营收类 item；**净利润总额（含少数股东损益）**（评审 0004 V9）；净利 measures 两维 + 逐年孰低（E3）；研发两源 |
| `cash_flow` | `net_cash_flow_from_operating: int` | ocf 类 item；勾稽② |
| `balance` | `total_assets, total_liabilities, total_equity, total_equity_attrib_to_parent, minority_interests: int` | 净资产类 item（归母口径绑定）；勾稽① |
| `equity_roll` | `{opening_attrib_parent, net_profit_attrib_parent, dividends, capital_injection, closing_attrib_parent: int}` | ROE 加权派生的输入；勾稽③ |
| `reconciliation` | `{net_profit_total, adjustments, net_cash_flow_from_operating: int}` | 间接法调节表；勾稽②。**起点为净利润总额（含少数股东损益），非归母**（评审 0004 V9）——归母起算会迫使少数损益被 adjustments 静默吸收；`adjustments` 含少数股东损益、折旧摊销等调节项 |

### 2.3 documentary（底稿事实项，documentary × worksheet 判定矩阵的载体）

| 字段 | 供给谁 |
|---|---|
| `mktcap_self_estimate: {value: int\|null, note: str} \| null` | 市值/预计市值类 item（`basis: self_estimate`）；**null → indeterminate（G-C 的落点）** |
| `invention_patents: {granted_count: int\|null, applied_to_main_business: bool\|null}` | 专利两叶合取（0001 B5） |
| `operating_years: int\|null` | 主体资格经营年限 |
| `public_float_ratio: decimal\|null` | 公开发行比例（条件型之一） |
| `total_shares_after_ipo: int\|null` | 发行后股本总额（单位：股；评审 0004 V10——设计 0002 §2.7 issuance 叶与设计 0007 §6 甲公司 8000 万股的数据载体；引擎 v1 无消费方，先落数据契约） |

### 2.4 declared（judgment × declared，永不 met）

| 字段 | 供给谁 |
|---|---|
| `self_developed_tech_intl_leading: bool\|null` | 科创属性定性；输出 pending_evidence |
| `rd_stage_or_innovation_redchip: bool\|null` | 红筹研发阶段/国家创新驱动 |
| `national_approved_or_phase2_clinic: bool\|null` | 国家批准/二期临床 |

### 2.5 覆盖核对（对 0002 的 7 metric + 24 条件型）

7 metric 全部有源：operating_revenues / net_profit_attrib_parent（两维）/ net_cash_flow_from_oper / total_equity_attr_to_parent ← statements；rd_investment_total ← 两源相加；roe_weighted_avg ← 派生（np + equity_roll）；mktcap ← documentary。21 定量条件型的字段需求由此全覆盖；3 定性 ← declared。

## 3. 派生与取数衔接（对齐设计 0005 §2）

- **逐年孰低**：引擎逐年取 `min(as_reported, excl_nonrecurring)` 再聚合；`excl_nonrecurring = null` → 整叶 indeterminate（不用申报值顶替）。
- **ROE 派生**：`roe_weighted_avg` = 净利润 / 按权益变动时间加权的平均归母净资产（equity_roll 提供逐笔变动）；分母 ≤ 0 → 缺值。
- **研发**：`rd_investment_total = rd_expensed + rd_capitalized`，任一源 null → 该年缺值。
- **stub**：`stub_period` 只进 facts 展示，永不进窗口与判定。

## 4. 勾稽七条的落法（F3）

| # | 约束（0001 §4.2） | 断言（fixtures loader 加载期） |
|---|---|---|
| ① | 资产 = 负债 + 权益 | `total_assets == total_liabilities + total_equity`；且 `attrib_parent + minority == total_equity` |
| ② | 间接法调节表平 | `net_profit_total + adjustments == ocf`（逐年）；且调节表 `net_profit_total` == 利润表 `net_profit_total`（**V9：起点为净利润总额，非归母**） |
| ③ | 权益变动勾稽 | `opening + np − dividends + capital_injection == closing`（归母，逐年） |
| ④ | 年份连续 | fiscal_years 连续整数；stub 与末年相邻 |
| ⑤ | 审计字段逐年存在 | `audit.status/opinion` schema 必填；基准样本全 unqualified，qualified 变体测降级 |
| ⑥ | 增长率合理区间 | **参数化进 `fixtures/sanity.yaml`**：营收/现金流 (−50%, +200%)；**净利 (−90%, +300%)**——甲公司 1.5→0.3 亿 = −80% 是设计好的剧情（window_roll 的戏剧性来源），默认区间会误伤 |
| ⑦ | 边界族 ±ε | 生成器（§7），不做加载断言 |

> ⑥ 的区间是**数据卫生参数**（防生成器手滑），不是法规语义——故放 fixtures 配置而非规则库。

## 5. base_co_2029（甲公司）数值定稿表

单位：万元（存储为元）。勾稽①②③逐年平衡（资产/负债见下注）。

| 年 | 营收 | 归母净利（申报） | 扣非 | 经营现金流 | 研发费用化 | 研发资本化 | 归母净资产（期末） |
|---|---|---|---|---|---|---|---|
| 2022 | 42,000 | 15,000 | 14,400 | 5,000 | 1,600 | 300 | 93,400 |
| 2023 | 50,000 | 3,000 | 3,000 | 6,000 | 1,800 | 300 | 96,200 |
| 2024 | 68,000 | 4,000 | 4,000 | 7,000 | 2,500 | 500 | 100,000 |

- 权益滚动：期初 2022 = 79,400；分红 1,000 / 200 / 200；无增资 → 期末 93,400 / 96,200 / 100,000 ✓（勾稽③）
- 少数股东权益 20,000（恒定）→ 合并权益 113,400 / 116,200 / 120,000；资产负债：2022 A=260,000 L=146,600；2023 A=270,000 L=153,800；2024 A=300,000 L=180,000（勾稽①）
- 调节表 adjustments = OCF − 净利润总额：−10,000 / +3,000 / +3,000（勾稽②；本样本少数损益恒 0，总额=归母——少数股东权益 20,000 恒定）
- applicant_profile：general / profitable / 高端装备制造业；audit：三年 audited + unqualified；`mktcap_self_estimate = null`（G-C 路径）；`operating_years = 12`；专利 5 项且应用于主营；declared 全 null（needs_review + pending_evidence 演示）

**两处 0001 附录 A 矛盾的处置**（F2 附注）：

1. **研发 7000 万 vs「占营收 6%」不能同真**：7000 / 160,000 = **4.375%**。定稿取 7000 万、强度实算 4.375%（< 5%）——甲公司不满足科创属性研发指标，与其「主板企业」定位自洽；附录 A 的「6%」按笔误处理，加勘误影响为零（附录 A 未用该值做任何判定示例）。
2. **净利 −80% 撞穿 ⑥ 默认区间**：见 §4——净利区间放宽为 (−90%, +300%)，剧情保留。

**保留的经典数字**（全链回归基准）：三年净利均为正 ✓；累计孰低 21,400 万 ≥ 20,000 ✓（申报 22,000）；**最近年 4,000 < 10,000 → diff 6,000 万**；现金流 18,000 < 20,000 ✗ 但营收 160,000 ≥ 150,000 ✓ → 条文 any 择一满足（E5 Kleene OR 的活例）；window_roll 进入年需 20,000 − 7,000 = **13,000 万** vs 最近年 4,000（×2 = 8,000 < 13,000 → 高风险）。

## 6. expected golden（F4）

`expected/summary.json` **只锁语义敏感点**，不锁全量快照（全量锁会随规则库演进频繁碎）：

```
{ rulebook_version, as_of, target,
  sets:     { "cn_main_general_g1": {outcome: criteria_not_met, blockers: [np_latest]},
              "star_general_g1":    {outcome: indeterminate, blockers: [mktcap]} },
  key_checks: [ {leaf: np_latest, state: not_met, diff: 6000_0000},
                {leaf: ocf_clause_any, state: met},            # Kleene OR 活例
                {leaf: np_3y_sum, state: met} ],
  window_roll: [ {leaf: np_3y_sum, required: 13000_0000, risk: high} ] }
```

> **套 ID 用 group_id**（`cn_main_general_g1` / `star_general_g1`），与 `rulebook/sets/*.yaml` 的 `group_id` 实物一致——不引入「套短名」别名层，避免两套 ID 空间。

维护纪律：golden 绑 `rulebook_version`；规则库升版后 golden 重算并人工过目（差异即回归清单）。

### 6.1 进度与覆盖率期望值（v0.2 增补，E9）

golden 同时锁量化指标（[设计 0005 §5.2](0005-engine-runtime-and-formula-semantics.md)，语义敏感点——**min 聚合与「未定义叶不进聚合」两处最易错**）：

```
  progress: {
    "cn_main_general_g1": {progress: 40, coverage: 100,
                            binding_clause_id: "cn_main_g1_c3",
                            next_binding_clause_id: "cn_main_g1_c2"},
    "star_general_g1":    {progress: 100, coverage: 80,
                            binding_clause_id: null,          # 无未定义叶参与绑定
                            next_binding_clause_id: null}
  }
```

| 套 | progress | coverage | 依据 |
|---|---|---|---|
| 主板第一套 | **40** | **100** | min(1.0 均为正, 1.0 累计, 0.4 最近年, 1.0 现金流/营收 any) = 0.4；4/4 叶可判 |
| 科创板第一套 | **100** | **80** | 市值叶未定义 → 不进聚合，min 仍 1.0；但 4/5 叶可判 → 覆盖率 80% |

- **主板套 `binding_clause_id` = `cn_main_g1_c3`（最近一年净利条款）**——progress 最小者；次弱 = `cn_main_g1_c2`（净利累计条款，gap 7%）。
- **科创板套 progress=100 但 coverage=80**：这组值是**双指标必要性的活例**——单看 100 分会以为这套没问题，实际市值那项是空的。golden 锁住这组值，防止未来有人「顺手」把未定义叶按 0 算进聚合（那正是 midas 病灶）。
- 进度百分比取**整数**（与 UI 展示一致）；引擎内部按 float64 计算，取整在 golden 断言侧做（round 半进位规则固定为「四舍五入到最近整数」）。

## 7. 生成器族（F5 / F6）

| 族 | 生成方式 | 测什么 |
|---|---|---|
| **±ε 边界族** | 读规则库阈值 → 每个数值叶生成 `thr+1 元` / `thr−1 元` 两变体（改 base_co_2029 对应年度值） | met/not_met 在阈值两侧精确翻转（E8 无 ε 比较的验证） |
| **knockout 缺数族** | 对 base 定稿表做删项：删 2022 整年 / 置空 2023 扣非 / 置空市值（G-C）/ 意见改 qualified | E3 三原则：叶级隔离、无静默回退、审计覆盖降级 |

两族均**测试期动态生成、不落静态文件**——阈值变了变体自动跟随规则库，不存在「边界文件过期」问题。

## 8. 决策点（F1~F6）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| F1 | 单文件 profile.json（statements 内嵌）+ expected/ 目录；整数元、JSON | 单文件 / 按年拆文件 | **单文件**——加载断言一次完成，拆文件无消费方 |
| F2 | 字段全集如 §2（顶层 5 块 + 逐年 7 块 + documentary 5 项 + declared 3 项；**2026-11-12 增补：净利润总额 + 发行后股本两字段，评审 0004 V9/V10**）；0001 附录 A 两处矛盾按 §5 处置（研发取 7000 万实算 4.375%；净利区间放宽） | 此 / 研发改 9600 万保 6% | **此**——保住「主板企业不过科创属性」的叙事自洽；9600 万方案会反转该结论 |
| F3 | 勾稽七条映射如 §4；断言在 fixtures loader（引擎与测试共用）；⑥ 区间参数化进 sanity.yaml（净利 (−90%, +300%)） | 此 / 区间硬编码 / 放规则库 | **此**——数据卫生参数归 fixtures，不污染法规语义 |
| F4 | golden 只锁语义敏感点 + 绑 rulebook_version；升版重算人工过目 | 锁敏感点 / 锁全量 | **锁敏感点**——全量锁随规则库演进高频碎，敏感点锁住的都是设计决策 |
| F5 | ±ε 边界族 + knockout 缺数族测试期动态生成（读规则库阈值），不落静态文件 | 动态 / 静态落盘 | **动态**——自动跟随规则库，无过期问题 |
| F6 | v1 清单：base_co_2029 + qualified_audit 变体 + 两生成器族（0001 §4.3 的「干净账+边界族+非标」落实）；G-C 由 mktcap=null 覆盖 | 此 / 再加红筹样本 | **此**——红筹专套未铺开（随校准管线），样本先行无 golden 可锁 |

| F7 | documentary 增 `rev_cagr_gt_peer_avg: bool\|null`（增长认定第三路径的行业对比结论，midas check07 同源）；企业数据底表预置布尔，null → indeterminate | 底稿布尔 / 引擎现算行业均值 | **底稿布尔**——行业可比公司集合与均值口径是企业数据底表的外部事实，引擎不自造对比基准 |
| F8 | 红筹豁免字段沿用既有 `company_stage`（`rd_stage` / `strategic_significance` 两枚举值即两条豁免触发），不新增 `national_strategy_redchip` 布尔 | 沿用枚举 / 加独立布尔 | **沿用枚举**——一个字段两值已承载「研发阶段 OR 国家战略」，加布尔会出现两处事实来源不一致的口径裂缝 |

> **拍板记录：2026-11-10 —— F1~F6 全部按推荐通过。** 随拍板：#2 关闭；设计 0001 附录 A 加勘误注二；**伞形三步（0004/0005/0006）决策全部拍板，系统设计收官**——实现期按 A6 顺序（M3 → M4/M5 → M1 全量 → 边界族回归），启动时点随 #7 拍板。

> **拍板记录：2026-11-12 —— F7/F8 随底稿 0002 问题二/三裁定落地**（用户 P4 拍板 confirmed ×3；F7/F8 是实现形态归位，substance 同一裁定）：metric `rev_cagr_vs_peer`（documentary/boolean）+ item `rev_cagr_gt_peer_avg` + 引擎 builder + 六个红筹未上市套的第三路径支路；豁免按 ADR-0008 `Clause.exemptions`（company_stage in_list）编入 21 条增长认定条款。

## 9. 对账与收官判据核验

| 项 | 关系 |
|---|---|
| #2（mock 契约） | 本文即其全部内容；F 拍板后 **#2 关闭** |
| 0001 §4 | 结构收敛（statements/ → 单文件）；⑥ 区间参数化；两处附录 A 矛盾处置（勘误性质，不动判定示例） |
| 0005 §2 取数面 | §2/§3 逐年扣非、逐年审计、equity_roll、mktcap null→indeterminate 全部落位 |
| 0002 七 metric | §2.5 覆盖核对通过 |
| **0005 E9（进度与覆盖率）** | §6.1 golden 增期望值；**科创板套 progress=100 / coverage=80 是双指标必要性的活例**（市值叶未定义 → 不进聚合但计入覆盖分母） |
| 0004 §2 映射表 | M3 ← 0006（本文）；M4/M5 ← 0005（E1~E9 已拍板）——**映射表全覆盖达成** |
| 收官判据（0004-P3） | F1~F6 拍板后：CONTEXT §5 设计类未决清零（#2/#4 关闭，#3/#5 剩实现项，#7 工程细节 + #8 搁置）→ **系统设计收官**，实现期按 A6 顺序启动（M3 → M4/M5 → M1 全量 → 边界族回归） |
