# -*- coding: utf-8 -*-
"""周报推送：QQ 邮箱 SMTP（HTML 邮件）

环境变量：
  MAIL_USER  发件 QQ 邮箱地址（如 12345@qq.com）
  MAIL_PASS  QQ 邮箱开启 SMTP 后获得的 16 位授权码（非登录密码）
  MAIL_TO    收件邮箱，缺省同发件人
  REPORT_URL 周报网页地址（可选，附在邮件尾部）
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

# 估值分位配色：低估绿 / 合理蓝 / 偏高橙 / 高估红（与网页周报一致）
BAND_COLORS = {
    "undervalued": "#2e7d32",
    "fair": "#1565c0",
    "high": "#ef6c00",
    "over": "#c62828",
    "unknown": "#757575",
}


def _cell_band(band_cn: str, band: str) -> str:
    color = BAND_COLORS.get(band, "#757575")
    return f'<b style="color:{color}">{band_cn}</b>'


def _cell_chg(chg) -> str:
    if not isinstance(chg, (int, float)):
        return "-"
    # A股惯例：涨红跌绿
    color = "#c62828" if chg > 0 else "#2e7d32"
    sign = "+" if chg > 0 else ""
    return f'<span style="color:{color}">{sign}{chg:.2f}%</span>'


def build_summary(records: list, report_url: str | None, report_date: str) -> str:
    """生成推送用的 HTML 摘要（表格 + 低估/高估名单 + 周报链接）"""
    rows = []
    for r in records:
        pe = f"{r['pe_value']:.2f}" if r.get("pe_value") is not None else "-"
        pep = f"{r['pe_percentile']:.0f}%" if r.get("pe_percentile") is not None else "-"
        pb = f"{r['pb_value']:.2f}" if r.get("pb_value") is not None else "-"
        pbp = f"{r['pb_percentile']:.0f}%" if r.get("pb_percentile") is not None else "-"
        rows.append(
            "<tr>"
            f"<td>{r['name']}</td><td>{pe}</td><td>{pep}</td>"
            f"<td>{_cell_band(r.get('pe_band_cn', '-'), r.get('pe_band'))}</td>"
            f"<td>{pb}</td><td>{pbp}</td>"
            f"<td>{_cell_band(r.get('pb_band_cn', '-'), r.get('pb_band'))}</td>"
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
    link = f'<p><a href="{report_url}">查看完整周报（含走势图）</a></p>' if report_url else ""
    return (
        "<html><body style=\"font-family:sans-serif;font-size:14px;color:#333\">"
        f"<h3>指数估值周报（{report_date}）</h3>"
        "<table cellpadding=\"6\" cellspacing=\"0\" border=\"1\" "
        "style=\"border-collapse:collapse;border-color:#ddd;font-size:13px\">"
        "<tr style=\"background:#f5f5f5\">"
        "<th>指数</th><th>PE</th><th>PE分位</th><th>状态</th>"
        "<th>PB</th><th>PB分位</th><th>状态</th><th>日涨跌</th></tr>"
        f"{''.join(rows)}"
        "</table>"
        f"<p>{'<br>'.join(notes)}</p>"
        f"{link}"
        "<p style=\"color:#999;font-size:12px\">PE/PB 为等权口径，分位基于近10年历史；不构成投资建议</p>"
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
