# 设计 0004：系统总体架构

- 日期：2026-11-10
- 性质：**伞形收官第 ① 步**——模块划分、端到端数据流、一次测评的运行时序、模块↔设计映射表；阶段切换（设计先行、实现冻结）后的首份产出
- 输入：[设计 0001](0001-top-down-redesign.md)（契约 v0.2 与判定语义）、[设计 0002](0002-rulebook-yaml-schema.md)（规则库 schema）、[设计 0003](0003-calibration-pipeline.md)（校准管线）、CONTEXT D1~D6
- 决策点：A1~A6（§8，**2026-11-10 已拍板：全部按推荐**）。编号前缀 **A**（Architecture），与设计 0001 的 P、设计 0002/0003 的 R 区分；引用带文档号（如「设计 0004-A2」）
- **v0.2（2026-11-10）**：§6.1 增补量化指标字段（progress / coverage / binding_clause_id / next_binding_clause_id）——对应设计 0005 E9 / [ADR-0007](adr/0007-progress-and-coverage-metrics.md)，**恢复量化展示但反转 0001 A5 与 CONTEXT #6**；§2 映射表 M4/M5 状态同步。

---

## 0. 为什么需要这份文档

已有三份设计是三个**局部**：0001 管输出长什么样，0002 管规则数据长什么样，0003 管规则数据怎么生产。三者拼装关系从未显式定义：

- 引擎消费规则库的**哪个面**（pydantic 对象？YAML 原文？）、企业数据从**哪个口**进入？
- 校准管线的三态产物（候选库 / 人工队列 / 正式库）放仓库哪里、谁有写权限？
- 叙述报告的边界文件是什么，外部 agent 到底拿到什么？

本文画「整台机器的装配图」。**收官判据**（上轮 P3）：本文 §2 的模块↔设计映射表全覆盖 + CONTEXT §5 设计类未决清零（仅剩 #7）→ 系统设计收官，进入实现期。

## 1. 架构原则（AR1~AR5）

| # | 原则 | 白话 |
|---|---|---|
| AR1 | **单向数据流**：离线产规则 → 在线只读消费 | 测评运行时绝不反向改规则库；规则变更只能走校准管线 → 签核 → 正式库 |
| AR2 | **运行期零 AI、纯确定性** | 同一（企业数据， 规则版本， run 坐标）进去，字节级同一结果出来；AI 只存在于离线校准（M1）和项目外叙述 agent |
| AR3 | **引擎零规则知识** | 阈值 / 窗口 / 套结构全部来自规则库；引擎只实现 26 个 item 的**语义**（怎么比、怎么聚合、怎么折叠）。引擎里写死任何阈值都是 bug |
| AR4 | **断言前置，fail fast** | 规则库加载期 lint（设计 0002 L1~L6）、企业数据加载期勾稽断言（设计 0001 §4 七条）——坏输入起不了 run，不带病出数 |
| AR5 | **facts 唯一事实源** | 每个数字只在 facts 出现一次；层①②③只存 id 引用（契约不变量 4）；叙述只复述带 refs 的数字（不变量 5） |

## 2. 三域八模块（A1）

| 域 | 模块 | 职责一句话 | 设计来源 | 状态 |
|---|---|---|---|---|
| 离线·规则生产 | **M1** 原文库 + 校准管线 | 法规原文 → 规则库 YAML 实例（副产品：midas 差异清单） | [设计 0003](0003-calibration-pipeline.md) | 方案定稿（R1~R11），实现待 |
| | **M2** 规则库（schema + 加载） | 规则数据形态 + 加载期 lint（= 设计 0003 L0 运行时形态） | [设计 0002](0002-rulebook-yaml-schema.md) | 定稿（R1~R6）；样板已验证（c68d02e，冻结） |
| 在线·测评 | **M3** 企业数据契约 | CompanyProfile / 三表 / expected golden / ±ε 边界族（mock） | **设计 0006** | 草案待拍板（F1~F6） |
| | **M4** 测评引擎 | 适用性 → 取数 → 叶判定 → 折叠 → 板块结论（含 #4 公式边界语义） | **设计 0005** | 定稿（E1~E9 拍板 2026-11-10） |
| | **M5** 分层计算 | 层①差距画像（含 scenario + 进度/覆盖率）/ 层②路径（hard gate→帕累托）/ 层③归因 | 设计 0005 §5.2/§6~§7 | 定稿（E1~E9 拍板 2026-11-10） |
| 出口·交互 | **M6** 叙述交接 | narrative_handoff（units / citation_index / disclaimers / forbidden_claims）随结果输出 | 设计 0001 §5.2；文件边界本文 §6 | 契约已定 |
| | **M7** CLI | 三命令用户面（本文 §5） | 本文 | 本文定 |
| 桥（可选） | **M8** midas 反向桥 | YAML → midas 预置表导出（投影视图） | 设计 0003 §11.3 | v1 缓（A5） |

> 层①②③是 M4 的后置阶段还是独立模块 → A2；M8 做不做 → A5。

## 3. 端到端数据流

```
【离线域 · 规则生产】（产出进 git，版本即规则版本）
法规原文库(source_texts/) ─► M1 校准管线(L0~L3) ─► 候选库(candidates/) ─人工签核─► 正式库(rulebook/)
        │                            │                  │
        │                            │                  └─ 任一闸门红 → 人工队列(review-queue/, evidence pack)
        │                            └─ L3 副产品：midas 存量差异清单（数据治理输出）
        └─ 版本元数据(文档名/生效日/条款号)                              │
                                                                    （可选）M8 桥：导出 midas 预置表
【在线域 · 一次测评 run】（只读）
rulebook/ ─► M2 加载+lint(as_of 过滤) ─┐
fixtures/companies/ ─► M3 加载+勾稽断言 ┴─► M4 引擎(适用性→取数→叶判定→折叠) ─► M5 分层①②③
                                                                          │
                                                                          ▼
                                                 result.json（契约 v0.2 全量 + narrative_handoff）
                                                                          │
【出口域】                                                  外部叙述 agent（项目外，D3）──► 叙述报告
```

要点：

- **三库一桥**：原文库（输入）→ 候选库（机器可写）→ 人工队列（签核工作台）→ 正式库（唯一被引擎加载）。正式库进 git，`rulebook_version` 即规则版本；M8 把正式库**投影**成 midas 预置表，midas 表永不回写（AR1）。
- **版本链**：`as_of_date` × `effective_from` 过滤 → 结果回写 `applied_rule_versions[]`——历史结果按当次规则版本冻结展示（设计 0003-R6）。
- **可追溯链**：结果里每个阈值判定 → item → metric → `law_ref = law_id#article` 引文（设计 0002 evidence 结构），叙述层引用直达法条。

## 4. 一次测评的十步运行时序（M4/M5 内部）

| 步 | 名称 | 干什么 | 主要输入→输出 |
|---|---|---|---|
| ① | 坐标装配 | CLI 参数 → run 坐标（E, as_of, report_period, target）；target 缺省 = 全部适用套 | 参数 → `run.input` |
| ② | 规则加载 | loader 按 as_of 过滤生效区间，全量 lint 通过才继续 | rulebook/ → `Rulebook` + `applied_rule_versions` |
| ③ | 企业数据加载 | profile + statements，七条勾稽断言全过才继续 | fixtures/ → `CompanyProfile`（已验证） |
| ④ | 适用性判定 | applicant_profile × applicability 谓词（等值/枚举/in_list 合取） | 套全集 → 适用集 + not_applicable 集（出分母、留事实层） |
| ⑤ | facts 构建 | 三表 → drivers / metrics（measures 两维：扣非 × 审计）/ items 实测 | statements → `facts.*` |
| ⑥ | 叶判定 | 26 item 语义：quantifier × window → 期间集合 → op(threshold) → 五态；缺数→indeterminate，judgment→needs_review+pending_evidence | facts + 规则库叶 → `facts.checks[]` |
| ⑦ | 折叠 | clause(logic) → branch → group → 段③ OR(套) → 三段 AND → 板块结论；五态折叠规则见设计 0001 §2.3 | checks → `facts.sets[].outcome` |
| ⑧ | 层①差距画像 | 逐套 blockers（叶级 not_met/indeterminate + diff 三分列）；scenario：growth / window_roll（确定性重算） | facts → `layers.gap` |
| ⑨ | 层②③ | hard gate 筛选 → 帕累托四轴 → recommendation/alternatives/excluded；归因 verifiability × substantive_obstacle | facts+gap → `layers.path/attribution` |
| ⑩ | 出口 | 汇编契约 v0.2 全量 result JSON，内嵌 narrative_handoff | 全部 → `result.json` |

> 与 D5 的关系：**复用责任链模式**（有序节点遍历 + 共享 Context），不逐字照搬 midas 的 Init→Calc→Fetch→Result 顺序；十步如何归并为链上节点（倾向 ① ~ ④ 为 Init、⑤ Fetch、⑥ Calc、⑦ ~ ⑨ Result）随设计 0005 拍板。

**甲公司贯穿走查**（数字沿用设计 0001 附录 A：净利 1.5/0.3/0.4 亿，营收累计 16 亿，现金流累计 1.8 亿）：

| 步 | 甲公司身上发生什么 |
|---|---|
| ④ | 一般企业 → 红筹 / 表决权差异专套全部 `not_applicable`（出分母，结果里仍可见） |
| ⑥ | 主板第一套定量叶：三年均为正 ✓；累计 2.2 亿 ≥ 2 亿 ✓；**最近 1 年净利 0.4 亿 < 1 亿 ✗**（diff 0.6 亿）；现金流/营收条文（any）：1.8 亿 < 2 亿 ✗ 但 16 亿 ≥ 15 亿 ✓；定性叶 → needs_review + pending_evidence |
| ⑦ | 现金流条文因 any 择一而**满足**；但最近 1 年净利叶 not_met → AND 一票否决 → 第一套 `criteria_not_met`（不折算分数，直接终态） |
| ⑧ | blockers = [np_latest 差 0.6 亿]；window_roll：累计叶当前满足，但窗口滑出 1.5 亿后进入年需 ≥ 2.0 − 0.7 = **1.3 亿** vs 最近年实际 0.4 亿 → 滚动风险高 |
| ⑨ | 第一套含 not_met 硬叶 → 不进 recommendation，入 `excluded{reason}`；推荐空时报告以层①差距画像为主体——**工具宁可说清差在哪，不硬推一个套** |
| ⑩ | result.json + narrative_handoff（三条固定边界：段①抽样核查 / 甜区声明 / 市值自估） |

## 5. CLI 用户面（M7，A3）

v1 三命令。命令名是**逻辑面**；打包入口（console script vs `-m`）归 #7 实现期定（`python -m ipo_eval_lab.rulebook` 即命令 1 的现行形态，已随 c68d02e 冻结）。

| 命令 | 输入 | 输出 | 模块 |
|---|---|---|---|
| `rulebook lint [--strict]` | rulebook/ | 清单 + 警告/错误 + 退出码 | M2 |
| `calibrate run --source <dir> --as-of <date>` | 原文库 | candidates/ + review-queue/ + report.md | M1 |
| `eval run --company <id> --as-of <date> [--boards …] [--sets …] [--report <path>]` | rulebook/ + fixtures/companies/\<id\>/ | result.json + 终端摘要 | M3~M6 |

缺省约定：`--as-of` 缺省 = 当日（**写入 `run.as_of_date`**，可复算）；`--report` 缺省 = `results/<company>_<asof>.json`（results/ 是否入 git 归 #7）。不做 REPL、不做服务端。

## 6. 叙述交接边界（M6，A4）

- **输出物 = 单文件 result.json**：契约 v0.2 全量（run / facts / layers）+ 内嵌 `narrative_handoff{units[], citation_index, disclaimers[], forbidden_claims[]}`。
- **外部 agent 的全部输入就是这个 JSON**：自包含——agent 不需要读规则库或 fixtures 就能叙述；提示词模板与产出 md 不在本仓库 v1 范围（D3）。
- **保证**（引擎侧兑现）：所有数字带 refs（不变量 5）；措辞遵循 E6（criteria_met / criteria_not_met / indeterminate + 限定语）；forbidden_claims 硬约束随文件传递。

### 6.1 量化指标字段（v0.2 增补，E9）

层① 差距画像的**每套**增四个字段（计算语义见 [设计 0005 §5.2](0005-engine-runtime-and-formula-semantics.md)，论证见 [ADR-0007](adr/0007-progress-and-coverage-metrics.md)）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `progress` | 0~100 | 达标进度 = min 折叠的叶分数 × 100（与 AND 判定同源） |
| `coverage` | 0~100 | 数据完整度 = 可判叶数 / 适用叶总数 × 100 |
| `binding_clause_id` | str\|null | 卡点 clause（progress 最小者） |
| `next_binding_clause_id` | str\|null | 次弱 clause（补完卡点后的下一个） |

- **进度与覆盖率必须成对出现**——单出进度无法区分「接近达标」与「大部分没数据」。
- **进度不参与判定**，也不被判定反推；判定仍由硬叶决定（Kleene AND）。
- **不引入权重表**：`progress = 100% ⟺ 套 met`（无未定义叶时），与判定同源。
- **跨套排序不合法**（叶集不同 → 不可比）：跨套排序走层②帕累托四轴；进度只作**同套跨期自比较**。
- `coverage < 100` 时，硬禁「可达标 / 预计能过」表述，进度一律限定为「已评估部分」。
- 进度**不进 narrative**（叙述层不得表述为「得分高所以能过」）。

## 7. 仓库布局（静态资产落点）

```
ipo-eval-lab/
├─ rulebook/            # M2 正式库（唯一被引擎加载的规则源；git 即版本管理）
├─ source_texts/        # M1 原文库输入（法规原文 + 版本元数据）
├─ candidates/          # M1 候选库（机器可入，待签核）
├─ review-queue/        # M1 人工队列（evidence pack）
├─ fixtures/companies/  # M3（base_co_2029 / boundary_epsilon / qualified 样本 + expected）
├─ results/             # 测评输出（是否入库归 #7）
├─ ipo_eval_lab/
│  ├─ rulebook/         # M2 schema+loader（已落地，冻结）
│  ├─ calibrate/        # M1（实现期）
│  ├─ engine/           # M4/M5（实现期）
│  └─ cli.py            # M7（实现期）
├─ docs/                # 设计 / 评审 / ADR / 校准底稿
├─ raw/                 # 外部原始材料归档（只读）
└─ tests/
```

一眼校验 AR1：**运行侧只读 `rulebook/` + `fixtures/`；离线侧写 `candidates/` → 签核后写 `rulebook/`**；`raw/` 永不改。

## 8. 决策点（A1~A6）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| A1 | 模块划分 = 三域八模块（§2）；替代 = 按数据对象平铺不分域 | 三域八模块 / 平铺 | **三域八模块**——离线/在线/出口的责任边界正是 AR1 单向流的落点；平铺会让「谁能写规则库」这类权限问题无处安放 |
| A2 | 层①②③ = M4 引擎内置后置阶段（同进程同 run），不拆独立模块 | 内置 / 独立模块 | **内置**——本地 CLI 工具没有服务边界可拆；分层只读 facts（AR5），拆开只添接口成本。设计 0005 仍单列 §层计算以保持可读性 |
| A3 | CLI v1 = 三命令（lint / calibrate / eval），无 REPL 无服务端；as-of 缺省当日并写入 run | 此 / 更多 | **此**——v1 用户只有自己；as-of 显式入 run 才能复算 |
| A4 | 测评输出 = 单文件 result.json（narrative_handoff 内嵌），不出 handoff.md / 不拆多文件 | 单 JSON / 拆分 | **单 JSON**——agent 消费一个文件最不易漏读免责；叙述模板（md 形态）v2 随实践再定 |
| A5 | M8 midas 反向桥 v1 **不实现**，仅在架构图保留出口 | 缓 / v1 做 | **缓**——YAML 先当唯一权威源跑通全链；桥是纯投影，随时可加，先做反而要在规则内容铺开前维护两份格式 |
| A6 | （**收官后另拍板**，非本轮执行）实现期顺序建议：M3 mock → M4/M5 引擎（用样板套端到端跑通）→ M1 全量 43 套铺开 → 边界族回归 → (可选) M8 | 此序 / M1 先 | **此序**——引擎验证只需已存在的 2 个样板套 + 1 个 mock 公司，不被规则内容进度阻塞；全量铺开放最后，正好接校准管线产出 |

> **拍板记录：2026-11-10 —— A1~A6 全部按推荐通过。** A6（实现期顺序）就此定序，启动时点待系统设计收官后与 #7 一并确认。

## 9. 与既有决策 / 未决问题的对账

| 项 | 关系 |
|---|---|
| D3（零 AI） | AR2 重申：AI 只在 M1（离线）与外部叙述 agent；在线域十步纯确定性 |
| D4（权威源链） | §3 数据流即其图示：原文 → YAML（正式库）→ midas 表降为投影（M8）；L3 差异清单反向喂 midas 治理 |
| D5（责任链） | §4 十步 = 责任链模式的节点素材；归并方案随设计 0005 |
| D6（四层） | 层①②③ = M5；层④ = 项目外 agent，边界本文 §6（单 JSON 自包含） |
| #3（规则库 schema） | M2；映射表确认已定稿，剩余项（trace_check、43 套铺开）属实现期 |
| #4（公式边界语义） | 归属 M4 → **设计 0005**（伞形第②步）：窗口 token→期间码、缺数回退、CAGR/ratio、lower_of_both 取数 |
| #2（mock 契约） | 归属 M3 → **设计 0006**（伞形第③步）：字段全集 + expected + 边界族 |
| #5（校准工作流） | M1；方案已定，CLI 命令面本文 §5 已给（`calibrate run`） |
| 上轮 P1~P4 | 本文兑现 P2 第①步；P1 实现冻结生效（c68d02e 封存为设计 0002 验证件） |

## 10. 后续设计（伞形第②③步 + v0.2 增补）

- **设计 0005《测评引擎运行时与公式语义》**（已拍板 E1~E9）：十步的责任链归并、26 item 判定语义矩阵、窗口 token → 期间码解析规则（`nth_year` / `last_n_years` / `latest`）、缺数→indeterminate 的精确边界（哪些缺年杀整套、哪些只杀一叶）、CAGR / ratio / lower_of_both、**进度与覆盖率（§5.2）**、层②帕累托与层③归因的计算语义。
- **设计 0006《mock 数据契约》**（已拍板 F1~F6）：CompanyProfile 字段全集、三表+权益结构 schema、expected golden 格式、±ε 边界族参数化生成、勾稽断言清单落位。
- **v0.2 增补**（[ADR-0007](adr/0007-progress-and-coverage-metrics.md)）：层① 每套增 `progress` / `coverage` / `binding_clause_id` / `next_binding_clause_id`，见 §6.1。

对照 §2 映射表复核全覆盖 → **系统设计已于 2026-11-10 收官**（tag `design-complete`）；实现期按 §8-A6 顺序启动。
