# 工单 01：违例结构化 + 预填模板（ingest 层）

- blockers：无
- 决策依据：[ADR-0013 修订 1](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

webui 要把违例渲染成分组清单、并生成「预填模板」（正确值回填、错误格清空标红批注），
前提是违例是**结构化数据**而非纯字符串。CLI 输出格式不变（向后兼容）。

## 任务

1. `ipo_eval_lab/ingest/importer.py`：
   - 新增 `Violation` frozen dataclass：`sheet / coord（可空）/ label / reason`，
     `__str__` 产出与现状一致的行文（`财务三年一期!C2 营业收入（元）：必填缺失`；
     无坐标的勾稽违例只输出 reason 主体）。
   - `IngestResult.violations` 类型改 `list[Violation]`：格层违例带坐标；勾稽层
     （`FixtureDataError.messages`）包装为 `coord=None` 的 Violation。
   - 同步更新 `tests/test_ingest_violations.py`（成员断言改对 `str(v)`）与
     `__main__.py` 打印（f-string 走 `__str__`）；CLI e2e 测试（test_ingest_cli.py）
     不回退。
2. 新增 `build_prefill_template(src_xlsx, violations, out_path) -> Path`（建议放
   `ingest/prefill.py`）：openpyxl 复制客户原件；对每个带坐标的违例——该格**清空** +
   红 `PatternFill` + `Comment(reason)`；无坐标格不动。正确值原样保留。

## TDD

`tests/test_ingest_prefill.py` 先红：
- 坏样例（缺 C2 + D18 枚举错）→ import → violations 全为 Violation 实例且
  `str(v)` 含坐标/字段名；预填件 C2/D18 为空且带批注与红底；
- 预填件**其余格值与原件逐格一致**；
- 把预填件的错误格填回样例正确值后重导 → `status == "ok"`（闭环：客户改完能过）。

## 出界

webui API（工单 03）；不做在线编辑。
