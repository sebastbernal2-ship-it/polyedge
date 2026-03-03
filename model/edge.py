"""
PolyEdge: Edge Calculation and Sizing Engine

Core logic:
  1. calc_edge() → your_prob - market_prob
  2. kelly_size() → fractional Kelly bet with bankroll cap
  3. get_trade_signals() → filter by edge threshold, return sorted signals

CONTEST STRATEGY:
  EDGE_THRESHOLD is the single gatekeeper. Set in config.py.
  Only trade when |edge| >= EDGE_THRESHOLD (e.g., 0.15 for 15 ppts).
  This focuses capital on high-conviction, high-edge opportunities.

WHALE INTEGRATION:
  If a whale trade aligns with your model, you can increase size (still capped by MAX_BET_FRACTION).
  If a whale trade opposes your model, reconsider or fade depending on whale credibility.
"""

from config import KELLY_FRACTION, MAX_BET_FRACTION, BANKROLL, EDGE_THRESHOLD
from model.estimator import estimate_edge, get_effective_prior, MARKET_PRIORS


def calc_edge(your_prob: float, market_prob: float) -> float:
    """
    Raw edge = your probability estimate - market probability (YES price).
    
    Interpretation:
      - edge > 0: market is underestimating YES probability (buy YES)
      - edge < 0: market is overestimating YES probability (buy NO)
      - |edge| > EDGE_THRESHOLD: consider trading
    """
    return round(your_prob - market_prob, 4)


def kelly_size(your_prob: float, market_price: float, bankroll: float) -> float:
    """
    Fractional Kelly bet sizing.
    b = net odds on a $1 bet (how much you win per $1 risked)
    f = (b*p - q) / b
    """
    b = (1 - market_price) / market_price  # payout ratio
    p = your_prob
    q = 1 - p
    f_full = (b * p - q) / b
    f_kelly = f_full * KELLY_FRACTION
    # cap at MAX_BET_FRACTION of bankroll
    return round(min(f_kelly, MAX_BET_FRACTION) * bankroll, 2)


def get_trade_signals(
    markets: list[dict],
    estimates: dict,
    threshold: float,
    use_llm: bool = True,
    use_news: bool = True,
) -> list[dict]:
    """
    Compare your probability estimates against live market prices.
    Returns markets where |edge| exceeds threshold, sorted by |edge| desc.
    For markets not in `estimates`, calls estimate_edge() with LLM/news flags.
    """
    signals = []
    for m in markets:
        mid = m["yes_price"]
        manual_p = estimates.get(m["id"])

        # Compute effective prior (slider overrides take precedence via `estimates` arg)
        effective_prior = estimates.get(m["id"]) if estimates and m.get("id") else get_effective_prior(m.get("id"))

        if manual_p is not None:
            your_p = manual_p
            reasoning = "Manual prior override"
            domain = "manual"
        else:
            result = estimate_edge(
                question=m["question"],
                market_prob=mid,
                end_date=m.get("end_date"),
                use_llm=use_llm,
                use_news=use_news,
                market_id=m.get("id"),
            )
            your_p = result["our_prob"]
            reasoning = result["reasoning"]
            domain = result["domain"]

        edge = calc_edge(your_p, mid)
        if abs(edge) >= threshold:
            side = "YES" if edge > 0 else "NO"
            mkt_price = mid if side == "YES" else m["no_price"]
            original_prior = MARKET_PRIORS.get(m.get("id"))
            signals.append({
                "question":    m["question"],
                "market_prob": mid,
                "your_prob":   your_p,
                "original_prior": original_prior,
                "effective_prior": effective_prior,
                "edge":        edge,
                "side":        side,
                "bet_size":    kelly_size(your_p, mkt_price, BANKROLL),
                "volume":      m["volume"],
                "end_date":    m["end_date"],
                "domain":      domain,
                "reasoning":   reasoning,
            })

    return sorted(signals, key=lambda x: abs(x["edge"]), reverse=True)
