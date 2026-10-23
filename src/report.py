# -*- coding: utf-8 -*-
"""HTML 周报生成：静态单页 + 历史归档，Pages 托管"""
import html
import logging
from datetime import date
from pathlib import Path

from .config import BAND_LABELS

log = logging.getLogger("valpulse.report")

BAND_CLASS = {
    "undervalued": "band-low",
    "fair": "band-fair",
    "high": "band-high",
    "over": "band-over",
    "unknown": "band-unknown",
}

CSS = """
:root { --ink:#26251F; --muted:#6B6A62; --line:#E4E2DA; --bg:#FAFAF7; --card:#FFFFFF; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  font-size:14px; line-height:1.65; }
.wrap { max-width:960px; margin:0 auto; padding:28px 20px 60px; }
header h1 { font-size:22px; margin:0 0 4px; }
header .sub { color:var(--muted); font-size:13px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:20px 0; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }
.card .k { color:var(--muted); font-size:12px; }
.card .v { font-size:20px; font-weight:600; margin-top:2px; }
table { width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--line); border-radius:10px; overflow:hidden; font-size:13px; }
th,td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--line); white-space:nowrap; }
th:first-child,td:first-child { text-align:left; }
th { background:#F3F1EA; font-weight:600; color:#4A4940; }
tr:last-child td { border-bottom:none; }
tr.cat td { background:#F7F6F1; font-weight:600; text-align:left; color:#4A4940; }
.band { display:inline-block; padding:1px 8px; border-radius:8px; font-size:12px; color:#fff; }
.band-low { background:#2E9B62; } .band-fair { background:#378ADD; }
.band-high { background:#EF9F27; } .band-over { background:#E24B4A; }
.band-unknown { background:#B4B2A9; }
.up { color:#D33F3F; } .down { color:#2E9B62; }
figure { margin:22px 0; background:var(--card); border:1px solid var(--line);
  border-radius:10px; padding:14px; }
figure img { width:100%; height:auto; }
figcaption { color:var(--muted); font-size:12px; margin-top:8px; }
.notes { color:var(--muted); font-size:12px; margin-top:26px; }
.notes li { margin:3px 0; }
footer { margin-top:18px; color:var(--muted); font-size:12px; }
a { color:#185FA5; }
"""


def _fmt(v, nd=2):
    return f"{v:.{nd}f}" if isinstance(v, (int, float)) else "-"


def _chg_cell(v):
    if not isinstance(v, (int, float)):
        return "<td>-</td>"
    cls = "up" if v > 0 else ("down" if v < 0 else "")
    sign = "+" if v > 0 else ""
    return f'<td class="{cls}">{sign}{v:.2f}%</td>'


def _band_cell(band):
    return f'<td><span class="band {BAND_CLASS.get(band, "band-unknown")}">{BAND_LABELS[band]}</span></td>'


def render(records: list, charts: dict, out_dir: Path, report_date: str,
           prev: dict | None) -> Path:
    """生成 reports/<日期>/index.html；out_dir 为日期目录"""
    out_dir.mkdir(parents=True, exist_ok=True)
    chart_links = {}
    for name, path in charts.items():
        if path and Path(path).exists():
            (out_dir / Path(path).name).write_bytes(Path(path).read_bytes())
            chart_links[name] = Path(path).name

    cn = [r for r in records if r["market"] == "cn"]
    cross = [r for r in records if r["market"] == "cross"]
    order = {"宽基": 0, "行业": 1, "策略": 2}

    def table_rows(items):
        html_rows = []
        last_cat = None
        for r in sorted(items, key=lambda x: (order.get(x["category"], 9), x["name"])):
            if r["category"] != last_cat:
                html_rows.append(f'<tr class="cat"><td colspan="8">{r["category"]}</td></tr>')
                last_cat = r["category"]
            wow = ""
            prev_rec = (prev or {}).get(r["code"], {})
            if prev_rec.get("pe_percentile") is not None and r.get("pe_percentile") is not None:
                d = r["pe_percentile"] - prev_rec["pe_percentile"]
                wow = f' ({d:+.1f})'
            html_rows.append(
                f"<tr><td>{html.escape(r['name'])}</td>"
                f"<td>{_fmt(r.get('pe_value'))}</td>"
                f"<td>{_fmt(r.get('pe_percentile'), 1) + '%' if r.get('pe_percentile') is not None else '-'}{wow}</td>"
                f"{_band_cell(r.get('pe_band'))}"
                f"<td>{_fmt(r.get('pb_value'))}</td>"
                f"<td>{_fmt(r.get('pb_percentile'), 1) + '%' if r.get('pb_percentile') is not None else '-'}</td>"
                f"{_band_cell(r.get('pb_band'))}"
                f"{_chg_cell(r.get('change_pct'))}</tr>")
        return "\n".join(html_rows)

    valid_pcts = [r["pe_percentile"] for r in records if r.get("pe_percentile") is not None]
    avg_pct = sum(valid_pcts) / len(valid_pcts) if valid_pcts else None
    low_n = sum(1 for r in records if r.get("pe_band") == "undervalued")
    high_n = sum(1 for r in records if r.get("pe_band") in ("high", "over"))

    cards = f"""
    <div class="cards">
      <div class="card"><div class="k">覆盖指数</div><div class="v">{len(records)}</div></div>
      <div class="card"><div class="k">PE 平均分位</div><div class="v">{_fmt(avg_pct, 1) + '%' if avg_pct is not None else '-'}</div></div>
      <div class="card"><div class="k">低估（PE&lt;20%）</div><div class="v">{low_n}</div></div>
      <div class="card"><div class="k">偏高+高估（PE&gt;70%）</div><div class="v">{high_n}</div></div>
    </div>"""

    figures = ""
    if chart_links.get("overview"):
        figures += (f'<figure><img src="{chart_links["overview"]}" alt="估值分位总览">'
                    f"<figcaption>绿色=低估（&lt;20%），蓝色=合理（20-70%），橙色=偏高（70-90%），红色=高估（&gt;90%）</figcaption></figure>")
    if chart_links.get("trends"):
        figures += (f'<figure><img src="{chart_links["trends"]}" alt="重点指数估值走势">'
                    f"<figcaption>虚线为窗口内 20/50/80 分位参考线，红点为最新值</figcaption></figure>")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>指数估值周报 {report_date}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>指数估值周报</h1>
  <div class="sub">{report_date} · 数据截至当日收盘 · 分位口径：近10年（剔除亏损期）</div>
</header>
{cards}
<figure><table>
<thead><tr><th>指数</th><th>PE</th><th>PE分位</th><th>状态</th><th>PB</th><th>PB分位</th><th>状态</th><th>日涨跌</th></tr></thead>
<tbody>
{table_rows(cn)}
<tr class="cat"><td colspan="8">跨境（月频数据）</td></tr>
{table_rows(cross)}
</tbody>
</table></figure>
{figures}
<div class="notes">
<ul>
<li>分位 = 当前值在近10年历史样本中的百分位（样本剔除 PE 为负的亏损期）；括号内为较上周变化。</li>
<li>A 股 PE/PB 为乐咕乐股等权口径（历史约 2005 年至今）；标普500/恒生科技为月度频率，PB 暂无免费数据源故留空。</li>
<li>日涨跌按 A 股惯例：红涨绿跌。数据来源于乐咕乐股、中证指数官网、腾讯行情、multpl.com、恒生指数公司。</li>
<li>本报告仅为数据整理，不构成投资建议。</li>
</ul>
</div>
<footer>ValPulse 自动生成 · <a href="../index.html">最新周报</a> · <a href="../archive.html">历史归档</a></footer>
</div>
</body>
</html>"""
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return out_dir / "index.html"


def render_archive(report_root: Path, items: list):
    """生成归档索引页，items 为 [(date, title), ...] 按日期降序"""
    rows = "\n".join(
        f'<li><a href="./{d}/index.html">{html.escape(t)}</a></li>' for d, t in items)
    page = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>估值周报归档</title><style>{CSS}</style></head>
<body><div class="wrap"><header><h1>估值周报归档</h1>
<div class="sub">ValPulse 每周自动生成</div></header>
<ul style="line-height:2">{rows}</ul>
<p><a href="./index.html">返回最新周报</a></p></div></body></html>"""
    (report_root / "archive.html").write_text(page, encoding="utf-8")
