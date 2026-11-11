# 05: 进度与覆盖率（E9 / ADR-0007）

**What to build:** 每套计算双指标并配对输出：progress（min 折叠的叶分数 ×100）+ coverage（可判叶数 / 适用叶总数 ×100）+ binding_clause_id / next_binding_clause_id。叶分数：met→1；not_met 有 gap_ratio→1−gap_ratio；thr=0 或布尔叶→0；**未定义→不进聚合、只进覆盖分母**。甲公司主板 40/100（卡点 c3、次弱 c2）；科创板 100/80（市值叶未定义——双指标必要性的活例）。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] golden progress 逐字对拍：主板 {40, 100, cn_main_g1_c3, cn_main_g1_c2}；科创板 {100, 80, null, null}
- [ ] 科创板市值叶：min 聚合仍 1.0（未定义不拉分），coverage 分母 5 分子 4 → 80——**防「顺手」把未定义叶按 0 算进聚合（midas 病灶）**
- [ ] thr=0 叶 not_met → 0 分（gap_ratio 无定义不硬凑）；布尔 / 动作叶 → 0 或 1
- [ ] 同向性测试：无未定义叶时 progress=100 ⟺ 套 met（min 与 AND 判定同源，永不出「100 分却 not_met」）
- [ ] progress 不参与判定、不被判定反推（判定与展示分离）
- [ ] coverage < 100 时生成 forbidden_claims（禁「可达标 / 预计能过」表述，进度限定「已评估部分」）
- [ ] progress 不进 narrative 叙述素材（禁「得分高所以能过」式表述的机器防线）
