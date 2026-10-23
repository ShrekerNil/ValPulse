# -*- coding: utf-8 -*-
"""分位计算：近10年窗口、负值剔除、四级分级"""
import logging
from datetime import date, datetime, timedelta

log = logging.getLogger("valpulse.percentile")


def _to_date(s: str) -> date:
    if isinstance(s, date):
        return s
    s = str(s)
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {s}")


def in_window(rows: list, window_years: int, value_key: str) -> list:
    """取近 window_years 年窗口内该指标的有效值（剔除 None 与非正数）"""
    if not rows:
        return []
    cutoff = date.today() - timedelta(days=window_years * 365)
    out = []
    for r in rows:
        try:
            d = _to_date(r.get("date", ""))
            v = r.get(value_key)
        except (ValueError, TypeError):
            continue
        if d < cutoff or v is None:
            continue
        if isinstance(v, (int, float)) and v > 0:
            out.append((d, float(v)))
    return out


def percentile(value: float, samples: list) -> float | None:
    """历史分位：样本中小于等于当前值的比例（0-100）"""
    if value is None or not samples:
        return None
    below = sum(1 for v in samples if v <= value)
    return below / len(samples) * 100.0


def band_of(pct: float | None, bands: list) -> str:
    """分位分级：低估 / 合理 / 偏高 / 高估"""
    if pct is None:
        return "unknown"
    if pct < bands[0]:
        return "undervalued"
    if pct < bands[1]:
        return "fair"
    if pct < bands[2]:
        return "high"
    return "over"


def latest_value(rows: list, value_key: str):
    """取最近一日的有效值"""
    best = None
    for r in rows or []:
        v = r.get(value_key)
        if v is None or not isinstance(v, (int, float)) or v <= 0:
            continue
        if best is None or str(r.get("date")) > str(best[0]):
            best = (r.get("date"), float(v))
    return best


def evaluate(rows: list, value_key: str, window_years: int, bands: list) -> dict:
    """对单个指标序列计算：当前值、近N年分位、分级、样本数"""
    cur = latest_value(rows, value_key)
    window = in_window(rows, window_years, value_key)
    samples = [v for _, v in window]
    pct = percentile(cur[1], samples) if cur else None
    return {
        "value": cur[1] if cur else None,
        "value_date": cur[0] if cur else None,
        "percentile": round(pct, 1) if pct is not None else None,
        "band": band_of(pct, bands),
        "sample_count": len(samples),
    }
