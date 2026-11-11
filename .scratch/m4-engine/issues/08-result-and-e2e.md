# 08: Result 出口与 eval run 端到端（契约 v0.2 组装 + golden 全量对拍）

**What to build:** `eval run` 一次跑完十步（设计 0004 §4），输出单文件 result.json：契约 v0.2 四段（run / facts / layers / narrative_handoff）+ 终端摘要。narrative_handoff 自包含（units / citation_index / disclaimers / forbidden_claims），外部叙述 agent 只需要这一个文件。golden summary.json 全字段对拍点亮——设计 0001 收官判据从「文档自检」变成「机器回归」。

**Blocked by:** 05, 06, 07

**Status:** ready-for-agent

- [ ] result.json 四段齐全；每个数字带 refs（不变量 5）；facts 与 Fold 出口冻结对象同源（AR5）
- [ ] narrative_handoff：三条固定 disclaimers（段①抽样核查 / 甜区声明 / 市值自估）+ forbidden_claims（含 coverage<100 禁令、scenario is_forecast 标注义务）随文件传递
- [ ] citation_index：阈值判定 → item → metric → law_ref（law_id#article）直达法条
- [ ] golden **全字段**对拍通过：sets / key_checks / window_roll / progress——任何一处语义漂移测试红
- [ ] `--report` 落 results/（不入 git，#7-E5）；`--as-of` 缺省 = 当日并写入 run.as_of_date
- [ ] 端到端测试：base_co_2029 与 qualified_audit 两样本各跑通一次（后者验证 E3 降级路径全链）
- [ ] 终端摘要：五态计数 + 每套一行结论 + blockers——不出现总分 / 维度分 / 雷达图
