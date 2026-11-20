"""data_source 判定（ADR-0013；工单 04）：目录自描述优先，调用方根兜底。

- enterprise：目录含 ingest.json（导入三件套之一）——.scratch/ingest 下的导入
  会话目录与 enterprises/ 下的显式保存目录都命中此条，故优先于路径判定；
- session：位于调用方的 scratch 根之下（webui 补录 ui-runs 的先例）——
  scratch 根由调用方传入（它知道自己建在哪），不按目录名猜；
- fixture：fixtures/companies 下的 mock 主体。
"""
from __future__ import annotations

from pathlib import Path

from typing import Literal

DataSource = Literal["fixture", "session", "enterprise"]


def data_source_of(
    company_dir: Path | str, scratch_root: Path | str | None = None
) -> DataSource:
    d = Path(company_dir).resolve()
    if (d / "ingest.json").is_file():
        return "enterprise"
    if scratch_root is not None and d.is_relative_to(Path(scratch_root).resolve()):
        return "session"
    return "fixture"
