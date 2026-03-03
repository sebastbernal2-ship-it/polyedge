import json
import os
from datetime import datetime
from typing import List, Dict, Any


WHALES_PATH = os.path.join(os.path.dirname(__file__), "whales_log.json")


def _safe_load() -> List[Dict[str, Any]]:
    try:
        if not os.path.exists(WHALES_PATH):
            return []
        with open(WHALES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        # Malformed file → return empty and allow rewrite on append
        return []


def _write_all(rows: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(WHALES_PATH), exist_ok=True)
    with open(WHALES_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def append_whale(entry: Dict[str, Any]) -> bool:
    """Append a whale entry to the JSON log if not duplicate.

    Deduplicate by (wallet, timestamp, market_id, price).
    Returns True if written, False if duplicate.
    """
    rows = _safe_load()
    key = (entry.get("wallet"), entry.get("timestamp"), entry.get("market_id"), entry.get("price"))
    for r in rows:
        if (r.get("wallet"), r.get("timestamp"), r.get("market_id"), r.get("price")) == key:
            return False
    rows.append(entry)
    _write_all(rows)
    return True


def load_recent_whales(limit: int = 50) -> List[Dict[str, Any]]:
    rows = _safe_load()
    def _ts(r):
        t = r.get("timestamp")
        try:
            return datetime.fromisoformat(t) if t else datetime.min
        except Exception:
            return datetime.min

    rows_sorted = sorted(rows, key=_ts, reverse=True)
    return rows_sorted[:limit]
