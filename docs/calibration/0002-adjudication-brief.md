# 校准底稿 0002：套级裁定备料（ADR-0009 B 档，10 项 → 3 个法律问题）

- 日期：2026-11-12
- 性质：**备料底稿，未拍板**。签核队列（as_of 2026-11-12）产出 10 项套级裁定，本稿把它们聚成 3 个底层法律问题，逐个给「引文实证 + 建议结论」；**结论须由用户逐项拍板后**，才用 `adjudicate` 落签核记录。
- 证据口径：引文取自候选库 `source.text`（经 L1b 锚点核验回原文）；原件归档 [raw/legal_docs_20261111](../../raw/legal_docs_20261111)。引文以原件为最终权威。
- 关联：[ADR-0009](../adr/0009-signoff-tiering-and-two-stage-ingestion.md)（裁定挂套级的理由）、[ADR-0008](../adr/0008-exemption-semantics.md)（豁免语义，问题二直接用）、[校准 0001](0001-set-inventory.md)（黄金集）

---

## 问题一：创业板 / 科创板「已在境外上市红筹」上市标准有无法律锚点？（裁定 ×4）

**涉裁定项**：`ChiNext:redchip_listed:1` / `ChiNext:redchip_listed:2` / `STAR:redchip_listed:1` / `STAR:redchip_listed:2`（四项 `no_anchor`，候选库条款数 = 0）

### 引文实证

**「已在境外上市」的红筹量化标准只存在于沪深主板 3.1.4**（沪深同文）：

> 已在境外上市的红筹企业，申请发行股票或者存托凭证并在本所上市的，应当至少符合下列标准中的一项：（一）市值不低于2000 亿元；（二）市值200 亿元以上，且拥有自主研发、国际领先技术，科技创新能力较强，在同行业竞争中处于相对优势地位。——上交所/深交所上市规则 3.1.4

**科创板 2.1.3 与创业板 2.1.3（同构）只覆盖「尚未在境外上市」**：

> 营业收入快速增长，拥有自主研发、国际领先技术，同行业竞争中处于相对优势地位的**尚未在境外上市红筹企业**，申请在科创板上市的，市值及财务指标应当至少符合下列标准之一：……——上交所科创板上市规则 2.1.3（创业板 2.1.3 文字同构）

全文检索（五部法规 185 条文，候选库全文）：

| 法规 | 含「红筹」条款 | 含「已在境外上市」 |
|---|---|---|
| 沪主板 3.1.4 / 3.1.5、深主板 3.1.4 / 3.1.5 | ✓ | **✓（3.1.4）** |
| 科创板 2.1.3 | ✓ | **✗** |
| 创业板 2.1.3 | ✓ | **✗** |
| 北交所 2.1.2 / 2.1.3 | ✗（全文无红筹条款） | ✗ |

**midas 存量佐证**：科创创四套 `redchip_listed` 快照行 = 2000 亿 / 200 亿，与主板 3.1.4 两档**数值完全同构**（calibration/midas_snapshot.yaml 行 264/274/774/784）——佐证「存量沿用主板口径」假设。另注：midas 行 2 只记了市值 ≥200 亿，连主板原文的定性条件「拥有自主研发、国际领先技术…」也没承载。

### 结构解读

科创/创业 2.1.3 第一句（「符合国办发﹝2018﹞21号相关规定的红筹企业，可以申请…上市」）是**准入资格条款**，不是市值及财务指标标准；其后的量化标准被「尚未在境外上市红筹企业」明确限定。即：**现行五部板块上市规则内，「已在境外上市红筹」在科创/创业板没有可编码的量化标准**。

### 建议结论：**rejected（选 c，midas 存量冗余）**

理由：D4 权威源链只认法规原文；原文没有的标准不编码（无锚点编码 = 把快照当权威源，正是设计 0003 §6 禁止的事）。裁定 rejected 后：

1. 该四套**不进规则库**（导出器本来也不会导它们——候选库里一条都没有）；
2. midas 存量四行进 **midas 差异清单**，交 midas 侧治理（M1 管线的 L3 副产品通道）；
3. golden_sets 对应组合标注 `removed`（拍板后再改，不提前）；
4. 引擎行为落点：该板块 + 该公司类型 → **显式「无适用上市条件套」**，不编一套出来。

### 备选乙（不推荐）

若认定国办发﹝2018﹞21 号文本身应作权威源（红筹试点政策的量化门槛）：须新增法条文档进原文库 → 重跑校准管线 → 候选重新签核。属 v2 范围决策，且该文件不在本次五份 PDF 内——**推荐不选**，理由同上（不在原文库的不编码）。

### 拍板命令（确认后执行，共 4 条）

```bash
python -m ipo_eval_lab.calibration adjudicate --key ChiNext:redchip_listed:1:no_anchor \
    --status rejected --reviewer yt --reason "原文实证：五部板块规则仅主板3.1.4有已上市红筹标准；科创/创业2.1.3只覆盖尚未境外上市红筹；midas存量与主板同构，判存量冗余（底稿0002问题一）"
```

---

## 问题二：红筹「研发阶段 / 国家战略」豁免如何编码？（裁定 ×3）

**涉裁定项**：`SSE-MB:redchip_unlisted:?2:unencoded_gap` / `ChiNext:redchip_unlisted:3` / `STAR:redchip_unlisted:3`

### 引文实证

豁免句**四部法规全有、逐字在文**（主板 ×2、科创/创业 ×1）：

> 处于研发阶段的红筹企业和对国家创新驱动发展战略有重要意义的红筹企业，不适用"营业收入快速增长"的上述要求。——沪/深主板 3.1.5、科创板 2.1.3（创业板 2.1.3 作「…的规定」，语义相同）

### 建议结论：**confirmed（选 a，豁免语义）**

法律依据明确、ADR-0008 豁免语义已落地（`Clause.exemptions` + 引擎消费 + 17 条回归），本问题只差把标注写进候选条款：

- 免除对象：「营业收入快速增长」相关叶（增长路径 clause 的 growth/cagr 叶）；
- 触发条件：`profile_field: company_stage = research_stage` **或** `profile_field: national_strategy_redchip = true`（两条 Exemption，主体侧事实字段 ADR-0008 §3 已扩）；
- 落点：沪深主板 redchip_unlisted 增长支路 clauses、科创/创业 redchip_unlisted 增长 clauses。

**拍板后动作**：给相应候选条款补 `exemptions` 字段（属「修改通过」）→ 该几条重走签核（`sign --decision amended`）→ 导出。

### 拍板命令（确认后执行，共 3 条）

```bash
python -m ipo_eval_lab.calibration adjudicate --key SSE-MB:redchip_unlisted:?2:unencoded_gap \
    --status confirmed --reviewer yt --reason "原文实证：主板3.1.5末句法定豁免逐字在文；按ADR-0008编为Clause.exemptions，免除增长叶（底稿0002问题二）"
# ChiNext:redchip_unlisted:3:unencoded_gap / STAR:redchip_unlisted:3:unencoded_gap 同理
```

---

## 问题三：增长认定第三路径（行业下行期）如何编码？（裁定 ×3）

**涉裁定项**：`SSE-MB:redchip_unlisted:?1:unencoded_gap` / `ChiNext:redchip_unlisted:?2` / `STAR:redchip_unlisted:?2`

### 引文实证

第三路径**原文有、四部法规全有**：

> （三）受行业周期性波动等因素影响，行业整体处于下行周期的，发行人最近3 年营业收入复合增长率高于同行业可比公司同期平均增长水平。——主板 3.1.5 / 科创板 2.1.3 / 创业板 2.1.3（「营业收入快速增长」三选一标准的第三项）

**缺的不是法律依据，是 item**：判定需要「同行业可比公司同期平均增长水平」——行业对比数据，mock 数据契约（设计 0006）里没有对应字段，黄金集如实记了「无 item」。

### 建议结论：**confirmed（选 b，独立条款 / 新增 item）**

原文明明白白给的路径不编码 = 覆盖缺口挂账（ADR-0007 coverage 会如实拦「可达标」结论，但缺路径本身是校准没做完）：

1. 新增 item（建议 `rev_cagr_gt_peer_avg`，boolean：发行人 3 年营收 CAGR 高于同行可比公司同期平均）；
2. mock 数据契约增补对应字段（设计 0006 增补一条；底稿先按行业下行期场景造数）；
3. 编码进「营业收入快速增长」clause 的任一叶（logic: any 第三叶）；
4. 数据缺时按缺数三原则 → indeterminate，不缩窗不回退。

### 拍板命令（确认后执行，共 3 条）

```bash
python -m ipo_eval_lab.calibration adjudicate --key SSE-MB:redchip_unlisted:?1:unencoded_gap \
    --status confirmed --reviewer yt --reason "原文实证：主板3.1.5增长标准（三）逐字在文；缺的是item，按(b)新增rev_cagr_gt_peer_avg+mock契约增补（底稿0002问题三）"
# ChiNext / STAR 同理
```

---

## 拍板后的联动动作清单（全部裁定落定后）

1. `adjudicate` 10 条记录落 `calibration/signoff-records.jsonl`（入 git）；
2. 问题一 rejected ×4 → golden_sets 四组合标 `removed`；midas 存量四行进差异清单；
3. 问题二 confirmed ×3 → 候选条款补 `exemptions` 字段，重构造队列后按 amended 重签；
4. 问题三 confirmed ×3 → 新增 item + mock 契约增补（设计 0006 加一条，需走 F 系列拍板惯例）→ 候选条款补叶，重签；
5. 重新 `signoff` 构造队列 → 条款级签核清零 → `export-official`。
