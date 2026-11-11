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
| D7 | 系统架构与阶段 | 三域八模块（离线规则生产 M1~M2 / 在线测评 M3~M5 / 出口交互 M6~M7，可选 M8 midas 桥）；单向数据流，`rulebook/` YAML 唯一权威源。伞形路线 设计 0004→0005→0006 已走完：**设计收官（2026-11-10）**，实现期按 A6 顺序启动（时点随 #7 拍板）。**收官 tag：`design-complete`**（落在评审处置提交 `85a1f3f` 之后）。见 [设计 0004](docs/design/0004-system-architecture.md) |

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
| #6 | 维度评分 | **反转**（原「关闭·删除计分」）→ **部分恢复**：恢复量化展示，形态 = **进度 + 覆盖率**双指标；**不恢复总分 / 维度分聚合**；判定与展示分离 | [ADR-0007](docs/adr/0007-progress-and-coverage-metrics.md) |

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

### 2.4 系统架构拍板（2026-11-10，A1~A6 全部按推荐）

三域八模块（离线规则生产 / 在线测评 / 出口交互，可选 M8 midas 桥）；层①②③ = 引擎内置后置阶段；CLI v1 三命令（lint / calibrate / eval）；输出单文件 result.json（narrative_handoff 内嵌）；M8 桥 v1 缓办；实现期顺序 M3 → M4/M5 → M1 全量 → 边界族回归 →（可选）M8（启动待收官，与 #7 一并）。方案：[设计 0004](docs/design/0004-system-architecture.md)。

### 2.5 引擎运行时与公式语义拍板（2026-11-10，E1~E8 全部按推荐；E9 见 §2.8）

五节点责任链（Init/Fetch/Calc/Fold/Result；facts 在 Fold 出口冻结；Fetch 先于 Calc）；窗口 token 单点解析（不足/断年→indeterminate 不缩窗、stub 不进窗口、与 L2 渲染器同源）；缺数三原则（叶级隔离 / 无静默回退 null 永不进比较 / 审计覆盖降级）+ measures 逐年孰低（扣非缺→整叶 indeterminate）；六量词公式表 + 差距三分列；折叠 **Kleene 双规则（勘误 0001 §2.3「同规则」表述）**；帕累托算全部适用套、推荐 = 前沿 ∩ 过闸套；window_roll 分量词公式 + 风险倍数 k 配置（缺省 2）、growth 两点情景（**ADR-0004 残点关闭**）；整数元 + float64 无 ε。方案：[设计 0005](docs/design/0005-engine-runtime-and-formula-semantics.md)；决策：[ADR-0006](docs/adr/0006-engine-runtime-and-formula-semantics.md)。**E9（进度与覆盖率，第六个语义单点）见 §2.8 / [ADR-0007](docs/adr/0007-progress-and-coverage-metrics.md)。**

### 2.6 mock 数据契约拍板（2026-11-10，F1~F6 全部按推荐）——**系统设计收官**

单文件 profile.json（statements 内嵌，整数元）+ expected golden（只锁语义敏感点、绑 rulebook_version）；字段全集覆盖 7 metric 与 24 条件型；勾稽七条映射进 fixtures loader（引擎与测试共用），⑥ 区间参数化（净利 (−90%, +300%)）；±ε 边界族 + knockout 缺数族测试期动态生成；v1 清单 = base_co_2029 + qualified_audit + 两生成器族。0001 附录 A 两处矛盾处置（研发 7000 万实算 4.375%、净利区间放宽，勘误注二）。**伞形三步（0004 A1~A6 / 0005 E1~E9 / 0006 F1~F6）决策全部拍板、0004 §2 映射表全覆盖——设计阶段收官，进入实现期（A6 顺序，启动时点随 #7 拍板）。**方案：[设计 0006](docs/design/0006-mock-data-contract.md)。

### 2.7 工程细节拍板（2026-11-10，E1~E5 全部按推荐）——**实现期启动**

Python 3.10（保持兼容）；不引入 uv；CLI 保持 `-m` 模块调用；pytest 根目录 `tests/`；`results/` 不入 git。**实现期按 A6 顺序即刻启动：M3 fixtures → M4/M5 引擎（样板套端到端）→ M1 校准管线跑全量 43 套 → 边界族回归**。方案：[设计 0008](docs/design/0008-engineering-details.md)。

### 2.8 进度与覆盖率拍板（2026-11-10，E9 / P1~P6 全部按推荐）——**首次反转已拍板决策**

用户复盘时提出：全删量化指标使页面只剩文字判断，体验偏弱；midas 的「100 分才算通过」是对的，但**不同项的权重应该不一样，而权重没有可参考的数据来源**。

**处置**：不引入权重表——权重进判定是改法律语义（「均须满足」变「加权满足」），进展示是无来源装饰（不可复算、变化不可预测 → 退化为心情件）。故**恢复量化展示但换构造**：形态 = **进度 + 覆盖率**双指标，判定与展示分离。

| 项 | 拍板 |
|---|---|
| **P1** | 恢复量化指标，形态 = 进度 + 覆盖率（**必须成对**，单出进度无法区分「接近达标」与「大部分没数据」） |
| **P2** | 套级聚合 **min**——与 Kleene AND 同源，`progress = 100% ⟺ 套 met`；分数即卡点差距，不被易过项稀释、不随已过项波动（均值门也不破，四病在门内数字：不指路 / 稀释 / 假涨 / null 定价，见 [ADR-0007](docs/adr/0007-progress-and-coverage-metrics.md)） |
| **P3** | **不恢复总分**；维度仅作 UI 分组展示，不聚合、不进判定、不进 narrative |
| **P4** | **不引入权重表**（论证见上） |
| **P5** | 补**次弱约束**——min 的颗粒度补强，回答「补完这个下一个是谁」 |
| **P6** | `coverage < 100%` **硬禁**「可达标 / 预计能过」表述，进度限定为「已评估部分」 |

**反转记录**：#6「维度评分·关闭（删除计分）」→ 部分恢复（**不恢复总分**；#6 原判据「避免恢复 midas 式总分」仍成立）；设计 0001 A5 同。**midas 的「100 才通过」本身被保留**——它是 AND 约束的正确表达，问题从来不在那道门，而在门旁挂的那个数。

落点：[ADR-0007](docs/adr/0007-progress-and-coverage-metrics.md)（决策） / [设计 0005 §5.2](docs/design/0005-engine-runtime-and-formula-semantics.md)（**第六个语义单点**：进度与覆盖率） / [设计 0004 §6.1](docs/design/0004-system-architecture.md)（出口字段） / [设计 0006 §6.1](docs/design/0006-mock-data-contract.md)（golden 期望值） / [设计 0007 §3.1](docs/design/0007-ui-prototype.md)（视觉规范）。

## 3. 契约 v0.2 骨架

> 字段级全集以 [设计 0001](docs/design/0001-top-down-redesign.md) §1~§5 为底稿；实现时由 pydantic 固化。本文记顶层结构与关键变更。

### 3.1 顶层

```
run       # 坐标：(E, as_of_date, report_period{fiscal_years, stub?, audit_status,
          #   audit_opinion}, applicant_profile, target) + applied_rule_versions[]
facts     # metric_definitions(最小) / drivers[] / items[] / checks[] / sets[](group+branch)
layers    # gap（差距画像 + scenario：growth / window_roll）
          #   每套含 progress / coverage / binding_clause_id / next_binding_clause_id
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
| **layers.gap.sets[]** | （无量化展示） | **每套增 progress（0~100, min 聚合）/ coverage（0~100）/ binding_clause_id / next_binding_clause_id**——恢复量化展示但**不恢复总分**；判定与展示分离，跨套排序不合法 |
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
10. **量化指标（E9）**：progress 与 coverage 必须成对出现；`progress = 100 ⟺ 套 met`（无未定义叶时）；未定义叶（indeterminate / needs_review）**不进 progress 聚合、只进 coverage 分母**；coverage < 100 时输出侧禁用「可达标」类表述；progress **不进 narrative**；**不引入权重表**。

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

> 阶段注记（2026-11-10 更新）：**系统设计已收官**——伞形三步（设计 0004 A1~A6 / 0005 E1~E9 / 0006 F1~F6）全部拍板，0004 §2 模块↔设计映射表全覆盖。**收官 tag：`design-complete`**。实现期按 A6 顺序启动（M3 fixtures → M4/M5 引擎 → M1 全量 43 套 → 边界族回归），启动时点随 #7 拍板确认；#3 的 trace_check / 全量铺开、#5 的管线实现均属实现期工作。
>
> **M3 已落地（2026-11-11，`edd47de` + 生成器族补齐）**：fixtures loader（勾稽①~⑥ + 跨表同源断言，**#9-V11 就此关闭**）+ 甲公司 / qualified_audit 样本 + golden（含 E9 期望值，另有 golden↔规则库实物 ID 守卫测试）+ ±ε 边界族 / knockout 缺数族两生成器（F5/F6：读规则库阈值动态生成；数值改动沿勾稽网络传播保持变体可加载；latest 量词用全序列等比缩放保同比轨迹——直改单年会让 thr 距 base 较远的叶撞穿 ⑥ 区间，如 rev_latest 6.8 亿→1 亿）。M3 域测试 38 绿。下一步 M4/M5 样板套端到端，首个回归用例 = 甲公司自检链（golden 的 key_checks / progress / window_roll）。

| 编号 | 内容 | 状态 |
|---|---|---|
| #2 | mock 数据契约 CompanyProfile 字段全集 | **关闭**（[设计 0006](docs/design/0006-mock-data-contract.md) F1~F6 拍板 2026-11-10 全部按推荐；0001 附录 A 两处矛盾已处置（研发 7000 万实算 4.375%、净利区间放宽）；甲公司定稿数值表（0006 §5）为全链回归基准） |
| #3 | 规则库 YAML schema | **进行中**（[设计 0002](docs/design/0002-rulebook-yaml-schema.md) R1~R6 已按推荐拍板；已落地：pydantic 模型+loader+CLI——加载期 lint L1~L6 即 [设计 0003](docs/design/0003-calibration-pipeline.md) L0 闸门的运行时形态，`_meta/metrics/items` 全量、法条样板×3、样板套×2（branch 择一 / clause any collapse），12 测试绿；待：`trace_check.py` 对拍 + 全量 43 group 铺开（随 #5 管线产出）） |
| #4 | 公式引擎边界语义（对齐 `FormulaFactory`） | **关闭**（[设计 0005](docs/design/0005-engine-runtime-and-formula-semantics.md) E1~E9 拍板 2026-11-10 全部按推荐；[ADR-0006](docs/adr/0006-engine-runtime-and-formula-semantics.md) + [ADR-0007](docs/adr/0007-progress-and-coverage-metrics.md)）。G-B 兑现：窗口 / 缺数 / 量词 / 折叠语义全部单点；0001 §2.3 已加勘误注——折叠 Kleene 双规则；**E9 增进度与覆盖率第六个语义单点**） |
| #5 | 校准工作流 | **方案已定**（[设计 0003](docs/design/0003-calibration-pipeline.md)，R1~R11 拍板；D4 修订见 [ADR-0005](docs/adr/0005-ai-assisted-calibration.md)），待实现。底稿：calibration/0001；待核：码值映射、表决权差异门槛、法条来源；注记 **G-C** 红筹「市值」叶 mock 无数据源→indeterminate、**G-D** IPO-41~61 板块匹配 21 套→段②逐套映射 |
| #7 | 工程细节（Python 3.12 / uv / CLI / pytest） | **关闭**（[设计 0008](docs/design/0008-engineering-details.md) E1~E5 拍板 2026-11-10 全部按推荐：Python 3.10 / 不引入 uv / `-m` CLI / 根目录 tests / results 不入 git；实现期按 A6 顺序即刻启动） |
| #8 | agent 技能：IPO 评测技能封装（v0 手册模式→v1 CLI 薄封装，S1~S4 草案 2026-11-10） | **搁置**（用户指示；实现期随引擎再启） |
| #9 | 评审 0004 的 P2 缺口（V6~V17）待实现期消化 | **待**：V6 as_of 生效过滤（loader 缺 as_of 参数，`effective_from` 从不参与过滤）、V7 同行比 item 缺失（`check07` 无 item 挂载）、V8 法规原文库 `source_texts/` 不存在（M1 前置子项）、V9 勾稽② 起算口径（应用净利润总额而非归母）、V10 `total_shares_after_ipo` 字段、~~V11 两处净资产跨表一致性~~（**已由 M3 fixtures loader 关闭**：勾稽③ 断言 equity_roll 期末归母 = 资产负债表归母，2026-11-11）、V12 run 级 vs 逐年审计字段关系、V13 未审计年度样本、V14 M2 状态拆「schema 定稿/数据待铺」、V15 pyproject pytest 移 dev、V16 target 语义表述、~~V17 UI 筛选粒度标注~~（**已由 UI v0.4 关闭**：筛选已改五态细分，见 [评审 0005](docs/reviews/0005-ui-interaction-professional-review.md) U3；遗留「跨列口径（任一命中 vs 全部命中）无切换」转 UI 后续迭代） |

## 6. 参考锚点

- 设计底稿（v0.2 契约来源）：[docs/design/0001-top-down-redesign.md](docs/design/0001-top-down-redesign.md)；规则库 schema（#3）：[docs/design/0002-rulebook-yaml-schema.md](docs/design/0002-rulebook-yaml-schema.md)；校准管线（#5）：[docs/design/0003-calibration-pipeline.md](docs/design/0003-calibration-pipeline.md)；系统总体架构（A1~A6 拍板）：[docs/design/0004-system-architecture.md](docs/design/0004-system-architecture.md)；引擎运行时与公式语义（#4 已关闭，E1~E9 拍板）：[docs/design/0005-engine-runtime-and-formula-semantics.md](docs/design/0005-engine-runtime-and-formula-semantics.md)；mock 数据契约（#2 已关闭，F1~F6 拍板）：[docs/design/0006-mock-data-contract.md](docs/design/0006-mock-data-contract.md)；工程细节（#7 已关闭，E1~E5 拍板）：[docs/design/0008-engineering-details.md](docs/design/0008-engineering-details.md)；交互原型（UI v0.5，P1~P4 拍板 2026-11-10；v0.5 增量化指标视觉规范 / E9）：[docs/design/0007-ui-prototype.md](docs/design/0007-ui-prototype.md) / [ui/prototype.html](ui/prototype.html)
- 套归组与校准底稿：[docs/calibration/0001-set-inventory.md](docs/calibration/0001-set-inventory.md)
- 评审：[0001 F5-R](docs/reviews/0001-gap-layer-design-review.md) / [0002 专业审计](docs/reviews/0002-professional-gap-audit.md) / [0003 需求评估](docs/reviews/0003-requirement-assessment.md) / [0004 系统整体设计复核](docs/reviews/0004-system-design-review.md)（P0×1 CAGR 公式方向——已修 + ADR-0006 勘误；P1×4 已修：`_meta` 形态 / 甲公司数值收敛 / UI 影子规则库 / 归因 5×3；P2×4 转 #9）/ [0005 交互原型专业性复核](docs/reviews/0005-ui-interaction-professional-review.md)（P0×1 板块定位「业务判不了 vs 工程没做」混同——已修并新增 `.pill-e` 工程态；P1×6 + P2×7 + P3×3，其中 10 项可执行改进已在 UI v0.4 全部落地；**P9 = A，2026-11-11**：U4 result.json 下载按钮连同「导出叙述 handoff」经拍板撤销移除——工程演示不进用户故事，UI v0.5.1；尾项 3 条转实现期）
- ADR：[0001 facts 双层](docs/adr/0001-facts-layer-granularity.md) / [0002 套建模](docs/adr/0002-set-modeling-three-segments.md) / [0003 口径与五态](docs/adr/0003-metrics-and-five-states.md) / [0004 差距画像](docs/adr/0004-gap-profile-and-scenarios.md) / [0005 AI 辅助校准](docs/adr/0005-ai-assisted-calibration.md) / [0006 引擎运行时与公式语义](docs/adr/0006-engine-runtime-and-formula-semantics.md) / [0007 进度与覆盖率双指标](docs/adr/0007-progress-and-coverage-metrics.md)（**反转 #6 / 0001 A5**：恢复量化展示 = 进度 + 覆盖率双指标，min 聚合与 AND 判定同源，无权重表，判定与展示分离）
- midas 代码地图：[docs/midas-code-map.md](docs/midas-code-map.md)；源码锚点：`ResultEvalServiceImpl`（isSatisfied/diff）、`CAGRFormula`、`IpoFormulaCalcService`（仓库 `E:\yonyouProject\midas`，只读对照）
- 原始材料归档（2026-11-10）：[raw/req_docx_20261110](raw/req_docx_20261110)（需求 docx 原件+全文提取）/ [raw/preset_xlsx_20261110](raw/preset_xlsx_20261110)（预置数据底稿原件+核心表导出；与 DB 快照冲突时以快照为准，已知笔误见 calibration/0001 §3-4）
