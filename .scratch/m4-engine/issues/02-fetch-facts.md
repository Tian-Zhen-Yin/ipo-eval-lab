# 02: Fetch 节点——facts 构建（六驱动 + 七指标，两维 measures）

**What to build:** Init 之后，企业三年 statements 变成 facts：六驱动 + 七指标全部就位，净利两维（申报 / 扣非）+ 逐年孰低序列、研发两源相加、ROE 加权派生、documentary / declared 事实项原样入 facts。甲公司 facts 可 dump 成 JSON 检视，数字与设计 0006 §5 定稿表逐项一致。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 甲公司 facts 对拍定稿表：孰低 1.44 / 0.3 / 0.4 亿；累计孰低 2.14 亿（申报 2.2 亿）；OCF 累计 1.8 亿；营收累计 16 亿；研发 1,900 / 2,100 / 3,000 万
- [ ] 逐年孰低 = min(申报, 扣非) 逐年进行后再聚合；扣非 null → 该年缺值，**不用申报值顶替**（E3）
- [ ] rd_investment_total = 费用化 + 资本化，任一源 null → 该年缺值
- [ ] roe_weighted_avg 加权派生：分母按 equity_roll 时间加权；分母 ≤ 0 → 缺值（不硬算）
- [ ] mktcap_self_estimate = null → mktcap 缺值（G-C 落点，是「没有」不是 0）
- [ ] stub_period 只进 facts 展示位，永不进窗口与判定（E2-2）
- [ ] 每个数字带 refs（来源字段路径），为不变量 5（叙述只复述带 refs 的数字）打基础
