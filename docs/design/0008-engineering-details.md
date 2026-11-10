# 设计 0008：工程细节（#7 决策与实现期启动）

- 日期：2026-11-10
- 性质：**系统设计收官后的工程决策**——Python 版本 / 包管理 / CLI 入口 / 测试布局 / 输出目录；吸收未决 **#7**
- 输入：[设计 0004](0004-system-architecture.md) A6（实现期顺序）、现状（代码 3.10 兼容、c68d02e 已有 `python -m ipo_eval_lab.rulebook` CLI、根目录 tests/ 布局）
- 决策点：E1~E5（§2，**2026-11-10 已拍板：全部按推荐**）。编号前缀 **E**（Engineering），与设计 0005 的 E1~E9 区分；引用带文档号（如「设计 0008-E2」）。

---

## 0. 现状

- 代码库已验证 3.10 兼容（c68d02e，`sys.path.insert` 隔离用户 site-packages）
- CLI 入口已实现：`python -m ipo_eval_lab.rulebook [path] [--strict]`（设计 0002 第 5 步落盘）
- 测试：根目录 `tests/test_rulebook_load.py`（12 测），`conftest.py`（仅注释）
- 输出目录：`results/` 未入 git（`ui/` 也是未跟踪目录）

## 1. 决策点（E1~E5）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| E1 | Python 版本：保持 3.10 兼容 vs 升级到 3.12 | 3.10 / 3.12 | **3.10**——当前代码已验证兼容；升级收益（性能/语法糖）对原型阶段不值代价；待需要时再升（pyproject.toml 锁 3.10+） |
| E2 | 是否引入 uv（现代包管理工具） | 引入 / 不引入 | **不引入**——v1 个人实验项目，pip + pyproject.toml 已够；uv 的依赖锁定与并发安装收益在单体库下不明显 |
| E3 | CLI 入口形态：`-m` 模块调用 vs console script | `-m` / console script | **保持 `-m`**——c68d02e 已验证路径；console script 在不同环境下需要额外安装配置，`-m` 直接可用 |
| E4 | pytest 布局：根目录 `tests/` vs 拆 `tests/` + `tests/unit/integration` | 根目录 `tests/` / 拆分 | **根目录 `tests/`**——当前 12 测全绿；拆分层级空收益（v1 规模下无需隔离） |
| E5 | `results/` 输出目录是否入 git | 入 / 不入 | **不入**——测评输出是用户产物，版本控制无意义；`.gitignore` 明确 |

> **拍板记录：2026-11-10 —— E1~E5 全部按推荐通过。** #7 关闭；实现期按 A6 顺序即刻启动（M3 → M4/M5 → M1 全量 → 边界族回归）。

## 2. 实现期启动确认（A6 已定序，现附执行清单）

| 阶段 | 交付物 | 验收标准 |
|---|---|---|
| M3 fixtures | `fixtures/` loader + base_co_2029 profile.json + qualified_audit 变体 + 两生成器族（±ε / knockout） | 勾稽七条断言全过；甲公司端到端（设计 0005 §末）golden 匹配 |
| M4/M5 引擎 | 五节点责任链实现 + 样板套端到端（设计 0002 的 2 个套 × 甲公司） | result.json 合契约 v0.2；层①②③ 四轴输出；甲公司自检链通过 |
| M1 校准管线 | 校准管线跑全量 43 套 → 候选库 / 人工队列 / 正式库 | L0~L3 闸门逻辑（L0=loader lint）；43 套产出后 rulebook/ 升版 |
| 边界族回归 | 生成器族集成到测试套件 | ±ε 全量阈值翻转；knockout 缺数场景全覆盖 |
| （可选）M8 桥 | YAML → midas 预置表导出 | 中性：不承诺 |

启动时点：E1~E5 拍板后即启动，顺序不变。

## 3. pyproject.toml 粗胚（草案，随 M3/M4 补充）

```toml
[project]
name = "ipo-eval-lab"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.13.4",
    "pyyaml>=6.0.3",
    "pytest>=9.0.3",
]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
```

## 4. .gitignore 补充

```
results/
__pycache__/
*.pyc
.pytest_cache/
```

## 5. 与 #7 的关系

E1~E5 拍板后 **#7 关闭**；实现期随 A6 顺序启动，不再有「前置决策」阻塞。
