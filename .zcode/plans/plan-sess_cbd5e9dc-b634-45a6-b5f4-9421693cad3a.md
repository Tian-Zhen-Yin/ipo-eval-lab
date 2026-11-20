# 全档响应式适配优化（ui/app）

## Context

用户反馈：项目页面在不同视口比例下适配差、问题多。核实结论——前端是纯静态 SPA（`ui/app/`），桌面优先设计：`max-width:1180px` 居中 + **仅一个 960px 断点**（且只把 4 个 grid 降单列，还漏了 `.scope-grid`）。已核实的具体问题：

**溢出/破版级**
1. 差距明细表 `#leaf-table`（结果页核心表，6 列）：外层 `.bd` 无 `overflow-x`（`index.html:126`）+ 表头全局 `nowrap`（`css:112`）+ 固定 % 列宽（`page-result.js:189`）→ 窄视口横向撑破卡片和页面
2. 四轴对比表 `#axes-table`（深度页）外层 `.bd` 无横滚（`index.html:164`）
3. `.scope-grid{1fr 1fr}` 无断点（`css:283`）→ 手机上两栏挤成 ~150px 宽
4. 顶栏 `.topbar-in` 固定 58px 高、子项不换行（`css:43-54`）→ <700px 时 logo+按钮+hint 溢出
5. 补录弹窗 `.amt-row`：input min 120px + select min 90px + checkbox label nowrap（`css:179-181`、`page-new.js:192`）→ 手机弹窗内溢出
6. `.scen` minmax 下限 320px（`css:233`）→ 360px 视口下溢出

**拥挤/难用级**
7. `.wizard` 左列固定 400px（`css:165`）→ 1000px 窗口右列被压到 ~500px；960 单列化后侧栏 sticky 仍粘屏
8. tooltip 固定 300px 宽仅 hover 触发（`css:326-330`）→ 窄屏超出屏幕、触屏不可用
9. crumb 用 `float:right`（`index.html:85`）、run 坐标头布局内联（`index.html:90-98`）→ 媒体查询无法覆盖内联样式

**维护性**
10. 死代码：`.atmx` grid（`css:242-249`，实际渲染用 `.atmx-t` 表）、`.hist-run`（`css:293`）

## 边界（redesign 约定）

- **保留**：视觉语言与契约五态色板（`css:5-17` 不可动）、页面信息结构、桌面 ≥1080px 的观感、全部业务功能与文案；`ui/prototype.html`、`docs/demo/roadshow.html` 为独立演示稿，不在本次范围
- **允许改**：断点体系、溢出处理、窄屏降级布局、少量**布局性**内联样式迁到 CSS 类（纯装饰性内联如颜色字号保留，控制回归面）
- 表格窄屏策略：**横滚 + 首列 sticky 固定**（信息密度保留、改动集中、回归风险低）

## 改造内容

### 1. `ui/app/css/app.css`（主战场）
- **≤1080 新档**：`.wizard` 左列 `minmax(300px,380px)` 替代固定 400px
- **≤960 扩充现有断点**：补 `.scope-grid→1fr`、`.wiz-side` 取消 sticky、顶栏 `.hint` 隐藏、main padding 收窄
- **≤640 新增手机档**：
  - 顶栏高度自适应、logo `small` 与 hint 隐藏、nav 按钮紧凑
  - main padding 16px、`h1.pt` 26→22px、`.verdict` padding 收窄
  - `.setcard .axes→1fr`；`.amt-row` 允许换行
  - `.modal` 手机全宽化（`.mbd/.mhd/.mft` padding 收窄）
  - `.scen`/`.rh-grid` minmax 下限改 `min(320px,100%)` / `min(148px,100%)`
  - tooltip `width:300px` → `max-width:min(300px,calc(100vw - 40px))`
- **表格横滚体系**：关键表 min-width（leaf 表 ~680px、axes ~560px、矩阵/滚动对比按内容）+ 横滚容器内首列 `position:sticky;left:0`（leaf 表条件列、矩阵测评项列、归因表行头）
- 删除死代码 `.atmx`、`.hist-run`

### 2. `ui/app/index.html`
- `#leaf-table`（:126）、四轴卡 `.bd`（:163-166）加 `overflow-x:auto`
- crumb `float:right`（:85）改 flex；run 坐标头（:90-98）内联布局迁 `.run-head` 类（观感不变）

### 3. `ui/app/js/page-result.js` / `page-new.js`
- leaf 表 % 列宽迁 CSS 类；矩阵表、滚动对比表加 min-width 类（`page-result.js:189,456`）
- 补录弹窗 checkbox label 去 nowrap 内联（`page-new.js:192`）

## 验证

1. `.venv/bin/python -m ipo_eval_lab.webui --port 8091` 起服务（`results/` 已有 6 份结果，三页开箱有内容）
2. browser-use 技能截图走查视口 **1440 / 1180 / 1024 / 768 / 600 / 390** × 5 视图（新建、结果-报告、结果-深度、结果-矩阵、历史）+ 补录弹窗 + loading 弹窗
3. 核验点：桌面观感不变；各档无横向溢出；窄屏表格横滚且首列跟随；顶栏/弹窗不溢出；触屏端说明 tooltip 不再超屏
4. `python -m pytest tests/ -q` 确认引擎侧零影响（本次不碰 Python）

**改动文件**：`ui/app/css/app.css`、`ui/app/index.html`、`ui/app/js/page-result.js`、`ui/app/js/page-new.js`