# 06: 层① 情景推演（window_roll 分量词 / growth 两点）

**What to build:** 对 not_met 或余量薄的数值叶输出确定性情景：window_roll 按**分量词**计算「窗口滑出最老一年后，进入年需要多少」（sum / avg / all_periods / latest 各有公式，设计 0005 §6），配风险倍数 k（缺省 2）分档 low / medium / high；growth 两点情景（r=0 与 r=hist_cagr）一律 is_forecast、绝不写成预测结论。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] golden window_roll 逐字对拍：np_3y_sum 进入年需 **1.3 亿**、risk=**high**（k=2：13,000 万 > 2 × 4,000 万）
- [ ] 分量词公式各自正确：sum 型减去滑出年、avg 型重算均值、latest 型直接换年、all_periods 型进入年需满足逐期约束
- [ ] growth 两点情景零编造：r_high=1.5×cagr 之类的系数**不许出现**（E7 拍板），只报 r∈{0, hist_cagr} 且必带 is_forecast
- [ ] 情景是确定性重算（同一 facts 重跑窗口），不是新数据源
- [ ] 噪声控制：已 met 且余量大的叶不出情景（均为正叶不出）
- [ ] window_roll 输出「进入年所需值」对照最近年实际值——差距画像的核心可执行信息
