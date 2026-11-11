# 设计 0009：上市法规原文库（#9-V8 缺口补齐）

- 日期：2026-11-11
- 性质：**#9-V8「法规原文库 `source_texts/` 不存在」** 方案设计
- 上游：D4 权威源链（法规原文 → 规则库 YAML）、设计 0003 校准管线
- 拍板：**P1 范围** = 只做原文库（切分 + 逐字条文）；P2 切分 = 混合·结构优先；P3 获取 = 浏览器半自动下载

---

## 0. 缺口确认

| 编号 | 内容 | 状态 |
|---|---|---|
| #9-V8 | 法规原文库 `source_texts/` 不存在（M1 前置子项） | **本设计补齐** |

设计 0003 §2 定义了「原文库」形态：
```
原文库（每条带：文档名/版本/生效日/条款号/正文）
```

这是权威源链的起点，也是 L0-8 版本对齐、L1b 引文防编造的前置。

---

## 1. 设计总则

### 1.1 职责边界

| 职责 | 是/否 | 说明 |
|---|---|---|
| 官方文档获取 | 是 | 用 browser-use 技能驱动浏览器下载 |
| 文档切分（条文级） | 是 | 混合·结构优先（正则/状态机 + 向量兜底） |
| 结构化提取（leaf/clause/branch） | **否** | 留给设计 0003 校准管线（L1 提取闸门） |
| 沪深同文归并 | 兜底 | 向量相似度判断是否为同一文本（设计 0003 无此需求，但设计 0001 P1 提到 43 套合并 34 个沪深同文） |

### 1.2 独立性保证

| 独立性来源 | 说明 |
|---|---|
| 数据视图独立 | 原文库 = 逐字权威源，不依赖任何规则库实例 |
| 可复算性 | 结构解析规则（正则/状态机）+ 向量相似度阈值 = 可重复 |
| 可审计性 | 每条条文带 `source_ref`（原文段落 offset），可追溯回文档 |

---

## 2. Schema 设计

### 2.1 目录结构

```
raw/legal_docs_<YYYYMMDD>/
├── README.md                # 归档元数据：各板块文档来源、版本、生效日
├── sse_main_2026.pdf        # 上交所主板上市规则
├── sse_star_2026.pdf        # 科创板上市规则
├── szse_main_2026.pdf       # 深交所主板上市规则
├── szse_chinext_2026.pdf    # 创业板上市规则
└── bse_2026.pdf             # 北交所上市规则

rulebook/source_texts/       # 输出：逐字条文库（YAML）
├── _meta.yaml               # 元数据：版本映射、切分配置
├── sse_main_2026.yaml
├── sse_star_2026.yaml
├── szse_main_2026.yaml
├── szse_chinext_2026.yaml
└── bse_2026.yaml
```

### 2.2 YAML 格式（单文件）

```yaml
# rulebook/source_texts/sse_star_2026.yaml
law_id: sse_star_2026
title: 上海证券交易所科创板股票上市规则
source_type: exchange_rule
effective_from: 2024-04-30    # 对应 README 中确认的生效日
source_ref: raw/legal_docs_20261111/sse_star_2026.pdf  # 归档文件路径
downloaded_at: 2026-11-11
checksum: sha256:abcd1234...   # 文档哈希，防篡改

articles:
  - article: "2.1.2"
    chapter: "第二章 首次公开发行股票并上市"
    section: "第一节 上市条件"
    text: |-
      发行人申请股票上市，市值及财务指标应当至少符合下列各项标准之一：
      （一）预计市值不低于人民币 10 亿元，最近两年净利润均为正且累计净利润不低于人民币 5000 万元，或者预计市值不低于人民币 10 亿元，最近一年净利润为正且营业收入不低于人民币 1 亿元；
      （二）预计市值不低于人民币 15 亿元，最近一年营业收入不低于人民币 2 亿元，且最近三年累计研发投入占最近三年累计营业收入的比例不低于 15%；
      ……
    source_offset: {page: 15, start: 120, end: 450}  # PDF 字节/字符偏移，可追溯
    extracted_at: 2026-11-11T10:30:00
    confidence: high                                  # high / medium / low（向量兜底段）
    extraction_method: regex                          # regex / vector / manual
```

### 2.3 元数据文件

```yaml
# rulebook/source_texts/_meta.yaml
rulebook_version: rb-2026.11
source_docs_version: 2026-11-11

version_mapping:
  sse_main_2026:
    doc_name: 上海证券交易所股票上市规则
    official_url: https://www.sse.com.cn/lawandrules/sselawrules/listing/main/
    effective_from: 2024-04-30
    file: raw/legal_docs_20261111/sse_main_2026.pdf
  sse_star_2026:
    doc_name: 上海证券交易所科创板股票上市规则
    official_url: https://www.sse.com.cn/lawandrules/sselawrules/listing/star/
    effective_from: 2024-04-30
    file: raw/legal_docs_20261111/sse_star_2026.pdf
  # ... 其他板块

extraction_config:
  regex_patterns:
    chapter: r"第[一二三四五六七八九十]+章"
    section: r"第[一二三四五六七八九十]+节"
    article: r"第[0-9]+条"
    subsection: r"[（一二三四五六七八九十]+]"
  vector_similarity_threshold: 0.85    # 沪深同文归并阈值
  fallback_to_llm: true                  # 异常文档是否降级到 LLM
```

---

## 3. 切分方案：混合·结构优先

### 3.1 主干：正则/状态机

交易所规则的结构极其规整：
- 层级：`第X章` → `第X节` → `第X条` → `（一）`/`1.`/`2.1.2`
- 位置：章节目录通常在文首，条文正文紧随

解析流程：

```
1. 文档解析（PDF → 文本）
   ├─ pdfplumber / PyMuPDF（优先，保留布局）
   └─ PDFMiner（备选，处理扫描版）

2. 章节目录提取
   ├─ 正则：r"第[一二三四五六七八九十]+章[^\n]+"
   └─ 构建层级树：章 → 节 → 条

3. 条文正文切分
   ├─ 按章节目录定位起始 offset
   ├─ 正则：r"第[0-9]+条[^\n]+\n([\s\S]+?)(?=第[0-9]+条|$)"
   └─ 清理：去除页眉/页脚、空行、格式化标记

4. 条款号归一化
   ├─ "2.1.2" → article: "2.1.2"
   ├─ "第一条" → article: "1"
   └─ 记录原始文本（text 逐字）
```

### 3.2 兜底：向量相似度

触发条件：
- 正则切分失败（异常文档形态：扫描版、表格、多栏）
- 沪深同文归并判断（设计 0001 P1 提到 43 套合并 34 个沪深同文）

向量化方案：
- 模型：text-embedding-3-small / sentence-transformers（本地）
- 粒度：条款级（每条 article 做一个 embedding）
- 阈值：`vector_similarity_threshold = 0.85`（可调）

同文归并输出：
```yaml
# rulebook/source_texts/_meta.yaml 补充
cross_board_equivalents:
  - group_id: "general:1"
    articles:
      - {law_id: sse_main_2026, article: "3.1.2"}
      - {law_id: szse_main_2026, article: "3.1.2"}
    similarity: 0.92
    human_reviewed: false      # 默认待人工确认
```

### 3.3 异常处置

| 异常类型 | 处置 |
|---|---|
| 正则无匹配 | 降级到向量切分（段落相似度）→ confidence=medium |
| 向量也失败 | 降级到 LLM（浏览器下载后，用 browser-use + LLM 抽取）→ confidence=low |
| 文档扫描版 | OCR（tesseract）+ 正则兜底 → 置信度低，人工队列 |

---

## 4. 文档获取：浏览器半自动下载

### 4.1 工具

- **browser-use 技能**（已有）：驱动浏览器访问交易所站点
- 拦截下载链接，保存到 `raw/legal_docs_<YYYYMMDD>/`
- 记录来源 URL、下载时间、文件哈希

### 4.2 流程

```
1. 启动 browser-use → 访问交易所规则列表页
2. 定位各板块最新上市规则链接（标题匹配）
3. 点击下载 → 拦截文件流 → 保存到 raw/legal_docs_<YYYYMMDD>/
4. 记录元数据（source_ref, official_url, effective_from）→ 手工确认生效日
5. 计算文件 checksum（sha256）→ 写入 YAML
```

### 4.3 脚本入口

```bash
# ipo_eval_lab/legal/fetch.py
python -m ipo_eval_lab.legal.fetch \
  --output-dir raw/legal_docs_20261111 \
  --boards SSE-MB SSE-STAR SZSE-MB SZSE-ChiNext BSE
```

---

## 5. 工程落地

### 5.1 模块结构

```
ipo_eval_lab/legal/
├── __init__.py
├── fetch.py          # 浏览器下载（browser-use 技能）
├── parse.py          # PDF → 文本
├── extract.py        # 正则/状态机切分
├── vector.py         # 向量相似度兜底
├── models.py         # Pydantic 契约（Article / SourceDoc）
└── __main__.py       # CLI 入口
```

### 5.2 契约（Pydantic）

```python
# ipo_eval_lab/legal/models.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class SourceOffset(BaseModel):
    page: int
    start: int
    end: int

class Article(BaseModel):
    article: str               # 条款号："2.1.2"
    chapter: Optional[str]     # 所属章节
    section: Optional[str]
    text: str                 # 逐字正文
    source_offset: SourceOffset
    extracted_at: datetime
    confidence: str = "high"  # high / medium / low
    extraction_method: str = "regex"  # regex / vector / manual

class SourceDoc(BaseModel):
    law_id: str
    title: str
    source_type: str = "exchange_rule"
    effective_from: str       # YYYY-MM-DD
    source_ref: str           # 归档文件路径
    downloaded_at: str
    checksum: str
    articles: List[Article]
```

### 5.3 CLI

```bash
# 主流程：下载 → 切分 → 向量兜底 → 输出 YAML
python -m ipo_eval_lab.legal \
  fetch --output-dir raw/legal_docs_20261111 \
  extract --input-dir raw/legal_docs_20261111 --output-dir rulebook/source_texts \
  dedup --input-dir rulebook/source_texts
```

### 5.4 测试

- 单元测试：正则模式匹配、offset 回溯
- 集成测试：小样（科创板 2.1.2 条）切分 + 逐字校验
- 回归测试：原文库哈希不变性（同文档多次切分产出相同 YAML）

---

## 6. 与既有设计的对账

| 设计项 | 关系 |
|---|---|
| D4 权威源链 | 本设计提供「法规原文」入口 |
| 设计 0003 校准管线 | 本设计输出 = L0/L1 输入（原文库） |
| 设计 0001 P1（43 套合并 34 个沪深同文） | 向量兜底段产出 cross_board_equivalents，支撑归并 |
| #9-V8 缺口 | 本设计直接补齐 |

---

## 7. 决策点

| # | 决策 | 结论 |
|---|---|---|
| Q1 | 范围边界 | **只做原文库**（切分 + 逐字条文），结构化提取留给设计 0003 |
| Q2 | 切分方案 | **混合·结构优先**（正则/状态机主干 + 向量兜底） |
| Q3 | 文档获取 | **浏览器半自动下载**（browser-use 技能） |
| Q4 | 向量兜底阈值 | **0.85**（可调，写入 _meta.yaml） |
| Q5 | 异常处置降级顺序 | 正则 → 向量 → LLM → 人工队列 |

---

## 8. 实测勘误（2026-11-11，落地后回填）

落地时以五份真实 PDF 的实测形态**修订 §2.3/§3 的初版假设**：

| 初版假设 | 实测形态 | 处置 |
|---|---|---|
| 条款号 `第X条` 汉字式 | **点分式** `X.Y` / `X.Y.Z`（科创板紧贴正文无空格，其余有空格） | ARTICLE_RE 重写 |
| 页码在页首页尾 | 页码行**位置不定**（提取序任意），形态 `11 ` / `— 11 —` / `- 11 -` | 全行过滤 |
| 无目录噪音 | 目录行含 4+ 半角引导点（正文无此形态） | 整行丢弃 |
| 条文连续不断行 | 硬换行 + 跨页拼接；**引用断行陷阱**：正文「豁免适用第 ⏎ 7.1.17 条第二款」行首条款号被误切 | **判别规则：条款号后紧跟「条」字 = 引用，不切**（定义形态条款号后直接跟正文） |
| vector 兜底 v1 就绪 | 未实现（v2）；本轮五份 PDF 结构规整，纯正则零告警拿下 | pending 记入 _meta.yaml |

**落地产出**（`rulebook/source_texts/`，全部 2026-04 修订现行版，checksum 入档）：
sse_main 526 / sse_star 406 / szse_main 520 / szse_chinext 390 / bse 379，合计 **2221 条**，条款号连续性校验全部零告警。

**校准副产品（原文库实证）**：
1. 上主板 3.1.2 ≍ 深主板 3.1.2（逐字同文，仅「最近3年/最近三年」字面异）——设计 0001「沪深同文合并」实证；
2. 沪深主板上市标准（二）原文确认为「预计市值不低于**50 亿**元」——midas 快照 350 亿笔误（calibration/0001 §3）获原文实证，属 L3 value_diff 案件。

**Q3 处置修订**：交易所站点实测上交所 403 反爬、深交所/北交所 iframe 动态加载，v1 改**手动下载归档**（用户 2026-11-11 完成），浏览器自动抓取留作 v2。
