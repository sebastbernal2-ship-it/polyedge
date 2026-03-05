from typing import List, Dict, Any
from config import EDGE_THRESHOLD, KELLY_FRACTION, MAX_BET_FRACTION, BANKROLL
from .estimator import estimate_edge_generic


def safe_kelly(your_prob: float, market_price: float, bankroll: float) -> float:
    """
    Kelly bet fraction for a YES position, capped and safe-guarded.
    your_prob, market_price are in [0,1].
    """
    edge = your_prob - market_price
    if edge <= 0 or market_price <= 0 or market_price >= 1:
        return 0.0
    b = (1.0 - market_price) / market_price  # payout ratio
    raw = edge / b
    frac = raw * KELLY_FRACTION
    frac = max(0.0, min(frac, MAX_BET_FRACTION))
    return frac


def get_trade_signals(
    markets: List[Dict[str, Any]],
    override_priors,
    edge_threshold: float = EDGE_THRESHOLD,
    use_llm: bool = False,
    use_news: bool = False,
) -> List[Dict[str, Any]]:
    """
    Build trade signals for a list of markets using the generic estimator.

    Each signal dict contains at least:
    - question
    - side ("Buy Yes"/"Buy No")
    - market_prob (float)
    - your_prob (float)
    - edge (float)
    - kelly_pct (float, percent of bankroll)
    - bet_size (float, dollars)
    """
    signals: List[Dict[str, Any]] = []

    for m in markets:
        try:
            question = m.get("question") or m.get("title") or m.get("name")
            if not question:
                continue

            # Market implied YES probability
            market_prob = m.get("yes_price") or m.get("probability")
            if market_prob is None:
                continue
            try:
                market_prob = float(market_prob)
            except Exception:
                continue
            if not (0.0 < market_prob < 1.0):
                continue

            # Ask generic estimator for our view
            est = estimate_edge_generic(
                market_info=m,
                market_prob=market_prob,
                override_priors=override_priors,
                use_llm=use_llm,
                use_news=use_news,
            )
            our_prob = est.get("our_prob")
            edge = est.get("edge")

            if our_prob is None or edge is None:
                continue
            try:
                our_prob = float(our_prob)
                edge = float(edge)
            except Exception:
                continue

            # Require a minimum edge
            if abs(edge) < edge_threshold:
                continue

            # Direction and Kelly
            side = "Buy Yes" if edge > 0 else "Buy No"
            effective_prob = our_prob if edge > 0 else (1.0 - our_prob)
            effective_price = market_prob if edge > 0 else (1.0 - market_prob)
            kelly_frac = safe_kelly(effective_prob, effective_price, BANKROLL)
            bet_size = BANKROLL * kelly_frac
            kelly_pct = kelly_frac * 100.0

            signals.append(
                {
                    "question": question,
                    "side": side,
                    "market_prob": market_prob,
                    "your_prob": our_prob,
                    "edge": edge,
                    "kelly_pct": kelly_pct,
                    "bet_size": bet_size,
                    "raw": est,
                }
            )
        except Exception:
            # Skip any market that blows up
            continue

    return signals


def get_smart_money_signals(
    markets: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:


    import json
    import os
    from model.market_flow import analyze_market_flow
    from config import BANKROLL

    WHALE_LOG_PATH = os.path.join("data", "whales_log.json")

    def _load_whales_from_file(path: str = WHALE_LOG_PATH):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            return []


    try:
        whale_trades_all = _load_whales_from_file()
    except Exception:
        whale_trades_all = []

    signals: List[Dict[str, Any]] = []

    for m in markets:
        question = m.get("question") or m.get("title") or m.get("name")
        if not question:
            continue

        market_prob = m.get("yes_price") or m.get("probability")
        try:
            market_prob = float(market_prob)
        except Exception:
            continue
        if not (0.0 < market_prob < 1.0):
            continue

        mid = m.get("id") or m.get("conditionId") or m.get("market_id")
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
        edge = float(res.get("edge") or 0.0)
        kelly_pct = float(res.get("kelly_pct") or 0.0)
        sm_pct = res.get("sm_pct")
        if sm_pct is not None:
            sm_pct = float(sm_pct)

        signals.append(
            {
                "question": question,
                "side": side,
                "market_prob": market_prob,
                "your_prob": res.get("prior_prob"),  # or blended prob if you have it
                "edge": edge,
                "kelly_pct": kelly_pct,
                "bet_size": BANKROLL * (kelly_pct / 100.0),
                "sm_pct": sm_pct,
                "raw": res,
            }
        )

    return signals
