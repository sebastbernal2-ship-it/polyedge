from dotenv import load_dotenv
load_dotenv()

from data.polymarket import get_iran_markets
from data.news import get_latest_headlines
from model.edge import get_trade_signals
from model.estimator import MARKET_PRIORS
from config import EDGE_THRESHOLD

def run():
    print("\n=== POLYEDGE SIGNAL SCAN ===\n")
    markets = get_iran_markets()
    print(f"Fetched {len(markets)} Iran markets\n")

    signals = get_trade_signals(markets, MARKET_PRIORS, EDGE_THRESHOLD)
    if not signals:
        print("No edges above threshold.")
    for s in signals:
        print(f"[{s['side']}] {s['question'][:60]}")
        print(f"  Market: {s['market_prob']:.0%} | Yours: {s['your_prob']:.0%} "
              f"| Edge: {s['edge']:+.0%} | Bet: ${s['bet_size']}")
        print()

    print("\n=== LATEST NEWS ===\n")
    for a in get_latest_headlines()[:10]:
        print(f"[{a['keyword']}] {a['title']}")

if __name__ == "__main__":
    run()
