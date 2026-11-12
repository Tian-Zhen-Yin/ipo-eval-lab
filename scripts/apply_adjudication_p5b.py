"""裁定落地补丁（底稿 0002 问题二/三，2026-11-12 用户拍板 confirmed）。

输入 candidates_merged.jsonl（L1a 机器产物，**不改**）→ 输出 candidates_amended.jsonl。

三项变更（全部源自已拍板裁定，本脚本只做机械落库，零自由裁量）：

问题二（红筹增长认定豁免 → ADR-0008 Clause.exemptions）：
  「处于研发阶段的红筹企业和对国家创新驱动发展战略有重要意义的红筹企业，
  不适用"营业收入快速增长"的上述要求。」——四部法规逐字在文。
  落点 = 增长认定条款（含路径 A/B 的营收前提叶 + cagr 叶 + 新增行业对比叶）；
  50亿标准的「营收≥5亿」是标准本体要求（3.1.5(三) 明文），**不豁免**。

问题三（增长认定第三路径 → 新 item rev_cagr_gt_peer_avg + 新支路）：
  「（三）受行业周期性波动等因素影响，行业整体处于下行周期的，发行人最近
  3年营业收入复合增长率高于同行业可比公司同期平均增长水平。」——四部法规逐字在文。
  - 100亿标准（cn_main g2 / star g1 / chinext g1）：新增 b3 支路；
  - 50亿标准（cn_main g3 / star g2 / chinext g2）：固定条件（市值/定性/营收5亿）
    上移 shared（结构归位：只有增长认定才是支路），cagr 留 b1，新增 b2 行业对比。
    ——路径 B（营收<5亿 + cagr20%）与标准本体「营收≥5亿」互斥，不编（黄金集已注记）。

用法：
    python scripts/apply_adjudication_p5b.py           # 生成
    python scripts/apply_adjudication_p5b.py --check   # 只校验幂等（CI 用）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "calibration" / "l1a" / "output" / "candidates_merged.jsonl"
OUT = REPO / "calibration" / "l1a" / "output" / "candidates_amended.jsonl"

# ── 豁免 payload（问题二）──
EXEMPT_NOTE = (
    "处于研发阶段的红筹企业和对国家创新驱动发展战略有重要意义的红筹企业，"
    "不适用\u201c营业收入快速增长\u201d的上述要求（3.1.5 / 2.1.3 末句，四部法规逐字在文）"
)


def _exemption(item_refs: list[str]) -> dict:
    return {
        "when": {
            "profile_field": "company_stage",
            "in_list": ["rd_stage", "strategic_significance"],
        },
        "excludes": list(item_refs),
        "note": EXEMPT_NOTE,
    }


# 豁免落点：group_id → clause_id 列表（营收前提叶 + cagr 叶；50亿套只豁免 cagr 叶）
EXEMPT_TARGETS: dict[str, list[str]] = {
    # 100亿标准：路径 A/B 的前提叶与 cagr 叶全属增长认定
    "cn_main_redchip_unlisted_g2": [
        "rc_unlisted_g2_b1_c1", "rc_unlisted_g2_b1_c2",
        "rc_unlisted_g2_b2_c1", "rc_unlisted_g2_b2_c2",
    ],
    "star_redchip_unlisted_g1": [
        "star_rc_g1_b1_c1", "star_rc_g1_b1_c2",
        "star_rc_g1_b2_c1", "star_rc_g1_b2_c2",
    ],
    "chinext_redchip_unlisted_g1": [
        "cnx_rc_g1_b1_c1", "cnx_rc_g1_b1_c2",
        "cnx_rc_g1_b2_c1", "cnx_rc_g1_b2_c2",
    ],
    # 50亿标准：只豁免 cagr 叶（营收≥5亿是标准本体，3.1.5(三) 明文）
    "cn_main_redchip_unlisted_g3": ["rc_unlisted_g3_b1_c4"],
    "star_redchip_unlisted_g2": ["star_rc_g2_b1_c2"],
    "chinext_redchip_unlisted_g2": ["cnx_rc_g2_b1_c2"],
}

# 50亿标准结构归位：固定条件条款 role branch → shared（不变内容，只挪位置）
# cn_main g3 全在 b1（无 shared）；star/chinext g2 的市值/定性已 shared，只挪营收5亿。
RESTRUCTURE_SHARED: dict[str, list[str]] = {
    "cn_main_redchip_unlisted_g3": [
        "rc_unlisted_g3_b1_c1", "rc_unlisted_g3_b1_c2", "rc_unlisted_g3_b1_c3",
    ],
    "star_redchip_unlisted_g2": ["star_rc_g2_b1_c1"],
    "chinext_redchip_unlisted_g2": ["cnx_rc_g2_b1_c1"],
}

# 新增第三路径支路（问题三）：group_id → (branch 后缀, clause_id, law 引文定位)
# law 定位 = (law_id, article)——引文从 source_texts 逐字取（quote 必须与原文一致）
PATH_C: dict[str, tuple[str, str, str, str]] = {
    # group_id: (clause_id, branch_id 后缀, law_id, article)
    "cn_main_redchip_unlisted_g2": ("rc_unlisted_g2_b3_c1", "b3", "sse_main_2026", "3.1.5"),
    "cn_main_redchip_unlisted_g3": ("rc_unlisted_g3_b2_c1", "b2", "sse_main_2026", "3.1.5"),
    "star_redchip_unlisted_g1": ("star_rc_g1_b3_c1", "b3", "sse_star_2026", "2.1.3"),
    "star_redchip_unlisted_g2": ("star_rc_g2_b2_c1", "b2", "sse_star_2026", "2.1.3"),
    "chinext_redchip_unlisted_g1": ("cnx_rc_g1_b3_c1", "b3", "szse_chinext_2026", "2.1.3"),
    "chinext_redchip_unlisted_g2": ("cnx_rc_g2_b2_c1", "b2", "szse_chinext_2026", "2.1.3"),
}

PATH_C_SENTINEL = "（三）受行业周期性波动等因素影响"

PATH_C_DISPLAY = "营收快速增长·路径C：行业下行期，3年复合增长率高于同行业可比公司同期平均"


def _law_path_c(law_id: str, article: str) -> tuple[str, str]:
    """从原文库逐字取条款全文 + 第三路径原句。

    quote 逐字取自**各自法规**——四部措辞有差（沪主板「最近3 年」、深主板/创业
    板「最近三年」），硬编码一句套四部会造出假引文（L1b 锚点即拦）。
    """
    doc = yaml.safe_load((REPO / "rulebook" / "source_texts" / f"{law_id}.yaml").read_text(encoding="utf-8"))
    for a in doc["articles"]:
        if a["article"] != article:
            continue
        text = a["text"]
        start = text.find(PATH_C_SENTINEL)
        assert start >= 0, f"{law_id}#{article} 未找到第三路径句首标记"
        end = text.find("。", start)
        assert end > start, f"{law_id}#{article} 第三路径句无句号终止"
        sentence = text[start:end + 1]
        for marker in ("下行周期", "同行业可比公司", "复合增长率高于"):
            assert marker in sentence, f"{law_id}#{article} 第三路径句缺标记：{marker}"
        return text, sentence
    raise KeyError(f"{law_id} 无条款 {article}")


def _mirror_law(board: str, law_id: str) -> str:
    """沪深镜像：SSE-MB 记录挂 sse 法、SZSE-MB 记录挂 szse 法。"""
    if law_id == "sse_main_2026" and board == "SZSE-MB":
        return "szse_main_2026"
    return law_id


def build() -> tuple[list[dict], dict[str, int]]:
    records = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
    stats = {"exempted": 0, "restructured": 0, "added": 0}

    by_key: dict[tuple[str, str], dict] = {}
    for r in records:
        by_key[(r["context"]["board"], r["clause_id"])] = r

    # 1) 豁免标注（问题二）
    for gid, clause_ids in EXEMPT_TARGETS.items():
        for cid in clause_ids:
            for r in records:
                if r["clause_id"] != cid or r["context"]["group_id"] != gid:
                    continue
                items = [lf["item_ref"] for lf in r["clause"]["leaves"]]
                ex = r["clause"].setdefault("exemptions", [])
                ex.clear()  # 幂等：重跑不叠加
                ex.append(_exemption(items))
                stats["exempted"] += 1

    # 2) 50亿标准结构归位（问题三配套）
    for gid, clause_ids in RESTRUCTURE_SHARED.items():
        for cid in clause_ids:
            for r in records:
                if r["clause_id"] != cid or r["context"]["group_id"] != gid:
                    continue
                r["context"]["role"] = "shared"
                r["context"]["branch_id"] = None
                stats["restructured"] += 1

    # 3) 第三路径新条款（问题三）——按 group 现有 board 集合逐板新增（镜像板挂镜像法）
    existing = {(r["context"]["board"], r["clause_id"]) for r in records}
    group_boards: dict[str, list[str]] = {}
    group_evidence: dict[str, dict] = {}
    for r in records:
        gid = r["context"]["group_id"]
        group_boards.setdefault(gid, [])
        if r["context"]["board"] not in group_boards[gid]:
            group_boards[gid].append(r["context"]["board"])
        group_evidence.setdefault(gid, r.get("evidence", {}))

    for gid, (cid, bsuffix, law_id, article) in PATH_C.items():
        for board in group_boards[gid]:
            if (board, cid) in existing:
                continue
            law = _mirror_law(board, law_id)
            text, sentence = _law_path_c(law, article)
            records.append({
                "clause_id": cid,
                "context": {
                    "board": board,
                    "company_type": "redchip_unlisted",
                    "group_no": records and next(
                        r["context"]["group_no"] for r in records
                        if r["context"]["group_id"] == gid
                    ),
                    "group_id": gid,
                    "branch_id": f"{gid}-{bsuffix}",
                    "role": "branch",
                    "scope": "set",
                },
                "clause": {
                    "clause_id": cid,
                    "law_ref": f"{law}#{article}",
                    "logic": "all",
                    "display": PATH_C_DISPLAY,
                    "leaves": [{
                        "leaf_id": f"{cid}_l1",
                        "item_ref": "rev_cagr_gt_peer_avg",
                        "op": "eq",
                        "threshold": True,
                        "threshold_format": "boolean",
                        "threshold_text": "高于同行业可比公司同期平均增长水平",
                        "quote": sentence,
                    }],
                    "exemptions": [_exemption(["rev_cagr_gt_peer_avg"])],
                },
                "source": {"law_id": law, "article": article, "chapter": None,
                           "section": None, "text": text},
                "evidence": group_evidence[gid],
                "extracted_at": "2026-11-12",
                "model_provider": "p5b-amendment",
                "model_name": "apply_adjudication_p5b",
            })
            stats["added"] += 1

    return records, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验产物是否最新（不改文件）")
    args = ap.parse_args()

    records, stats = build()
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)

    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != body:
            print("amended 候选库不是最新（跑 scripts/apply_adjudication_p5b.py）", file=sys.stderr)
            return 1
        print("amended 候选库与脚本一致")
        return 0

    OUT.write_text(body, encoding="utf-8")
    print(f"写入 {OUT.relative_to(REPO)}（{len(records)} 条候选）")
    print(f"  豁免标注（问题二）：{stats['exempted']} 条记录")
    print(f"  结构归位（问题三·50亿套）：{stats['restructured']} 条记录")
    print(f"  第三路径新增（问题三）：{stats['added']} 条记录")
    return 0


if __name__ == "__main__":
    sys.exit(main())
