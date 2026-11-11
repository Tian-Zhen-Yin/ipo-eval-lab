# 07: 层② 帕累托路径与层③ 归因（样板套最小实现）

**What to build:** hard gate（含 not_met 硬叶的套不进推荐）→ 帕累托四轴前沿算**全部适用套** → recommendation / alternatives / excluded{reason}；层③ 归因把每个 blocker 放进 verifiability × substantive_obstacle 矩阵（5×3）的格位。甲公司样板：推荐空——主板 not_met、科创板 indeterminate，工具宁可说清差在哪，不硬推一个套。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] 甲公司 recommendation = 空；两套都进 excluded 且各带 reason（not_met 硬叶 / indeterminate 数据缺口）
- [ ] 帕累托算全部适用套（不只过闸套，E6 拍板）——保持四轴区分度
- [ ] 禁「最优」表述、推荐不含 not_met 硬叶的套（E1~E4 拍板，对齐设计 0001 §5.1）
- [ ] np_latest 归因格位正确：可验证 × 实质障碍（净利差 60% 是实质差距不是数据问题）
- [ ] mktcap_forecast 归因格位正确：企业自估缺数据 → 可验证性降档（documentary 缺源），与净利类区分开
- [ ] 归因输出是格位 + 一句话依据，不编造治理建议
