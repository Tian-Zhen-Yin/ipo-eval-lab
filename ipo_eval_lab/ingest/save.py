"""enterprises/ 保存与列表（ADR-0013；工单 02 从 CLI 提取，CLI/webui 共用）。

防覆盖语义：目录已存在且未显式 overwrite → SaveRefused，原目录字节不动——
不可再生数据永不静默覆盖（ADR-0013）。CLI 的 exit 2 与「--overwrite」文案归
调用方（__main__），本模块只给可编程语义。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path


class SaveRefused(Exception):
    """目标主体已存在且未显式覆盖。"""


def save_enterprise(
    company_dir: Path | str,
    company_id: str,
    enterprises_root: Path | str,
    overwrite: bool = False,
) -> Path:
    """把导入会话目录（三件套）保存为 enterprises/<company_id>/。"""
    dest = Path(enterprises_root) / company_id
    if dest.exists() and not overwrite:
        raise SaveRefused(f"{dest} 已存在。不可再生数据永不静默覆盖——请显式覆盖或更换 company_id。")
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(Path(company_dir), dest)
    return dest


def list_enterprises(enterprises_root: Path | str) -> list[dict]:
    """列出已保存企业主体：ingest.json + profile.json 摘要；坏目录跳过不炸。"""
    root = Path(enterprises_root)
    if not root.is_dir():
        return []
    items: list[dict] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        meta_path, prof_path = d / "ingest.json", d / "profile.json"
        if not (meta_path.is_file() and prof_path.is_file()):
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            prof = json.loads(prof_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items.append(
            {
                "company_id": prof.get("company_id", d.name),
                "display_name": prof.get("display_name"),
                "imported_at": meta.get("imported_at"),
                "source_sha256": meta.get("source_sha256"),
                "fiscal_years": [s.get("fiscal_year") for s in prof.get("statements", [])],
            }
        )
    return items
