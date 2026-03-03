#!/usr/bin/env python3
import os
import time
import datetime as dt
import requests
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# =========================
# CONFIG
# =========================

# Minimum whale trade size in USD
MIN_USD = 10_000

# Polling interval in seconds
POLL_SECONDS = 30

# Polymarket CLOB base API
CLOB_BASE = "https://clob.polymarket.com"

# Target markets (you can tweak the search strings)
TARGET_MARKETS = {
    "US x Iran ceasefire by March 15": {
        "search": "US x Iran ceasefire by March 15",
    },
    "US/Israel strike on Fordow nuclear facility by March 31": {
        "search": "Fordow nuclear facility by March 31",
    },
    "Iranian regime fall by June 30": {
        "search": "Iranian regime fall by June 30",
    },
}

# Telegram optional (for alerts)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =========================
# DATA MODELS
# =========================

@dataclass
class MarketInfo:
    id: str
    question: str
    resolution_rules: str

@dataclass
class WhaleTrade:
    market_id: str
    market_label: str
    question: str
    wallet: str
    size_usd: float
    outcome: str
    price: float
    timestamp: int

# =========================
# HELPER FUNCTIONS
# =========================

def safe_get_json(url: str, params: Optional[Dict[str, Any]] = None) -> Any:
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

def get_markets_by_search(query: str) -> Optional[dict]:
    """
    Use Polymarket markets API to find a market by question text fragment.
    API sometimes returns a list, sometimes an object with 'markets'.
    """
    url = f"{CLOB_BASE}/markets"
    params = {
        "search": query,
        "limit": 5
    }
    data = safe_get_json(url, params=params)

    # Case 1: raw list
    if isinstance(data, list):
        return data[0] if data else None

    # Case 2: { "markets": [...] }
    markets = data.get("markets")
    if isinstance(markets, list) and markets:
        return markets[0]

    print(f"[WARN] Unexpected markets response for query='{query}': {data}")
    return None

def build_target_markets() -> Dict[str, MarketInfo]:
    """
    Resolve TARGET_MARKETS into full MarketInfo objects keyed by label.
    """
    resolved: Dict[str, MarketInfo] = {}
    for label, cfg in TARGET_MARKETS.items():
        search_str = cfg["search"]
        market_raw = get_markets_by_search(search_str)
        if not market_raw:
            print(f"[WARN] No market found for search: {search_str}")
            continue

        question = (
            market_raw.get("question") or
            market_raw.get("title") or
            ""
        )
        rules = (
            market_raw.get("resolutionRules") or
            market_raw.get("description") or
            ""
        )

        m = MarketInfo(
            id=str(market_raw["id"]),
            question=question,
            resolution_rules=rules
        )
        resolved[label] = m
        print(f"[INIT] Mapped '{label}' -> market id {m.id}")
    return resolved

def fetch_recent_fills(limit: int = 100) -> List[dict]:
    """
    Fetch recent order fills from Polymarket CLOB.
    """
    url = f"{CLOB_BASE}/fills"
    params = {"limit": limit}
    data = safe_get_json(url, params=params)

    # Expecting a list; if not, try to unwrap
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "fills" in data:
        return data["fills"]
    print(f"[WARN] Unexpected fills response: {data}")
    return []

def filter_whale_trades(
    fills: List[dict],
    markets: Dict[str, MarketInfo],
    min_usd: float
) -> List[WhaleTrade]:
    """
    Filter fills for big trades in our target markets.
    """
    # map market_id -> label
    market_ids = {m.id: label for label, m in markets.items()}
    whale_trades: List[WhaleTrade] = []

    for f in fills:
        market_id = str(f.get("marketId", ""))
        if market_id not in market_ids:
            continue

        size_usd = float(f.get("usdVolume", f.get("usdAmount", 0)) or 0)
        if size_usd < min_usd:
            continue

        label = market_ids[market_id]
        m = markets[label]

        outcome_index = f.get("outcome", f.get("outcomeIndex", 0))
        # 0 usually 'Yes', 1 'No' for binary markets
        outcome = "Yes" if outcome_index in (0, "0") else "No"

        price_raw = f.get("price", 0)
        try:
            price = float(price_raw)
        except Exception:
            price = 0.0

        timestamp = int(f.get("timestamp", int(time.time())))

        trade = WhaleTrade(
            market_id=market_id,
            market_label=label,
            question=m.question,
            wallet=str(f.get("taker", f.get("maker", ""))),
            size_usd=size_usd,
            outcome=outcome,
            price=price,
            timestamp=timestamp
        )
        whale_trades.append(trade)

    return whale_trades

def format_llm_prompt(trade: WhaleTrade, rules: str) -> str:
    ts = dt.datetime.utcfromtimestamp(trade.timestamp).isoformat() + "Z"
    prompt = f"""
You are an expert prediction-market analyst.

A large trader just took a {trade.outcome} position on this Polymarket market:

Question: {trade.question}
Market label: {trade.market_label}
Market id: {trade.market_id}
Trade size: ${trade.size_usd:,.2f}
Trade price: {trade.price:.3f}
Timestamp (UTC): {ts}
Wallet: {trade.wallet}

Resolution rules:
\"\"\"{rules}\"\"\"

Task:
1. Explain what event must *literally* occur for this market to resolve YES or NO.
2. Given current Iran/US geopolitical context, discuss scenarios in the next 3–5 days that could move this price sharply.
3. Say whether following this whale temporarily (for a 1–3 day swing trade, not hold-to-resolution) is:
   - High, medium, or low edge
   - Main risks where this could be a bad copy trade.
4. Suggest an entry range and a target exit price for a quick 100–200% ROI if you believe there is an edge.
"""
    return prompt.strip()

def send_telegram(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ALERT] (Telegram disabled) ", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("[ERR] Telegram send failed:", e)

def notify_whale(trade: WhaleTrade, rules: str):
    ts = dt.datetime.utcfromtimestamp(trade.timestamp).isoformat() + "Z"
    short_msg = (
        f"🐋 Whale in {trade.market_label}: {trade.outcome} "
        f"${trade.size_usd:,.0f} at {trade.price:.3f} ({ts})"
    )
    print(short_msg)
    send_telegram(short_msg)

    print("\n========== LLM PROMPT ==========\n")
    print(format_llm_prompt(trade, rules))
    print("\n===============================\n")

# =========================
# MAIN LOOP
# =========================

def main():
    print("[*] Resolving target markets from Polymarket search…")
    markets = build_target_markets()
    if not markets:
        print("[FATAL] No markets resolved. Check TARGET_MARKETS search strings.")
        return

    seen_trade_ids = set()
    print("[*] Starting whale monitor…")

    while True:
        try:
            fills = fetch_recent_fills(limit=100)
            whales = filter_whale_trades(fills, markets, MIN_USD)

            for f in whales:
                trade_id = f"{f.wallet}-{f.timestamp}-{f.market_id}-{f.price}"
                if trade_id in seen_trade_ids:
                    continue
                seen_trade_ids.add(trade_id)

                rules = markets[f.market_label].resolution_rules
                notify_whale(f, rules)

        except Exception as e:
            print("[ERR] Loop error:", e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
