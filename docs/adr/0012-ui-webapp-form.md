# ADR-0012：前端形态——本地轻服务 + 原生多文件（M-UI 阶段）

- 状态：Accepted（2026-11-13，用户拍板 P1/P2/P3 均按推荐）
- 关联：[设计 0007](../design/0007-ui-prototype.md)（交互原型，本 ADR 的呈现层基准）、[设计 0010](../design/0010-ui-implementation.md)（实现布局与 API 契约）、[ADR-0003](0003-metrics-and-five-states.md)（五态色板契约级）、[ADR-0007](0007-progress-and-coverage-metrics.md)（进度/覆盖率呈现禁令）、设计 0004 A3（v1 引擎「不做服务端」——本 ADR 的服务端**只在 UI 侧**，引擎 CLI 面不变）

## 背景

M1 三段收口 + M3~M7 引擎贯通后，前端仍是静态原型 `ui/prototype.html`（1284 行、
mock 甲公司、沪主板 3 套硬编码）。原型与真实数据的差距：

1. 13 个 mock 常量是手写快照，正式库 28 套/引擎 result.json 产后必然分叉；
2. V16 已判「仅铺沪主板」注释过时（正式库全量加载后其余 25 套可真渲染）；
3. 「新建测评 → 出结果」链路是断的——原型只能看，不能跑。

设计 0008 对前端实现零约定（该文档只拍板 E1~E5 纯后端工程决策）。

## 决策

**P1 = 本地轻服务**。新增 `ipo_eval_lab/webui.py`：Python 标准库 `http.server`
起本地服务（只绑 127.0.0.1，零新依赖），提供 5 个 GET + 1 个 POST（API 契约见
设计 0010）。引擎经 `run_eval()` **进程内直接调用**（不 subprocess）。
新建页可现场跑引擎出新 run，历史页自动列 `results/` 全部产物。

- 与设计 0004 A3「不做服务端」的关系：该约定的对象是**引擎架构**（M7 用户面 =
  CLI 三命令，不做 REPL/常驻服务）——维持不变；webui 是**展示层**的本地静态
  文件+JSON 服务，不是引擎的服务化，引擎对外的唯一编程接口仍是 `run_eval`。

**P2 = 原生多文件**。`ui/app/` 下 index.html + ES module JS，零构建工具、零
npm。原型 356 行契约级 CSS（五态色板）与交互骨架（弹窗/焦点陷阱/委托事件）直接
迁移；13 个 mock 常量与 16 处内联 onclick 退役。

**P3 = 三页全接真数据 + 修 V16/V17**，分 3 阶段交付、每阶段 git 检查点：
结果页（核心页）→ 新建页（现场跑通）→ 历史页 + 收尾。

## 不做的事（维持既有拍板）

- 不恢复总分/维度分/雷达图（0001 A5 / ADR-0007 呈现禁令）；
- 不恢复 result.json/narrative_handoff 下载按钮（P9 = A，UI v0.5.1）；
- 不做移动端适配（0007 §6.4：桌面 1366+）；
- 不动 `ui/prototype.html`（保留为设计 0007 交付物基准，只读）。

## 影响

- 新增目录：`ui/app/`（真前端）、`ipo_eval_lab/webui.py`（服务）、
  `tests/test_webui.py`；新增文档：本 ADR + 设计 0010。
- 会话补录产物落 `.scratch/ui-runs/<run_id>/profile.json`（真实 `fixtures/` 不动）；
  UI 触发的 run 落 `results/`（已 gitignore），命名加时间戳防覆盖。
- 安全边界：单用户本地工具，只绑回环地址，不做鉴权/并发。
