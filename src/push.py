# -*- coding: utf-8 -*-
"""PushPlus 推送：周报摘要（Markdown 模板）"""
import logging
import os

import requests

log = logging.getLogger("valpulse.push")

SEND_URL = "https://www.pushplus.plus/send"


def build_summary(records: list, report_url: str | None, report_date: str) -> str:
    """生成推送用的 Markdown 摘要"""
    lines = [f"## 指数估值周报（{report_date}）", ""]
    lines.append("| 指数 | PE | PE分位 | 状态 | PB | PB分位 | 状态 | 日涨跌 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in records:
        pe = f"{r['pe_value']:.2f}" if r.get("pe_value") is not None else "-"
        pep = f"{r['pe_percentile']:.0f}%" if r.get("pe_percentile") is not None else "-"
        peb = r.get("pe_band_cn", "-")
        pb = f"{r['pb_value']:.2f}" if r.get("pb_value") is not None else "-"
        pbp = f"{r['pb_percentile']:.0f}%" if r.get("pb_percentile") is not None else "-"
        pbb = r.get("pb_band_cn", "-")
        chg = f"{r['change_pct']:+.2f}%" if isinstance(r.get("change_pct"), (int, float)) else "-"
        lines.append(f"| {r['name']} | {pe} | {pep} | {peb} | {pb} | {pbp} | {pbb} | {chg} |")
    low = [r["name"] for r in records if r.get("pe_band") == "undervalued"]
    high = [r["name"] for r in records if r.get("pe_band") in ("high", "over")]
    lines.append("")
    if low:
        lines.append(f"**低估（PE分位<20%）**：{'、'.join(low)}")
    if high:
        lines.append(f"**偏高/高估（PE分位>70%）**：{'、'.join(high)}")
    if not low and not high:
        lines.append("本周无 PE 分位低于20%或高于70%的指数")
    if report_url:
        lines.append("")
        lines.append(f"[查看完整周报]({report_url})")
    lines.append("")
    lines.append("_PE/PB 为等权口径，分位基于近10年历史；不构成投资建议_")
    return "\n".join(lines)


def push_summary(title: str, content: str, token: str | None = None) -> bool:
    """推送到 PushPlus；无 token 时跳过并告警"""
    token = token or os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        log.warning("未配置 PUSHPLUS_TOKEN，跳过推送")
        return False
    try:
        r = requests.post(SEND_URL, json={
            "token": token,
            "title": title,
            "content": content,
            "template": "markdown",
        }, timeout=20)
        j = r.json()
        if j.get("code") == 200:
            log.info("PushPlus 推送成功")
            return True
        log.warning("PushPlus 推送失败: %s", j)
    except (requests.RequestException, ValueError) as e:
        log.warning("PushPlus 推送异常: %s", e)
    return False
