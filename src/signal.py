# -*- coding: utf-8 -*-
"""定投信号与温度合成：把分位结果翻译成小白可执行的动作。

口径参考蛋卷/且慢/有知有行的主流做法：
- 分位 <20% 低估：可加大定投；20-70% 合理：正常定投；
  70-90% 偏高：减少定投；>90% 高估：分批止盈。
- 市场温度 = 宽基指数 PE 分位等权均值（0-100），五档温带。
- 黄金无 PE/PB，只参与价格分位展示，不参与温度合成。
"""
import logging

log = logging.getLogger("valpulse.signal")

# 温度五档（华泰"温度计"/有知有行同款口径）
TEMP_BANDS = [
    (15, "极度低估", "积极定投区间"),
    (35, "相对低估", "可加大定投"),
    (55, "正常", "正常定投"),
    (75, "相对高估", "减少定投"),
    (101, "极度高估", "分批止盈区间"),
]

_SIGNALS = {
    "undervalued": ("可加大定投", "历史低位，参考加大至 1.5-2 倍", "positive"),
    "fair": ("正常定投", "历史中位，按计划定投", "neutral"),
    "high": ("减少定投", "历史偏高，可减半或暂停", "caution"),
    "over": ("分批止盈", "历史高位，可分批止盈", "warning"),
    "unknown": ("数据不足", "暂无可执行信号", "muted"),
}


def invest_signal(band: str, is_gold: bool = False) -> dict:
    """分位分级 -> 定投信号。黄金没有估值概念，单独走价格参考口径。"""
    if is_gold:
        return {"label": "仅价格参考", "detail": "黄金无 PE/PB 估值，按价格分位自行判断",
                "tone": "muted"}
    label, detail, tone = _SIGNALS.get(band, _SIGNALS["unknown"])
    return {"label": label, "detail": detail, "tone": tone}


def temperature_band(temp: float) -> tuple:
    """温度值 -> (档位名, 动作建议)"""
    for limit, name, action in TEMP_BANDS:
        if temp < limit:
            return name, action
    return TEMP_BANDS[-1][1], TEMP_BANDS[-1][2]


def _mean(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def market_temperature(records: list, broad_codes: list) -> dict:
    """大盘温度：宽基指数 PE 分位等权均值（黄金等无 PE 标的自动排除）"""
    by_code = {r["code"]: r for r in records}
    pcts, names = [], []
    for code in broad_codes:
        r = by_code.get(code)
        if r and r.get("pe_percentile") is not None:
            pcts.append(r["pe_percentile"])
            names.append(r["name"])
    temp = _mean(pcts)
    if temp is None:
        return {"temperature": None, "band": "数据不足", "action": "", "based_on": []}
    band, action = temperature_band(temp)
    return {"temperature": round(temp, 1), "band": band, "action": action,
            "based_on": names}


def portfolio_temperature(holdings: list) -> dict:
    """持仓组合温度：有估值分位的持仓等权平均（黄金不参与，单独说明）"""
    pcts, gold_notes = [], []
    for h in holdings:
        rec = h["record"]
        if h.get("is_gold"):
            if rec.get("price_percentile") is not None:
                gold_notes.append(
                    f'{rec["name"]}价格分位 {rec["price_percentile"]:.0f}%（仅价格参考）')
            continue
        if rec.get("pe_percentile") is not None:
            pcts.append(rec["pe_percentile"])
    temp = _mean(pcts)
    if temp is None:
        return {"temperature": None, "band": "数据不足", "action": "",
                "note": "；".join(gold_notes)}
    band, action = temperature_band(temp)
    note = "；".join(gold_notes)
    if note:
        note = f'估值温度基于 {len(pcts)} 只有估值分位持仓合成；{note}'
    else:
        note = f"估值温度基于 {len(pcts)} 只持仓等权合成"
    return {"temperature": round(temp, 1), "band": band, "action": action,
            "note": note}
