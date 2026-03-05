#!/usr/bin/env python3
"""CLI helper that prints top smart-money trades with edge and Kelly sizing."""

import json
import os

from config import BANKROLL
from data.polymarket import fetch_candidate_markets

# whales loader helper may not exist; try import, else read file
try:
    from data.whales import load_whale_log
except Exception:
    load_whale_log = None

from model.market_flow import analyze_market_flow


def _load_whales_fallback(path: str = "data/whales_log.json"):
    """Fallback loader when helper isn't available or file is missing."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return []


def main():
    markets = fetch_candidate_markets()

    # load whale trades
    if load_whale_log:
        try:
            whale_trades_all = load_whale_log()
        except Exception:
            whale_trades_all = []
    else:
        whales_path = os.path.join("data", "whales_log.json")
        if os.path.exists(whales_path):
            with open(whales_path, "r") as f:
                whale_trades_all = json.load(f)
        else:
            whale_trades_all = []

    results = []

    for m in markets:
        mid = m.get("id") or m.get("conditionId") or m.get("market_id")
        question = m.get("question") or m.get("title") or m.get("name") or ""
        mkt_price = m.get("yes_price") or m.get("probability")

        # need a usable price in (0,1)
        try:
            mkt_price = float(mkt_price)
        except Exception:
            continue
        if mkt_price is None or mkt_price <= 0 or mkt_price >= 1:
            continue

        # match whale trades by id or label
        trades = [
            t
            for t in whale_trades_all
            if (t.get("market_id") == mid) or (t.get("market_label") == question)
        ]
        if not trades:
            continue

        try:
            res = analyze_market_flow(m, trades, bankroll=BANKROLL)
        except Exception:
            continue

        side = res.get("recommendation") or "Skip"
        edge = res.get("edge") or 0.0
        kelly_pct = res.get("kelly_pct") or 0.0
        sm_pct = res.get("sm_pct")  # may be None

        # normalize types
        edge = float(edge)
        kelly_pct = float(kelly_pct)
        if sm_pct is not None:
            sm_pct = float(sm_pct)

        results.append(
            {
                "question": question,
                "side": side,
                "edge": edge,
                "kelly_pct": kelly_pct,
                "prior": res.get("prior_prob"),
                "sm_pct": sm_pct,
            }
        )

    # sort: highest smart-money %, then Kelly, then |edge|
    def sort_key(r):
        sm = r["sm_pct"]
        sm_rank = sm if sm is not None else -1.0  # None → lowest priority
        return (-sm_rank, -r["kelly_pct"], -abs(r["edge"]))

    results.sort(key=sort_key)

    # print header
    print(f"{'Side':8} {'SM%':>6} {'Edge%':>7} {'Kelly%':>7}  Question")
    for rec in results[:10]:
        sm = rec["sm_pct"]
        sm_str = f"{sm:5.1f}" if sm is not None else "  n/a"
        edge_pct = rec["edge"] * 100.0
        kelly = rec["kelly_pct"]
        side = rec["side"]
        print(
            f"{side:8} {sm_str} {edge_pct:7.1f} {kelly:7.1f}  {rec['question'][:100]}"
        )


if __name__ == "__main__":
    main()
