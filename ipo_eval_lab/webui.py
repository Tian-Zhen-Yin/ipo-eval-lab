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
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from pydantic import ValidationError

from .engine import EngineError, RunTarget, run_eval
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
                out.append({"file": p.name, "mtime": p.stat().st_mtime, "run": run})
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
        if not (company_dir / "profile.json").exists():
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
        except (EngineError, FileNotFoundError) as e:  # lint 红/勾稽红/日期非法 → 统一 400
            return 400, {"error": f"测评未能完成：{e}"}

        # 落盘（CLI 同约定 indent=2 UTF-8；重名/带补录 → 时间戳防覆盖）
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
            if urlsplit(self.path).path != "/api/run":
                self._send_json(404, {"error": "未知 API（POST 仅 /api/run）"})
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
