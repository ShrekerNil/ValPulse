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


def _index_code(code: str) -> str:
    """提取纯指数代码：931643.CSI -> 931643；GOLD.AU9999 -> Au99.99"""
    if code.startswith("GOLD."):
        return "Au99.99"
    return code.split(".")[0]


def holdings_of(cfg: dict, records_by_code: dict) -> list:
    """组装持仓视图：[{group, fund, code, record, is_gold, watch}]，记录缺失的跳过

    兼容两种配置：旧扁平列表 [{fund, code}] 或新分组 {组名: [{fund, code, watch?}]}。
    watch 为可选盯盘提示（仅场内需要）：{metric, rule}，卡片上渲染成小白可读文案。
    """
    out = []
    raw = cfg.get("holdings", {})
    if isinstance(raw, list):  # 兼容旧扁平结构
        grouped = [("持仓", raw)]
    else:
        grouped = list(raw.items())
    for group, items in grouped:
        for h in items:
            rec = records_by_code.get(h["code"])
            if rec is None:
                continue
            out.append({"group": group, "fund": h["fund"], "code": h["code"],
                        "fund_code": h.get("fund_code"),
                        "index_code": _index_code(h["code"]),
                        "record": rec, "is_gold": rec.get("market") == "gold",
                        "watch": h.get("watch"), "etf": h.get("etf")})
    return out
