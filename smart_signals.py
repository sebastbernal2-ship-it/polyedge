#!/usr/bin/env python3
"""CLI helper that prints top smart-money trades with edge and Kelly sizing.

Now powered by model.edge.get_smart_money_signals so logic matches the dashboard:
- Edge = your_prob - market_prob on the recommended side
- Kelly recomputed safely from that edge
- Ultra-longshot futures are filtered out in get_smart_money_signals
"""

from config import BANKROLL
from data.polymarket import fetch_candidate_markets
from model.edge import get_smart_money_signals


def main():
    # 1) Pull candidate markets from Polymarket
    markets = fetch_candidate_markets()

    # 2) Let the unified smart-money pipeline build signals (with all filters)
    signals = get_smart_money_signals(markets=markets)

    # 3) Sort: highest Smart Money %, then Kelly, then |edge|
    def sort_key(s):
        sm = s.get("sm_pct")
        sm_rank = sm if sm is not None else -1.0
        return (-sm_rank, -(s.get("kelly_pct", 0.0) or 0.0), -abs(s.get("edge", 0.0)))

    signals.sort(key=sort_key)

    # 4) Pretty-print the top signals
    print(f"{'Side':8} {'SM%':>6} {'Edge%':>7} {'Kelly%':>7}  Question")
    for sig in signals[:10]:
        side = sig.get("side", "Skip")
        sm = sig.get("sm_pct")
        sm_str = f"{sm:5.1f}" if sm is not None else "  n/a"
        edge = sig.get("edge", 0.0) or 0.0
        kelly_pct = sig.get("kelly_pct", 0.0) or 0.0
        q = sig.get("question", "")[:100]
        edge_pct = edge * 100.0
        print(f"{side:8} {sm_str} {edge_pct:7.1f} {kelly_pct:7.1f}  {q}")


if __name__ == "__main__":
    main()
