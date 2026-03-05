#!/usr/bin/env python3
"""Single-shot whale fetch — called by dashboard auto-refresh."""
from dotenv import load_dotenv
load_dotenv(override=True)

from whale_monitor import (
    fetch_recent_trades_global,
    filter_whale_trades,
    append_whale_to_log,
    auto_update_priors_from_whales,
    MIN_USD,
)

def run_once():
    trades = fetch_recent_trades_global()
    if not trades:
        return
    whales = filter_whale_trades(trades, MIN_USD)
    for w in whales:
        append_whale_to_log(w)
    auto_update_priors_from_whales()
    print(f"[whale_monitor_once] {len(whales)} whale trades logged.")

if __name__ == "__main__":
    run_once()
