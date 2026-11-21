"""M-UI 本地服务（ADR-0012 / 设计 0010）：静态前端 + JSON API，进程内调引擎。

边界（ADR-0012）：只绑 127.0.0.1、单用户、无鉴权——本模块是**展示层**，
不是引擎服务化；引擎唯一编程接口仍是 `run_eval`（设计 0004 A3 不变）。
handler 拆成 UiApp 纯方法（返回 (status, payload)），HTTP 层只做路由/编解码，
测试不起 socket（tests/test_webui.py）。

补录注入路径（设计 0010 §2）：overrides 非空时把 base profile 拷到
`.scratch/ui-runs/<run_id>/profile.json` 合并覆盖（null=清空→引擎侧
indeterminate），真实 fixtures/ 永不写；结果落 `results/`（gitignore），
带 overrides 或重名时加时间戳后缀防覆盖。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .ingest.importer import Violation, import_profile
from .ingest.prefill import build_prefill_template
from .ingest.save import SaveRefused, list_enterprises, save_enterprise
from .ingest.source import data_source_of
from .ingest.template import build_blank_template, build_sample_template

from pydantic import ValidationError

from .engine import EngineError, RunTarget, run_eval
from .fixtures import FixtureDataError
from .engine.result import state_counts
from .rulebook.loader import load_rulebook

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 前端资产就这几类（设计 0010 §1）；未知扩展名按二进制流兜底
_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
_MAX_BODY = 1_000_000  # POST 上限 1MB（补录表单远小于此）
_MAX_UPLOAD = 10_000_000  # 上传 xlsx 上限 10MB（ADR-0013 修订 1 护栏）

# 上传护栏：文件名白名单（无路径分隔符，中文合法）；company_id 同 CLI 语义
_FILENAME_RE = re.compile(r"^[A-Za-z0-9_().\-\u4e00-\u9fff ]+\.xlsx$")
_COMPANY_ID_RE = re.compile(r"^[a-z0-9_]+$")


# ── 规则库摘要（/api/rulebook；新建页套卡数据源）──


def _clause_summary(c: Any) -> dict[str, Any]:
    return {
        "clause_id": c.clause_id,
        "display": c.display,
        "law_ref": c.law_ref,
        "logic": c.logic,
        "leaves": [
            {
                "leaf_id": lf.leaf_id,
                "item_ref": lf.item_ref,
                "op": lf.op.value,
                "threshold": {"value": lf.threshold.value, "format": lf.threshold.format.value},
            }
            for lf in c.leaves
        ],
        "exemptions": [
            {"excludes": ex.excludes, "note": ex.note, "when": ex.when.model_dump()}
            for ex in c.exemptions
        ],
        "note": c.note,
    }


def rulebook_summary(rb: Any) -> dict[str, Any]:
    """Rulebook → JSON 友好摘要（items 查找表 + 36 组；scope 三段同形）。

    laws 只带**被条款引用**的条文原文（法条 ⓘ 悬浮文案源）——全量原文
    1.4MB 不进接口，被引用条文数十条足够 UI 用。
    """
    meta = {
        "rulebook_version": rb.meta.rulebook_version,
        "boards": rb.meta.boards,
        "company_types": rb.meta.company_types,
        "declared_no_sets": rb.meta.declared_no_sets,
    }
    items = {
        it.item_id: {
            "display": it.display,
            "nature": it.nature.value,
            "quantifier": it.quantifier.value if it.quantifier else None,
            "window": {"kind": it.window.kind, "n": it.window.n} if it.window else None,
            "pending_evidence": it.pending_evidence,
        }
        for it in rb.items
    }
    groups = []
    referenced: set[tuple[str, str]] = set()

    def take_refs(clauses: list[Any]) -> None:
        for c in clauses:
            law_id, _, art = c.law_ref.partition("#")
            referenced.add((law_id, art.split("(")[0]))  # (一) 后缀归并到节条文

    for g in rb.groups:
        take_refs(g.shared_clauses)
        for b in g.branches:
            take_refs(b.clauses)
        groups.append(
            {
                "scope": g.scope.value,
                "group_id": g.group_id,
                "display": g.display,
                "boards": g.boards,
                "company_type": g.company_type,
                "group_no": g.group_no,
                "section": g.section,
                "effective_from": g.effective_from.isoformat(),
                "law_refs": g.law_refs,
                "hard_filters": [
                    {"field": h.field, "op": h.op, "values": h.values, "note": h.note}
                    for h in g.hard_filters
                ],
                "shared_clauses": [_clause_summary(c) for c in g.shared_clauses],
                "branches": [
                    {
                        "set_id": b.set_id,
                        "display": b.display,
                        "aliases_midas": b.aliases.midas,
                        "clauses": [_clause_summary(c) for c in b.clauses],
                    }
                    for b in g.branches
                ],
                "note": g.note,
            }
        )
    laws: dict[str, dict[str, Any]] = {}
    for law in rb.laws:
        arts = {
            a.article: {"text": a.text, "note": a.note}
            for a in law.articles
            if (law.law_id, a.article) in referenced
        }
        if arts:
            laws[law.law_id] = {"title": law.title, "articles": arts}
    return {"meta": meta, "items": items, "groups": groups, "laws": laws}


@dataclass
class UiApp:
    """API 操作集（纯方法，返回 (status, payload)）；路径由 main/tests 注入。"""

    rulebook_dir: Path
    fixtures_root: Path
    results_dir: Path
    ui_dir: Path
    scratch_root: Path
    enterprises_root: Path = PROJECT_ROOT / "enterprises"  # 企业主体库（ADR-0013）
    _uploads: dict[str, dict[str, Any]] = field(default_factory=dict)  # upload_id → 预填记录

    def _load_rulebook(self) -> Any:
        # strict_global=True：UI 展示的数据必须过与 CI 同级的全库闸门
        return load_rulebook(self.rulebook_dir, strict_global=True).rulebook

    # -- GET /api/meta --
    def api_meta(self) -> tuple[int, dict[str, Any]]:
        return 200, rulebook_summary(self._load_rulebook())["meta"]

    # -- GET /api/rulebook --
    def api_rulebook(self) -> tuple[int, dict[str, Any]]:
        return 200, rulebook_summary(self._load_rulebook())

    # -- GET /api/companies --
    def api_companies(self) -> tuple[int, Any]:
        out: list[dict[str, Any]] = []
        root = self.fixtures_root / "companies"
        if root.is_dir():
            for d in sorted(root.iterdir()):
                p = d / "profile.json"
                if not (d.is_dir() and p.exists()):
                    continue
                raw = json.loads(p.read_text(encoding="utf-8"))
                ap = raw.get("applicant_profile") or {}
                out.append(
                    {
                        "id": d.name,
                        "display_name": raw.get("display_name", d.name),
                        "company_type": ap.get("company_type"),
                        "profit_status": ap.get("profit_status"),
                        "industry": ap.get("industry"),
                        "fiscal_years": sorted(s["fiscal_year"] for s in raw.get("statements", [])),
                        "profile": raw,  # 补录弹窗预填当前值用
                    }
                )
        return 200, out

    # -- GET /api/results --
    def api_results(self) -> tuple[int, Any]:
        out: list[dict[str, Any]] = []
        if self.results_dir.is_dir():
            for p in self.results_dir.glob("*.json"):
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue  # 半截文件/非 result 产物不进索引
                run = raw.get("run")
                if not isinstance(run, dict):
                    continue
                out.append({"file": p.name, "mtime": p.stat().st_mtime, "run": run,
                            "data_source": raw.get("data_source")})  # 历史页来源徽标（旧 JSON 无此键 → None）
        out.sort(key=lambda r: r["mtime"], reverse=True)
        return 200, out

    # -- GET /api/results/<file> --
    def api_result_file(self, name: str) -> tuple[int, Any]:
        # 文件名白名单：仅顶层 *.json，路径穿越零容忍
        if Path(name).name != name or not name.endswith(".json"):
            return 400, {"error": f"非法文件名：{name}"}
        p = (self.results_dir / name).resolve()
        if not str(p).startswith(str(self.results_dir.resolve())) or not p.exists():
            return 404, {"error": f"结果不存在：{name}"}
        try:
            return 200, json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return 500, {"error": f"结果文件损坏：{name}，请重新生成或删除该文件后重试"}

    # ── 企业数据接入（ADR-0013 修订 1；UiApp 方法均为纯函数风格）──

    def _auto_company_id(self) -> str:
        """ent_<日期>_<序号>：序号取会话目录与企业库中同日前缀的最大值 +1。"""
        day = datetime.now().strftime("%Y%m%d")
        prefix = f"ent_{day}_"
        seq = 0
        for root in (self.scratch_root / "ingest", self.enterprises_root):
            if not root.is_dir():
                continue
            for d in root.iterdir():
                if d.name.startswith(prefix):
                    tail = d.name[len(prefix):].split("_", 1)[0]
                    if tail.isdigit():
                        seq = max(seq, int(tail))
        return f"{prefix}{seq + 1}"

    # -- POST /api/ingest/upload（body = xlsx 原始字节，文件名走 X-Filename 头）--
    def api_ingest_upload(
        self, raw: bytes, filename: str, company_id: str | None
    ) -> tuple[int, dict[str, Any]]:
        if len(raw) > _MAX_UPLOAD:
            return 413, {"error": "文件超过 10MB 上限，请确认上传的是填写模板"}
        name = (filename or "").strip()
        if "/" in name or "\\" in name or not _FILENAME_RE.fullmatch(name):
            return 400, {"error": "文件名不合法：仅接受 .xlsx，且不含路径或特殊字符"}
        cid = company_id or self._auto_company_id()
        if not _COMPANY_ID_RE.fullmatch(cid):
            return 400, {"error": "company_id 仅允许小写字母、数字与下划线"}

        uploads = self.scratch_root / "ingest-uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        upload_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(self._uploads) + 1:03d}"
        src = uploads / f"{upload_id}_{name}"
        src.write_bytes(raw)

        r = import_profile(src, cid, out_root=self.scratch_root / "ingest")
        self._uploads[upload_id] = {"path": src, "violations": r.violations}
        # 上传记录落盘：预填下载在服务重启后仍可用（走查 P2-3）
        (uploads / f"{upload_id}.json").write_text(
            json.dumps(
                {"path": str(src), "company_id": cid,
                 "violations": [asdict(v) for v in r.violations]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if r.status == "violations":
            return 200, {
                "status": "violations",
                "violations": [asdict(v) for v in r.violations],
                "company_id": cid,
                "upload_id": upload_id,
                "session_dir": None,
            }

        prof = json.loads((r.company_dir / "profile.json").read_text(encoding="utf-8"))  # type: ignore[union-attr]
        stmts = prof["statements"]
        doc, dec = prof.get("documentary") or {}, prof.get("declared") or {}
        filled = sum(v is not None for v in dec.values())
        filled += 1 if doc.get("mktcap_self_estimate") else 0
        pats = doc.get("invention_patents") or {}
        filled += (pats.get("granted_count") is not None) + (pats.get("applied_to_main_business") is not None)
        for k in ("operating_years", "public_float_ratio", "total_shares_after_ipo",
                  "rev_cagr_gt_peer_avg", "rd_staff_ratio"):
            filled += doc.get(k) is not None
        preview = {
            "display_name": prof["display_name"],
            "fiscal_years": [s["fiscal_year"] for s in stmts],
            "revenue": [s["income"]["operating_revenues"] for s in stmts],
            "net_profit_attrib": [s["income"]["net_profit_attrib_parent"]["as_reported"] for s in stmts],
            "audit_opinion": [s["audit"]["opinion"] for s in stmts],
            # 申报口径确认感（走查 P3-5）：客户能看到问卷部分被读到（9 项底稿 + declared 全集）
            "declared": {"filled": int(filled), "total": 9 + len(dec)},
        }
        return 200, {
            "status": "ok",
            "violations": [],
            "derived": r.derived_fields,
            "company_id": cid,
            "upload_id": upload_id,
            "session_dir": str(r.company_dir),
            "preview": preview,
        }

    # -- POST /api/ingest/save --
    def api_ingest_save(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        cid = str(body.get("company_id") or "")
        if not _COMPANY_ID_RE.fullmatch(cid):
            return 400, {"error": "company_id 缺失或不合法（小写字母/数字/下划线）"}
        ingest_root = (self.scratch_root / "ingest").resolve()
        d = Path(str(body.get("session_dir") or ""))
        if not (d.is_dir() and d.resolve().is_relative_to(ingest_root)):
            return 400, {"error": f"session_dir 非法：必须是位于 {ingest_root} 之下的导入会话目录"}
        try:
            dest = save_enterprise(d, cid, self.enterprises_root, overwrite=bool(body.get("overwrite")))
        except SaveRefused as e:
            meta_path = self.enterprises_root / cid / "ingest.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
            return 409, {
                "error": str(e),
                "existing": {  # 覆盖确认弹窗的指纹：对着具体数据确认
                    "imported_at": meta.get("imported_at"),
                    "source_sha256": meta.get("source_sha256"),
                    "display_name": meta.get("display_name"),
                },
            }
        return 200, {"saved": str(dest), "company_id": cid}

    # -- GET /api/ingest/prefill/<upload_id>（返回 (status, mime, bytes)）--
    def api_ingest_prefill(self, upload_id: str) -> tuple[int, str, bytes]:
        rec = self._uploads.get(upload_id)
        if rec is None:  # 内存未命中 → 查盘（服务重启后链接仍有效，走查 P2-3）
            p = self.scratch_root / "ingest-uploads" / f"{upload_id}.json"
            if p.is_file():
                try:
                    meta = json.loads(p.read_text(encoding="utf-8"))
                    rec = {
                        "path": Path(meta["path"]),
                        "violations": [Violation(**v) for v in meta.get("violations", [])],
                    }
                except (json.JSONDecodeError, KeyError, OSError, TypeError):
                    rec = None
        if rec is None or not rec["path"].is_file():
            return 404, "application/json", json.dumps(
                {"error": "上传记录不存在或已过期，请重新上传"}, ensure_ascii=False
            ).encode("utf-8")
        out = rec["path"].with_name(f"{rec['path'].stem}_prefill.xlsx")
        build_prefill_template(rec["path"], rec["violations"], out)
        return 200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", out.read_bytes()

    # -- GET /api/ingest/template/<blank|sample>（走查 P1-1：模板获取入口）--
    def api_ingest_template(self, kind: str) -> tuple[int, str, bytes]:
        if kind not in ("blank", "sample"):
            return 400, "application/json", json.dumps(
                {"error": "模板类型仅支持 blank / sample"}, ensure_ascii=False
            ).encode("utf-8")
        out = self.scratch_root / "ingest-uploads" / f"template_{kind}.xlsx"
        out.parent.mkdir(parents=True, exist_ok=True)
        (build_sample_template if kind == "sample" else build_blank_template)(out)
        return 200, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", out.read_bytes()

    # -- GET /api/enterprises --
    def api_enterprises(self) -> tuple[int, Any]:
        return 200, list_enterprises(self.enterprises_root)

    # -- GET /<静态资源>（/ → index.html）--
    def api_static(self, rel: str) -> tuple[int, str, bytes]:
        f = (self.ui_dir / rel).resolve()
        if not str(f).startswith(str(self.ui_dir.resolve())) or not f.is_file():
            return 404, "application/json; charset=utf-8", json.dumps(
                {"error": f"资源不存在：{rel}"}, ensure_ascii=False
            ).encode("utf-8")
        return 200, _MIME.get(f.suffix, "application/octet-stream"), f.read_bytes()

    # -- POST /api/run --
    _FIELD_ZH = {
        "operating_years": "经营年限",
        "public_float_ratio": "公开发行比例",
        "total_shares_after_ipo": "发行后股本总额",
        "mktcap_self_estimate": "预计市值",
    }

    def api_run(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        company = body.get("company")
        if not company:
            return 400, {"error": "未指定测评主体"}
        overrides = body.get("overrides") or {}
        doc_over: dict[str, Any] = overrides.get("documentary") or {}
        dec_over: dict[str, Any] = overrides.get("declared") or {}

        company_dir = self.fixtures_root / "companies" / str(company)
        if not (company_dir / "profile.json").exists():  # 企业主体库兜底（ADR-0013 修订 1）
            alt = self.enterprises_root / str(company)
            if (alt / "profile.json").exists():
                company_dir = alt
            else:
                return 400, {"error": f"测评主体不存在：{company}"}

        overlaid = bool(doc_over or dec_over)
        if overlaid:
            try:
                raw = json.loads((company_dir / "profile.json").read_text(encoding="utf-8"))
                raw.setdefault("documentary", {}).update(doc_over)  # null=清空→indeterminate
                raw.setdefault("declared", {}).update(dec_over)
            except json.JSONDecodeError:
                return 400, {"error": "主体底表数据损坏，请检查后重试"}
            session_dir = (
                self.scratch_root / "ui-runs" / f"{company}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "profile.json").write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if (company_dir / "ingest.json").is_file():  # 企业主体：带出自描述，⑥不误伤（ADR-0013）
                shutil.copyfile(company_dir / "ingest.json", session_dir / "ingest.json")
            company_dir = session_dir

        try:
            ctx = run_eval(
                company_dir=company_dir,
                rulebook_dir=self.rulebook_dir,
                fixtures_root=self.fixtures_root,
                as_of=body.get("as_of"),
                target=RunTarget(boards=body.get("boards"), sets=body.get("sets")),
            )
        except ValidationError as e:  # 补充数据格式错误（extra=forbid / 类型不符）
            first = (e.errors() or [{}])[0]
            tail = ".".join(str(x) for x in first.get("loc", ()) if x != "body").split(".")[-1]
            field = self._FIELD_ZH.get(tail, tail or "输入")
            return 400, {"error": f"补充的数据格式不正确（{field}），请检查后重试"}
        except (EngineError, FileNotFoundError, FixtureDataError) as e:  # lint 红/勾稽红/日期非法 → 统一 400
            return 400, {"error": f"测评未能完成：{e}"}

        # 落盘（CLI 同约定 indent=2 UTF-8；重名/带补录 → 时间戳防覆盖）
        ctx.result["data_source"] = data_source_of(company_dir, self.scratch_root)  # ADR-0013 来源打标
        asof = ctx.run["as_of_date"]
        name = f"{company}_{asof}.json"
        if overlaid or (self.results_dir / name).exists():
            name = f"{company}_{asof}_{datetime.now().strftime('%H%M%S')}.json"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        (self.results_dir / name).write_text(
            json.dumps(ctx.result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )

        gap = ctx.result["layers"]["gap"]
        path = ctx.result["layers"]["path"]
        counts = state_counts(ctx.facts)
        return (
            200,
            {
                "file": name,
                "company_id": ctx.run["company_id"],
                "as_of_date": asof,
                "state_counts": {s: counts.get(s, 0) for s in
                                 ("met", "not_met", "indeterminate", "needs_review", "not_applicable")},
                "applicable": [g.group_id for g in ctx.selection.applicable],
                "sets": [
                    {"group_id": s["group_id"], "outcome": s["outcome"],
                     "progress": s["progress"], "coverage": s["coverage"]}
                    for s in gap["sets"]
                ],
                "recommendation": path["recommendation"],
                "alternatives": path["alternatives"],
            },
        )


# ── HTTP 层（薄壳：路由 + 编解码 + 静态文件）──


def make_handler(app: UiApp) -> type[BaseHTTPRequestHandler]:
    class UiHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: Any) -> None:
            data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _dispatch_api(self, name: str) -> None:
            try:
                if name == "meta":
                    status, payload = app.api_meta()
                elif name == "rulebook":
                    status, payload = app.api_rulebook()
                elif name == "companies":
                    status, payload = app.api_companies()
                elif name == "results":
                    status, payload = app.api_results()
                elif name.startswith("results/"):
                    status, payload = app.api_result_file(unquote(name[len("results/"):]))
                elif name == "enterprises":
                    status, payload = app.api_enterprises()
                elif name.startswith(("ingest/prefill/", "ingest/template/")):
                    # 文件下载：绕过 JSON 编码，按 (status, mime, bytes) 直发
                    if name.startswith("ingest/prefill/"):
                        st, ctype, data = app.api_ingest_prefill(unquote(name[len("ingest/prefill/"):]))
                        fname = "prefill.xlsx"
                    else:
                        kind = unquote(name[len("ingest/template/"):])
                        st, ctype, data = app.api_ingest_template(kind)
                        fname = "填写示例.xlsx" if kind == "sample" else "空白模板.xlsx"
                    self.send_response(st)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(data)))
                    if st == 200:
                        self.send_header(
                            "Content-Disposition",
                            f"attachment; filename*=UTF-8''{quote(fname)}",
                        )
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(data)
                    return
                else:
                    status, payload = 404, {"error": f"未知 API：{name}"}
            except EngineError as e:
                status, payload = 400, {"error": str(e)}
            except FileNotFoundError as e:
                status, payload = 400, {"error": str(e)}
            self._send_json(status, payload)

        def _serve_static(self, path: str) -> None:
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            status, ctype, data = app.api_static(rel)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            # 本地工具 UI 迭代频繁：禁止启发式缓存，避免改完前端浏览器仍用旧 JS
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802（http.server 命名）
            parts = urlsplit(self.path)
            if parts.path.startswith("/api/"):
                self._dispatch_api(parts.path[len("/api/"):].rstrip("/"))
            else:
                self._serve_static(unquote(parts.path))

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/api/ingest/upload":
                # 上传走原始字节流（ADR-0013 修订 1）：文件名/主体 id 在请求头
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    if length > _MAX_UPLOAD:
                        self._send_json(413, {"error": "文件超过 10MB 上限，请确认上传的是填写模板"})
                        return
                    raw = self.rfile.read(length) if length else b""
                    filename = unquote(self.headers.get("X-Filename") or "").strip()
                    cid = unquote(self.headers.get("X-Company-Id") or "").strip() or None
                    status, payload = app.api_ingest_upload(raw, filename, cid)
                except (ValueError, OSError) as e:
                    status, payload = 400, {"error": f"上传失败：{e}"}
                self._send_json(status, payload)
                return
            if path == "/api/ingest/save":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                    status, payload = app.api_ingest_save(body if isinstance(body, dict) else {})
                except json.JSONDecodeError as e:
                    status, payload = 400, {"error": f"请求体不是合法 JSON：{e}"}
                self._send_json(status, payload)
                return
            if path != "/api/run":
                self._send_json(404, {"error": "未知 API（POST 仅 /api/run、/api/ingest/*）"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if length > _MAX_BODY:
                    self._send_json(400, {"error": "上传的文件过大"})
                    return
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                if not isinstance(body, dict):
                    self._send_json(400, {"error": "请求体格式错误，请发送 JSON 对象"})
                    return
                status, payload = app.api_run(body)
            except EngineError as e:
                status, payload = 400, {"error": str(e)}
            except json.JSONDecodeError as e:
                status, payload = 400, {"error": f"请求体不是合法 JSON：{e}"}
            self._send_json(status, payload)

        def log_message(self, fmt: str, *args: Any) -> None:  # 安静些：只留一行
            sys.stderr.write("[webui] %s\n" % (fmt % args))

    return UiHandler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ipo-eval-lab webui", description="IPO 条件测评 · 本地 Web UI（ADR-0012：只绑 127.0.0.1）"
    )
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--open", action="store_true", help="启动后打开浏览器")
    parser.add_argument("--rulebook", default=str(PROJECT_ROOT / "rulebook"))
    parser.add_argument("--fixtures", default=str(PROJECT_ROOT / "fixtures"))
    parser.add_argument("--results", default=str(PROJECT_ROOT / "results"))
    parser.add_argument("--ui", default=str(PROJECT_ROOT / "ui" / "app"))
    args = parser.parse_args(argv)

    app = UiApp(
        rulebook_dir=Path(args.rulebook),
        fixtures_root=Path(args.fixtures),
        results_dir=Path(args.results),
        ui_dir=Path(args.ui),
        scratch_root=PROJECT_ROOT / ".scratch",
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    url = f"http://127.0.0.1:{args.port}"
    print(f"[webui] 服务中：{url}  （Ctrl+C 退出）")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[webui] 已退出")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
