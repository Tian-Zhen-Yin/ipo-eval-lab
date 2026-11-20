# 工单 04：前端「数据接入」页

- blockers：03
- 决策依据：[ADR-0013 修订 1](../../../docs/adr/0013-enterprise-data-ingestion.md)
- 惯例：ui/app/ 原生 ES module、零构建零 npm（ADR-0012 P2）；样式沿用现有契约级
  CSS（五态色板 ADR-0003 不动——本页是工作流页，不涉五态）

## 任务（ui/app/）

1. `index.html`：导航加「数据接入」+ 页容器；`main.js` 路由注册。
2. 新建 `page-ingest.js` 四态工作流：
   - **空态**：拖拽/选择 xlsx（dropzone；非 .xlsx 拒收，前端先拦一道）；
   - **违例态**：清单按「格错（有坐标）/ 账不平（勾稽号）」分组渲染，红字 +
     `sheet!坐标`；按钮「下载违例报告」（文本，含全部违例）与「下载预填模板」
     （GET /api/ingest/prefill/<upload_id>）；顶部保留「重新上传」；
   - **预览态**：主体卡（display_name、年度、营收/归母净利摘要、审计意见）+
     derived 清单（黄色警示样式，文案「客户留空，系统按会计恒等式推导」）；
     「保存主体」按钮（高级折叠：自定义 company_id 输入，`[a-z0-9_]+` 校验）；
   - **保存冲突态**：409 → 确认弹窗显示**原导入时间 + sha256 前 8 位**
     （「覆盖将替换以上主体数据，不可再生、请确认」）→ 覆盖/取消；
     保存成功 → 跳「新建测评」并预选该主体。
3. `api.js`：`uploadIngest(file, companyId?)`（FileReader→ArrayBuffer，fetch POST，
   `X-Filename: encodeURIComponent(file.name)`）、`saveIngest(...)`、
   `fetchPrefillUrl(id)`；`dialogs.js` 复用现有弹窗/焦点陷阱骨架。
4. 上传中/校验中 loading 态（import_profile 秒级，转圈即可）。

## 验证

无 JS 测试基建（现状即无）：起 webui（127.0.0.1）+ browser-use 实测四态截图走查
（空态/违例态/预览态/冲突态），与工单 03 的后端测试互补；中文文件名上传链路必测。

## 出界

新建页/历史页改动（05）；模板在线编辑。
