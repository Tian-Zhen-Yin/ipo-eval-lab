"""接入演示原型 · mock 数据一键再生成（README 见同目录）。

五主体（四示例 + 一企业）构造 → 勾稽①~⑤自洽校验 → 真实引擎跑结果 → 写 mock/。
数字约束：fixtures 模式过⑥卫生区间（营收/OCF ∈ [-50%,200%]，净利 ∈ [-90%,300%]）。
"""
import json
import shutil as sh
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # 仓库根（脚本身在 .scratch 下）

from openpyxl import load_workbook

from ipo_eval_lab.engine import RunTarget, run_eval
from ipo_eval_lab.fixtures.models import CompanyProfile
from ipo_eval_lab.fixtures.loader import check_profile
from ipo_eval_lab.ingest.importer import import_profile
from ipo_eval_lab.ingest.template import build_sample_template

BUILD = Path(".scratch/proto-build")
MOCK = Path(".scratch/proto-deploy/mock")


def statements(rows):
    """全推导保证勾稽自洽：parent=opening+np-div+inj；equity=parent+minority；assets=liab+equity。"""
    out = []
    for (year, o, rev, npt, np, ocf, liab, minority, div, inj, rd, excl) in rows:
        parent = o + np - div + inj
        equity = parent + minority
        out.append({
            "fiscal_year": year,
            "audit": {"status": "audited", "opinion": "unqualified",
                      "report_id": f"华诚审[{year+1}]{(year % 7) * 111 + 101:03d}号"},
            "income": {"operating_revenues": rev, "net_profit_total": npt,
                       "net_profit_attrib_parent": {"as_reported": np, "excl_nonrecurring": excl},
                       "rd_expensed": rd, "rd_capitalized": None},
            "cash_flow": {"net_cash_flow_from_operating": ocf},
            "balance": {"total_assets": liab + equity, "total_liabilities": liab,
                        "total_equity": equity, "total_equity_attrib_to_parent": parent,
                        "minority_interests": minority},
            "equity_roll": {"opening_attrib_parent": o, "net_profit_attrib_parent": np,
                            "dividends": div, "capital_injection": inj, "closing_attrib_parent": parent},
            "reconciliation": {"net_profit_total": npt, "adjustments": ocf - npt,
                               "net_cash_flow_from_operating": ocf},
        })
    return out


M = 1_000_000
SPEC = {
    "hengyue_heavy": ("恒岳重型装备股份有限公司", "通用设备制造业", "profitable", [
        (2022, 4_960*M, 8_200*M, 780*M, 780*M, 900*M, 6_240*M, 110*M, 120*M, 0, 210*M, None),
        (2023, 5_620*M, 8_600*M, 850*M, 850*M, 950*M, 6_300*M, 150*M, 190*M, 0, 230*M, None),
        (2024, 6_280*M, 9_050*M, 930*M, 930*M, 1_020*M, 6_390*M, 160*M, 220*M, 0, 255*M, None)],
     {"mktcap_self_estimate": {"value": 30_000*M, "note": "按可比公司法预估"},
      "invention_patents": {"granted_count": 86, "applied_to_main_business": True},
      "operating_years": 22, "public_float_ratio": 0.25, "total_shares_after_ipo": 1_200*M},
     {"org_structure_sound": True, "biz_team_stable": True, "main_board_fit": True}),
    "lanting_bio": ("苏州澜庭生物医药股份有限公司", "医药制造业", "profitable", [
        (2022, 470*M, 300*M, 20*M, 20*M, 25*M, 410*M, 10*M, 0, 30*M, 90*M, 15*M),
        (2023, 520*M, 520*M, 70*M, 70*M, 60*M, 455*M, 10*M, 0, 0, 130*M, 58*M),
        (2024, 590*M, 850*M, 165*M, 165*M, 150*M, 545*M, 10*M, 0, 30*M, 190*M, 145*M)],
     {"mktcap_self_estimate": {"value": 6_000*M, "note": "在研管线折现（企业自估）"},
      "invention_patents": {"granted_count": 32, "applied_to_main_business": True},
      "operating_years": 9, "rd_staff_ratio": 0.41},
     {"self_developed_tech_intl_leading": True, "star_industry_fit": True}),
    "guiyan_chip": ("无锡硅研微电子股份有限公司", "软件和信息技术服务业", "loss_making", [
        (2022, 620*M, 120*M, -80*M, -80*M, -60*M, 80*M, 0, 0, 0, 100*M, None),
        (2023, 540*M, 180*M, -50*M, -50*M, -40*M, 70*M, 0, 0, 0, 120*M, None),
        (2024, 490*M, 260*M, -30*M, -30*M, -20*M, 50*M, 0, 0, 0, 140*M, None)],
     {"mktcap_self_estimate": {"value": 4_500*M, "note": "按最近一轮融资估值"},
      "invention_patents": {"granted_count": 58, "applied_to_main_business": True},
      "operating_years": 7, "rd_staff_ratio": 0.55},
     {"import_substitution": True, "star_industry_fit": True}),
    "chuyuan_textile": ("楚源纺织科技股份有限公司", "纺织业", "profitable", [
        (2022, 1_850*M, 2_500*M, 240*M, 240*M, 290*M, 1_180*M, 0, 70*M, 0, 45*M, None),
        (2023, 2_020*M, 2_200*M, 90*M, 90*M, 150*M, 1_280*M, 0, 70*M, 0, 40*M, 70*M),
        (2024, 2_040*M, 1_800*M, 12*M, 12*M, 80*M, 1_310*M, 0, 32*M, 0, 38*M, 12*M)],
     {"mktcap_self_estimate": {"value": 1_500*M, "note": "按可比公司法预估"},
      "invention_patents": {"granted_count": 11, "applied_to_main_business": None},
      "operating_years": 18, "public_float_ratio": 0.30, "total_shares_after_ipo": 500*M}, {}),
}

AS_OF = "2026-11-21"


def main() -> None:
    sh.rmtree(BUILD, ignore_errors=True)
    BUILD.joinpath("companies").mkdir(parents=True)

    # 企业主体：样例模板更名（华晟）→ 走真实导入链路
    tmp = BUILD / "e.xlsx"
    build_sample_template(tmp)
    wb = load_workbook(tmp)
    wb["主体信息"]["B2"] = "深圳华晟智能装备股份有限公司"
    wb["主体信息"]["B5"] = "专用设备制造业"
    wb.save(tmp)
    r = import_profile(tmp, "hszn_01", out_root=BUILD / "out")
    assert r.status == "ok", [str(v) for v in r.violations]

    out_dir = MOCK / "results"
    sh.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    companies_json, index = [], []
    for cid in [*SPEC, "hszn_01"]:
        d = BUILD / "companies" / cid
        if cid in SPEC:
            name, industry, profit, rows, doc, dec = SPEC[cid]
            prof = {"company_id": cid, "display_name": name,
                    "applicant_profile": {"company_type": "general", "profit_status": profit,
                                          "industry": industry, "company_stage": None,
                                          "redchip_status": None},
                    "statements": statements(rows), "stub_period": None,
                    "documentary": doc, "declared": dec}
            d.mkdir(parents=True)
            (d / "profile.json").write_text(json.dumps(prof, ensure_ascii=False, indent=2),
                                            encoding="utf-8")
            check_profile(CompanyProfile.model_validate(prof), None)
        else:
            sh.copytree(r.company_dir, d)
        ctx = run_eval(company_dir=d, rulebook_dir=Path("rulebook"), fixtures_root=Path("fixtures"),
                       as_of=AS_OF, target=RunTarget(boards=None, sets=None))
        res = ctx.result
        res["data_source"] = "enterprise" if (d / "ingest.json").is_file() else "fixture"
        fname = f"{cid}_{AS_OF}.json"
        (out_dir / fname).write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str),
                                     encoding="utf-8")
        p = json.loads((d / "profile.json").read_text())
        companies_json.append({"id": cid, "display_name": p["display_name"],
                               "company_type": p["applicant_profile"]["company_type"],
                               "profit_status": p["applicant_profile"]["profit_status"],
                               "industry": p["applicant_profile"]["industry"],
                               "fiscal_years": [s["fiscal_year"] for s in p["statements"]],
                               "profile": p})
        index.append({"file": fname, "mtime": 1795270000 + len(index) * 3600,
                      "run": res["run"], "data_source": res["data_source"]})

    # 企业主体只走 enterprises 通道（companies 不含 hszn_01，防下拉双现）
    companies_json = [c for c in companies_json if c["id"] != "hszn_01"]
    (MOCK / "companies.json").write_text(json.dumps(companies_json, ensure_ascii=False),
                                         encoding="utf-8")
    (MOCK / "enterprises.json").write_text(json.dumps(
        [{"company_id": "hszn_01", "display_name": "深圳华晟智能装备股份有限公司",
          "imported_at": "2026-11-21T22:40:00", "source_sha256": "f" * 64,
          "fiscal_years": [2023, 2024, 2025]}], ensure_ascii=False, indent=2), encoding="utf-8")
    (MOCK / "results-index.json").write_text(json.dumps(index, ensure_ascii=False),
                                             encoding="utf-8")
    (MOCK / "result-acme.json").unlink(missing_ok=True)  # 旧单结果文件退役
    print("主体:", [c["id"] for c in companies_json], "+ hszn_01(企业)")
    print("结果:", sorted(p.name for p in out_dir.iterdir()))


if __name__ == "__main__":
    main()
