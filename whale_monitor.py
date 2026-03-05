#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv(override=True)

import os
import json
import time as _time
import requests
from datetime import datetime, timezone
from typing import List, Dict
from dataclasses import dataclass

from data.polymarket import fetch_candidate_markets
from wallet_tracker import run_scoring  # wallet scorer


# --- CONFIG ---

DATA_API = "https://data-api.polymarket.com"

EVENT_MIN_USD = 50        # everything above this is an "event"
MIN_USD = 2000            # whales for SM / priors
POLL_SECONDS = 30

BASE_DATA_DIR = "data"
EVENT_LOG_PATH = os.path.join(BASE_DATA_DIR, "events_log.json")
WHALE_LOG_PATH = os.path.join(BASE_DATA_DIR, "whales_log.json")

LAST_SCORE_TS = 0
SCORE_INTERVAL_SEC = 6 * 3600  # re-score wallets every 6 hours


# --- DATA MODEL ---

@dataclass
class WhaleTrade:
    market_id: str      # conditionId
    market_label: str   # question text
    wallet: str
    size_usd: float
    outcome: str
    price: float
    timestamp: int


# --- MARKET DISCOVERY ---

def build_conditionid_to_label() -> Dict[str, str]:
    """Map conditionId -> question/label from candidate markets."""
    mapping: Dict[str, str] = {}
    try:
        ms = fetch_candidate_markets()
        for m in ms:
            cid = str(m.get("id"))
            label = m.get("question") or m.get("title") or m.get("name")
            if cid and label:
                mapping[cid] = label
        print(f"[INIT] conditionId->label mapping: {len(mapping)} markets")
    except Exception as e:
        print(f"[WARN] build_conditionid_to_label failed: {e}")
    return mapping


# --- TRADE FETCHING ---

def fetch_recent_trades_global(limit: int = 500) -> List[dict]:
    """Fetch recent big trades across ALL markets (by size filter only)."""
    try:
        resp = requests.get(
            f"{DATA_API}/trades",
            params={
                "limit": limit,
                "filterType": "CASH",
                "filterAmount": EVENT_MIN_USD,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            print(f"[GLOBAL] Got {len(data)} trades >= ${EVENT_MIN_USD:,}")
            return data
        print(f"[WARN] Unexpected global trades response: {str(data)[:200]}")
        return []
    except Exception as e:
        print(f"[WARN] Global trades fetch failed: {e}")
        return []


def filter_whale_trades(trades: List[dict]) -> List[WhaleTrade]:
    """
    Turn global trades into structured trades for markets we know,
    keeping all events >= EVENT_MIN_USD.
    """
    id_to_label = build_conditionid_to_label()
    whales: List[WhaleTrade] = []

    for t in trades:
        cid = str(t.get("conditionId") or t.get("market") or "")
        if cid not in id_to_label:
            continue

        try:
            size_usd = float(
                t.get("size_usd")
                or t.get("size")
                or t.get("cashAmount")
                or t.get("usdAmount")
                or 0
            )
        except Exception:
            size_usd = 0.0
        if size_usd < EVENT_MIN_USD:
            continue

        label = id_to_label[cid]
        outcome = str(t.get("outcome") or t.get("side") or "")

        try:
            price = float(t.get("price") or 0)
        except Exception:
            price = 0.0

        try:
            ts = int(t.get("timestamp") or int(_time.time()))
        except Exception:
            ts = int(_time.time())

        wallet = str(
            t.get("proxyWallet")
            or t.get("maker")
            or t.get("taker")
            or t.get("user")
            or ""
        )

        whales.append(
            WhaleTrade(
                market_id=cid,
                market_label=label,
                wallet=wallet,
                size_usd=size_usd,
                outcome=outcome,
                price=price,
                timestamp=ts,
            )
        )

    print(f"[FILTER] Kept {len(whales)} events in known markets")
    return whales


# --- LOGGING ---

def _append_to_json(path: str, entry: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    log: List[dict] = []
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                log = json.load(f)
        except Exception:
            log = []
    log.append(entry)
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def append_event_to_logs(trade: WhaleTrade):
    """
    Write every event >= EVENT_MIN_USD to events_log.json.
    If it's >= MIN_USD, also write to whales_log.json.
    """
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

    # All events log
    _append_to_json(EVENT_LOG_PATH, entry)

    # Whale-only log
    if trade.size_usd >= MIN_USD:
        _append_to_json(WHALE_LOG_PATH, entry)


# --- PRIORS FROM WHALES ---

def auto_update_priors_from_whales():
    """Set override priors based on last 48h of whale flow."""
    from model.estimator import set_override_prior
    from collections import defaultdict

    if not os.path.exists(WHALE_LOG_PATH):
        return

    try:
        with open(WHALE_LOG_PATH) as f:
            log = json.load(f)
    except Exception:
        return

    cutoff = int(_time.time()) - 48 * 3600
    summary = defaultdict(lambda: {"Yes": 0.0, "No": 0.0, "count": 0})

    for t in log:
        if t.get("timestamp", 0) < cutoff:
            continue
        label = t.get("market_label", "")
        outcome = t.get("outcome", "")
        size = float(t.get("size_usd", 0))
        if label and outcome in ("Yes", "No"):
            summary[label][outcome] += size
            summary[label]["count"] += 1

    for label, data in summary.items():
        total = data["Yes"] + data["No"]
        count = data["count"]
        if total < 50_000 or count < 3:
            continue
        p_yes = data["Yes"] / total
        set_override_prior(label, round(p_yes, 3))
        print(
            f"[AUTO-PRIOR] {label}: p_yes={p_yes:.3f} "
            f"(${total:,.0f} volume, {count} trades)"
        )


# --- MAIN LOOP ---

def main():
    global LAST_SCORE_TS

    print("\n=== POLYMARKET EVENT / WHALE MONITOR (global) ===\n")
    print(f"Event floor: ${EVENT_MIN_USD:,}")
    print(f"Whale floor: ${MIN_USD:,}")
    print(f"Poll interval: {POLL_SECONDS}s\n")

    seen: set = set()

    while True:
        try:
            print(f"[{datetime.now(timezone.utc).isoformat()}] Polling trades…")
            trades = fetch_recent_trades_global()
            if not trades:
                print("  -> No trades returned")
            else:
                events = filter_whale_trades(trades)
                for w in events:
                    key = f"{w.wallet}-{w.timestamp}-{w.market_id}-{w.price}"
                    if key in seen:
                        continue
                    seen.add(key)
                    append_event_to_logs(w)

                try:
                    auto_update_priors_from_whales()
                except Exception:
                    pass

                # Periodically refresh Smart Money wallet scores
                now_ts = _time.time()
                if now_ts - LAST_SCORE_TS >= SCORE_INTERVAL_SEC:
                    try:
                        run_scoring()
                        LAST_SCORE_TS = now_ts
                        print("[SMART MONEY] Wallet scoring refreshed.")
                    except Exception as e:
                        print(f"[WARN] Wallet scoring failed: {e}")

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()

        _time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
