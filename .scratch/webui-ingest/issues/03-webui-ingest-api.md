# 工单 03：webui 接入 API（后端）

- blockers：01（结构化违例/预填）、02（save/list）
- 决策依据：[ADR-0013 修订 1](../../../docs/adr/0013-enterprise-data-ingestion.md)（必读）
- 惯例：对齐 [ADR-0012](../../../docs/adr/0012-ui-webapp-form.md)（UiApp 纯方法 +
  HTTP 薄壳，测试不起 socket——见 tests/test_webui.py）

## 背景

webui 现状：GET 5 个 + POST 仅 `/api/run`（`_dispatch_post` 硬编码，webui.py:372）；
`api_run` 只认 `fixtures/companies/<c>`；`/api/companies` 只扫 fixtures。上传走
**原始字节流**（filename 放请求头），零 multipart、零新依赖。

## 任务（ipo_eval_lab/webui.py）

1. POST 分发扩展为路由表。
2. `POST /api/ingest/upload`：body = xlsx 原始字节。
   - 请求头 `X-Filename`（URL 解码）：**必须 .xlsx 后缀 + 白名单净化**
     （`[A-Za-z0-9_().\-一-龥 ]+`，拒绝路径分隔符/`..`），坏名 400；
   - `Content-Length ≤ 10MB`，超限 413；
   - `X-Company-Id` 可选（`[a-z0-9_]+`，非法 400）；缺省 `ent_YYYYMMdd_N`（同日序号）；
   - 落 `.scratch/ingest/uploads/<ts>_<净化名>`（返回 `upload_id` 供预填），
     `import_profile(x, company_id, out_root=.scratch/ingest)`；
   - 响应：`{status: ok|violations, violations[](结构化), derived[], company_id,
     session_dir, upload_id, preview{display_name, fiscal_years[], revenue[], np[],
     audit_opinion}}`；违例时不落盘、无 session_dir。
3. `POST /api/ingest/save`：`{company_id, session_dir, overwrite?}` →
   `save_enterprise(...)`；`SaveRefused` → **409 + `{existing:{imported_at,
   source_sha256}}`**（覆盖确认弹窗的指纹数据）。
   - **路径安全**：`session_dir` resolve 后必须位于 `.scratch/ingest` 之下，否则 400
     （防任意目录拷贝进 enterprises/）。
4. `GET /api/ingest/prefill/<upload_id>`：按 upload_id 找源件与已存违例 →
   `build_prefill_template` → xlsx 文件流（不存在/过期 → 404）。
5. `GET /api/enterprises`：`list_enterprises(enterprises_root)`。
6. `api_run` 主体解析：fixtures 未命中 → 查 `enterprises/<company_id>`
   （`UiApp` 增 `enterprises_root`，缺省 `REPO/enterprises`）；`/api/companies` 响应
   增 `enterprises` 分组（现有 fixtures 键不动，前端渐进迁移）。

## TDD

`tests/test_webui_ingest.py` 先红（UiApp 方法直调）：好件上传（含中文文件名）→ ok +
preview 字段；坏件 → violations 结构化含坐标且未落盘；护栏逐条（.exe 400、>10MB 413、
`../` 文件名 400、坏 company_id 400、越权 session_dir 400）；save 冲突 409 带指纹 →
overwrite 成功；api_run 跑企业主体（ent 目录 + fixtures sanity.yaml）出 200 且
`data_source == "enterprise"`；prefill 端点返回 xlsx 字节。

## 出界

前端页面（04/05）；在线编辑；鉴权（安全边界仍单用户本地，ADR-0012）。
