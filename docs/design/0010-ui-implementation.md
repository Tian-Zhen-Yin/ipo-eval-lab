# 设计 0010：前端实现布局与 API 契约（M-UI）

> 拍板（2026-11-13，P1~P3 全按推荐）：形态见 [ADR-0012](../adr/0012-ui-webapp-form.md)。
> 交付分 3 阶段，每阶段 git 检查点。呈现规范以 [设计 0007](0007-ui-prototype.md) 为唯一基准
> （五态色板 / 进度覆盖率双指标 / 三页签分区 / 措辞禁令全部沿用，不在本文重复）。

## 1. 目录布局

```
ipo_eval_lab/webui.py        # 本地服务（http.server，只绑 127.0.0.1；python -m 启动）
ui/
  prototype.html             # 设计 0007 交付物，只读不动
  app/
    index.html               # 三页骨架（迁移原型 HTML，删 mock 内容节点）
    css/app.css              # 原型契约级 CSS 迁移 + 数据态扩展
    js/main.js               # 入口 / 页路由 / init
    js/api.js                # fetch 封装
    js/adapters.js           # result.json / 规则库 → 视图模型（唯一知道契约键名的文件）
    js/format.js             # 五态徽章 / 单位 / tabular-nums 格式化
    js/dialogs.js            # 弹窗 + 焦点陷阱 + 补录表单
    js/page-new.js / page-result.js / page-history.js
tests/test_webui.py          # handler 纯函数测试（不起真 socket）
```

数据层铁律：**只有 `adapters.js` 允许出现契约键名**（`layers.gap.progress` 之类），
页面代码只消费视图模型——引擎字段改名时只改一处。

## 2. API 契约（v1）

| 方法 | 路径 | 返回 |
|---|---|---|
| GET | `/` 与 `/static/*` | `ui/app/` 静态资源（Content-Type 按扩展名；路径归一化防目录穿越） |
| GET | `/api/meta` | `{rulebook_version, boards[], company_types[], declared_no_sets[][]}` |
| GET | `/api/rulebook` | `{meta, items:{item_id:{display,nature,quantifier,window}}, groups:[组摘要]}` |
| GET | `/api/companies` | `[{id, display_name, fiscal_years, company_type}]`（读 fixtures/companies/*/profile.json） |
| GET | `/api/results` | `[{file, run:{company_id, as_of_date, …}}]`（results/*.json 索引，按 mtime 倒序） |
| GET | `/api/results/<file>` | 该 result.json 全文（文件名白名单校验：仅 `results/` 下 `*.json`） |
| POST | `/api/run` | 入参 `{company, as_of?, boards?, sets?, overrides?}` → 引擎 → `{file, summary}` |

**组摘要**（scope 三段同形）：`{scope, group_id, display, boards[], company_type,
group_no?, section?, effective_from, law_refs[], hard_filters[]?, shared_clauses[]+branches[].clauses[]}`；
条款摘要含 `clause_id/display/law_ref/logic` 与 `leaves[]`（`leaf_id/item_ref/op/threshold`）——
新建页套卡的阈值摘要行与结果页条文对照都从这一份取。

**POST /api/run 语义**：
1. `overrides: {documentary?: {...}, declared?: {...}}` 非空时，把 base profile 拷贝到
   `.scratch/ui-runs/<run_id>/profile.json` 再合并覆盖（`null` 值 = 清空该字段，
   引擎自然落 indeterminate——缺数据≠0）；真实 `fixtures/` 永不写。
2. `run_eval(company_dir, rulebook_dir, fixtures_root, as_of, RunTarget(boards, sets))` 进程内调用。
3. 结果落盘 `results/<company>_<asof>.json`（CLI 同约定）；文件已存在或带 overrides 时
   追加 `_<HHMMSS>` 防覆盖。返回 `{file, summary:{state_counts, applicable, …}}`。
4. 引擎错误（lint 红 / 勾稽红 / 公司不存在）→ HTTP 400 + `{error}`，不落半截文件。

## 3. 阶段划分

| 阶段 | 内容 | 出口判据 |
|---|---|---|
| 0 | 服务骨架 + 本文档 + ADR-0012 + test_webui | pytest 绿；`/api/rulebook` 返回 36 组 |
| 1 | 结果页接真数据（三页签全量） | base/qualified/unaudited 三份产物渲染无 KeyError |
| 2 | 新建页：28 套套卡 + 表单联动 + 补录弹窗 + POST /api/run | 新建→跑→跳结果页全链路通；V16 占位文案删除 |
| 3 | 历史页 + V17 跨列口径切换 + CONTEXT 更新 + 全站验收 | 浏览器走查三页 + pytest 全绿 |

## 4. 与原型的差异清单（迁移时逐项处理）

1. 13 个 mock 常量（SETS/ISSUANCE/POSITIONING/ATTR/HIST/ROLL/MX/SUP/SCEN/BASIS_DETAIL…）全部退役，由 `/api/*` 数据驱动。
2. 16 处内联 `onclick` 改事件委托（原型 v0.2 叶表已是委托，沿用该模式）。
3. `stdFor()` 沪主板短路 → 板块×类型×28 套真数据分组（V16 关闭）。
4. 五态筛选加「任一列命中 / 全部列命中」口径切换（V17 关闭）。
5. 历史页窗口滚动图：results/ 样本稀疏时降级为占位说明（不编造数据）。
6. 键盘可达性（`.kb-ring` 焦点环 / Esc / 焦点陷阱 / `aria-expanded`）按原型 v0.4 机制原样迁移。
