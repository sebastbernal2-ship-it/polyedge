from config import LLM_API_KEY, ENABLE_LLM_ANALYSIS, KELLY_FRACTION, MAX_BET_FRACTION, BANKROLL
from model.llm_analysis import analyze_whale
from data.prior import get_prior_or_market

# Safe import of wallet_score function
try:
    from wallet_tracker import get_wallet_score
except Exception:
    def get_wallet_score(_wallet: str):
        return None


SMART_MIN_USD = 500

# minimum edge (difference between your probability and market price) required
# to justify taking a trade. expressed as decimal (e.g. 0.03 = 3 percentage points).
EDGE_THRESHOLD = 0.03  # 3 percentage points


def _vol(trades, side):
    return sum(
        float(t.get("size_usd", t.get("size", 0)))
        for t in trades
        if (t.get("outcome") or t.get("side", "")).lower() == side
        and float(t.get("size_usd", t.get("size", 0))) >= SMART_MIN_USD
    )


def _safe_kelly(your_prob, mkt_price, bankroll):
    edge = your_prob - mkt_price
    if edge <= 0 or mkt_price >= 1.0:
        return 0.0
    raw_kelly = edge / (1.0 - mkt_price)
    fractional = raw_kelly * KELLY_FRACTION
    capped = min(fractional, MAX_BET_FRACTION)
    return max(0.0, capped)


def _safe_edge(your_prob, mkt_price):
    return round(your_prob - mkt_price, 4)


def _normalize_range(val):
    if val is None:
        return None
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        try:
            return (float(val[0]), float(val[1]))
        except Exception:
            return None
    try:
        f = float(val)
        return (round(f - 0.03, 2), round(f + 0.03, 2))
    except Exception:
        return None


def _make_skip():
    return {
        "recommendation": "Skip", "direction": "Neutral", "confidence": "Low",
        "entry_range": None, "exit_range": None, "risks": "",
        "market_direction_comment": "", "prior_prob": None, "prior_source": None,
        "prior_fallback": True, "edge": 0.0, "kelly_pct": 0.0,
        "strategy_decision": "Skip", "strategy_reason": "Skipped",
        "raw": None,
    }


def analyze_market_flow(market_info, whale_trades, rules=None, bankroll=None):
    if bankroll is None:
        bankroll = BANKROLL

    if not ENABLE_LLM_ANALYSIS or not LLM_API_KEY:
        return _make_skip()
    if not whale_trades:
        return _make_skip()

    # Wallet enrichment
    for t in whale_trades:
        try:
            s = get_wallet_score(t.get("wallet", ""))
            if s:
                label = s.get("label", "Unknown")
                geo_wr = s.get("geo_win_rate")
                geo_closed = s.get("geo_closed", 0)
                overall_wr = s.get("overall_win_rate")

                # Prefer geo_win_rate if we have at least 3 closed geo trades.
                if geo_wr is not None and geo_closed >= 3:
                    wr = geo_wr
                else:
                    wr = overall_wr

                t["_wallet_label"] = label
                t["_wallet_win_rate"] = wr
            else:
                t["_wallet_label"] = "Unknown"
                t["_wallet_win_rate"] = None
        except Exception:
            t["_wallet_label"] = "Unknown"
            t["_wallet_win_rate"] = None

    sm_yes   = _vol(whale_trades, "yes")
    sm_no    = _vol(whale_trades, "no")
    sm_total = sm_yes + sm_no
    sm_pct   = (100 * sm_yes / sm_total) if sm_total > 0 else None

    q         = market_info.get("question", "") if isinstance(market_info, dict) else str(market_info)
    mkt_price = market_info.get("yes_price", 0.5) if isinstance(market_info, dict) else 0.5
    prior     = get_prior_or_market(q, mkt_price)
    pp        = prior["prob"]

    # ── Smart money signal values (set if strong signal exists) ──
    sm_rec       = None
    sm_conf      = "High"
    sm_ev        = 0.0
    sm_kv        = 0.0
    sm_comment   = ""

    # placeholders we'll set later depending on which branch is chosen
    your_prob = None
    final_prob = None
    final_side = None

    if sm_total >= 10_000 and sm_pct is not None:
        # compute market and smart‑money fractions
        yes_mkt = mkt_price
        no_mkt  = 1.0 - mkt_price
        yes_sm  = sm_pct / 100.0
        no_sm   = 1.0 - yes_sm

        # Strong smart-money thresholds: ≥75% YES or ≤25% YES.
        if sm_pct >= 75:
            # Strongly pro-YES; smart money should dominate but blend a
            # little prior and market price, staying within ±10pp of the
            # raw smart‑money rate.
            your_prob = 0.25 * pp + 0.65 * yes_sm + 0.10 * yes_mkt
            your_prob = max(min(your_prob, yes_sm + 0.10), yes_sm - 0.10)
            sm_rec = "Buy Yes"
        elif sm_pct <= 25:
            # Strongly pro-NO, mirror the logic above on the NO side.
            no_prior = 1.0 - pp
            your_no = 0.25 * no_prior + 0.65 * no_sm + 0.10 * no_mkt
            your_no = max(min(your_no, no_sm + 0.10), no_sm - 0.10)
            your_prob = 1.0 - your_no
            sm_rec = "Buy No"

        if sm_rec is not None:
            # use local helpers for edge/kelly
            sm_ev = _safe_edge(your_prob, mkt_price)
            sm_kv = _safe_kelly(your_prob, mkt_price, bankroll)
            # prepare a cleaned-up sentence fragment for inclusion later
            side = "YES" if sm_rec == "Buy Yes" else "NO"
            sm_comment = (
                f"Smart money flow is strongly skewed toward {side}; "
                f"about {sm_pct:.0f}% of ≥${SMART_MIN_USD} whale volume is on {side} "
                f"(${sm_total:,.0f} total)."
            )

    # ── News context ──────────────────────────────────────────
    news_lines = []
    try:
        from model.estimator import fetch_news
        from data.news import score_headline_relevance
        for a in (fetch_news(q) or [])[:5]:
            title = a.get("title", "")
            scr = score_headline_relevance(title, q)
            if scr > 0.1:
                news_lines.append(f"- {title} (rel={scr:.2f})")
    except Exception:
        pass

    # ── LLM on largest trade (always runs) ───────────────────
    best = max(whale_trades, key=lambda t: float(t.get("size_usd", t.get("size", 0))), default=None)
    if not best:
        return _make_skip()

    llm   = analyze_whale(market_info, best, rules)
    p_yes = llm.get("p_yes", 0.5)

    sm_signal = (sm_pct / 100.0) if sm_pct is not None else pp
    blended   = 0.4 * pp + 0.4 * p_yes + 0.2 * sm_signal

    dist = abs(blended - 0.5)
    conf = "High" if dist > 0.20 else "Medium" if dist > 0.10 else "Low"

    # Decide final recommendation. smart‑money wins if it produced a
    # strong override; otherwise fall back to blended probability.
    if sm_rec is not None:
        rec = sm_rec
        ev  = sm_ev
        kv  = sm_kv
        direction = "Bullish Yes" if sm_rec == "Buy Yes" else "Bearish Yes"
        conf = sm_conf
    else:
        if blended >= 0.60:
            rec = "Buy Yes"
            direction = "Bullish Yes"
            ev  = _safe_edge(blended, mkt_price)
            kv  = _safe_kelly(blended, mkt_price, bankroll)
        elif blended <= 0.40:
            rec = "Buy No"
            direction = "Bearish Yes"
            no_prob = 1.0 - blended
            no_mkt  = 1.0 - mkt_price
            ev  = _safe_edge(no_prob, no_mkt)
            kv  = _safe_kelly(no_prob, no_mkt, bankroll)
        else:
            rec = "Skip"
            direction = "Neutral"
            ev  = _safe_edge(blended, mkt_price)
            kv  = 0.0

    # Decide strategy based on edge and Kelly.
    if ev is None:
        strategy_decision = "Skip"
        strategy_reason = "No edge available."
    elif ev <= 0:
        strategy_decision = "Skip"
        strategy_reason = "No positive edge at current price."
    else:
        abs_edge = abs(ev)
        if abs_edge < EDGE_THRESHOLD:
            strategy_decision = "Skip"
            strategy_reason = f"Edge {ev:.1%} is too small to justify a trade."
        else:
            # Positive and above threshold.
            strategy_decision = "Trade"
            # Kelly may be zero-clamped already; just describe it.
            strategy_reason = f"Edge {ev:.1%}, Kelly {kv:.1%} – take trade with sized stake."

    # figure out the final probability and side used for the recommendation
    if rec == "Buy Yes":
        final_side = "YES"
        if your_prob is not None:
            final_prob = your_prob
        else:
            final_prob = blended
    elif rec == "Buy No":
        final_side = "NO"
        if your_prob is not None:
            final_prob = 1.0 - your_prob
        else:
            final_prob = 1.0 - blended
    else:
        final_side = None
        final_prob = None

    # combine price/prob, smart money, wallet credibility, LLM commentary and any
    # news lines into a single narrative paragraph.
    llm_comment = llm.get("edge_comment") or ""
    news_block = "\n".join(news_lines) if news_lines else ""

    comment_parts = []
    # price vs probability sentence
    if final_prob is not None and final_side is not None:
        market_pct = mkt_price if final_side == "YES" else 1.0 - mkt_price
        comment_parts.append(
            f"Estimated {final_side} probability is {final_prob:.0%}, market is {market_pct:.0%}, "
            f"so edge is {ev:+.1%} on {final_side}."
        )
    # smart money note
    if sm_comment:
        comment_parts.append(sm_comment)
    # wallet credibility (use largest trade)
    wallet_comment = ""
    if best:
        wl = best.get("_wallet_label")
        wr = best.get("_wallet_win_rate")
        if wl:
            wallet_comment = f"Top whale wallet is {wl}"
            if wr is not None:
                wallet_comment += f" with win rate ~{wr:.0%}"
            wallet_comment += "."
    if wallet_comment:
        comment_parts.append(wallet_comment)
    # LLM detail
    if llm_comment:
        comment_parts.append(llm_comment)
    # news lines
    if news_block:
        comment_parts.append(news_block)

    comment = "\n\n".join(comment_parts)

    return {
        "recommendation": rec,
        "direction": direction,
        "confidence": conf,
        "entry_range": _normalize_range(llm.get("entry")),
        "exit_range": _normalize_range(llm.get("exit")),
        "risks": llm.get("risks") or "",
        "market_direction_comment": sm_comment,
        "prior_prob": pp,
        "prior_source": prior.get("source"),
        "prior_fallback": prior.get("fallback", False),
        "edge": round(ev, 4),
        "kelly_pct": round(kv * 100, 1),
        "strategy_decision": strategy_decision,
        "strategy_reason": strategy_reason,
        "sm_pct": sm_pct,
        "blended_prob": blended,  # <── expose this for get_smart_money_signals
        "raw": {
            "whales": whale_trades,
            "llm": llm,
            "news": news_lines,
        },
    }
