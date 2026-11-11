# 04: Fold 节点——Kleene 双规则折叠与套终态 / 板块结论

**What to build:** 叶状态折叠成条文 / 支路 / 套 / 三段结论：clause(all) AND、clause(any) OR（任一 met 先满足）、branch AND、group OR、套 AND、三段 AND(段①发行, 段②定位, OR(段③套)) → 板块结论。甲公司跑通两条标志性路径：现金流条文因 any 择一而 met（Kleene OR 活例）；主板套因 c3 not_met 一票否决 → criteria_not_met；科创板因市值叶 indeterminate 传染 → 套 indeterminate。

**Blocked by:** 03

**Status:** ready-for-agent

- [ ] golden sets 对拍：主板 criteria_not_met（blockers=[np_latest]）、科创板 indeterminate（blockers=[mktcap_forecast]）
- [ ] Kleene 双规则（ADR-0006 / 勘误 0001 §2.3）：AND 任一 not_met → not_met；OR 任一 met → met；unknown（indeterminate / needs_review）传染为 indeterminate——**不复刻 0001 §2.3 原文「同规则」的错误**
- [ ] 三段树：段②定位在样板期为 pass-through 占位（G-D 映射属 M1 全量），不阻塞结论
- [ ] facts 在 Fold 出口冻结（AR5）：Result 段再读 facts 得到同一对象，任何后置阶段不得改写
- [ ] 不可能路径测试：含未定义叶的套永远出不了 criteria_met
