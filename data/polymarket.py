from typing import List, Dict, Any
from datetime import datetime, timezone
import requests
import json

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL  = "https://clob.polymarket.com"

def get_iran_markets():
    """Pull all active Iran-tagged markets with current prices."""
    all_markets = []
    for offset in [0, 100, 200]:
        resp = requests.get(f"{GAMMA_URL}/markets", params={
            "limit": 100,
            "active": True,
            "closed": False,
            "order": "volume",
            "tag_id": 78,
            "related_tags": True,
            "offset": offset
        })
        resp.raise_for_status()
        all_markets.extend(resp.json())

    parsed = []
    for m in all_markets:
        raw_prices = m.get("outcomePrices", '["0","1"]')
        if isinstance(raw_prices, str):
            prices = json.loads(raw_prices)
        else:
            prices = raw_prices

        raw_tokens = m.get("clobTokenIds", "[]")
        if isinstance(raw_tokens, str):
            token_ids = json.loads(raw_tokens)
        else:
            token_ids = raw_tokens

        parsed.append({
            "id":        m.get("conditionId"),
            "question":  m.get("question"),
            "yes_price": float(prices[0]),
            "no_price":  float(prices[1]),
            "volume":    float(m.get("volume") or 0),
            "end_date":  m.get("endDate"),
            "token_ids": token_ids,
        })
    return parsed


    parsed = []
    for m in all_markets:
        raw_prices = m.get("outcomePrices", '["0","1"]')
        if isinstance(raw_prices, str):
            prices = json.loads(raw_prices)
        else:
            prices = raw_prices

        parsed.append({
            "id":        m.get("conditionId"),
            "question":  m.get("question"),
            "yes_price": float(prices[0]),
            "no_price":  float(prices[1]),
            "volume":    float(m.get("volume") or 0),
            "end_date":  m.get("endDate"),
            "token_ids": m.get("clobTokenIds", []),
        })
    return parsed

def get_price_history(token_id: str, interval="1h"):
    """Pull price history for a single token."""
    try:
        resp = requests.get(f"{CLOB_URL}/prices-history", params={
            "market": token_id,
            "interval": interval,
            "fidelity": 60
        })
        resp.raise_for_status()
        return resp.json().get("history", [])
    except Exception:
        return []


# ---- Auto-discovery helpers (loose) ----

import requests

GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_candidate_markets(deadline=None) -> list[dict]:
    """
    Fetch a broad set of active markets from Polymarket.
    Very loose filtering: just require id + question; yes_price optional.
    """
    params = {
        "limit": 2000,
        "active": True,
        "closed": False,
        "order": "volume",
    }
    r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
    r.raise_for_status()
    markets = r.json()
    if not isinstance(markets, list):
        return []

    out = []
    for m in markets:
        if not isinstance(m, dict):
            continue

        m_id = m.get("conditionId") or m.get("id")
        label = m.get("question") or m.get("title") or m.get("name")

        # outcomePrices is usually a JSON string like '["0.23","0.77"]'
        raw_prices = m.get("outcomePrices")
        yes_price = None
        if raw_prices is not None:
            try:
                if isinstance(raw_prices, str):
                    prices = json.loads(raw_prices)
                else:
                    prices = raw_prices
                if isinstance(prices, (list, tuple)) and prices:
                    yes_price = float(prices[0])
            except Exception:
                yes_price = None

        if not m_id or not label:
            continue

        out.append(
            {
                "id": str(m_id),
                "question": str(label),
                "yes_price": yes_price,
                "resolve_time": None,
            }
        )

    return out

