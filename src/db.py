# -*- coding: utf-8 -*-
"""SQLite 数据层：全历史序列 + 每期汇总，替代原快照 JSON 机制。

设计：
- series 表存每个标的的全部历史序列（pe/pb/price），主键 (code, date, metric)
- snapshots 表存每期算好的分位结果，供前端日期回看与环比
- 前端数据由 export_web_data 导出为 reports/data/*.json（唯一数据出口）
"""
import json
import logging
import sqlite3
from datetime import date
from pathlib import Path

log = logging.getLogger("valpulse.db")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "valuation.db"
SNAPSHOT_DIR = DATA_DIR / "snapshots"

SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    code   TEXT NOT NULL,
    date   TEXT NOT NULL,
    metric TEXT NOT NULL,          -- pe | pb | price
    value  REAL,
    PRIMARY KEY (code, date, metric)
);
CREATE TABLE IF NOT EXISTS snapshots (
    date     TEXT NOT NULL,
    code     TEXT NOT NULL,
    name     TEXT,
    market   TEXT,
    category TEXT,
    frequency TEXT,
    pe       REAL,
    pe_pct   REAL,
    pe_band  TEXT,
    pe_samples INTEGER,
    pb       REAL,
    pb_pct   REAL,
    pb_band  TEXT,
    pb_samples INTEGER,
    price    REAL,
    price_pct REAL,
    price_band TEXT,
    change_pct REAL,
    PRIMARY KEY (date, code)
);
CREATE INDEX IF NOT EXISTS idx_series_code ON series(code, metric, date);
CREATE INDEX IF NOT EXISTS idx_snap_date ON snapshots(date);
"""

METRICS = ("pe", "pb", "price")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection):
    conn.executescript(SCHEMA)
    conn.commit()


def save_series(conn: sqlite3.Connection, code: str, metric: str, rows: list):
    """写入/更新一个标的的某类指标全历史。rows: [{date, value}]"""
    if metric not in METRICS:
        raise ValueError(f"未知指标类型: {metric}")
    conn.executemany(
        "INSERT INTO series(code, date, metric, value) VALUES(?,?,?,?) "
        "ON CONFLICT(code, date, metric) DO UPDATE SET value=excluded.value",
        [(code, r["date"], metric, r["value"]) for r in rows if r.get("value") is not None])
    conn.commit()


def save_snapshot(conn: sqlite3.Connection, report_date: str, records: list):
    """写入一期汇总（分位与分级已由调用方算好）"""
    rows = []
    for r in records:
        rows.append((
            report_date, r["code"], r.get("name"), r.get("market"),
            r.get("category"), r.get("frequency", "daily"),
            r.get("pe_value"), r.get("pe_percentile"), r.get("pe_band"),
            r.get("pe_samples"),
            r.get("pb_value"), r.get("pb_percentile"), r.get("pb_band"),
            r.get("pb_samples"),
            r.get("price"), r.get("price_percentile"), r.get("price_band"),
            r.get("change_pct"),
        ))
    conn.executemany(
        "INSERT INTO snapshots VALUES(" + ",".join(["?"] * 18) + ") "
        "ON CONFLICT(date, code) DO UPDATE SET "
        "name=excluded.name, pe=excluded.pe, pe_pct=excluded.pe_pct, "
        "pe_band=excluded.pe_band, pe_samples=excluded.pe_samples, "
        "pb=excluded.pb, pb_pct=excluded.pb_pct, pb_band=excluded.pb_band, "
        "pb_samples=excluded.pb_samples, price=excluded.price, "
        "price_pct=excluded.price_pct, price_band=excluded.price_band, "
        "change_pct=excluded.change_pct", rows)
    conn.commit()


def load_series_all(conn: sqlite3.Connection) -> dict:
    """全历史序列：{code: {metric: [[date, value], ...]}}"""
    out = {}
    for row in conn.execute(
            "SELECT code, metric, date, value FROM series ORDER BY code, metric, date"):
        out.setdefault(row["code"], {}).setdefault(row["metric"], []).append(
            [row["date"], row["value"]])
    return out


def load_snapshots(conn: sqlite3.Connection) -> list:
    """全部历史汇总，按日期正序"""
    return [dict(r) for r in conn.execute(
        "SELECT * FROM snapshots ORDER BY date, code")]


def import_legacy_snapshots(conn: sqlite3.Connection) -> int:
    """把旧的 data/snapshots/*.json 快照导入 snapshots 表（一次性兼容）"""
    if not SNAPSHOT_DIR.exists():
        return 0
    count = 0
    for p in sorted(SNAPSHOT_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        records = data.get("records") or []
        if not records:
            continue
        save_snapshot(conn, data.get("date") or p.stem, records)
        count += 1
    if count:
        log.info("已导入旧快照 %d 期", count)
    return count


def export_web_data(conn: sqlite3.Connection, out_dir: Path):
    """导出前端数据文件：series.json + snapshots.json"""
    data_dir = out_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "series.json").write_text(
        json.dumps(load_series_all(conn), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    (data_dir / "snapshots.json").write_text(
        json.dumps(load_snapshots(conn), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    log.info("前端数据已导出: %s", data_dir)
