# -*- coding: utf-8 -*-
"""图表生成：分位总览条形图 + 重点指数估值走势图"""
import logging
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.dates import DateFormatter, MonthLocator  # noqa: E402

log = logging.getLogger("valpulse.charts")

BAND_COLORS = {
    "undervalued": "#2E9B62",
    "fair": "#378ADD",
    "high": "#EF9F27",
    "over": "#E24B4A",
    "unknown": "#B4B2A9",
}
UP_RED = "#D33F3F"
DOWN_GREEN = "#2E9B62"
LINE_BLUE = "#378ADD"
GRID_GRAY = "#B4B2A9"


def setup_font():
    """按平台可用中文字体设置，避免图表中文乱码"""
    candidates = ["Microsoft YaHei", "Noto Sans CJK SC", "PingFang SC",
                  "WenQuanYi Zen Hei", "SimHei"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            plt.rcParams["font.family"] = [name]
            break
    else:
        log.warning("未找到中文字体，图表中文可能显示为方块")
    plt.rcParams["axes.unicode_minus"] = False


def chart_overview(records: list, out_path: str, bands: list):
    """分位总览：横向条形图，每条为一个指数的 PE 或 PB 分位，按分级着色"""
    items = []
    for r in records:
        if r.get("pe_percentile") is not None:
            items.append((f"{r['name']} PE", r["pe_percentile"], r["pe_band"]))
        if r.get("pb_percentile") is not None:
            items.append((f"{r['name']} PB", r["pb_percentile"], r["pb_band"]))
    if not items:
        return False
    items.sort(key=lambda x: x[1])
    labels = [i[0] for i in items]
    values = [i[1] for i in items]
    colors = [BAND_COLORS.get(i[2], BAND_COLORS["unknown"]) for i in items]

    fig_h = max(4.0, 0.32 * len(items) + 1.6)
    fig, ax = plt.subplots(figsize=(9.2, fig_h), dpi=150)
    y = range(len(items))
    ax.barh(list(y), values, color=colors, height=0.62, zorder=3)
    for i, v in zip(y, values):
        ax.text(v + 1.2, i, f"{v:.0f}%", va="center", fontsize=9, color="#444441")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlim(0, 108)
    ax.set_xlabel("近10年历史分位（%）", fontsize=10)
    for xv in bands:
        ax.axvline(xv, color=GRID_GRAY, lw=0.8, ls="--", zorder=2)
        ax.text(xv, len(items) - 0.2, f"{xv}%", ha="center", fontsize=8,
                color="#5F5E5A")
    ax.set_title("主要指数估值分位总览（PE/PB，近10年）", fontsize=13, pad=12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", color="#E8E6DF", lw=0.6, zorder=0)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return True


def chart_trends(series_list: list, out_path: str):
    """重点指数估值走势：2x2 子图，折线 + 20/50/80 分位参考线 + 当前值标注"""
    series_list = [s for s in series_list if len(s["points"]) >= 2]
    if not series_list:
        return False
    n = len(series_list)
    cols = 2
    rows = (n + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(10.5, 3.4 * rows),
                             dpi=150, squeeze=False)
    for idx, s in enumerate(series_list):
        ax = axes[idx // cols][idx % cols]
        pts = s["points"]
        xs = [datetime.strptime(p[0], "%Y-%m-%d") for p in pts]
        ys = [p[1] for p in pts]
        vals = sorted(ys)
        q20 = vals[int(len(vals) * 0.2)]
        q50 = vals[int(len(vals) * 0.5)]
        q80 = vals[int(len(vals) * 0.8)]
        for q, lb in ((q20, "20%"), (q50, "50%"), (q80, "80%")):
            ax.axhline(q, color=GRID_GRAY, lw=0.7, ls="--")
            ax.text(xs[0], q, f" {lb}", fontsize=7.5, color="#5F5E5A", va="bottom")
        ax.plot(xs, ys, color=LINE_BLUE, lw=1.4)
        cur = s["current"]
        ax.scatter([xs[-1]], [cur], color=UP_RED, s=28, zorder=5)
        ax.annotate(f"{cur:.1f}（{s['percentile']:.0f}%分位）",
                    (xs[-1], cur), textcoords="offset points", xytext=(-8, 10),
                    ha="right", fontsize=9, color=UP_RED)
        ax.set_title(s["name"], fontsize=11)
        ax.xaxis.set_major_locator(MonthLocator(interval=24))
        ax.xaxis.set_major_formatter(DateFormatter("%Y-%m"))
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#E8E6DF", lw=0.6)
        ax.tick_params(labelsize=8.5)
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig.suptitle("重点指数近10年估值走势", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    return True
