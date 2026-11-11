# 01: eval run 入口与 Init 节点（run 坐标 + as_of 过滤 + 适用性判定）

**What to build:** 用户执行 eval run 命令（`-m` 模块调用形态），传入公司 ID 与 as_of 日期，终端打印：run 坐标（E / as_of_date / report_period / applicant_profile / target）+ 适用套清单与不适用套及原因。规则库按 as_of 过滤生效区间——`effective_from` 从此真正参与过滤（CONTEXT #9-V6 就此关闭）。五节点责任链骨架（Init → Fetch → Calc → Fold → Result，设计 0005 §1）立起，Fetch 之后的节点为占位直通，但 Context 已是 append-only。

**Blocked by:** None（可立即开始）

**Status:** ready-for-agent

- [ ] as_of 早于套的 effective_from → 该套不进本次 run 且给出原因（例：as_of=2024-04-01 时主板套 2024-04-30 修订版未生效）
- [ ] applicant_profile.company_type=general → 两个样板套（cn_main_general_g1 / star_general_g1）均适用；redchip 公司 → 套级 not_applicable，出分母、留在事实层
- [ ] target 的 boards / sets 过滤生效；缺省 = 全部适用套（不是全部套）
- [ ] run 坐标写入 Context（后续 Result 段复用同一对象）；as_of 缺省 = 当日且**显式写入** run.as_of_date（可复算）
- [ ] applied_rule_versions[] 记录本次实际生效的规则版本（设计 0003-R6 版本链）
- [ ] 坏输入起不了 run：不存在的公司 ID、规则库 lint 红（AR4）
- [ ] 测试覆盖上述各条 + 甲公司端到端冒烟（适用套清单正确打印）
