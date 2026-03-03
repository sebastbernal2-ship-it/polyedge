#!/usr/bin/env python3
import os
import time
import datetime as dt
import requests
from dataclasses import dataclass
from typing import List, Optional

# =========================
# CONFIG
# =========================

# Minimum whale trade size in USD
MIN_USD = 10_000

# Polling interval in seconds
POLL_SECONDS = 30

# Polymarket main CLOB API and markets API
CLOB_BASE = "https://clob.polymarket.com"

# Target markets (you can expand this list)
TARGET_MARKETS = {
    # label: market question fragment or explicit id
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

def get_markets_by_search(query: str) -> Optional[dict]:
    """
    Use Polymarket search API to find a market by question text fragment.
    """
    url = f"{CLOB_BASE}/markets?search={requests.utils.quote(query)}&limit=5"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data:
        return None
    # Return first match
    return data[0]

def build_target_markets() -> dict:
    """
    Resolve TARGET_MARKETS into full MarketInfo objects keyed by label.
    """
    resolved = {}
    for label, cfg in TARGET_MARKETS.items():
        market_raw = get_markets_by_search(cfg["search"])
        if not market_raw:
            print(f"[WARN] No market found for search: {cfg['search']}")
            continue
        m = MarketInfo(
            id=market_raw["id"],
            question=market_raw.get("question", ""),
            resolution_rules=market_raw.get("resolutionRules", "") or market_raw.get("description", "")
        )
        resolved[label] = m
        print(f"[INIT] Mapped '{label}' -> market id {m.id}")
    return resolved

def fetch_recent_fills(limit: int = 100) -> List[dict]:
    """
    Fetch recent order fills from Polymarket CLOB.
    """
    url = f"{CLOB_BASE}/fills?limit={limit}"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

def filter_whale_trades(
    fills: List[dict],
    markets: dict,
    min_usd: float
) -> List[WhaleTrade]:
    """
    Filter fills for big trades in our target markets.
    """
    market_ids = {m.id: label for label, m in markets.items()}
    whale_trades: List[WhaleTrade] = []

    for f in fills:
        market_id = f.get("marketId")
        if market_id not in market_ids:
            continue
        size_usd = float(f.get("usdVolume", 0))
        if size_usd < min_usd:
            continue

        label = market_ids[market_id]
        m = markets[label]

        outcome_index = f.get("outcome", 0)
        # 0 usually 'Yes', 1 'No' for binary markets
        outcome = "Yes" if outcome_index == 0 else "No"

        trade = WhaleTrade(
            market_id=market_id,
            market_label=label,
            question=m.question,
            wallet=f.get("taker", ""),
            size_usd=size_usd,
            outcome=outcome,
            price=float(f.get("price", 0)),
            timestamp=int(f.get("timestamp", int(time.time())))
        )
        whale_trades.append(trade)

    return whale_trades

def format_llm_prompt(trade: WhaleTrade, rules: str) -> str:
    """
    Build a ready-to-paste prompt for your LLM (me) to analyze the trade.
    """
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
    """
    Print + optional Telegram alert + show LLM prompt.
    """
    ts = dt.datetime.utcfromtimestamp(trade.timestamp).isoformat() + "Z"
    short_msg = (
        f"🐋 Whale in {trade.market_label}: {trade.outcome} "
        f"${trade.size_usd:,.0f} at {trade.price:.3f} ({ts})"
    )
    print(short_msg)
    send_telegram(short_msg)

    # Also print the LLM prompt to your console
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
                # Avoid duplicate alerts: use composed id (wallet+timestamp+market)
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
