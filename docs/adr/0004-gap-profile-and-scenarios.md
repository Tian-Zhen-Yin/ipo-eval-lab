# ADR-0004：层①定位为差距画像，时间维度降为情景推演

- 状态：Accepted（2026-11-10，P4/P8 拍板；F5/F6 终案）
- 关联：[评审 0001](../reviews/0001-gap-layer-design-review.md)（F5-R）、[评审 0002](../reviews/0002-professional-gap-audit.md) E1~E4、[设计 0001](../design/0001-top-down-redesign.md) §5.1

## 决策

1. **层①结论本体 = 差距画像**：逐套 blockers（叶级 not_met/indeterminate 清单 + diff + lever 分类 + 严重度直方图）；不跨套排序（"市值差 20%"与"专利差 2 项"不可通约）。
2. **lever 分类与 drivers 保留**（评审 0001 贡献）：grow / derived / wait / adjust / act 五类；6 个财务驱动的年序列为 `facts.drivers[]` 一等数组。
3. **scenario_projection 两类**：
   - `growth`：历史 CAGR 区间（r_low/r_high → years_low/years_high），`is_forecast: true`，`basis: historical_cagr`；**无来源不编数**；参数库 / 兜底率不建。
   - **`window_roll`（P8，v1 新增）**：报告期滚动一年后旧年滑出窗口，对每个窗口型定量叶输出**进入年所需值** `required_entering_year_value = 阈值 − 窗口剩余年值合计`，与最近一年实际对照标滚动风险（阈值入规则库配置）——**确定性、零增长率假设**。
4. **套级时间区间**仅当套内无 act/adjust 阻塞叶（P4），必标 is_forecast。
5. **层②（F6 终案）**：先 hard gate 筛选（段①② not_met 或结构性不可达 → excluded{reason}），剩余套做帕累托四轴 `[not_met 叶数, max gap_ratio, years_high, data_uncertainty]`；不压单值、不称"最优"；输出 recommendation / alternatives / excluded，tiebreak 权重在 `metric` 块显式声明。
6. **data_uncertainty ≠ 审核通过概率**：该轴度量数据完整度（indeterminate + needs_review 计数）；板块通过率、问询强度、政策窗口属监管判断，工具无数据也无权下结论。

## 被否方案

- 单点 eta_years（增长率差 5pct 年数差 1.4~2.1 年，伪精确）；
- 单标量 distance（会推荐"离门槛最近但含一票否决项"的套）；
- 参数库 / 行业基准库进 v1（基准库 Phase 2，仅作红筹同行比叶的前置依赖时再启）。

## 示例（设计 0001 附录 A）

甲公司净利 1.5/0.3/0.4 亿：「三年累计≥2亿」2024 年报口径达标（2.2亿）；window_roll：2025 年报口径需 2025 年净利 ≥ 2.0 − 0.7 = **1.3亿**（2024 实际仅 0.4亿）→ 滚动风险高。公司什么都没做错，晚一年申报结论反转——这是无需增长率假设即可算出的结构性风险。
