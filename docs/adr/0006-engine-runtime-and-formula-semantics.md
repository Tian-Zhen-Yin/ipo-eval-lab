# ADR-0006：测评引擎运行时与公式语义

- 状态：Accepted（2026-11-10，[设计 0005](../design/0005-engine-runtime-and-formula-semantics.md) E1~E8 拍板，全部按推荐）
- 关联：设计 0005（方案全文）、设计 0001 §2.3（**勘误**）、设计 0002（window token / measures）、设计 0004（AR1~AR5 / 十步）、CONTEXT #4 / D5

## 背景

未决 #4（G-B）：midas check04/11 证明**窗口语义无单一定义点必然产生矛盾配置**；`ResultEvalServiceImpl` 的 null→0 让缺数静默变成「不达标」；且设计 0001 §2.3「折叠 AND 与 OR 同规则」按字面执行会错杀 OR 已满足条文（甲公司现金流条文：现金流 1.8 亿 ✗ / 营收 16 亿 ✓ → 字面折叠成 not_met，恰是 0001 附录 A 立意要修的病）。

## 决策

1. **五节点责任链**：Init(①~④) / Fetch(⑤) / Calc(⑥) / Fold(⑦) / Result(⑧~⑩)；Context append-only 无回边；**facts 在 Fold 出口冻结**（AR5「层只读 facts」的强制点）；Fetch 先于 Calc（复用 midas 责任链模式，不照搬其节点顺序）。
2. **窗口 token 单点解析**：`latest / last_n_years / nth_year` 锚 FY_end 的解析表；不足或断年 → indeterminate（**不缩窗、不外推、不补零**）；stub 不进窗口；解析表与设计 0003 L2 回译渲染器**同源**。
3. **缺数三原则**：叶级隔离（缺年只杀涉年叶，套级传染只经折叠）/ 无静默回退（null 永不进比较）/ 审计覆盖降级（非标意见→needs_review、未审计年度→indeterminate）。measures **逐年孰低**；扣非缺 → 整叶 indeterminate。
4. **六量词公式表**（latest/sum/all_periods/avg/cagr/ratio）+ 差距三分列（diff / required_delta / required_action）；CAGR 首年 ≤0、ratio 分母合计 0 → indeterminate。
   > **勘误（2026-11-10，评审 0004 V1）**：本条引用的 cagr 公式原写 `(x[首年]/x[末年])^(1/(n−1)) − 1`（分子分母颠倒），已改为 `(x[末年]/x[首年])^(1/(n−1)) − 1`——与「复合增长率」标准定义及设计 0005 §6 的 window_roll 反解式自洽。
5. **折叠 = Kleene 三值按 AND/OR 双规则**（AND：任一 not_met 先否决；OR：任一 met 先满足；unknown 传染为 indeterminate）；not_applicable 仅套级。**勘误设计 0001 §2.3 的「同规则」表述**。
6. **层②**：帕累托前沿算**全部适用套**（四轴保区分度），recommendation = 前沿 ∩ 过闸套，excluded 分 reason（hard_leaf_not_met / dominated）。
7. **情景**：window_roll 按量词给进入年所需值（sum = 阈值−剩余合计；cagr = 首年′×(1+thr)^(n−1)），滚动风险倍数 k 入规则库配置（缺省 2）；growth 仅两点 r∈{0, historical_cagr}，一律 is_forecast——**ADR-0004 残点（假设来源）就此关闭**。
8. **数值表示**：金额整数元存储、float64 计算、比较不带 ε；Decimal 缓。

## 被否方案

- 短窗口回退（midas check04/11 的错法）；扣非缺用申报值顶替（系统性高估）；折叠 AND/OR 同规则（错杀 OR 已满足条文，与 G1/P7 立法动机矛盾）；growth 用连续增长率区间（r_high=1.5×cagr 之类系数即编数）；全程 Decimal（当前无非整阈值需求）。

## 后果

- 未决 #4 关闭（G-B 兑现：窗口 / 缺数 / 量词 / 折叠语义全部单点）。
- 实现期引擎按设计 0005 §1~§8 实施；文末「甲公司端到端自检链」为首个回归用例。
- 设计 0001 §2.3 勘误注随本 ADR 回写；mock 契约（设计 0006）须提供本语义所需全部输入（逐年扣非、逐年审计字段、权益变动序列）。
