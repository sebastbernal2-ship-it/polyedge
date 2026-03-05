#!/usr/bin/env python3
import time
import json
import requests
from datetime import datetime, timezone

from model.market_flow import analyze_market_flow
from data.polymarket import get_iran_markets
from whale_monitor import TARGET_MARKETS

WEBHOOK_URL = "https://discord.com/api/webhooks/1478864458595045610/hhzY_-Nqgs4QY9IgKPASvZjOykj-yPE9XJRdSpsh5EFFKKblZPb-1A5GhryGlm2l29ZW"
POLL_SECONDS = 300  # 5 minutes
EDGE_THRESHOLD = 0.03  # 3 percentage points

# Simple state to avoid spamming repeated alerts
last_decisions = {}  # {market_id: strategy_decision}

def send_alert(market_label, rec, edge, kelly, strategy_reason):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f"📈 PolyEdge Signal\n"
        f"Market: {market_label}\n"
        f"Time: {now}\n\n"
        f"Recommendation: {rec}\n"
        f"Strategy: {strategy_reason}\n"
        f"Edge: {edge:.1%} | Kelly: {kelly:.1%} of bankroll"
    )
    try:
        requests.post(WEBHOOK_URL, json={"content": text}, timeout=5)
    except Exception as e:
        print("Failed to send Discord alert:", e)



def fetch_markets():
    """Return the three Iran target markets with live prices.

    The helper pulls all active Iran-tagged markets from the Polymarket
    API and then filters down to the three IDs defined in
    ``whale_monitor.TARGET_MARKETS`` so that we reuse the same labels and
    identifiers used elsewhere in the project.

    Each entry is a dict with at least ``id``, ``label``, ``question``
    and ``yes_price`` keys as the watcher logic expects.
    """
    all_markets = get_iran_markets()
    id_to_label = {v: k for k, v in TARGET_MARKETS.items()}
    out = []
    for m in all_markets:
        mid = m.get("id")
        label = id_to_label.get(mid)
        if not label:
            continue
        out.append({
            "id": mid,
            "label": label,
            "question": m.get("question"),
            "yes_price": m.get("yes_price"),
        })
    return out


def main():
    global last_decisions

    while True:
        try:
            # 1) Get current markets and prices (only the three Iran targets)
            markets = fetch_markets()

            # 2) Load whale trades once
            with open("data/whales_log.json") as f:
                trades = json.load(f)

            # 3) For each target market, run analyze_market_flow
            for m in markets:
                market_id = m.get("id") or m.get("market_id")
                market_label = m.get("question") or m.get("label")

                # Filter trades for this market
                mtrades = [t for t in trades if t.get("market_id") == market_id]
                if not mtrades:
                    continue

                market_info = {
                    "question": market_label,
                    "yes_price": m.get("yes_price"),
                    "market_id": market_id,
                }

                res = analyze_market_flow(market_info, mtrades)

                rec = res.get("recommendation")
                edge = res.get("edge") or 0.0
                kelly = res.get("kelly_pct") or 0.0
                strat_decision = res.get("strategy_decision", "Skip")
                strat_reason = res.get("strategy_reason", "")

                # Only alert when we switch from SKIP -> Trade AND edge >= threshold
                prev = last_decisions.get(market_id, "Skip")
                if strat_decision == "Trade" and prev != "Trade" and edge >= EDGE_THRESHOLD:
                    send_alert(market_label, rec, edge, kelly, strat_reason)

                last_decisions[market_id] = strat_decision

        except Exception as e:
            print("Watcher loop error:", e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
