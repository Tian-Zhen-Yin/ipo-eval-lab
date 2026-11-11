# 上市法规原文归档（设计 0009 §2.1）

本目录存储各交易所最新上市规则的官方 PDF 文档，是规则库权威源链的起点。

## 归档规则

| 板块 | 文件名 | 官方规则名称 | 官方地址 | 生效日 |
|---|---|---|---|---|
| 上交所主板 | sse_main_2026.pdf | 上海证券交易所股票上市规则（2026年4月第二十次修订） | https://www.sse.com.cn/lawandrules/sselawrules/listing/main/ | 2026-04 修订（精确施行日待核） |
| 上交所科创板 | sse_star_2026.pdf | 上海证券交易所科创板股票上市规则（2026年4月第六次修订） | https://www.sse.com.cn/lawandrules/sselawrules/listing/star/ | 2026-04 修订（精确施行日待核） |
| 深交所主板 | szse_main_2026.pdf | 深圳证券交易所股票上市规则（2026年4月第十七次修订） | https://www.szse.cn/lawrules/ → 本所业务规则 → 股票类 | 2026-04 修订（精确施行日待核） |
| 深交所创业板 | szse_chinext_2026.pdf | 深圳证券交易所创业板股票上市规则（2026年4月第十一次修订） | https://www.szse.cn/lawrules/ → 本所业务规则 → 股票类 | 2026-04 修订（精确施行日待核） |
| 北交所 | bse_2026.pdf | 北京证券交易所股票上市规则（2026年4月24日第四次修订） | https://www.bse.cn/business/fxrz_list.html | 2026-04-24 |

## 切分产出（2026-11-11）

| law_id | 条文数 | 校验 |
|---|---|---|
| sse_main_2026 | 526 | 条款号连续，无告警 |
| sse_star_2026 | 406 | 条款号连续，无告警 |
| szse_main_2026 | 520 | 条款号连续，无告警 |
| szse_chinext_2026 | 390 | 条款号连续，无告警 |
| bse_2026 | 379 | 条款号连续，无告警 |

切分器与校验逻辑见 `ipo_eval_lab/legal/extract.py`；元数据见 `rulebook/source_texts/_meta.yaml`。

## 校验步骤

1. 下载后计算 SHA256 哈希，写入 `rulebook/source_texts/_meta.yaml` 的 `checksum` 字段
2. 确认生效日（通常在规则正文首页或修订通知中）
3. 确认版本号（如"2026年修订版"）

## 注意事项

- 只收录官方发布的 PDF/HTML 文档，不收录第三方转载
- 下载日期：2026-11-11
- 本目录为 D1「只消费本地文件」原则的唯一输入源
