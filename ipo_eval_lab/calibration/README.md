# M1 校准管线说明书

设计文档：[设计 0003](../docs/design/0003-calibration-pipeline.md) · 活动图：[assets/m1-calibration-pipeline.png](../docs/design/assets/m1-calibration-pipeline.png)

## 定位

AI 辅助 + 三道异构闸门 + 两级入库。**管线自身不调用模型**——L1a（AI 提取）与 L2（回译判断）由外部 agent 会话执行，产出 JSON 落盘；管线只做确定性校验与合成。

```
candidates.jsonl（L1a 产出）  ─┐
l2_judgments.jsonl（L2 产出） ─┴→ [ L0 → L1b → L2 解析 → L3 ] → candidates/ + review-queue/ + report.md
```

## 快速开始

```bash
# 只跑 L0（毫秒级，零 AI 成本，先筛掉结构垃圾）
python -m ipo_eval_lab.calibration check \
    --candidates candidates.jsonl --as-of 2026-11-11

# 完整批次（L2 判定从预跑结果读入）
python -m ipo_eval_lab.calibration run \
    --candidates candidates.jsonl \
    --l2-judgments l2_judgments.jsonl \
    --as-of 2026-11-11 \
    --output results/calibration
```

## 文件布局

```
config/anchor_normalization.yaml   R10 归一化规则表（中文数字/单位/算子/量词/窗口）
calibration/midas_snapshot.yaml    L3 对比基线（占位，待 midas 导出填充）
ipo_eval_lab/calibration/
  ├─ models.py       Pydantic 契约（CandidateRule / GateResult / EvidencePack / ...）
  ├─ l0_gate.py      L0 八项 lint（0-1 ～ 0-8）
  ├─ l1b_gate.py     引文逐字命中 / 数值锚点 / 覆盖率扫描
  ├─ l2_gate.py      确定性渲染器 + NLI prompt 构建 + 结果解析
  ├─ l3_gate.py      midas 逐 leaf diff（五分类）+ 差异清单生成
  ├─ confidence.py   g1~g4 合成 + evidence pack
  ├─ pipeline.py     主流程编排 + 落盘
  └─ __main__.py     CLI（run / check）
```

## 门禁语义

| 闸门 | 谁跑 | 失败处置 |
|---|---|---|
| L0 | 管线（零 AI） | 该条直接进人工队列，不调模型 |
| L1a | 外部 agent | 解析失败 → 进人工队列 |
| L1b | 管线（零 AI） | 引文/锚点硬拦截；覆盖率警告降为 g2 |
| L2 | 外部 agent | `equivalent≠yes` → 人工队列 |
| L3 | 管线（零 AI） | value/structure_diff → g3（入库但必检） |

## 置信度

```
g4 = L0✓ ∧ L1b✓ ∧ L2=yes ∧ L3=exact           → 自动入候选库
g3 = 前三项✓ ∧ L3=value/structure_diff        → 候选库 + 必检标记
g2 = 覆盖率警告 / partial                      → 人工队列
g1 = 任一硬拦截                                → 人工队列（evidence pack）
```

## 边界（D3 / AR2）

- 引擎运行时零 AI：管线产出 `rulebook/*.yaml`，引擎只加载正式库
- 正式库只能由人工签核产生（R3）
- 模型配置不在代码里写死，L1a/L2 由外部注入
