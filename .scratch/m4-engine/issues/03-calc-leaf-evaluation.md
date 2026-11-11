# 03: Calc 节点——叶判定（窗口 token / 六量词 / 五态 / 差距三分列）

**What to build:** 适用套的每个叶拿到五态判定与差距数字：窗口 token（latest / last_n_years / nth_year）解析成期间码锚定 FY_end；六量词按设计 0005 §4.2 公式表计算；op 比较 float64 无 ε；差距三分列（数值叶 diff + gap_ratio / 计数叶 required_delta / 布尔叶 required_action）。甲公司主板 5 叶的判定表可打印检视，与 golden key_checks 逐字一致。

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] 甲公司主板 5 叶：c1 三年均为正 met；c2 累计孰低 2.14 ≥ 2 亿 met；c3 最近年 0.4 < 1 亿 **not_met，diff=6,000 万、gap_ratio=0.6**；b1_c1 的 OCF 支路 not_met（差 2,000 万）、营收支路 met
- [ ] golden key_checks 三条逐字对拍通过（np_latest / OR 择一条文 / np_3y_sum）
- [ ] 窗口不足（只有 2 年却要 last_n_years(3)）→ indeterminate，**不缩窗、不外推、不补零**
- [ ] CAGR 用修正公式 (x[末]/x[首])^(1/(n−1)) − 1——写一个手算算例测试防回归（评审 0004 P0 病灶是方向反了）
- [ ] qualified_audit 变体：2023 非标意见 → 净利类叶按 E3 审计覆盖降级转 indeterminate（不静默当正常年用）
- [ ] judgment 叶（declared 布尔）→ needs_review + pending_evidence，**永不 met**
- [ ] null 永不进比较（修 midas `isSatisfied(null)→0` 病灶的最底层防线）
