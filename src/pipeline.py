# -*- coding: utf-8 -*-
"""ValPulse 主流程：抓取 -> 分位 -> 图表 -> 报告 -> 推送"""
import json
import logging
import shutil
import sys
from datetime import date
from pathlib import Path

from . import charts as charts_mod
from . import fetchers, percentile as pct_mod
from .config import (BAND_LABELS, REPORT_DIR, SNAPSHOT_DIR, all_indexes,
                     load_config)
from .push import build_summary, push_summary
from .report import render, render_archive

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("valpulse.pipeline")

# 乐咕字段口径：addTtmPe/addPb 与中证官方整体法交叉验证一致（差异<5%）
PE_KEY = "addTtmPe"
PB_KEY = "addPb"


def _pe_key_of(rows: list) -> str:
    """按数据源返回可用的 PE 字段名"""
    if not rows:
        return "addTtmPe"
    keys = set()
    for r in rows[:20]:
        keys.update(r.keys())
    if "addTtmPe" in keys:
        return "addTtmPe"
    if "pe" in keys:
        return "pe"
    return "ttmPe"


def fetch_all(cfg: dict) -> tuple:
    """抓取全部指数原始数据，返回 (raw, failed)"""
    fcfg = cfg.get("fetch", {})
    lg = fetchers.LeguleguClient(
        interval=fcfg.get("interval_seconds", 8),
        csrf_ttl=fcfg.get("csrf_refresh_seconds", 100),
        max_retries=fcfg.get("max_retries", 3),
        backoff=tuple(fcfg.get("backoff_seconds", [20, 45, 90])),
    )
    raw, failed = {}, []
    for item in all_indexes(cfg):
        code, market = item["code"], item["market"]
        entry = {"meta": item, "pe": None, "pb": None}
        try:
            if market == "cn":
                entry["pe"] = lg.fetch_pe(code)
                entry["pb"] = lg.fetch_pb(code)
                if not entry["pe"]:
                    csi = fetchers.fetch_csi_pe(code)
                    if csi:
                        entry["pe"] = csi
                        entry["pe_fallback"] = "csi"
                        log.info("%s 乐咕 PE 失败，已用中证官网兜底（%d 行）",
                                 code, len(csi))
            elif item.get("source") == "multpl":
                entry["pe"] = fetchers.fetch_multpl_spx()
                entry["frequency"] = "monthly"
            elif item.get("source") == "legulegu_hsi":
                entry["pe"] = lg.fetch_hsi_pe(code)
                entry["frequency"] = "monthly"
        except Exception as e:  # 单个指数失败不影响整体
            log.exception("%s 抓取异常: %s", code, e)
        if not entry["pe"] and not entry["pb"]:
            failed.append(code)
            log.error("%s 抓取完全失败", code)
        raw[code] = entry
    return raw, failed


def compute_records(cfg: dict, raw: dict, tx: dict) -> list:
    """分位计算 + 组装报告记录"""
    pcfg = cfg.get("percentile", {})
    window = pcfg.get("window_years", 10)
    bands = pcfg.get("bands", [20, 70, 90])
    min_samples = pcfg.get("min_samples", 30)
    records = []
    for code, entry in raw.items():
        meta = entry["meta"]
        pe_key = _pe_key_of(entry["pe"])
        pe_eval = pct_mod.evaluate(entry["pe"], pe_key, window, bands)
        pb_eval = pct_mod.evaluate(entry["pb"], PB_KEY, window, bands)
        if pe_eval["sample_count"] < min_samples:
            log.warning("%s PE 窗口样本仅 %d 个，标注数据不足",
                        code, pe_eval["sample_count"])
            pe_eval["band"] = "unknown"
        tx_sym = fetchers.tencent_symbol(code, meta["market"])
        quote = tx.get(tx_sym, {})
        rec = {
            "code": code, "name": meta["name"], "market": meta["market"],
            "category": meta.get("category", "宽基"),
            "frequency": entry.get("frequency", "daily"),
            "pe_fallback": entry.get("pe_fallback"),
            "pe_value": pe_eval["value"], "pe_date": pe_eval["value_date"],
            "pe_percentile": pe_eval["percentile"], "pe_band": pe_eval["band"],
            "pe_band_cn": BAND_LABELS[pe_eval["band"]],
            "pe_samples": pe_eval["sample_count"],
            "pb_value": pb_eval["value"], "pb_date": pb_eval["value_date"],
            "pb_percentile": pb_eval["percentile"], "pb_band": pb_eval["band"],
            "pb_band_cn": BAND_LABELS[pb_eval["band"]],
            "pb_samples": pb_eval["sample_count"],
            "price": quote.get("price"),
            "change_pct": quote.get("change_pct"),
        }
        records.append(rec)
    return records


def build_trend_series(cfg: dict, raw: dict, records: list) -> list:
    """为重点指数构建走势图数据"""
    pcfg = cfg.get("percentile", {})
    window = pcfg.get("window_years", 10)
    series = []
    by_code = {r["code"]: r for r in records}
    for code in cfg.get("chart_focus", []):
        entry = raw.get(code)
        rec = by_code.get(code)
        if not entry or not entry["pe"] or not rec or rec["pe_percentile"] is None:
            continue
        key = _pe_key_of(entry["pe"])
        points = [(str(r.get("date")), float(r[key]))
                  for r in entry["pe"]
                  if isinstance(r.get(key), (int, float)) and r[key] > 0]
        window_pts = [p for p in points
                      if p[0] >= (date.today().replace(year=date.today().year - window)
                                  .isoformat())]
        series.append({"name": rec["name"], "points": window_pts or points[-260:],
                       "current": rec["pe_value"],
                       "percentile": rec["pe_percentile"]})
    return series


def load_previous() -> dict:
    """读取上一期快照用于环比"""
    snaps = sorted(SNAPSHOT_DIR.glob("*.json"))
    today = date.today().isoformat()
    for p in reversed(snaps):
        if p.stem < today:
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                return {r["code"]: r for r in data.get("records", [])}
            except (OSError, ValueError, KeyError):
                continue
    return {}


def run() -> int:
    cfg = load_config()
    charts_mod.setup_font()
    today = date.today()
    report_date = today.isoformat()

    log.info("开始抓取数据")
    raw, failed = fetch_all(cfg)

    tx_map = {}
    for item in all_indexes(cfg):
        sym = fetchers.tencent_symbol(item["code"], item["market"])
        tx_map[sym] = item["code"]
    tx = fetchers.fetch_tencent(tx_map)
    log.info("腾讯行情获取 %d 条", len(tx))

    # 跨境指数腾讯未覆盖的（如标普500），用东方财富兜底拿价格涨跌
    em_map = {}
    for item in all_indexes(cfg):
        if item["market"] != "cross":
            continue
        sym = fetchers.tencent_symbol(item["code"], item["market"])
        if sym in tx:
            continue
        esym = fetchers.eastmoney_symbol(item["code"])
        if esym:
            em_map[esym] = item["code"]
    if em_map:
        em = fetchers.fetch_eastmoney(em_map)
        for esym, code in em_map.items():
            if esym in em:
                tx[fetchers.tencent_symbol(code, "cross")] = em[esym]
        log.info("东财兜底行情 %d 条", len(em))

    records = compute_records(cfg, raw, tx)
    log.info("分位计算完成：%d 个指数，失败 %d 个", len(records), len(failed))

    series = build_trend_series(cfg, raw, records)
    chart_dir = REPORT_DIR / "_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    overview_png = chart_dir / "overview.png"
    trends_png = chart_dir / "trends.png"
    charts_mod.chart_overview(records, str(overview_png), cfg["percentile"]["bands"])
    charts_mod.chart_trends(series, str(trends_png))

    prev = load_previous()
    date_dir = REPORT_DIR / report_date
    render(records, {"overview": str(overview_png), "trends": str(trends_png)},
           date_dir, report_date, prev)
    shutil.copyfile(date_dir / "index.html", REPORT_DIR / "index.html")
    for name in ("overview.png", "trends.png"):
        src_png = date_dir / name
        if src_png.exists():
            shutil.copyfile(src_png, REPORT_DIR / name)
    items = sorted(((p.parent.name, f"指数估值周报 {p.parent.name}")
                    for p in REPORT_DIR.glob("*/index.html")), reverse=True)
    render_archive(REPORT_DIR, items)
    log.info("报告已生成: %s", date_dir)

    snapshot = {"date": report_date, "records": records, "failed": failed}
    (SNAPSHOT_DIR / f"{report_date}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")

    title = f"指数估值周报 {report_date}"
    content = build_summary(records, None, report_date)
    if failed:
        content += f"\n\n> 注意：{len(failed)} 个指数数据抓取失败：{'、'.join(failed)}"
    push_summary(title, content)
    return 0


if __name__ == "__main__":
    sys.exit(run())
