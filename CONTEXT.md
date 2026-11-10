# CONTEXT：ipo-eval-lab

> 本项目**决策与契约的单一入口**。
> **v0.2（2026-11-10）**：按 [设计 0001](docs/design/0001-top-down-redesign.md)（P1~P8 拍板）整体替换 v0.1；v0.1 已冻结于 git tag `context-v0.1`。HANDOFF.md 已删除（吸收完毕）。

## 1. 项目定位与边界

| # | 决策 | 内容 |
|---|------|------|
| D1 | 定位 | 本地个人实验项目；企业数据 = mock（只消费本地文件，采集不在范围） |
| D2 | 技术栈 | Python：pydantic 契约 + YAML 规则库 + CLI；代码不复用 midas，只复用设计语义 |
| D3 | AI 接入 | 项目内零 AI 依赖。引擎输出结构化结果 JSON；第四层叙述报告由外部 agent 读 JSON 生成，LLM 只叙述、不碰计算 |
| D4 | 标准校准 | 权威源链：**法规原文（authority）→ 规则库 YAML（校准）→ midas 快照（trace）**；上市标准套为一等公民（group/branch 层级）。2026-11-10 修订：校准 = AI 辅助提取 + 三道异构闸门 + 人工签核（[ADR-0005](docs/adr/0005-ai-assisted-calibration.md) / [设计 0003](docs/design/0003-calibration-pipeline.md)） |
| D5 | 测评链 | 复用 midas 责任链模式：Init→Calc→Fetch→Result 四节点 + Context 有序遍历；公式语义对齐 `FormulaFactory` |
| D6 | 结果分析 | 四层：①差距画像（含 window_roll 情景）②路径（hard gate → 帕累托）③归因（可核验性 × 实质障碍，正交）→ 前三层纯规则；④叙述报告（agent，带免责与禁令） |

## 2. 决策历史

### 2.1 v0.1 决策的处置

| # | v0.1 决策 | 处置 | 落点 |
|---|---|---|---|
| R1 | L4 契约边界 | 保留；narrative_handoff 扩充 disclaimers/forbidden_claims | 本版 §3 |
| R2 | facts 双层 | 保留 + 修订（measures[] / 五态 / drivers[] / nature） | [ADR-0001 Amendment 1](docs/adr/0001-facts-layer-granularity.md) |
| R3 | 三态 | **推翻 → 五态**（动机：修复 midas `null→0` 与无 `not_applicable` 的语义合流，`ResultEvalServiceImpl.java:149`；**非**推翻其"100 分门"布尔形状——勘误见 [0002 文末](docs/reviews/0002-professional-gap-audit.md)） | [ADR-0003](docs/adr/0003-metrics-and-five-states.md) |
| R4 | diff/gap_ratio | 部分保留：数值项保留；计数/布尔分列；禁跨项聚合 | ADR-0003 |
| F5 | eta 口径 | **关闭**（差距画像 + 情景推演） | [ADR-0004](docs/adr/0004-gap-profile-and-scenarios.md) |
| F6 | distance 度量 | **关闭**（帕累托四轴替代单标量） | ADR-0004 |
| #6 | 维度评分 | **关闭**（删除计分） | 设计 0001 A5 |

### 2.2 本轮拍板（2026-11-10，全部按推荐）

| # | 内容 |
|---|---|
| P1 | item 宇宙按**条件型**重建（24 种：21 定量 + 3 定性），`check01~61` 降为 alias |
| P2 | 固定三段树（AND(发行条件, 板块定位, OR(套))），不建通用表达式引擎 |
| P3 | judgment 项：不进层② hard gate，但计入套终态 indeterminate，输出 pending_evidence |
| P4 | 套级时间区间仅对无 act/adjust 阻塞叶的套给，一律 is_forecast |
| P5 | 种子数据修正（185/64/234/63；非笛卡尔积；红筹/表决权专套真实存在）接受为记录 |
| P6 | ADR 编号：0002 套建模 / 0003 口径与五态 / 0004 差距画像 |
| P7 | 套内 OR 建模：group（官方套）+ branch（支路）+ clause logic + 共享条文不变量 |
| P8 | window_roll 情景进 v1（进入年所需值，确定性、零增长率假设） |

### 2.3 校准管线拍板（2026-11-10，R1~R11 全部按推荐）

「同模型三次投票」重构为**三道异构闸门**（L0 确定性 / L1 提取+锚点 / L2 回译）+ L3 快照对照 + 两级入库（机器 → 候选库；人工签核 → 正式库）；item 级隔离不中止批次；置信度由可验证事实合成并在黄金集上校准。方案：[设计 0003](docs/design/0003-calibration-pipeline.md)；决策：[ADR-0005](docs/adr/0005-ai-assisted-calibration.md)。

## 3. 契约 v0.2 骨架

> 字段级全集以 [设计 0001](docs/design/0001-top-down-redesign.md) §1~§5 为底稿；实现时由 pydantic 固化。本文记顶层结构与关键变更。

### 3.1 顶层

```
run       # 坐标：(E, as_of_date, report_period{fiscal_years, stub?, audit_status,
          #   audit_opinion}, applicant_profile, target) + applied_rule_versions[]
facts     # metric_definitions(最小) / drivers[] / items[] / checks[] / sets[](group+branch)
layers    # gap（差距画像 + scenario：growth / window_roll）
          # path（hard gate → 帕累托四轴） / attribution（verifiability × substantive_obstacle）
narrative_handoff  # units[] + citation_index + disclaimers[] + forbidden_claims[]
```

### 3.2 关键变更 vs v0.1

| 对象 | v0.1 | v0.2 |
|---|---|---|
| run 坐标 | company/report_period 占位 | as_of_date + 审计口径四字段 + applicant_profile + applied_rule_versions[] |
| items | check01~61 单值 measurement | 按条件型重建；measures[]（扣非 × 审计，默认归母）；nature × basis 判定矩阵；lever / driver_ids |
| checks | 三态、单 op | 五态；scope ∈ {issuance, positioning, set}；量词六值；差距三分列（diff / required_delta / required_action） |
| sets | 64 组合平铺 | group（官方套 43）+ branch（支路，挂 set_id）；applicability 谓词（等值/枚举/in_list）；删 pass_ratio |
| layers.gap | eta 单点年数 | 差距画像 + scenario（growth 区间 / window_roll 进入年所需值） |
| layers.path | distance 单标量排序 | hard gate 筛选 → 帕累托四轴（含 data_uncertainty）；recommendation/alternatives/excluded |
| layers.attribution | cause 单字段 | verifiability × substantive_obstacle 正交 |
| narrative | 无免责 | disclaimers[]（含三条固定边界）+ forbidden_claims[] |

### 3.3 契约不变量（v0.2）

1. 引用完整：check.item_id ∈ items；check.set_id ∈ sets；set 成员 ⊆ items。
2. 计数守恒：五态计数之和 == 适用项数（not_applicable 单列，不计入分母）。
3. not_met 数值叶必有 diff/gap_ratio 与非空 evidence；计数叶用 required_delta；布尔叶用 required_action。
4. 各层只存 id 引用；层内不得出现 measurement 值。
5. narrative 数字必带 refs。
6. 同 group_no 各 branch 必须共享公共条文（违者为转写噪音旗标，交校准 #5）。
7. nature=judgment 的 check 状态只能为 needs_review（永不 met），且带 pending_evidence。
8. grow 项必须映射到已存在 driver；套级时间区间仅当套内无 act/adjust 阻塞叶。
9. window_roll 的 required_entering_year_value 必须可由「阈值 − 窗口剩余年值合计」复算。

约定：百分比存小数；金额存元；实测与阈值同量纲（`suffix` 仅展示）。

## 4. 种子数据（2026-11-09 快照，全量复核修正）

| 对象 | 数量 | 说明 |
|---|---|---|
| 规则原文条文 | 185 | `mt_ipo_listing_standard` |
| 套条目 | 64 | 含 21 处「或」支路拆行 |
| **官方套（group）** | **43**（沪深同文合并 34） | 归组与证据：[calibration/0001](docs/calibration/0001-set-inventory.md) |
| 阈值 | 234 | op/format 码值映射待校准 |
| 规则包 | 63 | midas standardId（非套，仅 trace） |
| UI 测评项 | 61 | 32 项底稿自填；重建后降为 alias |
| 条文条件型 | 24 | 21 定量 + 3 定性（item 宇宙依据） |

已知校准发现：主板 sort3「市值≥350亿」为笔误（应为 50亿）；快照反映 2026-04 修订后规则；科创板/创业板表决权差异门槛疑为旧值。

## 5. 未决问题

| 编号 | 内容 | 状态 |
|---|---|---|
| #2 | mock 数据契约 CompanyProfile 字段全集 | 待（骨架：设计 0001 §4——七条勾稽 + 边界族 ±ε） |
| #3 | 规则库 YAML schema | **进行中**（草案：[设计 0002](docs/design/0002-rulebook-yaml-schema.md)；骨架：group/branch/clause/leaf + 条文库 + applicability + effective_from；新增输入 **G-A** lint 五条——量纲一致/组合覆盖+空集报错/每套≥1条文/引用完整/窗口不重述，源自评审 0003 需求侧事故反推） |
| #4 | 公式引擎边界语义（对齐 `FormulaFactory`） | 待（**G-B**：优先级上升——midas check04/11 证明窗口语义无单一定义点必然产生矛盾配置；窗口抽象（window token）随 #3 schema 收敛，引擎语义单点实现） |
| #5 | 校准工作流 | **方案已定**（[设计 0003](docs/design/0003-calibration-pipeline.md)，R1~R11 拍板；D4 修订见 [ADR-0005](docs/adr/0005-ai-assisted-calibration.md)），待实现。底稿：calibration/0001；待核：码值映射、表决权差异门槛、法条来源；注记 **G-C** 红筹「市值」叶 mock 无数据源→indeterminate、**G-D** IPO-41~61 板块匹配 21 套→段②逐套映射 |
| #7 | 工程细节（Python 3.12 / uv / CLI / pytest） | 待 |

## 6. 参考锚点

- 设计底稿（v0.2 契约来源）：[docs/design/0001-top-down-redesign.md](docs/design/0001-top-down-redesign.md)；规则库 schema（#3）：[docs/design/0002-rulebook-yaml-schema.md](docs/design/0002-rulebook-yaml-schema.md)；校准管线（#5）：[docs/design/0003-calibration-pipeline.md](docs/design/0003-calibration-pipeline.md)
- 套归组与校准底稿：[docs/calibration/0001-set-inventory.md](docs/calibration/0001-set-inventory.md)
- 评审：[0001 F5-R](docs/reviews/0001-gap-layer-design-review.md) / [0002 专业审计](docs/reviews/0002-professional-gap-audit.md) / [0003 需求评估](docs/reviews/0003-requirement-assessment.md)
- ADR：[0001 facts 双层](docs/adr/0001-facts-layer-granularity.md) / [0002 套建模](docs/adr/0002-set-modeling-three-segments.md) / [0003 口径与五态](docs/adr/0003-metrics-and-five-states.md) / [0004 差距画像](docs/adr/0004-gap-profile-and-scenarios.md) / [0005 AI 辅助校准](docs/adr/0005-ai-assisted-calibration.md)
- midas 代码地图：[docs/midas-code-map.md](docs/midas-code-map.md)；源码锚点：`ResultEvalServiceImpl`（isSatisfied/diff）、`CAGRFormula`、`IpoFormulaCalcService`（仓库 `E:\yonyouProject\midas`，只读对照）
- 原始材料归档（2026-11-10）：[raw/req_docx_20261110](raw/req_docx_20261110)（需求 docx 原件+全文提取）/ [raw/preset_xlsx_20261110](raw/preset_xlsx_20261110)（预置数据底稿原件+核心表导出；与 DB 快照冲突时以快照为准，已知笔误见 calibration/0001 §3-4）
