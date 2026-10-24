# -*- coding: utf-8 -*-
"""ValPulse 主流程：抓取 -> 分位 -> SQLite -> 导出 -> 看板 -> 邮件推送"""
import logging
import os
import sys
from datetime import date
from pathlib import Path

from . import db, fetchers, percentile as pct_mod
from .config import (BAND_LABELS, REPORT_DIR, all_indexes, holdings_of,
                     load_config)
from .push import build_summary, push_summary
from .report import render_dashboard
from .signal import market_temperature, portfolio_temperature

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
    """抓取全部标的原始数据，返回 (raw, failed)"""
    fcfg = cfg.get("fetch", {})
    lg = fetchers.LeguleguClient(
        interval=fcfg.get("interval_seconds", 8),
        csrf_ttl=fcfg.get("csrf_refresh_seconds", 100),
        max_retries=fcfg.get("max_retries", 3),
        backoff=tuple(fcfg.get("backoff_seconds", [20, 45, 90])),
    )
    window = cfg.get("percentile", {}).get("window_years", 10)
    raw, failed = {}, []
    for item in all_indexes(cfg):
        code, market = item["code"], item["market"]
        source = item.get("source")
        entry = {"meta": item, "pe": None, "pb": None}
        try:
            if market == "gold":
                # 黄金无 PE/PB，只抓价格序列
                entry["price_series"] = fetchers.fetch_gold_history()
            elif source == "csi":
                # 乐咕未收录的指数（A500/证券公司）：中证官网 PE 为主源
                entry["pe"] = fetchers.fetch_csi_pe(code, window)
                if entry["pe"]:
                    entry["pe_fallback"] = "csi"
                    log.info("%s 走中证官网 PE 主源（%d 行）", code, len(entry["pe"]))
            elif market == "cn":
                entry["pe"] = lg.fetch_pe(code)
                entry["pb"] = lg.fetch_pb(code)
                if not entry["pe"]:
                    csi = fetchers.fetch_csi_pe(code, window)
                    if csi:
                        entry["pe"] = csi
                        entry["pe_fallback"] = "csi"
                        log.info("%s 乐咕 PE 失败，已用中证官网兜底（%d 行）",
                                 code, len(csi))
            elif source == "multpl":
                entry["pe"] = fetchers.fetch_multpl_spx()
                entry["frequency"] = "monthly"
            elif source == "legulegu_hsi":
                entry["pe"] = lg.fetch_hsi_pe(code)
                entry["frequency"] = "monthly"
        except Exception as e:  # 单个标的失败不影响整体
            log.exception("%s 抓取异常: %s", code, e)
        if not entry["pe"] and not entry["pb"] and not entry.get("price_series"):
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
        rec = {
            "code": code, "name": meta["name"], "market": meta["market"],
            "category": meta.get("category", "宽基"),
            "frequency": entry.get("frequency", "daily"),
            "pe_fallback": entry.get("pe_fallback"),
        }
        if meta["market"] == "gold":
            # 黄金：只有价格分位，无 PE/PB 概念
            ev = pct_mod.evaluate(entry.get("price_series") or [], "price",
                                  window, bands)
            rec.update({
                "price": ev["value"], "price_percentile": ev["percentile"],
                "price_band": ev["band"], "price_samples": ev["sample_count"],
                "pe_value": None, "pe_percentile": None, "pe_band": "unknown",
                "pe_samples": 0,
                "pb_value": None, "pb_percentile": None, "pb_band": "unknown",
                "pb_samples": 0,
            })
            # 日涨跌取序列尾部两日收盘价
            ps = entry.get("price_series") or []
            if len(ps) >= 2 and ps[-2]["price"]:
                rec["change_pct"] = round(
                    (ps[-1]["price"] - ps[-2]["price"]) / ps[-2]["price"] * 100, 2)
            else:
                rec["change_pct"] = None
            records.append(rec)
            continue
        pe_key = _pe_key_of(entry["pe"])
        pe_eval = pct_mod.evaluate(entry["pe"], pe_key, window, bands)
        pb_eval = pct_mod.evaluate(entry["pb"], PB_KEY, window, bands)
        if pe_eval["sample_count"] < min_samples:
            log.warning("%s PE 窗口样本仅 %d 个，标注数据不足",
                        code, pe_eval["sample_count"])
            pe_eval["band"] = "unknown"
        tx_sym = fetchers.tencent_symbol(code, meta["market"])
        quote = tx.get(tx_sym, {})
        rec.update({
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
        })
        records.append(rec)
    return records


def save_series_to_db(conn, raw: dict):
    """把本期抓到的全历史序列写入 SQLite（前端图的数据源）"""
    for code, entry in raw.items():
        if entry.get("pe"):
            key = _pe_key_of(entry["pe"])
            db.save_series(conn, code, "pe",
                           [{"date": r["date"], "value": r[key]} for r in entry["pe"]
                            if isinstance(r.get(key), (int, float)) and r[key] > 0])
        if entry.get("pb"):
            db.save_series(conn, code, "pb",
                           [{"date": r["date"], "value": r[PB_KEY]} for r in entry["pb"]
                            if isinstance(r.get(PB_KEY), (int, float)) and r[PB_KEY] > 0])
        if entry.get("price_series"):
            # 注意字段名转换：fetchers 返回 price，db 层统一用 value
            db.save_series(conn, code, "price",
                           [{"date": r["date"], "value": r["price"]}
                            for r in entry["price_series"]
                            if r.get("price") is not None])


def _run() -> int:
    cfg = load_config()
    window = cfg.get("percentile", {}).get("window_years", 10)
    conn = db.connect()
    db.init_db(conn)
    imported = db.import_legacy_snapshots(conn)

    today = date.today()
    report_date = today.isoformat()

    log.info("开始抓取数据（历史快照导入 %d 期）", imported)
    raw, failed = fetch_all(cfg)

    tx_map = {}
    for item in all_indexes(cfg):
        if item["market"] == "gold":
            continue  # 黄金涨跌由价格序列计算
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
    log.info("分位计算完成：%d 个标的，失败 %d 个", len(records), len(failed))

    save_series_to_db(conn, raw)
    db.save_snapshot(conn, report_date, records)
    db.export_web_data(conn, REPORT_DIR)

    by_code = {r["code"]: r for r in records}
    holdings = holdings_of(cfg, by_code)
    port_temp = portfolio_temperature(holdings)
    mkt_temp = market_temperature(records, cfg.get("broad_indexes", []))
    render_dashboard(REPORT_DIR, report_date, holdings,
                     cfg.get("broad_indexes", []), window)
    log.info("看板已生成: %s", REPORT_DIR / "index.html")

    title = f"ValPulse 估值周报 {report_date}"
    content = build_summary(records, holdings, port_temp, mkt_temp,
                            os.environ.get("REPORT_URL") or None)
    if failed:
        content += (f'<p style="color:#c62828">注意：{len(failed)} 个标的'
                    f"抓取失败：{'、'.join(failed)}</p>")
    push_summary(title, content)
    return 0


def run() -> int:
    """入口：整体失败时发告警邮件（Actions 环境附运行日志链接）"""
    try:
        return _run()
    except Exception:
        log.exception("流水线整体失败")
        try:
            run_url = os.environ.get("RUN_URL")
            detail = f'<p><a href="{run_url}">查看运行日志</a></p>' if run_url else ""
            push_summary(f"ValPulse 运行失败 {date.today().isoformat()}",
                         f"<p>本周流水线执行失败，请检查 GitHub Actions 日志。</p>{detail}")
        except Exception:
            log.exception("告警邮件发送失败")
        return 1


if __name__ == "__main__":
    sys.exit(run())
