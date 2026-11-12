# midas 存量差异清单

- as_of：2026-11-12（P5b 裁定落地后）
- 差异条数：23
- 治理方向：value_diff/structure_diff 多为快照不精确（ADR-0010：候选以原文为准，快照不回改候选）；source_only = 原文有而快照缺的口径；snapshot_only = 快照存量行在权威规则库中无对应（套级裁定 rejected 或非套判断行），midas 侧应下线或改判

## value_diff（2 条）

- `cn_main_g2_b1_c1 · mktcap_forecast`：item mktcap_forecast 阈值不同：候选 (ge,5000000000.0) vs 快照 (ge,35000000000.0)（套 SSE-MB:general:2）
- `cn_main_g2_b1_c1 · mktcap_forecast`：item mktcap_forecast 阈值不同：候选 (ge,5000000000.0) vs 快照 (ge,35000000000.0)（套 SZSE-MB:general:2）

## structure_diff（7 条）

- `rc_unlisted_g2_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1)、(ge,0.2) vs 快照 (gt,0.1)、(gt,0.2)（套 SSE-MB:redchip_unlisted:2）
- `rc_unlisted_g3_b1_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1) vs 快照 (gt,0.1)（套 SSE-MB:redchip_unlisted:3）
- `rc_unlisted_g2_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1)、(ge,0.2) vs 快照 (gt,0.1)、(gt,0.2)（套 SZSE-MB:redchip_unlisted:2）
- `rc_unlisted_g3_b1_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1) vs 快照 (gt,0.1)（套 SZSE-MB:redchip_unlisted:3）
- `cnx_rc_g1_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1)、(ge,0.2) vs 快照 (gt,0.1)、(gt,0.2)（套 ChiNext:redchip_unlisted:1）
- `star_rc_g1_c1 · rev_3y_cagr`：item rev_3y_cagr op 不同（同阈值、op 不同：边界含否）：候选 (ge,0.1)、(ge,0.2) vs 快照 (gt,0.1)、(gt,0.2)（套 STAR:redchip_unlisted:1）
- `bse_g1_c0 · np_2y_each`：item np_2y_each op 不同（同阈值、op 不同：边界含否）：候选 (ge,15000000.0) vs 快照 (gt,15000000.0)（套 BSE:general:1）

## snapshot_only（6 条）

- `（候选库无此套）ChiNext:redchip_listed:1`：快照有套 ChiNext:redchip_listed:1 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判
- `（候选库无此套）ChiNext:redchip_listed:2`：快照有套 ChiNext:redchip_listed:2 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判
- `（候选库无此套）ChiNext:redchip_unlisted:3`：快照有套 ChiNext:redchip_unlisted:3 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判
- `（候选库无此套）STAR:redchip_listed:1`：快照有套 STAR:redchip_listed:1 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判
- `（候选库无此套）STAR:redchip_listed:2`：快照有套 STAR:redchip_listed:2 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判
- `（候选库无此套）STAR:redchip_unlisted:3`：快照有套 STAR:redchip_unlisted:3 而候选库无对应——多为套级裁定 rejected（法律无锚点，见黄金集 adjudication 注记）或 midas 把非套判断行存成套（见黄金集 gaps）；该套存量行 midas 侧应下线或改判

## source_only（8 条）

- `rc_unlisted_g2_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 SSE-MB:redchip_unlisted:2）
- `rc_unlisted_g3_b1_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 SSE-MB:redchip_unlisted:3）
- `rc_unlisted_g2_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 SZSE-MB:redchip_unlisted:2）
- `rc_unlisted_g3_b1_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 SZSE-MB:redchip_unlisted:3）
- `cnx_rc_g1_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 ChiNext:redchip_unlisted:1）
- `cnx_rc_g2_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 ChiNext:redchip_unlisted:2）
- `star_rc_g1_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 STAR:redchip_unlisted:1）
- `star_rc_g2_c1 · rev_cagr_gt_peer_avg`：快照无 item rev_cagr_gt_peer_avg（套 STAR:redchip_unlisted:2）
