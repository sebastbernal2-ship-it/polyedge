from config import KELLY_FRACTION, MAX_BET_FRACTION, BANKROLL

def calc_edge(your_prob: float, market_prob: float) -> float:
    """Raw edge = your estimate minus market price."""
    return round(your_prob - market_prob, 4)

def kelly_size(your_prob: float, market_price: float, bankroll: float) -> float:
    """
    Fractional Kelly bet sizing.
    b = net odds on a $1 bet (how much you win per $1 risked)
    f = (b*p - q) / b
    """
    b = (1 - market_price) / market_price   # payout ratio
    p = your_prob
    q = 1 - p
    f_full = (b * p - q) / b
    f_kelly = f_full * KELLY_FRACTION
    # cap at MAX_BET_FRACTION of bankroll
    return round(min(f_kelly, MAX_BET_FRACTION) * bankroll, 2)

def get_trade_signals(markets: list[dict], estimates: dict,
                      threshold: float) -> list[dict]:
    """
    Compare your probability estimates against live market prices.
    Returns markets where edge exceeds threshold.
    markets: from polymarket.get_iran_markets()
    estimates: dict of {market_id: your_probability}
    """
    signals = []
    for m in markets:
        mid = m["yes_price"]
        your_p = estimates.get(m["id"])
        if your_p is None:
            continue
        edge = calc_edge(your_p, mid)
        if abs(edge) >= threshold:
            side = "YES" if edge > 0 else "NO"
            mkt_price = mid if side == "YES" else m["no_price"]
            signals.append({
                "question":    m["question"],
                "market_prob": mid,
                "your_prob":   your_p,
                "edge":        edge,
                "side":        side,
                "bet_size":    kelly_size(your_p, mkt_price, BANKROLL),
                "volume":      m["volume"],
                "end_date":    m["end_date"],
            })
    return sorted(signals, key=lambda x: abs(x["edge"]), reverse=True)
