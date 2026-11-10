# 设计 0002：规则库 YAML schema（未决 #3 草案）

- 日期：2026-11-10
- 性质：未决 **#3 规则库 YAML schema** 的第一版草案；落实 P1（item 按条件型重建）、P2（固定三段树）、P7（group/branch/clause 四层）的**存储形态**；吸收评审 0003 交叉对照产出的 **G-A（lint 五条）** 与 **G-B（窗口抽象）**
- 关联：[ADR-0002](../adr/0002-set-modeling-three-segments.md)（四层结构与三段树）、[ADR-0003](../adr/0003-metrics-and-five-states.md)（口径与量词）、[calibration/0001](../calibration/0001-set-inventory.md)（43 官方套）、[CONTEXT §3.3](../../CONTEXT.md)（契约不变量）
- 状态：**草案，R1~R6 待拍板**；拍板后按 §9 落地步骤实施

---

## 0. 目标与非目标

**目标**：把「法规原文 → 规则库 YAML」这一环的物理形态定下来——实体、字段、文件组织、加载期校验（lint）、与 midas 快照的 trace 约定。写完即可开始铺数据（校准 #5 并行）。

**非目标**：公式引擎实现（#4，本文只定 `window token` 契约）；mock 数据（#2）；有效期/过渡期（v2）；通用谓词语言（永不做，ADR-0002）。

**一条铁律**（D4 权威源链）：YAML 是**人工校准的产物**，不是快照的格式转换——快照字段（std_id、checkNN）只进 `aliases` 作 trace，不参与建模。

---

## 1. 文件组织（R1）

```
rulebook/
  _meta.yaml                  # rulebook_version + 全局约定（单位/格式/枚举）
  metrics.yaml                # metric_definitions（v1：6 驱动 + 市值，C6 简化）
  items.yaml                  # 条件型库（24 种：21 定量 + 3 定性）
  legal/                      # 法条库（evidence_ref 指向这里）
    csrc_205.yaml             # 《首发注册管理办法》
    sse_main_2026.yaml        # 沪交易所上市规则（按文件分）
    szse_chinext_2026.yaml
    bse_2026.yaml
    guideline_star.yaml       # 科创属性指引等（source_type: guideline_qa）
  issuance/                   # 段① 发行条件（L1 四节的 v1 子集）
    common.yaml
  positioning/                # 段② 板块定位（每板块一文件）
    star.yaml  chinext.yaml  bse.yaml  cn_main.yaml
  sets/                       # 段③ 官方套（43 group，按板块×类型分文件）
    cn_main_general.yaml      # 沪深同文合并（calibration：34 份标准文本）
    star_general.yaml
    star_redchip_unlisted.yaml
    ...
```

白话：**实体决定文件**（指标/条件型/法条各一个库），**板块决定套文件**。单文件 < 300 行，校准 #5 逐文件签收。

---

## 2. 实体 schema

### 2.1 `_meta.yaml`——全局约定

```yaml
rulebook_version: rb-2026.11     # run.applied_rule_versions[] 记录此值
conventions:
  percent: decimal               # 百分比一律存小数（0.25 = 25%）——G-A-1 量纲 lint 的基准
  money: yuan                    # 金额一律存元（200000000 = 2 亿）
  op: [eq, ne, gt, ge, lt, le]   # 实测快照仅出现 eq/gt/ge 三种
  format: [number, percent, integer, boolean]
note: suffix（年/项）仅展示用，不参与判定与存储
```

### 2.2 `metrics.yaml`——指标定义（C6）

v1 只定义 **7 个**：6 个财务驱动 + 市值（全量 v2）。**量纲与口径在这里单点声明**（R5），leaf 不重复。

```yaml
- metric_id: net_profit_attrib_parent
  display: 归母净利润
  unit: yuan
  basis: attrib_parent                  # 归母强制（G4），从取数上不可能拿合并口径
  measures:                             # ADR-0003 两维
    deduction: [as_reported, excl_nonrecurring]
    audit: [audited]
  decision_measure: lower_of_both       # 判定取扣非前后孰低；measures[] 全套进 facts 供展示
  sources: {ads: [net_profit_attrib_parent_ytd_cf, net_profit_attrib_parent_excl_extra_ytd_cf]}

- metric_id: operating_revenues
  display: 营业收入（本年累计）
  unit: yuan
  quantifier_scope: ytd
  sources: {ads: [operating_revenues_ytd_bl_cf]}

- metric_id: mktcap
  display: 市值/预计市值
  unit: yuan
  nature: documentary                   # 非财报指标：企业自估（G4）
  basis_hint: self_estimate             # 叙述层强制「企业自估」限定；红筹已上市叶记 source: offshore_market（G-C：mock 无此数据源 → indeterminate）
```

（其余 4 驱动：net_cash_flow_from_oper / total_equity_attr_to_parent / rd_investment_total / rd_expense——结构同上，rd 拆二按 ADR-0003。）

### 2.3 `items.yaml`——条件型库（24 种，P1 的落地）

item = 可复用的**条件类型**（量词+窗口+指标），**不带阈值**；阈值在 leaf 上。61 个 checkNN 降级为 `aliases`。

```yaml
- item_id: np_3y_allpos
  display: 最近3年净利润均为正
  nature: quantitative
  basis: calc
  metric_ref: net_profit_attrib_parent
  quantifier: all_periods              # 量词六值：latest/all_periods/sum/avg/cagr/ratio
  window: {kind: last_n_years, n: 3}   # 窗口 token（§3），引擎单点解析
  lever: grow
  driver_ids: [net_profit_attrib_parent]
  aliases: {midas: [check09, check10, check14, check15]}   # 扣非成对叶被 measures[] 吸收，四变一

- item_id: np_3y_sum
  display: 最近3年净利润累计
  quantifier: sum
  window: {kind: last_n_years, n: 3}
  aliases: {midas: [check12, check17]}

- item_id: rev_3y_cagr
  display: 最近3年营业收入复合增长率
  quantifier: cagr
  window: {kind: last_n_years, n: 3}
  aliases: {midas: [check06]}

- item_id: rd_intensity_3y
  display: 最近3年累计研发投入占最近3年累计营业收入比例
  quantifier: ratio
  window: {kind: last_n_years, n: 3}
  numerator: rd_investment_total
  denominator: operating_revenues       # 分母≤0 → N/A → indeterminate（五态，不判 not_met）
  aliases: {midas: [check30]}

- item_id: mktcap_forecast
  display: 预计市值
  nature: documentary                   # 填报值：有值按值判，无值 indeterminate
  basis: worksheet
  aliases: {midas: [check01]}

- item_id: self_developed_tech          # 定性 3 种之一
  display: 自主研发与国际领先技术
  nature: judgment                      # 永不 met（ADR-0003 判定矩阵）→ needs_review + pending_evidence
  basis: declared
  aliases: {midas: [check33]}
```

**算例（midas 冗余叶被吸收）**：midas 用 check08（净利>0）+ check13（扣非>0）两条实现「孰低」，我们用 `item(measures: lower_of_both) × 1 叶` 实现——叶数从 234 收敛到约 180，且**不可能配出「净利用非扣非、扣非忘了配」这种半套口径**（这正是需求侧 check12 张冠李戴的病根）。

### 2.4 `legal/`——法条库（D4）

```yaml
- law_id: sse_main_2026
  title: 上海证券交易所股票上市规则（2026年4月修订）
  source_type: exchange_rule            # v1 三值：law / exchange_rule / guideline_qa
  effective_from: 2026-04-24
  articles:
    - article: "3.1.2"
      text: 发行条件第（一）种情形：最近三年净利润均为正且累计不低于2亿元……
```

引用形如 `law_ref: sse_main_2026#3.1.2`。**clause 的 law_ref 必填**（lint），阈值无出处=校准未完成=加载失败。

### 2.5 `sets/`——官方套（group → branch → clause → leaf）

以**科创板·一般·第一套**为例（快照 IPO-15/16 两行 = 两个 branch）：

```yaml
- scope: set
  group_id: star_general_g1
  display: 科创板标准一（市值＋净利润）
  boards: [STAR]
  company_type: general
  group_no: 1                            # 官方套号，仅编号不排序（A3）
  effective_from: 2019-03-01             # 待校准 #5 回填
  law_refs: [sse_star_2026#2.1.2]
  shared_clauses:                        # 不变量 #6 的结构化载体：公共条文写一次
    - clause_id: star_g1_c0
      display: 预计市值不低于10亿元
      law_ref: sse_star_2026#2.1.2(一)
      leaves:
        - leaf_id: star_g1_c0_l1
          item_ref: mktcap_forecast
          op: ge
          threshold: {value: 1000000000, format: number}
  branches:                              # group 内 OR
    - set_id: star_general_g1-b1         # branch = set_id（层②/差距画像的引用单元）
      display: 两年净利路径
      aliases: {midas: [IPO-15]}
      clauses:                           # branch 内 AND
        - clause_id: star_g1_b1_c1
          display: 最近两年净利润均为正
          law_ref: sse_star_2026#2.1.2(一)
          leaves:
            - {leaf_id: star_g1_b1_c1_l1, item_ref: np_allpos_2y, op: gt, threshold: {value: 0, format: number}}
        - clause_id: star_g1_b1_c2
          display: 最近两年净利润累计不低于5000万元
          law_ref: sse_star_2026#2.1.2(一)
          leaves:
            - {leaf_id: star_g1_b1_c2_l1, item_ref: np_2y_sum, op: ge, threshold: {value: 50000000, format: number}}
    - set_id: star_general_g1-b2
      display: 一年净利＋营收路径
      aliases: {midas: [IPO-16]}
      clauses:
        - {clause_id: star_g1_b2_c1, law_ref: sse_star_2026#2.1.2(一), leaves: [{leaf_id: l1, item_ref: np_latest, op: gt, threshold: {value: 0, format: number}}]}
        - {clause_id: star_g1_b2_c2, law_ref: sse_star_2026#2.1.2(一), leaves: [{leaf_id: l1, item_ref: rev_latest, op: ge, threshold: {value: 100000000, format: number}}]}
```

**判定折叠算例**（ADR-0003 规则）：某公司市值 12 亿、b1 路径两年净利 3000 万+4000 万（累计 7000 万≥5000 万 ✓，均为正 ✓）→ b1 = met；b2 未评（OR 短路策略由引擎定，事实层仍全量记录）；shared_c0 met → **group = met**。若两年累计只有 4000 万 → b1 not_met、b2 若 1 年净利>0 且营收 0.8 亿<1 亿 → not_met → group not_met，blockers = [np_2y_sum(差1000万), rev_latest(差2000万)]——差距画像的直接输入。

### 2.6 `positioning/`——段②板块定位

```yaml
- board: STAR
  display: 科创属性（3 项常规指标＋例外）
  hard_filters:                          # 行业负面清单 = 硬筛（G3：in_list）
    - {field: industry, op: not_in, list_ref: star_negative_list}
  regular:                               # 常规指标 AND
    - clause_id: star_pos_rd
      display: 研发投入：占比≥5% 或 累计≥8000万     # ← 指标内联「或」→ clause any（R2）
      law_ref: guideline_star#4
      logic: any                         # clause 内叶择一
      leaves:
        - {leaf_id: l1, item_ref: rd_intensity_3y, op: ge, threshold: {value: 0.05, format: percent}}
        - {leaf_id: l2, item_ref: rd_3y_sum, op: ge, threshold: {value: 80000000, format: number}}
    # ……研发人员占比、成长性指标（数值以校准 #5 为准，此处为结构示例）
  exceptions:                            # 例外条款 OR（全部 judgment → needs_review，永不 met）
    - clause_id: star_pos_exc1
      law_ref: guideline_star#5(一)
      leaves: [{leaf_id: l1, item_ref: core_tech_national_recognition, op: eq, threshold: {value: true, format: boolean}}]
```

**G-D 落点**：需求 IPO-41~61 的 21 套「板块匹配度标准」逐套映射到本结构（regular/exceptions/hard_filters），映射表进校准 #5 底稿。

### 2.7 `issuance/`——段①发行条件（v1 子集）

结构复用 sets 机制，`scope: issuance`，按 L1 四节打 `section` 标签；v1 只铺**主体资格 + 规范运行**两节（募资运用零覆盖——叙述层边界声明 1 的依据）。双档条件示例：

```yaml
- scope: issuance
  section: subject_qualification
  clause_id: iss_sq_public_float
  display: 公开发行比例
  law_ref: csrc_205#2.1(4)
  branches:                              # 双档 = branch 择一：≥25% 或 (股本≥4亿 ∧ ≥10%)
    - set_id: iss_sq_pf-b1
      clauses:
        - {leaves: [{leaf_id: l1, item_ref: public_float_ratio, op: ge, threshold: {value: 0.25, format: percent}}]}
    - set_id: iss_sq_pf-b2
      clauses:
        - {leaves: [{leaf_id: l1, item_ref: total_shares_after_ipo, op: ge, threshold: {value: 400000000, format: number}}]}
        - {leaves: [{leaf_id: l1, item_ref: public_float_ratio, op: ge, threshold: {value: 0.10, format: percent}}]}
```

（midas 把它拆成 IPO-37/38 两套「标准」参与维度计分；我们是发行条件内择一，语义归位。）

---

## 3. 窗口抽象（G-B 的 schema 侧）

**窗口只允许 token，不允许手写区间**（G-A-5——midas check04/11 的「同一 `~3` 两种区间」事故在结构上不可复现）：

| token | 语义（引擎单点实现） | 例子（报告期结束年 2024） |
|---|---|---|
| `{kind: nth_year, n: 1\|2\|3}` | 结束年往前第 n 年的 YYYY-12 | n=2 → 2023-12 |
| `{kind: last_n_years, n: 2\|3}` | 连续 n 个年度的 YYYY-12 集合 | n=3 → 2022/2023/2024-12 |
| `{kind: latest}` | 结束年当年 | 2024-12 |

- 量词消费窗口：`sum/avg/all_periods/ratio` 用集合型；`latest/cagr` 用单点/首尾。
- **解析失败策略（#4 的 schema 立场）**：窗口解析不到数据（如缺 2023-12）→ 该叶 `indeterminate`，**无静默回退**（不取年内最新、不取上年顶替）——回退语义若要加，属 #4 拍板范围，schema 预留 `fallback: null` 字段位。

---

## 4. lint（G-A 落地：加载期断言，坏配置起不来）

| # | 规则 | 来源 | 实现要点 |
|---|---|---|---|
| L1 | 量纲一致：同 metric 的阈值 format 唯一；percent 存小数、money 存元 | G-A-1 | metric ↔ leaf format 交叉校验 |
| L2 | 组合覆盖：每个 (board, company_type) 要么 ≥1 group，要么显式 `declared_no_sets: true`；**run 时适用套为空 → 报错退出**，不出空报告 | G-A-2 | 覆盖矩阵 lint + 运行期检查双层 |
| L3 | 每 group ≥1 clause；多 branch 的 group，`shared_clauses` 非空 | G-A-3 + 不变量 #6 | 结构即校验（shared 写一次） |
| L4 | 引用完整：leaf.item_ref ∈ items；item.metric_ref ∈ metrics；clause.law_ref ∈ legal；set 成员 ⊆ items | G-A-4 + 不变量 #1 | pydantic 加载断言 |
| L5 | 窗口不重述：leaf/item 只出现 token，任何实体不得出现期间区间字符串 | G-A-5 | 正则黑名单（`-12`、`至`） |
| L6 | evidence 必填：clause.law_ref 非空；rulebook_version、effective_from 非空 | D2/D4 | 加载断言 |
| L7 | alias 唯一且全覆盖：std_id/checkNN 在 alias 中各出现一次；43 group / 快照 64 行 / 234 阈值对拍计数守恒 | trace | `scripts/trace_check.py`（对拍脚本，§6） |

---

## 5. 与快照的对拍（trace）

- `aliases: {midas: [IPO-15, check06…]}` 记录溯源；**不复制快照的任何判定字段**。
- 对拍脚本产出三张守恒表：group 43 ↔ calibration/0001；branch/clause ↔ 快照 64 条目（R2 选定后注明 collapse 关系）；leaf 阈值 ↔ 234 行（已知三处 midas 错误按 calibration §4 剔除后比对）。
- 快照与 YAML 冲突 → **YAML 赢**（权威源链），冲突记录进校准日志。

---

## 6. 落地步骤（拍板后）

1. pydantic 模型（含 L1~L6 断言）+ `_meta/metrics/items` 三个基础库全量（~1 人天）
2. 样板套文件 2 个：`star_general.yaml`（branch 择一）+ `cn_main_general.yaml`（clause any，R2 验证件）（~1 人天）
3. `scripts/trace_check.py` 对拍（L7）（~0.5 人天）
4. 全量铺开 43 group + positioning 5 板块 + issuance 2 节（**与校准 #5 交错进行**，每文件签收法条出处）（~3~4 人天，含校准）

---

## 7. 需要拍板的决策点（R1~R6）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| R1 | 文件组织 | a. 按实体+板块分文件（§1）<br>b. 单一大文件 | **a**——校准可逐文件签收；单文件 2000+ 行不可评审 |
| R2 | 单叶「或」的落位 | a. clause `logic: any`（设计 0001 §2.2 例；主板第一套=1 个 branch，快照 2 行 alias 到同 branch）<br>b. branch-per-快照行（ADR-0002 字面；主板第一套=2 branches） | **a**——忠于官方文本粒度（指标内联「或」vs 法条并列情形）；代价：ADR-0002「branch 与快照行一一对应」需加一条勘误注（alias 覆盖即可） |
| R3 | 标识命名 | a. 语义 id（`star_general_g1-b1`）+ boards[] 数组（沪深同文合并共享 group）<br>b. 沿用快照 sort 拼接 | **a**——沪深 34 份同文若不共享 group，shared_clauses 要维护两份，违反 DRY |
| R4 | leaf 与 item 的分工 | a. leaf 只带 `item_ref + op + threshold`（本文）<br>b. leaf 内联 metric/quantifier/window | **a**——24 条件型复用；内联则口径分裂（check12 病根复发） |
| R5 | 量纲归属 | a. 单位/口径在 metric 层单点，leaf 只存 `{value, format}`（本文）<br>b. leaf 带单位字段 | **a**——单位字段出现在两处 = 量纲 lint 失效（IPO-03 的 2.5 亿写成 2.5 即此类） |
| R6 | lint 形态 | a. pydantic 加载断言（坏配置起不来）+ CLI `lint` 子命令<br>b. 独立后校验脚本 | **a**——加载即校验，不存在「带病运行」窗口期；CLI 入口供 CI/校准流程用 |

R2 是唯一动已拍板文档的项（ADR-0002 需补勘误注）；R4/R5 是同一条原则（单点定义）在两个实体的应用；R1/R3/R6 无争议。
