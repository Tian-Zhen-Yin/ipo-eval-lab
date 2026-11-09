# ADS 模型数据同步（2026-11-09）

- **来源**：daily AP 数据中台（同隧道 `jumper-dev.yonyoucloud.com:33061`），schema = **`s_0000mmcsl4rk60wm270000`**（租户 ID 全小写），租户 `0000MMCSL4RK60WM270000`，只读 ro_all_db
- **范围**：IPO 测评 `index_source` 指向的 4 个模型物理表，**全量同步**（行数小，无需期间过滤）；`*_backup` 表未同步（index_source 不引用）
- **用途**：ipo-eval-lab 的 mock 企业数据底稿（D1）；列结构见 `_schema.json`（含列 comment）

## 同步清单

| 表 | 行 | 列 | 期间范围 | 组织数 |
|---|---|---|---|---|
| mt_ads_profitability_cf | 351 | 140 | 2021-12 ~ 2026-12（57 个 period_code） | 37 |
| mt_ads_funds_cash_analysis | 351 | 127 | 2021-12 ~ 2026-12 | 37 |
| mt_ads_equity_analysis | 268 | 26 | 2022-01 ~ 2026-12 | **8**（覆盖缺口） |
| ads_mt_ads_innovation_capability | 349 | 22 | 2021-12 ~ 2026-**10**（滞后） | 37 |

## 数据结构要点（本地引擎取数契约的输入）

- **期间粒度=月**：`period_code` 形如 `2023-12`（另有 `year`/`month` 列），一年多个期末快照；公式 `~近N年`/`#第N年` 的取数要按年选期——**选哪个 period_code（年末 12？最新≤年末？）是 grilling 待定问题 #4 的输入**（midas 侧逻辑在 `IpoFetchAdsDataServiceImpl`，可在 midas 仓库核对）
- **组织列**：`dim_y_rpt_org` + `dim_y_rpt_org_name`（与 midas 看板侧 `consol_org→dim_y_rpt_org` 一致）
- **指标列命名**：`<指标>_<口径>_<币别>_<模型>` 后缀，如 `operating_revenues_ytd_bl_cf`（ytd 累计 / bl 本位币 / cf 模型代号）；同一指标存在 `_ytd_`/`_ptd_`（当期）、`_yb_`/`_pe_`/`_pb_` 多口径变体——公式只引用 ytd/bl 口径
- 每表带 `ytenant_id`、`all_dimension_md5`（维度指纹）、`dw_data_from`（数据来源标记）、`dim_y_ana_month`
- **覆盖率缺口**：equity_analysis 只有 8 个组织（其他表 37 个）；innovation 期间滞后到 2026-10——做 mock 边界样本时要注意口径差异本身就是测试素材

## 公式指标列覆盖校验（已闭环）

61 项测评项 = 32 底稿项（不查 ADS）+ 29 ADS 项；29 项公式引用的 **10 个去重指标列全部命中**同步 CSV：

| 表 | 引用列 |
|---|---|
| mt_ads_profitability_cf (5) | `operating_revenues_ytd_bl_cf`、`net_profit_ytd_bl_cf`、`net_profit_attrib_parent_excl_extra_ytd_cf` 等 |
| ads_mt_ads_innovation_capability (3) | `rd_investment_ytd_bl_cf`、`rd_personnel_ratio_pe_bl_cf`、`intensity_develop_invest_cf` 等 |
| mt_ads_funds_cash_analysis (1) | `net_cash_flow_from_oper_cf` |
| mt_ads_equity_analysis (1) | `equity_avg_cf` |

（完整清单以 mt_ipo_evaluation_item.json 的 formula 为准）
