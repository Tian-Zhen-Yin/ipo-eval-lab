# 接入演示原型（ZCode Sites 线上物的本地母本）

线上：https://ent-ingest-demo-dob8.zai.site （stage 由 `.zcode-site/` 打包，重发前先重建）

## 构成

- `app/`：真实 webui 前端的副本，仅两处改动——`js/api.js` 换成 mock 层（GET 读
  `mock/*.json`，POST 走内嵌剧本，上传按文件名路由：名含「坏」→违例、含「示例」→
  通过、其余→缺必填）；模板/预填下载链接指向静态 `mock/*.xlsx`。
- `mock/`：内嵌数据。`companies.json` 四家示例主体 + `enterprises.json` 华晟（企业
  通道）+ `results/` 五份**真实引擎跑出的结果 JSON**（勾稽自洽、法条引用内洽）。
- `demo.mp4`：63 秒实录（本原型站录制，与访客所见一致；分段素材在 `recordings/proto2-r*.webm`）。
- `gen_mock.py`：五主体构造 + 引擎跑结果的一键再生成。

## 五主体阵容（覆盖不同运营状况）

| id | 公司 | 画像 |
|---|---|---|
| hengyue_heavy | 恒岳重型装备 | 主板蓝筹·稳健盈利（82→90.5 亿） |
| lanting_bio | 苏州澜庭生物医药 | 科创高增长·研发驱动 |
| guiyan_chip | 无锡硅研微电子 | 亏损收窄（loss_making） |
| chuyuan_textile | 楚源纺织科技 | 业绩大幅下滑 |
| hszn_01 | 深圳华晟智能装备 | 企业接入主体（xlsx 导入链路演示） |

## 再生流水线

1. `python gen_mock.py`（重造 mock 数据；数字改动需过勾稽①~⑤与⑥卫生区间）
2. 改 `app/` 如需；同步 `cp -R mock /tmp/proto/` 本地试（注意 python http.server 无
   no-cache，验前强刷）
3. 重录视频：浏览器五段录（R1 模板→R2 违例→R3 预览保存→R4 测评→R5 历史）+
   ffmpeg concat → 替换 demo.mp4
4. 重建 stage：`app/* + mock + demo.mp4 → .zcode-site/stage/dist/`，套 site-deploy
   模板后 `check` + `deploy`（同站点链接不变）
