# 工单 05：CLI 入口 + enterprises/ 保存与防覆盖

- blockers：02
- 决策依据：[ADR-0013](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）

## 背景

ADR-0013：CLI 先行（webui 上传页后置）。默认落 `.scratch/ingest/`（可清理）；
`--save` 才永久入 `enterprises/<company_id>/`（gitignore）；`--save` 遇已存在
**报错**，须显式 `--overwrite`——不可再生数据永不静默覆盖。

## 任务

1. `ingest/__main__.py`：
   `python -m ipo_eval_lab.ingest <客户.xlsx> --company-id <id> [--save] [--overwrite] [--out-root DIR]`
   - 成功：打印 `company_dir` + derived 字段清单（人读格式）；exit 0。
   - 违例：打印收集式报告（勾稽号/中文字段/sheet 行号），**不落盘**；exit 1。
   - `--save` 且 `enterprises/<company_id>/` 已存在且无 `--overwrite`：报错提示
     「须 --overwrite 或更换 company_id」；exit 2。
2. `.gitignore` 追加 `enterprises/`（先查现状再追加，勿重复）。
3. run 联动：`--save` 保存后的目录可直接被 `run_eval(company_dir=...)` /
   webui 选择跑（依赖工单 04 的企业模式，验证一次端到端即可）。

## TDD

`tests/test_ingest_cli.py` 先红（subprocess 或直接调 main(argv)）：
成功/违例/防覆盖三态 + `enterprises/` 已进 `.gitignore`（读文件断言）。
端到端：save 后目录 `run_eval` 跑通且⑥不误伤。

## 出界

不做 webui 上传页；不做模板版本迁移。
