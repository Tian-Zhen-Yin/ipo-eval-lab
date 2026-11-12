# 人工签核队列

- as_of：2026-11-12
- 生成时间：2026-11-12T15:26:44
- 候选条款总数：133
- 条款级待签：69
- 套级裁定待办：10

## 条款级分档统计

| 档 | 含义 | 条数 | 待签 |
|---|---|---|---|
| A | 必核：黄金集覆盖 / 闸门失败 / midas 差异 | 53 | 53 |
| C | 抽检：闸门全绿且 midas 一致 | 80 | 16 |

## 套级裁定清单（法律适用性，与条款级并列，不得互相替代）

### SSE-MB:redchip_unlisted:?1:unencoded_gap

- 落档原因：黄金集 gaps：增长认定第三路径（行业下行期 cagr>同行平均）无 item
- 候选库中该套条款数：12（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：SSE-MB redchip_unlisted：黄金集记录「增长认定第三路径（行业下行期 cagr>同行平均）无 item」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。

### SSE-MB:redchip_unlisted:?2:unencoded_gap

- 落档原因：黄金集 gaps：研发阶段/国家战略红筹豁免未编码
- 候选库中该套条款数：12（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：SSE-MB redchip_unlisted：黄金集记录「研发阶段/国家战略红筹豁免未编码」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。

### ChiNext:redchip_listed:1:no_anchor

- 落档原因：黄金集 covered=false（ChiNext/redchip_listed 套 1）
- 候选库中该套条款数：0（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：1
- 裁定问句：ChiNext redchip_listed 套 1：黄金集标注 covered=false——现行规则原文库无对应「上市标准」条款（原文仅覆盖「尚未在境外上市」红筹）。请裁定：(1) 该套是否存在法律依据？依据出自哪份文件、哪一条？(2) 若存在，凭 midas 快照补条款是否合规（快照是 trace，不是权威源）？(3) 若不存在，应从规则库移除该套——请明示。

### ChiNext:redchip_listed:2:no_anchor

- 落档原因：黄金集 covered=false（ChiNext/redchip_listed 套 2）
- 候选库中该套条款数：0（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：1
- 裁定问句：ChiNext redchip_listed 套 2：黄金集标注 covered=false——现行规则原文库无对应「上市标准」条款（原文仅覆盖「尚未在境外上市」红筹）。请裁定：(1) 该套是否存在法律依据？依据出自哪份文件、哪一条？(2) 若存在，凭 midas 快照补条款是否合规（快照是 trace，不是权威源）？(3) 若不存在，应从规则库移除该套——请明示。

### ChiNext:redchip_unlisted:3:unencoded_gap

- 落档原因：黄金集 gaps：套3 特殊红筹豁免（redchip_special，expected_branches=0）未编码——豁免语义需人工签核
- 候选库中该套条款数：10（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：ChiNext redchip_unlisted：黄金集记录「套3 特殊红筹豁免（redchip_special，expected_branches=0）未编码——豁免语义需人工签核」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。

### ChiNext:redchip_unlisted:?2:unencoded_gap

- 落档原因：黄金集 gaps：增长认定第三路径（行业下行期 cagr>同行平均）无 item
- 候选库中该套条款数：10（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：ChiNext redchip_unlisted：黄金集记录「增长认定第三路径（行业下行期 cagr>同行平均）无 item」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。

### STAR:redchip_listed:1:no_anchor

- 落档原因：黄金集 covered=false（STAR/redchip_listed 套 1）
- 候选库中该套条款数：0（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：1
- 裁定问句：STAR redchip_listed 套 1：黄金集标注 covered=false——现行规则原文库无对应「上市标准」条款（原文仅覆盖「尚未在境外上市」红筹）。请裁定：(1) 该套是否存在法律依据？依据出自哪份文件、哪一条？(2) 若存在，凭 midas 快照补条款是否合规（快照是 trace，不是权威源）？(3) 若不存在，应从规则库移除该套——请明示。

### STAR:redchip_listed:2:no_anchor

- 落档原因：黄金集 covered=false（STAR/redchip_listed 套 2）
- 候选库中该套条款数：0（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：1
- 裁定问句：STAR redchip_listed 套 2：黄金集标注 covered=false——现行规则原文库无对应「上市标准」条款（原文仅覆盖「尚未在境外上市」红筹）。请裁定：(1) 该套是否存在法律依据？依据出自哪份文件、哪一条？(2) 若存在，凭 midas 快照补条款是否合规（快照是 trace，不是权威源）？(3) 若不存在，应从规则库移除该套——请明示。

### STAR:redchip_unlisted:3:unencoded_gap

- 落档原因：黄金集 gaps：套3 特殊红筹豁免（redchip_special，expected_branches=0）未编码
- 候选库中该套条款数：10（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：STAR redchip_unlisted：黄金集记录「套3 特殊红筹豁免（redchip_special，expected_branches=0）未编码」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。

### STAR:redchip_unlisted:?2:unencoded_gap

- 落档原因：黄金集 gaps：增长认定第三路径（行业下行期 cagr>同行平均）无 item
- 候选库中该套条款数：10（0 表示候选库无此套——这本身是「规则库缺套」信号）
- midas 快照行数（仅参考）：None
- 裁定问句：STAR redchip_unlisted：黄金集记录「增长认定第三路径（行业下行期 cagr>同行平均）无 item」。请裁定该条目的法律依据与适用条件，并确认应如何编码：(a) 作为豁免语义（ADR-0008：Clause.exemptions，命中即 not_applicable）；(b) 作为独立条款（需有可取数的 item）；(c) 属 midas 侧冗余，不进规则库。请给出结论与依据。
