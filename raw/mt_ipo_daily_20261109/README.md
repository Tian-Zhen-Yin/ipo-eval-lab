# mt_ipo 预置数据导出（2026-11-09）

- **来源**：daily TP 分库1（JumpServer 隧道 `jumper-dev.yonyoucloud.com:33061`，只读 ro_all_db），schema=`mtd_base`，租户 `0000MMCSL4RK60WM270000`，全部按 `ytenant_id='0'`（预置）过滤
- **用途**：ipo-eval-lab M1（规则库初版导出）与 M4（校准+evidence）的原始底稿；列结构见 `_schema.json`
- **多语**：`*_i` 表为主表的 locale 扩展（实测 3 个 locale）；主表内也有 name1~name6/suffix1~suffix6 内嵌多语列，两套并存

## 行数（daily 实际值 vs midas 种子 SQL）

| 表 | daily | 种子 SQL | 漂移 |
|---|---|---|---|
| mt_ipo_evaluation_item | 61 | 61 | - |
| mt_ipo_evaluation_standard | 63 | 61 | +2 |
| mt_ipo_eval_thresold | 234 | 227 | +7 |
| mt_ipo_rel_std_board | 100 | 98 | +2 |
| mt_ipo_std_cpy_type | 120 | 118 | +2 |
| mt_ipo_listing_standard | 185 | 178 | +7 |
| mt_ipo_listing_board | 5 | 5 | - |
| mt_ipo_company_type | 4 | 4 | - |
| mt_ipo_evaluation_dim | 4 | 4 | - |
| mt_ipo_keyword | 20 | - | - |
| mt_ipo_industry | 1751 | - | 未导出 |

**结论：daily 已有 patch 增量，以本导出为准，勿用 midas 仓库种子 SQL 直接当现状。**

## 枚举解码（已核对 midas 源码 CompareOpEnum / DataFormatEnum）

- `op`：1=EQ 等于、7=GT 大于、8=GE 大于等于（本数据只用这 3 种：EQ 61 / GT 58 / GE 115）
- `format`：0=BOOLEAN、1=INTEGER、2=NUMBER、3=PERCENT、4=TEXT（本数据：BOOL 61 / INT 7 / NUM 134 / PCT 32）
- `type`（测评项）：1=固定展示、2=条件类需底稿填写、NULL=取数类（本数据：6/5/50）

## 关键结构发现（拍平与校准的依据）

1. **阈值是双外键**：`std_id` + `eval_item_id`——同一测评项在不同标准下有不同阈值（61 项全部有阈值，30 项挂多阈值；check01 市值挂 35 条阈值横跨几乎全部标准）。per-item × per-standard-set 拍平的数据基础已存在
2. **`mt_ipo_listing_standard` 是"上市标准套"的事实载体**：`board_id` + `company_type_id` + `asset_name`（即标准套名，如"市值+净利润"、"市值+营收+科研能力+特殊企业"）+ `requirement` 文本。D4 决策"标准套一等公民"应从这里提取
3. **`mt_ipo_evaluation_standard.name` 全部为 NULL**（只有 code `IPO-xx`）——标准无可读名，需靠 listing_standard 文本或阈值反推
4. 公式语法实测：`RAW()`（底稿直取）、`DB($指标,#N)`（第N年）、`AVG($指标,~N)`、`SUM($指标,~N)`，与 FormulaFactory 一致

## 已知异常（M1 导出/校准清单要处理）

- ~~`index_source` 前缀不一致~~ **2026-11-09 修正：不是异常**。`ads_mt_ads_innovation_capability` 就是该表在 AP 数据中台的**真实物理表名**（见 `../ads_daily_20261109/`），index_source=物理表名，7 项引用一致正确
- `mt_ipo_std_cpy_type` 列名拼写错误：`cpy_ytpe_id`（少 r）
- `mt_ipo_evaluation_item` 中 6 项 type=1 但 index_source=底稿、formula=RAW、format=PERCENT/INTEGER（check38 公开发行比例、check50 发明专利数等"固定展示+可判定"混合项）
- 维度标准分布不均：财务 38 / 板块定位 21 / 主体资质 3 / 治理运营 1
