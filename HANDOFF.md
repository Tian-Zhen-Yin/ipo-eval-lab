# HANDOFF：本地独立 IPO 评测项目（ipo-eval-lab）

> 交接自 midas 仓库会话（2026-11-09）。该会话完成了 midas IPO 模块代码勘察与设计大分叉拍板，
> 本文档供新会话在本目录（项目根）继续 grilling。读完即可丢弃本文档（内容吸收进 CONTEXT.md/ADR 后删除）。

## 项目一句话

脱离 yonyou 体系的**本地个人实验项目**（非产品化）：Python 确定性评测引擎，复用 midas IPO 测评的责任链设计；
企业数据为 mock（从 yonyou 日常环境拉取固化，采集实现不在项目范围）；叙述报告由 ZCode skill/agent 基于结构化结果 JSON 生成。

## 已定案决策（不再讨论）

| # | 决策 | 内容 |
|---|------|------|
| D1 | 定位 | 本地实验项目；企业数据 = mock（不考虑采集实现，项目只消费本地文件） |
| D2 | 技术栈 | **Python**（pydantic 契约 + YAML 规则库 + CLI；代码不复用 midas，只复用设计） |
| D3 | AI 接入 | **项目内零 AI 依赖**。引擎输出结构化结果 JSON；第四层叙述报告由 ZCode skill/agent 读 JSON 生成。LLM 只叙述、不碰数据计算 |
| D4 | 标准校准 | 对照交易所规则原文逐条校准 midas 的 61 测评项/227 阈值，每条补 evidence 法规出处；**上市标准"套"为一等公民**（科创板 5 套/创业板 3 套/北交所 4 套等） |
| D5 | 测评链 | 复用 midas 责任链模式：Init→Calc→Fetch→Result 四节点 + Context 有序遍历；公式引擎语义对齐 `FormulaFactory` |
| D6 | 结果分析 | **四层递进**：①差距量化（含 CAGR 类"还要几年追上"）②最优路径（枚举 板块×标准套，输出最优可上岸组合）③归因诊断（数据质量 vs 真实差距）→ 前三层纯规则；④叙述报告（LLM via agent），结论带 evidence 溯源 |

## 参考 artifact（勿重复搬运，按路径引用）

- **`docs/midas-code-map.md`** —— midas IPO 模块代码地图（链结构/公式引擎/规则表结构/61 项清单/AI 分析弱点/种子 SQL 路径）。
  公式语义对齐（grilling 问题 #4）和 M1 种子导出脚本都要以它为底图，涉及源码类可直接去 midas 仓库按路径核对。
- 深挖背景（可选）：`C:\Users\17402\.zcode\cli\memories\projects\midas-d8f1ae36e88457a3\memory\ipo-local-eval-project.md`
  与同目录 `ipo-eval-refactor-direction.md`（此前 midas 内重构推演、AI 病灶调研、理想架构"证据机器"的来源）。

## 待 grilling 的问题（按优先级）

1. **结果 JSON 契约 schema**：四层各自的字段全集；`eta_years`（还要几年追上）的口径；最优路径 distance 的度量方式
2. **mock 数据契约 CompanyProfile**：字段结构；period 如何表达；底稿 BOOLEAN 项表示；缺失值表示
3. **规则库 YAML schema**：拍平成 per-item × per-standard-set 阈值后的字段全集；维度；适用板块
4. **公式引擎边界语义**：对照 midas `FormulaFactory` 逐条对齐——数据缺年怎么处理、CAGR 年数基准、`~近N年` 窗口起点
5. **校准工作流形态**：交易所规则原文从哪来（人工整理 vs 抓取）；对照清单的形态（建议也是 YAML/表格，evidence 回填可增量）
6. **维度评分口径**：midas 现状 = 每维度取最高分标准、总分 = 维度均分；保留还是重定义
7. **工程细节**：Python 版本（建议 3.12）/ uv / CLI 形态（建议 typer 或 argparse）/ pytest

## Suggested skills（新会话依次调用）

1. `/setup-matt-pocock-skills` —— 若未配置过 tracker/文档布局（首次在本项目用这些 skill 时）
2. `/grill-with-docs` —— **主任务**：磨上面 7 个问题，落 `CONTEXT.md` + ADR
3. `/to-spec` → `/to-tickets` —— grilling 收敛后；本项目建设量级是多 session（骨架/引擎/分析/校准/skill 五段）
4. `/implement` —— 逐票执行，票间 `/clear`

## 环境注意

- Windows 10 + Git Bash；目录已 `git init`（无远程）
- midas 仓库在 `E:\yonyouProject\midas`（对照源码用，不要把任何东西写回去）
- 提示：midas 是 Java 8 项目，其中公式/判定逻辑是**语义移植底稿**，不是依赖——一切以本项目的 Python 实现为准
