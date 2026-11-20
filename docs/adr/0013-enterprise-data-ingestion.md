# ADR-0013：企业数据接入——标准模板 Excel + 三件套主体目录（代跑起步阶段）

- 状态：Accepted（2026-11-20，用户拍板 Q1~Q13 均按推荐）
- 关联：**修订 [CONTEXT](../../CONTEXT.md) D1**「企业数据 = mock」边界——真实企业数据经模板接入进入范围；[设计 0006](../design/0006-mock-data-contract.md)（勾稽①~⑥与 sanity 卫生参数语义，本 ADR 的分流对象）；[ADR-0012](0012-ui-webapp-form.md)（`.scratch` 会话目录先例、单用户本地工具安全边界）

## 背景

引擎数据入口至今只有 `fixtures/`（mock 主体 4 家 + `sanity.yaml`）。真实客户要用自身
数据评测。既有事实：`run_eval()` 只吃 `company_dir`（schema 严格的 `profile.json`，经
`load_company()` 勾稽①~⑥校验）；webui 补录已有 `.scratch/ui-runs/<id>_<ts>/` 会话目录
模式；勾稽⑥区间按设计 0006-F3 是「mock 生成器卫生参数，非法规语义」，对真实企业
（如净利 −80% 下滑）会误伤。交付形态：客户把数据交给运营方**代跑**起步，模块按
可整体**私有部署**设计。

## 决策

**通道与起点**：唯一入口是标准填写模板 Excel——客户财务填「3 个完整会计年度 +
可选 1 期」，模板列结构写死。审计报告 PDF/Word 解析**不做**（版式不可控，二期再议）。
工具形态 CLI 先行（`python -m ipo_eval_lab.ingest 客户.xlsx --company-id <id> [--save]`），
webui 上传页后置到私有部署阶段。

**分层模板**：必填 = 主表行（营收、净利总额、归母申报+扣非可选、研发两源可选、OCF、
总资产、总负债、归母权益、审计三字段；另首年期初归母权益——推导不可行，事实必填）；
可选 = 勾稽行（少数权益、分红、增资、调节表）——填了照常勾稽校验（保留拦截力），
缺了由导入器推导、导入报告列 `derived` 清单（两项分红/增资都缺时残差归 dividends、
injection=0，报告披露）。documentary/declared 申报口径做独立 sheet，**留空合法**
（null → indeterminate）。

**勾稽分流（企业模式）**：企业数据保留①②③④⑤（会计恒等式+连续性——不过 = 搬运
错误，正好拦截），**跳过⑥**。由目录自描述驱动：`load_company()` 见 `ingest.json`
即按企业模式校验——签名与调用方（CLI/webui/runner）零改动。

**三件套主体目录契约**：`profile.json` + `source.xlsx`（客户原件快照）+ `ingest.json`
（`data_source: "enterprise"`、`derived_fields[]`、模板版本、原件 sha256、导入时间）。
run 结果 meta 打 `data_source: fixture | session | enterprise`。

**落盘与防丢**：默认落 `.scratch/ingest/<company_id>_<ts>/`（可整目录清理）；`--save`
显式入 `enterprises/<company_id>/`（gitignore，与 `fixtures/companies` **物理分离**，
防 golden/勾稽逻辑误伤）。`company_id` 由运营方分配（客户缩写+序号），客户自填名称
只进展示字段、不进路径。`--save` 遇已存在目录**报错**，须显式 `--overwrite`——
不可再生数据永不静默覆盖。

**模块形状**：`ipo_eval_lab/ingest/` 对外唯一入口
`import_profile(xlsx_path, company_id, out_root=None) -> IngestResult`
（`status: ok|violations`、`company_dir`、`violations[]` 收集式带 sheet/行号/勾稽号、
`derived_fields[]`）；违例**不落盘**。模板字段坐标常量与 importer 共用一份定义；
手工维护财务友好模板 + golden 对拍测试（样例模板 → 导入 → 期望 `profile.json`）
锁住「模板↔schema」不脱钩，样例一份三用（客户底稿/测试夹具/使用说明）。
**接缝收在 `CompanyProfile` schema——引擎不知道 Excel 的存在。**

**依赖**：引入 `openpyxl`（项目**首个**第三方运行时依赖，仅 ingest 模块使用）——
模板必须真 xlsx（客户财务的交付格式），手写 zip+xml 解析维护成本高于这唯一依赖；
ADR-0012 P1 的 webui「零新依赖」范围不变。

## 不做的事

- 不做多租户/在线注册/鉴权（非 SaaS；安全边界同 ADR-0012：单用户本地工具）；
- 不做自由格式 Excel 的自动列映射/字段推断（只认标准模板）；
- 不做脱敏/加密（代跑阶段；私有部署阶段经 `ingest.json` 扩展，不动契约主体）；
- 不动 `fixtures/`（mock 与真实数据物理分离）。

## 影响

- 新增：`ipo_eval_lab/ingest/`（template/importer/`__main__`）、`enterprises/`（gitignore）、
  `.scratch/ingest/`、`tests/test_ingest_*.py`。
- 修改：`load_company()` 增「见 `ingest.json` → 企业模式（⑥跳）」行为分支；
  run 结果 meta 增 `data_source`；[CONTEXT](../../CONTEXT.md) D1 修订（本 ADR）。
- 实现工单：`.scratch/ent-ingest/issues/`（01~05，blockers-first：01 → 02 → {03, 04, 05}）。
