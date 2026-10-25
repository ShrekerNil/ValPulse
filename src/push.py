# -*- coding: utf-8 -*-
"""周报推送：QQ 邮箱 SMTP（HTML 邮件）

环境变量：
  MAIL_USER  发件 QQ 邮箱地址（如 12345@qq.com）
  MAIL_PASS  QQ 邮箱开启 SMTP 后获得的 16 位授权码（非登录密码）
  MAIL_TO    收件邮箱，缺省同发件人
  REPORT_URL 看板网页地址（可选，附在邮件尾部）
"""
import logging
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

log = logging.getLogger("valpulse.push")

SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465  # SSL

# 估值分位配色：低估绿 / 合理蓝 / 偏高橙 / 高估红（与看板一致）
BAND_COLORS = {
    "undervalued": "#2e7d32",
    "fair": "#1565c0",
    "high": "#ef6c00",
    "over": "#c62828",
    "unknown": "#757575",
}

# 定投信号（与 signal.py 口径一致）
SIGNAL_LABELS = {
    "undervalued": ("可加大定投", "#2e7d32"),
    "fair": ("正常定投", "#1565c0"),
    "high": ("减少定投", "#ef6c00"),
    "over": ("分批止盈", "#c62828"),
    "unknown": ("数据不足", "#757575"),
}


def _cell_chg(chg) -> str:
    if not isinstance(chg, (int, float)):
        return "-"
    # A股惯例：涨红跌绿
    color = "#c62828" if chg > 0 else "#2e7d32"
    sign = "+" if chg > 0 else ""
    return f'<span style="color:{color}">{sign}{chg:.2f}%</span>'


def _fmt(v, d=2):
    return f"{v:.{d}f}" if isinstance(v, (int, float)) else "-"


def _pct(v):
    return f"{v:.0f}%" if isinstance(v, (int, float)) else "-"


def build_summary(records: list, holdings: list, port_temp: dict,
                  mkt_temp: dict, report_url: str | None) -> str:
    """生成推送用的 HTML 摘要：持仓模块 + 大盘温度 + 全部指数简表"""
    # 我的持仓
    h_rows = []
    for h in holdings:
        r = h["record"]
        if h.get("is_gold"):
            val = f"金价 {_fmt(r.get('price'))} 元/克 · 价格分位 {_pct(r.get('price_percentile'))}"
            sig, color = "仅价格参考", "#757575"
        else:
            val = f"PE分位 {_pct(r.get('pe_percentile'))}"
            sig, color = SIGNAL_LABELS.get(r.get("pe_band"), SIGNAL_LABELS["unknown"])
        h_rows.append(
            "<tr>"
            f"<td>{h['fund']}<br><span style='color:#999;font-size:12px'>"
            f"跟踪：{r['name']}</span></td>"
            f"<td>{val}</td>"
            f"<td><b style='color:{color}'>{sig}</b></td>"
            f"<td>{_cell_chg(r.get('change_pct'))}</td>"
            "</tr>"
        )
    port_html = (
        f'<p style="font-size:15px">组合估值温度 <b style="font-size:22px;color:#1565c0">'
        f'{port_temp["temperature"]:.0f}℃</b> · {port_temp["band"]} · '
        f'{port_temp["action"]}<br>'
        f'<span style="color:#999;font-size:12px">{port_temp.get("note", "")}</span></p>'
        if port_temp.get("temperature") is not None else
        '<p style="color:#999">持仓数据不足</p>')
    mkt_html = (
        f'<p style="font-size:15px">大盘温度 <b style="font-size:22px;color:#1565c0">'
        f'{mkt_temp["temperature"]:.0f}℃</b> · {mkt_temp["band"]} · '
        f'{mkt_temp["action"]}<br>'
        f'<span style="color:#999;font-size:12px">'
        f'基于 {"、".join(mkt_temp.get("based_on", []))} PE 分位等权合成</span></p>'
        if mkt_temp.get("temperature") is not None else
        '<p style="color:#999">宽基数据不足</p>')

    # 全部指数简表
    rows = []
    for r in records:
        if r.get("market") == "gold":
            rows.append(
                "<tr>"
                f"<td>{r['name']}</td>"
                f'<td colspan="2">金价 {_fmt(r.get("price"))} 元/克 · '
                f'价格分位 {_pct(r.get("price_percentile"))}</td>'
                f'<td colspan="2" style="color:#757575">黄金无 PE/PB 估值概念</td>'
                f"<td>{_cell_chg(r.get('change_pct'))}</td>"
                "</tr>"
            )
            continue
        pe_color = BAND_COLORS.get(r.get("pe_band"), "#757575")
        pb_none = r.get("pb_value") is None
        pb_color = "#757575" if pb_none else BAND_COLORS.get(r.get("pb_band"), "#757575")
        rows.append(
            "<tr>"
            f"<td>{r['name']}</td>"
            f"<td><span style='color:{pe_color};font-weight:600'>{_fmt(r.get('pe_value'))}</span></td>"
            f"<td>{_pct(r.get('pe_percentile'))}</td>"
            f"<td><span style='color:{pb_color};font-weight:600'>{'-' if pb_none else _fmt(r.get('pb_value'))}</span></td>"
            f"<td>{_pct(r.get('pb_percentile'))}</td>"
            f"<td>{_cell_chg(r.get('change_pct'))}</td>"
            "</tr>"
        )
    low = [r["name"] for r in records if r.get("pe_band") == "undervalued"]
    high = [r["name"] for r in records if r.get("pe_band") in ("high", "over")]
    notes = []
    if low:
        notes.append(f"<b style='color:#2e7d32'>低估（PE分位&lt;20%）</b>：{'、'.join(low)}")
    if high:
        notes.append(f"<b style='color:#c62828'>偏高/高估（PE分位&gt;70%）</b>：{'、'.join(high)}")
    if not notes:
        notes.append("本周无 PE 分位低于 20% 或高于 70% 的指数")
    link = (f'<p><a href="{report_url}">查看完整看板'
            f'（走势图 / 历史日期回看）</a></p>') if report_url else ""
    table_head = (
        '<tr style="background:#f5f5f5">'
        '<th>指数</th><th>PE</th><th>PE分位</th>'
        '<th>PB</th><th>PB分位</th><th>日涨跌</th></tr>')
    return (
        '<html><body style="font-family:sans-serif;font-size:14px;color:#333">'
        "<h3>我的持仓</h3>"
        + port_html
        + '<table cellpadding="6" cellspacing="0" border="1" '
          'style="border-collapse:collapse;border-color:#ddd;font-size:13px">'
          '<tr style="background:#f5f5f5"><th>基金</th><th>估值状态</th>'
          "<th>定投信号</th><th>日涨跌</th></tr>"
        + "".join(h_rows)
        + "</table>"
        "<h3>大盘</h3>"
        + mkt_html
        + "<h3>全部指数</h3>"
          '<table cellpadding="6" cellspacing="0" border="1" '
          'style="border-collapse:collapse;border-color:#ddd;font-size:13px">'
        + table_head + "".join(rows) + "</table>"
        + f"<p>{'<br>'.join(notes)}</p>"
        + link
        + '<p style="color:#999;font-size:12px">分位基于近10年历史；'
          "「无PB数据」为数据源不提供该指标，非系统缺数；"
          "定投信号为规则化提示，不构成投资建议</p>"
        "</body></html>"
    )


def push_summary(title: str, content: str) -> bool:
    """通过 QQ 邮箱 SMTP 发送 HTML 邮件；未配置账号时跳过并告警"""
    user = os.environ.get("MAIL_USER")
    passwd = os.environ.get("MAIL_PASS")
    to = os.environ.get("MAIL_TO") or user
    if not (user and passwd):
        log.warning("未配置 MAIL_USER/MAIL_PASS，跳过邮件推送")
        return False
    msg = MIMEText(content, "html", "utf-8")
    msg["Subject"] = Header(title, "utf-8")
    msg["From"] = formataddr(("ValPulse", user))
    msg["To"] = to
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
            smtp.login(user, passwd)
            smtp.sendmail(user, [to], msg.as_string())
        log.info("邮件推送成功 -> %s", to)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning("邮件推送失败: %s", e)
    return False
