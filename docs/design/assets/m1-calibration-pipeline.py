# -*- coding: utf-8 -*-
"""M1 校准管线活动图 —— 卡片流水线版（matplotlib 自绘，E 方案）。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import font_manager

for cand in ["Microsoft YaHei", "SimHei", "DengXian"]:
    if any(cand.lower() in f.name.lower() for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

BG, INK, MUTED = "#ffffff", "#0f172a", "#64748b"
BLUE = ("#eff6ff", "#3b82f6")
AMBER = ("#fffbeb", "#f59e0b")
GREEN = ("#ecfdf5", "#10b981")
RED = ("#fef2f2", "#ef4444")
GRAY = ("#f8fafc", "#94a3b8")
ORANGE = ("#fff7ed", "#f97316")

fig = plt.figure(figsize=(16, 9), dpi=150, facecolor=BG)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")


def card(x, y, w, h, title, lines, fill, stroke=None, tsize=11.0, lsize=8.5,
         accent=True, tcolor=INK):
    if stroke is None:
        fill, stroke = fill
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.9",
        linewidth=1.5, edgecolor=stroke, facecolor=fill, zorder=2))
    if accent:
        ax.add_patch(FancyBboxPatch(
            (x, y + h - 0.5), w, 0.5, boxstyle="round,pad=0,rounding_size=0.25",
            linewidth=0, facecolor=stroke, zorder=3))
    ty = y + h - (1.8 if accent else 1.3)
    ax.text(x + w / 2, ty, title, ha="center", va="center",
            fontsize=tsize, fontweight="bold", color=tcolor, zorder=4)
    if accent:
        ty -= 1.8
    for i, ln in enumerate(lines):
        ax.text(x + w / 2, ty - i * 1.45, ln, ha="center", va="center",
                fontsize=lsize, color=MUTED, zorder=4)


def arrow(x1, y1, x2, y2, color="#94a3b8", style="-", label=None, lw=1.5,
          rad=0.0, lx=None, ly=None, lsize=8.0, lcolor=None):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=13,
        linewidth=lw, color=color, linestyle=style,
        connectionstyle=f"arc3,rad={rad}", zorder=1))
    if label:
        ax.text(lx if lx is not None else (x1 + x2) / 2,
                ly if ly is not None else (y1 + y2) / 2, label,
                ha="center", va="center", fontsize=lsize,
                color=lcolor or color, zorder=5,
                bbox=dict(boxstyle="round,pad=0.24", fc="white", ec="none", alpha=0.96))


def pill(x, y, w, h, text, fill, stroke, tcolor="#334155", size=8.4):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=1.1",
        linewidth=1.2, edgecolor=stroke, facecolor=fill, zorder=3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=size, color=tcolor, zorder=4)


# ── 标题 ──
ax.text(3, 96.2, "M1 校准管线 · 活动图", fontsize=19, fontweight="bold",
        color=INK, ha="left", va="center")
ax.text(3, 92.6, "三道异构闸门 + 两级入库　·　AI 只出现在候选库之前，正式库必须人工签核",
        fontsize=10.5, color=MUTED, ha="left", va="center")

# ── 泳道 ──
ax.add_patch(FancyBboxPatch(
    (2.6, 27.5), 94.8, 60.5, boxstyle="round,pad=0,rounding_size=1.4",
    linewidth=1.4, edgecolor="#cbd5e1", facecolor="#fcfdff",
    linestyle=(0, (5, 4)), zorder=0))
ax.text(4.6, 86.2, "泳道：校准管线（确定性代码为主 · 运行时零 AI）",
        fontsize=10, fontweight="bold", color="#475569", ha="left", va="center")

# ── 第一排：五个闸门 ──
GY, GH, GW, GS = 68.5, 13.2, 15.2, 2.6
gates = [
    ("L0　确定性闸门", ["8 项 lint · 零 AI · 毫秒级",
                        "量纲 / 唯一性 / 悬空引用",
                        "窗口不重述 / 版本对齐"], BLUE),
    ("L1a　AI 提取", ["温度 0 · 全库仅 1 次生成",
                      "metric 白名单 26 项",
                      "quote 必须逐字摘抄"], AMBER),
    ("L1b　锚点核对", ["引文逐字命中防编造",
                      "数值锚点须在归一化集合内",
                      "覆盖率扫描（抓漏条件）"], BLUE),
    ("L2　回译闸门", ["结构化 → 渲染回中文",
                      "异构模型做等价判断",
                      "判断题，不是问答题"], AMBER),
    ("L3　快照闸门", ["与 midas 现值逐条 diff",
                      "exact / value_diff",
                      "structure_diff / 仅一侧有"], BLUE),
]
xs, x = [], 5.2
for title, lines, (f, s) in gates:
    card(x, GY, GW, GH, title, lines, f, s)
    xs.append((x, x + GW))
    x += GW + GS
for i in range(4):
    arrow(xs[i][1], GY + GH / 2, xs[i + 1][0], GY + GH / 2, color="#475569", lw=1.8)

# ── 第二排：原文库 / 置信度合成 / 差异清单 ──
card(5.2, 50.0, 26.0, 11.6, "原文库　source_texts/",
     ["2221 条 · 五板块上市规则全文切分",
      "每条带 文档名 / 版本 / 生效日",
      "条款号 / 正文"], GRAY)
card(35.0, 50.0, 30.0, 11.6, "置信度合成　g1 ~ g4",
     ["由可验证事实合成，不采信模型自报",
      "g4 自动入候选库 · g3 入库但必检",
      "g2 / g1 进人工队列"], GRAY)
card(69.0, 50.0, 26.0, 11.6, "副产品：midas 差异清单",
     ["L3 天然产出，服务 midas 数据治理",
      "快照有原文无 → 旧规残留 / 漏收",
      "原文有快照无 → 新规，正常记录"], GRAY)

arrow(12.8, GY, 12.8, 61.6, color="#475569", lw=1.6)
ax.text(11.2, 64.6, "输入", fontsize=8.4, color="#475569", ha="center", va="center")
# L3 → 差异清单（垂直）
arrow(84.0, GY, 84.0, 61.6, color="#94a3b8", style="--", lw=1.4)
# L3 → 置信度合成（回弯）
arrow(78.6, GY, 62.0, 61.6, color="#475569", lw=1.8, rad=-0.22)

# ── 第三排：候选库 / 人工队列 / 正式库 ──
BY, BH = 33.0, 11.4
card(5.2, BY, 26.0, BH, "候选库　candidates/",
     ["机器可入：g4 自动 · g3 带必检标记",
      "仍需人工签核后才进正式库"], GREEN)
card(37.0, BY, 26.0, BH, "人工队列　review-queue/",
     ["evidence pack = 原文引文 + 候选结构",
      "+ 哪道闸为什么红 · 单条 1 分钟审完"], RED)
card(68.8, BY, 26.2, BH, "正式库　rulebook/",
     ["人工签核产生 · 引擎唯一加载源",
      "midas 预置表成为 YAML 的投影视图"], GREEN)

arrow(42.0, 50.0, 18.2, BY + BH, color="#475569", lw=1.8, rad=0.16,
      label=" g4 / g3 ", lx=27.0, ly=47.6, lcolor="#047857")
arrow(58.0, 50.0, 50.0, BY + BH, color=RED[1], lw=1.8,
      label=" g2 / g1 ", lx=57.5, ly=47.6, lcolor="#b91c1c")

# ── 红色总线：L0 / L1b / L2 的红 → 人工队列 ──
BUS = 46.6
ax.plot([12.8, 50.0], [BUS, BUS], color=RED[1], linewidth=1.4,
        linestyle=(0, (4, 3)), zorder=1)
for gx in (12.8, 48.4, 66.2):
    ax.plot([gx, gx], [GY, BUS], color=RED[1], linewidth=1.4,
            linestyle=(0, (4, 3)), zorder=1)
arrow(50.0, BUS, 50.0, BY + BH, color=RED[1], lw=1.6)
ax.text(24.0, BUS + 1.2, "任一闸门红 → 该条进人工队列（批次不中止）",
        fontsize=8.4, color=RED[1], ha="left", va="center")

# ── 第四排：规则工程师签核 ──
card(10.0, 16.0, 80.0, 10.6, "规则工程师签核",
     ["① 打开 evidence pack：原文引文、候选结构、每道闸的红 / 绿原因，一屏看完",
      "② 判定后签核入库　→　批次继续，不因单条失败中止"], ORANGE, tsize=11.5)

arrow(18.2, BY, 18.2, 26.6, color="#475569", lw=1.6)
arrow(50.0, BY, 50.0, 26.6, color="#475569", lw=1.6)
arrow(81.9, 26.6, 81.9, BY, color="#475569", lw=1.8)
ax.text(83.6, 29.8, "签核入库", fontsize=8.4, color="#475569",
        ha="left", va="center")

# ── 图例 ──
ax.text(5.2, 9.4, "图例", fontsize=9.5, fontweight="bold", color="#475569",
        ha="left", va="center")
leg = [("确定性闸门（零 AI）", BLUE), ("AI 调用（管线内 · 运行时无 AI）", AMBER),
       ("产物 / 存储", GREEN), ("人工介入", ORANGE), ("人工队列 / 拦截", RED)]
lx = 11.6
for name, (f, s) in leg:
    pill(lx, 8.2, 16.4, 2.5, name, f, s)
    lx += 17.0

ax.text(5.2, 4.4,
        "闸门失败模式互不重叠：L1 抓提取与锚点（数据视图独立）· L2 抓 AND/OR 与量词结构（任务独立）· L3 抓版本与旧值（快照独立）",
        fontsize=8.8, color=MUTED, ha="left", va="center")

fig.savefig("C:/Users/17402/AppData/Local/Temp/m1viz/e.png",
            dpi=150, facecolor=BG, bbox_inches="tight", pad_inches=0.2)
print("saved e.png")
