# midas IPO 评测模块代码地图（对照底稿）

> 来源：2026-11-09 对 `E:\yonyouProject\midas` 的勘察（Explore 汇总）。本文档是 ipo-eval-lab 的**语义移植底稿**：
> 公式引擎、判定逻辑、规则数据结构均以 midas 现实现为对齐基准；涉及实现细节可去 midas 仓库按路径核对。

模块横跨 4 个 maven 模块：`midas-api`（接口/Controller）、`midas-domain`（实体/DTO/枚举）、`midas-service`（实现）、`midas-app`（Controller 注册）。
注意：代码中没有名为 Chain/Handler/Pipeline 的类——"责任链"实际是"Spring 注入 List + @Order 顺序遍历"的轻量实现。

---

## 1. 责任链设计（评测执行链）

| 角色 | 类 | 路径（midas-service/midas-api/midas-domain 下 `com/yonyou/midas/ipo/`） | 职责 |
|---|---|---|---|
| 链节点接口 | `IpoEvalService` | midas-api `...\ipo\eval\IpoEvalService.java` | `void handle(IpoEvalContext context) throws Exception` |
| 抽象基类 | `AbsIpoEvalService` | `...\ipo\eval\AbsIpoEvalService.java` | 空实现，节点继承它 |
| 链执行器 | `IpoEvalProcessorImpl` | midas-service `...\ipo\processor\impl\IpoEvalProcessorImpl.java` | 构造器注入 `List<IpoEvalService>`，按 Spring `@Order` 顺序 for 循环逐个调用 |
| 上下文 | `IpoEvalContext` | midas-domain `...\ipo\eval\context\IpoEvalContext.java` | `@Data @Builder`：orgId/startYear/endYear/boardId/industryId/companyTypeId/period/summaryReportId + `conditions`(测评内容)、`calcConditions`/`fetchConditions`(分流)、`calcResults`/`fetchResult`(中间结果)、`evalResult`(最终结果) |

**链节点（按执行顺序）：**

| 顺序 | 类 | 路径（midas-service `...\ipo\`） | 职责 |
|---|---|---|---|
| @Order(1) | `InitEvalServiceImpl` | `...\init\service\InitEvalServiceImpl.java` | 委托 `IpoEvalInitServiceImpl.init()`：按 `moduleCode == fadmportal.ipo.IPOCompanyWorksheet` 把 conditions 分流为 `fetchConditions`（底稿取数类）与 `calcConditions`（公式计算类） |
| @Order(2) | `CalcEvalServiceImpl` | `...\calc\service\impl\CalcEvalServiceImpl.java` | 组装 `IpoFormulaParamDTO`，调 `IpoFormulaCalcService.evaluate()` 取指标并执行公式 → `context.calcResults` |
| @Order(3) | `FetchEvalServiceImpl` | `...\fetch\service\FetchEvalServiceImpl.java` | 查 `IPOCompanyWorksheet` + `IPOEntityTestItem`（企业底稿手工数据）→ `IpoEvalFetchResultDTO` 加入 `context.fetchResult` |
| @Order(4) | `ResultEvalServiceImpl` | `...\result\service\ResultEvalServiceImpl.java` | 核心：条件-标准-阈值匹配 → `isSatisfied()` 判达标 → diff/diffRate → 维度评分 → 明细/汇总落库 → 异步触发 AI |

**公式计算子链**（Calc 节点内部）：`IpoFormulaCalcServiceImpl.evaluate()` → `FormulaFactory`（解析 `AVG(...)`/`CAGR(...)` 等公式串，提取 `$指标`、`~近N年`、`#第N年` 参数）→ 5 个公式实现 `AvgFormula`/`CAGRFormula`/`DBFormula`/`PercentageFormula`/`SumFormula`（`getFormulaCode()` 返回 AVG/CAGR/DB/PERCENTAGE/SUM）→ 取数由 `IpoFetchAdsDataServiceImpl` 调数据中台 `SummaryQueryService.registrySummaryQueryV1` 后内存聚合。

**移植时的公式语义锚点**：公式串形如 `SUM($研发投入, ~近3年)`、`CAGR($营收, ~近3年)`；`$` 前缀 = 指标名（对应 ADS 模型字段），`~` = 近 N 年窗口，`#` = 第 N 年定点。本地实现需逐类核对边界语义（缺年、CAGR 基准年、窗口起点），源码在 midas-service `...\ipo\calc\` 下。

## 2. 测评项与判定

**配置全在数据库表 + 种子 SQL（非硬编码）**：

- `IPOConditionTestItem`（fadmportal.ipo.IPOConditionTestItem）——测评项定义：type（1=固定展示项 / 2=条件类需用户填写 / 其他=取数类）、formula（公式串）、index_source（指标来源模型编码）、defaultValue、format、code、name(多语)、desc
- `IPOEntityTestItem`（fadmportal.ipo.IPOEntityTestItem）——企业级测评项实际值（挂 `IPOCompanyWorksheet` 底稿下，用户手工填写）
- `EvaluationThresold`（fadmportal.ipo.EvaluationThresold）——阈值：evalItemId + op（GT/LT/GE/LE）+ val + format（NUMBER/PERCENT/INTEGER/BOOLEAN）+ suffix，外键指向标准
- `EvaluationItem`（fadmportal.ipo.evaluationItem）——测评维度表

**测评维度 4 个**（`mt_ipo_evaluation_dim`，枚举 `IpoEvalDimensionEnum`，midas-service `...\ipo\aianalyze\enums\`）：
`financial_status` 财务指标 / `subject_qualification` 主体资质 / `governance_operation` 治理及运营 / `sector_alignment` 板块定位

**61 个测评项（check01~check61）分类概览**：
- 市值 check01（RAW 公式，来源=底稿）
- 营收 check02~07（近 N 年营收/增长率/CAGR/高于同行）
- 净利润 check08~17（第 1/2/3 年净利、累计、扣非口径）
- 现金流/净资产 check18~24（经营现金流净额、净资产、加权 ROE）
- 研发 check25~31（研发人员占比、研发投入金额/累计/CAGR、占营收比）
- 资质 check32~37（业务批准、自主研发、红筹、股份公司、经营年限、发行后股本）
- 治理规范 check38~49（公开发行比例、独立性、团队稳定、股权清晰、无违法、审计/内控意见等，多为 BOOLEAN 底稿项）
- 科创属性 check50~55（发明专利数、国家三大奖、重大科技专项、进口替代等）
- 板块定位 check56~61（现代产业体系、主板/科创板/创业板/北交所定位）

**判定逻辑**：统一在 `ResultEvalServiceImpl.isSatisfied(evalValue, op, thresholdVal, format)`（数值型按 CompareOpEnum 比较，布尔型按字符串相等）；diff/diffRate 同处计算；无逐项硬编码 if——逻辑全部数据驱动（公式串+阈值+比较符在 DB）。

**维度评分口径（现状）**：每维度取"最高分标准"计分，总分 = 4 维度均分。→ 本项目 grilling 待定问题 #6。

## 3. 上市标准数据

来源：imeta 元数据实体 + 种子 SQL，读取走进程内缓存（`CacheManager`，key `ipoBoardStandard`），无外部接口。

| 实体 | ENTITY_NAME | 说明 |
|---|---|---|
| `ListingBoard` | fadmportal.ipo.listingBoard | 板块 + IPOKeyWord 子表；种子：SSE-MB 上交所主板 / STAR Market 科创板 / SZSE-MB 深交所主板 / ChiNext 创业板 / BSE 北交所（枚举 `ListingBoardEnum`，midas-domain `...\enums\`） |
| `ListingStandards` | fadmportal.ipo.listingStandards | 标准文本：boardId/companyTypeId/requirement/evalItemName/description |
| `IPOEvaluationCriteriaForm` | fadmportal.ipo.IPOEvaluationCriteriaForm | 评测标准表（testDimension 维度），聚合标准-板块/企业类型/阈值关系 |
| `StdModuleRelationship` | fadmportal.ipo.StdModuleRelationship | 标准↔板块（boardId + foreignerKey=标准id） |
| `StdCompanyTypeRelationship` | fadmportal.ipo.StdCompanyTypeRelationship | 标准↔企业类型 |
| `EvaluationThresold` | — | 标准↔阈值（见上） |

**选标准逻辑**（`IpoEvaluationServiceImpl.handleData()`，midas-service `...\ipo\eval\service\impl\`）：板块 → StdModuleRelationship → 与 StdCompanyTypeRelationship（企业类型）取交集得标准 id → 查阈值 + 测评项 formula/index_source → `List<IpoEvalConditionDTO>` 入上下文。
→ **本地项目的拍平方向**：标准/阈值/板块三层关系 → per-item × per-standard-set 的阈值表 + evidence 出处（HANDOFF.md 决策 D4）。

**种子 SQL 路径（M1 导出脚本的输入）**：
`E:\yonyouProject\midas\midas-bootstrap\scripts\db\init\rdb\0001_yonbip-fi-mt\0020_self\{DDL,DML}\mt_ipo_*.sql`
核心文件含 `mt_ipo_evaluation_item_20260531141549619.sql`（61 条）等；227 条阈值在 eval_thresold 相关 DML 中。

## 4. 结果分析现状（= 本项目要重设计的部分）

策略模式（`AiAnalysisStrategy<T,R>`，midas-api `...\ipo\aianalyze\`）：`AiAnalysisContext` 注入策略列表按 `supports()` 匹配。

- `DetailAiAnalysisStrategy`：`List<IpoEvalResultDTO>` 5 条一批 → 回写明细表 `suggestion`（JSON）；**仅针对 dimName=财务指标**，每条建议 ≤30 字
- `SummaryAiAnalysisStrategy`：汇总评分+各维度明细 → 回写 `IPOEvaluationResults.overallConclusion/advantageSummary/disadvantageSummary`（**三字段写同一完整 JSON**）
- Prompt 硬编码在 `PromptEnum`（midas-common `...\airesult\enums\prompt\`），占位符 `{IPO_ASSESSMENT_DATA}`；模型 deepseek-v4-flash（`AiAnalyzeConstant`，DOMAIN=BOAIPO）
- 触发：明细落库后按 5 条/批异步（detached 线程 + CountDownLatch），前端轮询 `checkAiConclusionStatus`；**全链路不落 prompt/模型/token/traceId；失败吞异常**
- 已知 bug（勘察确认）：`ResultEvalServiceImpl.java:376-377` 喂 AI 的 boardMatchScore/managementScore **维度互换**；`ResultEvalServiceImpl.java:312-314` 空维度应 `continue` 却 `return` 中断汇总落库；`IpoEvaluationServiceImpl.java:249-254` null 调 `isEmpty()`
- 未提交修复（midas 工作区）：两个策略的 `.content(content + prompt)` → `.content(prompt)`（数据重复拼接修复，占位符注入早已存在）

→ 弱点总结（本项目四层分析的设计动机）：只覆盖财务维度、每条 ≤30 字无量化差距、无跨板块最优路径、无归因分层、AI 触发与结果耦合、无 evidence。

## 5. 报告/结果数据模型（语义参照）

| 类 | 路径（midas-domain `com\yonyou\midas\ipo\`） | 职责 |
|---|---|---|
| `IPOEvaluationResults` | `domain\IPOEvaluationResults.java` | 汇总报告：reportPeriod/orgId/boardId/companyTypeId + 评分（total/financial/qualification/management/boardMatch）+ AI 结论三字段 |
| `EvaluationResultDetail` | `domain\EvaluationResultDetail.java` | 明细（FOREIGNERKEY=汇总id）：evalDimId/standardId/evalItemId/calcIndexValue/diffValue/diffRate/complianceStatus/suggestion |
| `IpoEvalResultDTO` | `eval\result\dto\` | 链内结果：detailId/businessId/standardId/throldId/throldValue/value/diff/diffRate/dimId/status/dataFormat/period |
| `IpoEvalConditionDTO` | `eval\param\dto\` | 链内条件：businessId/moduleCode/formula/standardId |
| `SummaryData`/`DetailData`/`DimData` | `result\` | 报告 VO（标题/得分/维度/AI JSON 提取 `AIExtractorUtil`） |

## 6. 入口与流程（理解全貌用）

```
POST /ipo/evaluation (orgId, startYear, endYear, listingBoardId, industryId, companyTypeId)
  └─ IpoEvaluationServiceImpl.evaluation()
       ├─ handleData(): 板块→标准∩企业类型→阈值+测评项 ⇒ context.conditions
       └─ IpoEvalProcessorImpl.handle(context)  // @Order 遍历
            ① Init 分流 → ② Calc 公式计算(ADS 取数) → ③ Fetch 底稿数据 → ④ Result 匹配判定/评分/落库/异步 AI
  ← 返回 summaryReportId
之后: /ipo/result/summary|report 读报告; 前置 /ipo/ruleCheck 校验底稿完整性
```

## 7. 复用边界（ipo-eval-lab 视角）

| 照搬语义（Python 重写） | 全部丢弃/重写 |
|---|---|
| FormulaFactory 公式串语法与 5 类公式 | imeta 元数据实体、多语、租户（ytenant_id） |
| isSatisfied 比较符/格式判定、diff/diffRate | ADS 数据中台取数 → 本地 profile 文件 |
| 责任链模式（Context + 有序节点） | Spring @Order 装配 → 显式列表/注册 |
| 61 项+227 阈值种子数据（导出为初版 YAML） | detached 线程 AI 触发 + 轮询 → 零 AI 依赖（D3） |
| handleData 的 板块∩企业类型 选标准思想 | 三层标准关系 → per-item × per-set 拍平（D4） |
