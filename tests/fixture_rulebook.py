"""引擎测试夹具：把**正式库的数据层**与**样板套的结构层**装成一个规则库根。

## 为什么要有这个

`rulebook/sets/` 是**正式库**——ADR-0005 R3 的产物，只含已签核条款，由
`export-official` 落盘。它覆盖全部 28 个套、生效日是现行版（2026-04-30）。

引擎的**结构验证**（设计 0002 步骤 2 的两个验证件）需要的是另一种东西：
- `star_general.yaml`：group 内 branch 择一
- `cn_main_general.yaml`：clause 内联「或」→ clause any + 快照两行 collapse
  到同一 branch（R2-a）

这两份手写样板套含 midas 溯源别名（IPO-15/16、IPO-01/02），是**设计形态的证据**，
正式库的机器导出版本没有这些别名。二者不能互相替代：
- 用正式库跑结构验证 → 验不到「分支择一」与「clause any」（正式库里是别的形态）
- 用样板套跑生产回归 → 验的是 2 个套，不是 28 个套，且生效日是旧的

所以：**数据层用正式库、结构层用样板套**，装到一起给引擎用。

## 怎么装

正式库的 `_meta.yaml` / `metrics.yaml` / `items.yaml` / `legal/` **只读复用**
（不复制、不快照）——否则改一条 item 要同步两处，迟早漂移。
只有 `sets/` 换成夹具里的样板套。

用法：

```python
from tests.fixture_rulebook import fixture_rulebook_dir
rb_dir = fixture_rulebook_dir()      # 临时目录，可直接给 load_rulebook / run_eval
```
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO = Path(__file__).resolve().parents[1]
OFFICIAL = REPO / "rulebook"
SAMPLE_SETS = Path(__file__).resolve().parent / "fixtures" / "rulebook" / "sets"

# 复用的数据层（只读）
_DATA_LAYER = ("_meta.yaml", "metrics.yaml", "items.yaml")
_DATA_DIRS = ("legal",)


@contextmanager
def fixture_rulebook_dir() -> Iterator[Path]:
    """产出临时规则库根：正式库数据层 + 样板套 sets/。退出时清理。"""
    tmp = Path(tempfile.mkdtemp(prefix="rb_fixture_"))
    try:
        for name in _DATA_LAYER:
            shutil.copy2(OFFICIAL / name, tmp / name)
        for d in _DATA_DIRS:
            shutil.copytree(OFFICIAL / d, tmp / d)
        # sets/ 换成样板套——正式库的套不参与结构验证
        shutil.copytree(SAMPLE_SETS, tmp / "sets")
        yield tmp
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


__all__ = ["fixture_rulebook_dir", "OFFICIAL", "SAMPLE_SETS"]
