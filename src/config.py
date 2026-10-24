# -*- coding: utf-8 -*-
"""配置加载与共享数据结构"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
REPORT_DIR = ROOT / "reports"

BAND_LABELS = {
    "undervalued": "低估",
    "fair": "合理",
    "high": "偏高",
    "over": "高估",
    "unknown": "数据不足",
}


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for d in (SNAPSHOT_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return cfg


def all_indexes(cfg: dict) -> list:
    """合并 A股/黄金/跨境指数为统一列表（market: cn/gold/cross）"""
    items = []
    for it in cfg.get("indexes", []):
        items.append({**it, "market": "cn", "source": it.get("source", "legulegu")})
    for it in cfg.get("gold", []):
        items.append({**it, "market": "gold", "source": "gold"})
    for it in cfg.get("cross_border", []):
        items.append({**it, "market": "cross"})
    return items


def holdings_of(cfg: dict, records_by_code: dict) -> list:
    """组装持仓视图：[{fund, code, record, is_gold}]，记录缺失的跳过"""
    out = []
    for h in cfg.get("holdings", []):
        rec = records_by_code.get(h["code"])
        if rec is None:
            continue
        out.append({"fund": h["fund"], "code": h["code"],
                    "record": rec, "is_gold": rec.get("market") == "gold"})
    return out
