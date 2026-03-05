#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv(override=True)

import os
import json
import time as _time
import requests
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass

from data.polymarket import fetch_candidate_markets
from wallet_tracker import run_scoring


# --- CONFIG ---

DATA_API = "https://data-api.polymarket.com"
CHAIN_ID = 137

EVENT_MIN_USD = 50      # everything above this is an "event"
MIN_USD = 1000          # whales only (should match whale_monitor.py)

BASE_DATA_DIR = "data"
EVENT_LOG_PATH = os.path.join(BASE_DATA_DIR, "events_log.json")
WHALE_LOG_PATH = os.path.join(BASE_DATA_DIR, "whales_log.json")


# --- DATA MODEL ---

@dataclass
class Trade:
    timestamp: int
    market_id: str
    market_label: str
    wallet: str
    size_usd: float
    outcome: str
    price: float


# --- HELPERS ---

def _append_to_json(path: str, entry: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing: List[dict] = []
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = []
    existing.append(entry)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)


def append_event_to_logs(trade: Trade) -> None:
    entry = {
        "timestamp": trade.timestamp,
        "market_id": trade.market_id,
        "market_label": trade.market_label,
        "wallet": trade.wallet,
        "size_usd": trade.size_usd,
        "size": trade.size_usd,
        "outcome": trade.outcome,
        "side": trade.outcome,
        "price": trade.price,
    }

    # All events
    _append_to_json(EVENT_LOG_PATH, entry)

    # Whale-only subset
    if trade.size_usd >= MIN_USD:
        _append_to_json(WHALE_LOG_PATH, entry)


def fetch_trades_for_market(market_id: str, since_ts: int) -> List[dict]:
    """
    Backfill trades from Polymarket data API since a given unix timestamp.
    Uses a single-page fetch with `after` filter, which is enough for a few weeks.
    """
    resp = requests.get(
        f"{DATA_API}/trades",
        params={
            "market": market_id,
            "limit": 1000,
            "offset": 0,
            "chainId": CHAIN_ID,
            "after": str(since_ts),
            "filterType": "CASH",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json() or []
    # Safety filter
    return [t for t in data if int(t.get("timestamp", 0)) >= since_ts]


def normalize_trade(raw: dict, market_label: str) -> Optional[Trade]:
    try:
        ts = int(raw.get("timestamp", 0))
        wallet = (
            raw.get("user")
            or raw.get("proxyWallet")
            or raw.get("maker")
            or raw.get("taker")
            or ""
        )
        usd = float(
            raw.get("cashAmount")
            or raw.get("usdAmount")
            or raw.get("size_usd")
            or raw.get("size")
            or 0
        )
        price = float(raw.get("price") or 0)
        side = raw.get("side") or raw.get("outcome") or ""
        outcome = "Yes" if str(side).upper() in ("BUY", "YES") else "No"
    except Exception:
        return None

    if usd < EVENT_MIN_USD:
        return None

    return Trade(
        timestamp=ts,
        market_id=raw.get("marketId") or raw.get("conditionId") or "",
        market_label=market_label,
        wallet=str(wallet),
        size_usd=usd,
        outcome=outcome,
        price=price,
    )


# --- BACKFILL LOGIC ---

def backfill_days(days: int = 14):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    since_ts = int(since.timestamp())
    print(
        f"[BACKFILL] Backfilling events since {since.isoformat()} "
        f"(unix {since_ts}) for ALL candidate markets"
    )

    markets = fetch_candidate_markets()
    print(f"[BACKFILL] Found {len(markets)} candidate markets")

    seen = set()
    total_events = 0
    total_whales = 0

    for m in markets:
        market_id = m.get("id")
        label = m.get("question") or m.get("title") or m.get("name")
        if not market_id or not label:
            continue

        print(f"[BACKFILL] Fetching market: {label}")
        try:
            raw_trades = fetch_trades_for_market(market_id, since_ts)
        except Exception as e:
            print(f"  [WARN] Failed to fetch trades for {label}: {e}")
            continue

        print(f"  -> got {len(raw_trades)} raw trades")
        for r in raw_trades:
            t = normalize_trade(r, label)
            if not t:
                continue

            key = f"{t.wallet}-{t.timestamp}-{t.market_id}-{t.price}"
            if key in seen:
                continue
            seen.add(key)

            append_event_to_logs(t)
            total_events += 1
            if t.size_usd >= MIN_USD:
                total_whales += 1

    print(
        f"[BACKFILL] Done. Logged {total_events} events ≥ ${EVENT_MIN_USD} "
        f"and {total_whales} whales ≥ ${MIN_USD}."
    )


def main():
    backfill_days(days=14)  # change to 7, 30, etc. if you want

    # Run wallet scoring after backfill
    try:
        print("[BACKFILL] Running wallet scoring after backfill...")
        run_scoring()
        print("[BACKFILL] Wallet scoring complete.")
    except Exception as e:
        print(f"[BACKFILL] Skipped wallet scoring: {e}")


if __name__ == "__main__":
    main()
