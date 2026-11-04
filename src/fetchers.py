# -*- coding: utf-8 -*-
"""数据抓取模块：乐咕（A股 PE/PB）、中证官方（PE 兜底/A500与券商主源）、腾讯（行情）、multpl（标普500 PE/PB）、
乐咕恒生专题页、蛋卷（指数 PB 历史）、中证 factsheet（最新 PB）、东财（黄金K线/行情兜底）"""
import io
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("valpulse.fetch")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
BASE_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
CSRF_PAGE = "https://legulegu.com/stockdata/sz50-ttm-lyr"


class LeguleguClient:
    """乐咕乐股客户端：管理 CSRF 令牌、请求限速与失败重试。

    该站点对频率敏感（约 10 次请求后进入短时限流），
    因此请求间隔、CSRF 刷新与退避重试均由本类统一控制。
    """

    def __init__(self, interval: int = 8, csrf_ttl: int = 100,
                 max_retries: int = 3, backoff=(20, 45, 90)):
        self.session = requests.Session()
        self.session.headers.update(BASE_HEADERS)
        self.interval = interval
        self.csrf_ttl = csrf_ttl
        self.max_retries = max_retries
        self.backoff = backoff
        self._csrf = None
        self._csrf_at = 0.0
        self._last_request_at = 0.0

    def _ensure_csrf(self, force: bool = False) -> bool:
        now = time.monotonic()
        if self._csrf and not force and now - self._csrf_at < self.csrf_ttl:
            return True
        try:
            r = self.session.get(CSRF_PAGE, timeout=25)
            r.raise_for_status()
            tag = BeautifulSoup(r.text, "lxml").find("meta", attrs={"name": "_csrf"})
            if tag is None:
                log.warning("乐咕 CSRF 页面未返回令牌（status=%s）", r.status_code)
                return False
            self._csrf = tag.attrs["content"]
            self._csrf_at = now
            return True
        except requests.RequestException as e:
            log.warning("乐咕 CSRF 获取失败: %s", e)
            return False

    def _throttle(self):
        wait = self.interval - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def get_index_data(self, api_path: str, index_code: str):
        """请求 index-basic-pe / index-basic-pb 等接口，返回 data 列表或 None"""
        for attempt in range(self.max_retries):
            if not self._ensure_csrf(force=attempt > 0):
                time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
                continue
            self._throttle()
            self._last_request_at = time.monotonic()
            try:
                r = self.session.get(
                    f"https://legulegu.com/api/stockdata/{api_path}",
                    params={"token": self._token(), "indexCode": index_code},
                    timeout=25,
                )
                if r.status_code != 200:
                    log.warning("乐咕 %s %s HTTP %s（第%d次）", api_path, index_code,
                                r.status_code, attempt + 1)
                else:
                    j = r.json()
                    data = j.get("data")
                    if data:
                        return data
                    log.warning("乐咕 %s %s 返回空数据", api_path, index_code)
            except (requests.RequestException, ValueError) as e:
                log.warning("乐咕 %s %s 异常: %s（第%d次）", api_path, index_code, e,
                            attempt + 1)
            time.sleep(self.backoff[min(attempt, len(self.backoff) - 1)])
        return None

    @staticmethod
    def _token() -> str:
        from hashlib import md5
        return md5(date.today().isoformat().encode()).hexdigest()

    def fetch_pe(self, index_code: str):
        return self.get_index_data("index-basic-pe", index_code)

    def fetch_pb(self, index_code: str):
        return self.get_index_data("index-basic-pb", index_code)

    def fetch_hsi_pe(self, index_code: str):
        """恒生主题指数月度 PE/股息率（数据源为恒生指数公司）"""
        return self.get_index_data("hsidata", index_code)


def fetch_csi_pe(index_code: str, window_years: int = 10) -> list:
    """中证指数官网每日市盈率（整体法），作为 A 股 PE 的兜底与交叉校验"""
    code = index_code.split(".")[0]
    start = date.today().replace(year=date.today().year - window_years)
    end = date.today()
    try:
        r = requests.get(
            "https://www.csindex.com.cn/csindex-home/perf/index-perf",
            params={"indexCode": code, "startDate": start.strftime("%Y%m%d"),
                    "endDate": end.strftime("%Y%m%d")},
            headers=BASE_HEADERS, timeout=30)
        j = r.json()
        rows = j.get("data") or []
        return [{"date": x["tradeDate"], "close": x.get("close"),
                 "pe": x.get("peg")} for x in rows if x.get("peg")]
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("中证 PE 接口失败 %s: %s", index_code, e)
        return []


def fetch_tencent(symbols: dict) -> dict:
    """腾讯实时行情：symbols 为 {腾讯代码: 显示名}，返回价格与涨跌幅"""
    if not symbols:
        return {}
    out = {}
    codes = list(symbols)
    for i in range(0, len(codes), 10):
        batch = codes[i:i + 10]
        try:
            r = requests.get("https://qt.gtimg.cn/q=" + ",".join(batch),
                             headers=BASE_HEADERS, timeout=20)
            r.encoding = "gbk"
            for line in r.text.split(";"):
                m = re.match(r'v_([a-zA-Z0-9]+)="(.*)"', line.strip())
                if not m:
                    continue
                code, payload = m.group(1), m.group(2).split("~")
                if len(payload) > 39 and payload[3]:
                    out[code] = {
                        "price": _num(payload[3]),
                        "change_pct": _num(payload[32]) if len(payload) > 32 else None,
                        "pe": _num(payload[39]) if len(payload) > 39 else None,
                    }
        except requests.RequestException as e:
            log.warning("腾讯行情批量失败: %s", e)
    return out


def fetch_eastmoney(secids: dict) -> dict:
    """东方财富行情兜底：主要覆盖腾讯没有的跨境指数（如标普500）"""
    out = {}
    for secid in secids:
        try:
            r = requests.get(
                "https://push2.eastmoney.com/api/qt/stock/get",
                params={"secid": secid, "fields": "f43,f57,f58,f170"},
                headers=BASE_HEADERS, timeout=20)
            d = r.json().get("data") or {}
            if d.get("f43"):
                out[secid] = {
                    "price": _num(d["f43"]) / 100.0,
                    "change_pct": _num(d.get("f170")) / 100.0
                    if d.get("f170") is not None else None,
                }
        except (requests.RequestException, ValueError) as e:
            log.warning("东财行情失败 %s: %s", secid, e)
    return out


def eastmoney_symbol(index_code: str, market: str = "cross") -> str:
    """指数代码转东财 secid：SPX -> 100.SPX，HSTECH -> 124.HSTECH；
    中证 H 系列（如 H30184.CSI）腾讯不收录，走东财 2.H30184"""
    if market == "cn" and index_code.startswith("H") and index_code.endswith(".CSI"):
        return "2." + index_code.split(".")[0]
    table = {"SPX": "100.SPX", "HSTECH": "124.HSTECH", "NDX": "100.NDX",
             "HSI": "124.HSI"}
    return table.get(index_code, "")


def fetch_gold_history(start: str = "20160101") -> list:
    """上海金 Au99.99 日线历史：东方财富 118.AU9999 为主，新浪财经为备。

    黄金没有 PE/PB（无盈利与净资产概念），仅返回收盘价序列。
    """
    rows = _fetch_gold_eastmoney(start)
    if not rows:
        log.info("东财黄金K线无数据，切换新浪源")
        rows = _fetch_gold_sina()
    return rows


def _fetch_gold_eastmoney(start: str) -> list:
    """东财 K 线（主源），被限流时换延迟镜像域名"""
    for host in ("push2his.eastmoney.com", "push2delay.eastmoney.com"):
        try:
            r = requests.get(
                f"https://{host}/api/qt/stock/kline/get",
                params={"secid": "118.AU9999", "klt": "101", "fqt": "1",
                        "beg": start, "end": "20500101",
                        "fields1": "f1,f2,f3,f4,f5,f6",
                        "fields2": "f51,f52,f53,f54,f55,f56,f57"},
                headers=BASE_HEADERS, timeout=30)
            klines = (r.json().get("data") or {}).get("klines") or []
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 3:
                    rows.append({"date": parts[0], "price": _num(parts[2])})
            rows.sort(key=lambda x: x["date"])
            if rows:
                log.info("黄金 Au99.99 历史 %d 行（东财 %s）", len(rows), host)
                return rows
        except (requests.RequestException, ValueError) as e:
            log.warning("东财黄金K线失败 %s: %s", host, e)
    return []


def _fetch_gold_sina(start: str = "20160101") -> list:
    """新浪财经 Au99.99 历史交易（兜底源）。

    页面支持 start/end 区间查询但单次上限约 40 行，
    因此按 40 天分段从 start 翻到今天拼全历史。
    """
    try:
        rows, seen = [], set()
        cur = datetime.strptime(start, "%Y%m%d").date()
        end = date.today()
        while cur <= end:
            seg_end = min(cur + timedelta(days=40), end)
            r = requests.get(
                "https://vip.stock.finance.sina.com.cn/q/view/vGold_History.php",
                params={"breed": "AU9999",
                        "start": cur.isoformat(), "end": seg_end.isoformat()},
                headers=BASE_HEADERS, timeout=20)
            soup = BeautifulSoup(r.text, "lxml")
            for tr in soup.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 5:
                    continue
                dt = tds[0].get_text(strip=True)
                close = _num(tds[4].get_text(strip=True))
                if close and dt[:4].isdigit() and dt not in seen:
                    seen.add(dt)
                    rows.append({"date": dt, "price": close})
            cur = seg_end + timedelta(days=1)
        rows.sort(key=lambda x: x["date"])
        if rows:
            log.info("黄金 Au99.99 历史 %d 行（新浪分段）", len(rows))
        return rows
    except (requests.RequestException, ValueError) as e:
        log.warning("新浪黄金历史失败: %s", e)
        return []


def fetch_multpl_spx() -> list:
    """multpl.com 标普500 月度 PE 历史（约1871年至今的表格页）"""
    try:
        r = requests.get("https://www.multpl.com/s-p-500-pe-ratio/table/by-month",
                         headers=BASE_HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            dt = _parse_month(tds[0].get_text(strip=True))
            val = _num(tds[1].get_text(strip=True))
            if dt and val:
                rows.append({"date": dt, "pe": val})
        rows.sort(key=lambda x: x["date"])
        return rows
    except requests.RequestException as e:
        log.warning("multpl 抓取失败: %s", e)
        return []


def fetch_multpl_pb() -> list:
    """multpl.com 标普500 季度市净率历史（1999-12 至今；† 标记为估算值）"""
    try:
        r = requests.get(
            "https://www.multpl.com/s-p-500-price-to-book/table/by-quarter",
            headers=BASE_HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            dt = _parse_month(tds[0].get_text(strip=True))
            val = _num(tds[1].get_text(strip=True))
            if dt and val:
                rows.append({"date": dt, "pb": val})
        rows.sort(key=lambda x: x["date"])
        if rows:
            log.info("multpl 标普500 PB 历史 %d 行（季频）", len(rows))
        return rows
    except requests.RequestException as e:
        log.warning("multpl PB 抓取失败: %s", e)
        return []


def danjuan_symbol(index_code: str) -> str:
    """指数代码转蛋卷代码：000300.SH -> SH000300，399975.SZ -> SZ399975，HSTECH -> HKHSTECH"""
    if index_code == "HSTECH":
        return "HKHSTECH"
    if "." not in index_code:
        return ""
    code, suffix = index_code.split(".", 1)
    if suffix in ("SH", "SZ"):
        return suffix + code
    return ""


def fetch_danjuan_pb(index_code: str, day: str = "all") -> list:
    """蛋卷基金（雪球）指数 PB 历史：周频、无需鉴权，day 仅支持 3y/5y/all"""
    code = danjuan_symbol(index_code)
    if not code:
        return []
    try:
        r = requests.get(
            f"https://danjuanfunds.com/djapi/index_eva/pb_history/{code}",
            params={"day": day}, headers=BASE_HEADERS, timeout=25)
        data = r.json().get("data") or {}
        rows = []
        for item in data.get("index_eva_pb_growths") or []:
            pb, ts = item.get("pb"), item.get("ts")
            if pb is None or not ts:
                continue
            d = datetime.fromtimestamp(ts / 1000,
                                       tz=timezone(timedelta(hours=8))).date()
            rows.append({"date": d.isoformat(), "pb": float(pb)})
        rows.sort(key=lambda x: x["date"])
        if rows:
            log.info("蛋卷 %s PB 历史 %d 行（周频）", code, len(rows))
        return rows
    except (requests.RequestException, ValueError) as e:
        log.warning("蛋卷 PB 抓取失败 %s: %s", code, e)
        return []


def fetch_multpl_spx_dy() -> list:
    """multpl.com 标普500 月度股息率历史（%），数据可回溯至 1871 年"""
    try:
        r = requests.get(
            "https://www.multpl.com/s-p-500-dividend-yield/table/by-month",
            headers=BASE_HEADERS, timeout=30)
        soup = BeautifulSoup(r.text, "lxml")
        rows = []
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) != 2:
                continue
            dt = _parse_month(tds[0].get_text(strip=True))
            val = _num(tds[1].get_text(strip=True))
            if dt and val:
                rows.append({"date": dt, "dy": val})
        rows.sort(key=lambda x: x["date"])
        if rows:
            log.info("multpl 标普500 股息率 %d 行（月频）", len(rows))
        return rows
    except requests.RequestException as e:
        log.warning("multpl 股息率抓取失败: %s", e)
        return []


def fetch_danjuan_yield(index_code: str) -> list:
    """蛋卷 detail 接口的最新股息率（%），仅单点，需按周累积成历史"""
    code = danjuan_symbol(index_code)
    if not code:
        return []
    try:
        r = requests.get(f"https://danjuanfunds.com/djapi/index_eva/detail/{code}",
                         headers=BASE_HEADERS, timeout=25)
        data = r.json().get("data") or {}
        y = data.get("yeild")
        if isinstance(y, (int, float)) and y > 0:
            return [{"date": date.today().isoformat(), "dy": round(float(y) * 100, 2)}]
    except (requests.RequestException, ValueError) as e:
        log.warning("蛋卷股息率抓取失败 %s: %s", code, e)
    return []


def fetch_csi_factsheet_metrics(index_code: str) -> dict:
    """中证官方 factsheet PDF 的最新估值快照：{date, pb, dy}。

    仅最新一期，无历史归档；作为 A500/半导体等无免费历史源时的现值补充，
    pipeline 会因样本不足标注"数据不足"。
    """
    code = index_code.split(".")[0]
    url = ("https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
           f"indices/detail/files/zh_CN/{code}factsheet.pdf")
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("未安装 pypdf，跳过中证 factsheet（%s）", code)
        return {}
    try:
        r = requests.get(url, headers=BASE_HEADERS, timeout=40)
        if r.status_code != 200 or b"%PDF" not in r.content[:16]:
            log.warning("中证 factsheet 不可用 %s（HTTP %s）", code, r.status_code)
            return {}
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join(p.extract_text(extraction_mode="layout") or ""
                         for p in reader.pages)
        out = {}
        m_pb = re.search(r"市净率\s+([0-9]+(?:\.[0-9]+)?)", text)
        m_dy = re.search(r"股息率\s+([0-9]+(?:\.[0-9]+)?)%", text)
        if m_pb:
            out["pb"] = float(m_pb.group(1))
        if m_dy:
            out["dy"] = float(m_dy.group(1))
        dates = re.findall(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if dates:
            y, mo, d = max(dates, key=lambda x: (int(x[0]), int(x[1]), int(x[2])))
            out["date"] = f"{y}-{int(mo):02d}-{int(d):02d}"
        if not out.get("pb") and not out.get("dy"):
            log.warning("中证 factsheet 未找到市净率/股息率 %s", code)
        else:
            log.info("中证 factsheet %s PB=%s 股息率=%s（%s）", code,
                     out.get("pb"), out.get("dy"), out.get("date", "日期不明"))
        return out
    except (requests.RequestException, ValueError) as e:
        log.warning("中证 factsheet 解析失败 %s: %s", code, e)
        return {}


def fetch_dividend_yield(index_code: str) -> list:
    """指数股息率（%）：标普走 multpl 月频历史；其余优先蛋卷最新值，回退中证 factsheet"""
    if index_code == "SPX":
        return fetch_multpl_spx_dy()
    rows = fetch_danjuan_yield(index_code)
    if rows:
        return rows
    m = fetch_csi_factsheet_metrics(index_code)
    if m.get("dy") and m.get("date"):
        return [{"date": m["date"], "dy": m["dy"]}]
    return []


def _num(s):
    try:
        return float(str(s).replace(",", "").replace("†", "")
                     .replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_month(s: str):
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def tencent_symbol(index_code: str, market: str) -> str:
    """指数代码转腾讯代码：000300.SH -> sh000300；000510.CSI -> sh000510；HSTECH -> hkHSTECH；SPX -> usSPX"""
    if market == "cn":
        code = index_code.split(".")[0]
        # 沪市：.SH 后缀；中证指数 .CSI 以 000 开头也属沪市（如 000510.CSI），399 开头为深市
        is_sh = index_code.endswith(".SH") or (
            index_code.endswith(".CSI") and code.startswith("000")
        )
        return ("sh" if is_sh else "sz") + code
    return ("hk" + index_code) if index_code.startswith("HS") else ("us" + index_code)
