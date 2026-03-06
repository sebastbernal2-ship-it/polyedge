import os
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
import datetime
import json

from config import EDGE_THRESHOLD, BANKROLL
from data.polymarket import fetch_candidate_markets
from model.edge import get_smart_money_signals


st.set_page_config(
    page_title="PolyEdge",
    page_icon="📈",
    layout="wide",
)


def format_signal_label(sig: Dict[str, Any]) -> str:
    """
    Label for the selectbox:
    Question | side | SM% | edge% | Kelly% | bet$
    """
    edge_pct = sig.get("edge", 0.0) * 100.0
    kelly_pct = sig.get("kelly_pct", 0.0)
    bet = sig.get("bet_size", 0.0)
    side = sig.get("side", "Buy Yes")
    q = sig.get("question", "")[:120]
    sm_pct = sig.get("sm_pct")
    if sm_pct is None:
        sm_str = "SM n/a"
    else:
        sm_str = f"SM {sm_pct:.1f}%"
    return f"{q} | {side} | {sm_str} | edge {edge_pct:+.1f}% | Kelly {kelly_pct:.1f}% | ${bet:.2f}"


def is_politics_market(m: Dict[str, Any]) -> bool:
    """
    Simple politics filter: checks category/tags or question text.
    """
    cat = (m.get("category") or "").lower()
    tags = " ".join(m.get("tags") or []).lower()
    q = (m.get("question") or m.get("title") or m.get("name") or "").lower()

    politics_keywords = [
        "election",
        "president",
        "senate",
        "house seat",
        "governor",
        "parliament",
        "congress",
        "democrat",
        "republican",
        "labour",
        "tory",
        "prime minister",
        "mp ",
        "mp?",
        "mp,",
        "mp.",
    ]

    text = " ".join([cat, tags, q])
    return any(k in text for k in politics_keywords)


def main() -> None:
    st.title("PolyEdge – Smart Money Signal Dashboard")

    # Sidebar controls
    st.sidebar.header("Controls")

    use_llm = st.sidebar.checkbox("Use LLM features", value=False)
    use_news = st.sidebar.checkbox("Use news features", value=False)

    # Smart Money slider (0–100%)
    min_sm_pct = st.sidebar.slider(
        "Minimum Smart Money % (SM%)",
        min_value=0.0,
        max_value=100.0,
        value=0.0,
        step=5.0,
        help="Only show markets where Smart Money is at least this % on the recommended side.",
    )

    # Edge threshold slider (in percent)
    edge_threshold_pct = st.sidebar.slider(
        "Minimum edge (%)",
        min_value=0.0,
        max_value=30.0,
        value=0.0,
        step=1.0,
        help="Only show trades where |our_prob - market_prob| is at least this many percentage points.",
    )
    edge_threshold = edge_threshold_pct / 100.0

    # Minimum Kelly slider (in percent of bankroll)
    min_kelly_pct = st.sidebar.slider(
        "Minimum Kelly (%)",
        min_value=0.0,
        max_value=20.0,
        value=0.0,
        step=0.5,
        help="Only show trades where Kelly recommends at least this % of bankroll.",
    )

    politics_only = st.sidebar.checkbox(
        "Politics only",
        value=False,
        help="If checked, only show markets that look like politics.",
    )

    st.sidebar.markdown(f"**Bankroll**: ${BANKROLL:,.2f}")

    st.write(
        "This dashboard shows model-driven trading signals over Polymarket markets, "
        "ranked by Smart Money concentration, Kelly sizing, and edge."
    )

    # Fetch markets
    st.subheader("Candidate markets")
    try:
        markets: List[Dict[str, Any]] = fetch_candidate_markets()
    except Exception as e:
        st.error(f"Failed to fetch markets: {e}")
        return

    st.caption(f"Fetched {len(markets)} raw markets from Polymarket.")

    # Optional politics filter before signal estimation
    if politics_only:
        markets = [m for m in markets if is_politics_market(m)]
        st.caption(f"After politics filter: {len(markets)} markets.")

    # Build signals
    st.subheader("Smart Money trade signals")

    override_priors: Dict[str, float] = {}

    with st.spinner("Computing smart-money signals..."):
        try:
            signals = get_smart_money_signals(markets=markets)
        except Exception as e:
            st.error(f"Error computing trade signals: {e}")
            return

    # Normalize sm_pct if present
    for s in signals:
        sm = s.get("sm_pct")
        if sm is not None:
            try:
                s["sm_pct"] = float(sm)
            except Exception:
                s["sm_pct"] = None

    # Apply user filters (SM%, edge, Kelly) on top of ranking
    filtered = []
    for s in signals:
        edge = abs(s.get("edge", 0.0))
        kelly = s.get("kelly_pct", 0.0) or 0.0
        sm_pct = s.get("sm_pct")

        if edge < edge_threshold:
            continue
        if kelly < min_kelly_pct:
            continue
        if min_sm_pct > 0.0:
            # if we require SM%, skip entries with no smart-money info
            if sm_pct is None or sm_pct < min_sm_pct:
                continue

        filtered.append(s)

    if not filtered:
        st.info(
            "No signals found at these Smart Money / edge / Kelly settings. "
            "Try lowering one or more sliders."
        )
        return

    st.caption(
        f"Found {len(filtered)} signals with SM% ≥ {min_sm_pct:.1f}%, "
        f"|edge| ≥ {edge_threshold_pct:.1f}% and Kelly ≥ {min_kelly_pct:.1f}% "
        f"(bankroll = ${BANKROLL:,.2f})."
    )

    # Sort: Smart Money %, then Kelly, then |edge|
    def sort_key(s: Dict[str, Any]):
        sm = s.get("sm_pct")
        sm_rank = sm if sm is not None else -1.0
        return (-sm_rank, -(s.get("kelly_pct", 0.0) or 0.0), -abs(s.get("edge", 0.0)))

    signals_sorted = sorted(filtered, key=sort_key)

    # Build lookup from market id -> signal (for edge in events table)
    signal_by_id: Dict[str, Dict[str, Any]] = {}
    for s in signals_sorted:
        m_id = str(s.get("id") or s.get("market_id") or "")
        if not m_id:
            continue
        signal_by_id[m_id] = s

    # Table preview
    st.markdown("### Ranked Smart Money signals")
    table_rows = []
    for s in signals_sorted[:50]:
        table_rows.append(
            {
                "Question": (s.get("question") or "")[:80],
                "Side": s.get("side"),
                "SM%": s.get("sm_pct"),
                "Edge%": (s.get("edge", 0.0) or 0.0) * 100.0,
                "Kelly%": s.get("kelly_pct", 0.0) or 0.0,
                "Bet $": s.get("bet_size", 0.0) or 0.0,
            }
        )
    st.dataframe(table_rows, use_container_width=True)

    # Select a signal
    st.markdown("### Inspect / log a specific trade")
    labels = [format_signal_label(s) for s in signals_sorted]
    idx = st.selectbox(
        "Select a trade",
        options=range(len(signals_sorted)),
        format_func=lambda i: labels[i],
    )
    sig = signals_sorted[idx]

    # Display details
    st.markdown("#### Signal details")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Side", sig["side"])
        st.metric("Market prob (YES)", f"{sig['market_prob']:.3f}")
    with col2:
        st.metric("Your prob (YES)", f"{sig['your_prob']:.3f}")
        st.metric("Edge (ppts)", f"{(sig['edge'] * 100.0):+.2f}")
    with col3:
        st.metric("Kelly (%)", f"{sig['kelly_pct']:.2f}")
        st.metric("Bet size ($)", f"{sig['bet_size']:.2f}")

    st.write("**Question**")
    st.write(sig["question"])

    sm_pct = sig.get("sm_pct")
    if sm_pct is not None:
        st.caption(f"Smart Money on recommended side: {sm_pct:.1f}%")

    with st.expander("Raw estimator output"):
        st.json(sig.get("raw", {}))

    # Log trade section
    st.markdown("#### Log this trade")
    with st.form("log_trade_form"):
        size_filled = st.number_input(
            "Size filled ($)",
            min_value=0.0,
            value=float(f"{sig['bet_size']:.2f}"),
            step=0.5,
        )
        price_filled = st.number_input(
            "Average fill price (YES prob)",
            min_value=0.0,
            max_value=1.0,
            value=float(f"{sig['market_prob']:.3f}"),
            step=0.01,
        )
        note = st.text_input("Notes (optional)", "")
        submitted = st.form_submit_button("Log trade")
        if submitted:
            st.success(
                f"Logged trade: {sig['side']} on '{sig['question']}' "
                f"for ${size_filled:.2f} at {price_filled:.3f}."
            )

    # =================== EVENT / WHALE BROWSERS ===================

    st.markdown("---")
    st.header("All Events (≥ low USD floor)")

    event_path = os.path.join("data", "events_log.json")
    scores_path = os.path.join("data", "wallet_scores.json")

    if not (os.path.exists(event_path) and os.path.exists(scores_path)):
        st.info("Run whale_monitor.py and wallet_tracker.py to populate events and Smart Money data.")
    else:
        with open(event_path) as f:
            events = json.load(f)
        with open(scores_path) as f:
            scores = {s["wallet"]: s for s in json.load(f)}

        rows = []
        for t in events:
            w = t.get("wallet")
            s = scores.get(w, {})

            m_id = str(t.get("market_id", ""))
            q_label = t.get("market_label", "")

            sig_for_event = signal_by_id.get(m_id, {})

            rows.append({
                "time": datetime.datetime.fromtimestamp(t.get("timestamp", 0)),
                "market": q_label,
                "wallet": w,
                "size_usd": float(t.get("size_usd", 0)),
                "side": t.get("outcome", t.get("side", "")),
                "price": float(t.get("price", 0)),
                "edge": float(sig_for_event.get("edge", 0.0)) * 100.0,
                "kelly_pct": sig_for_event.get("kelly_pct", 0.0) or 0.0,
                "sm_label": s.get("label", "Unknown"),
                "geo_wr": s.get("geo_winrate", s.get("overall_winrate", 0.0)),
                "geo_trades": s.get("geo_closed", s.get("overall_closed", 0)),
            })

        df_all = pd.DataFrame(rows)
        st.dataframe(df_all, use_container_width=True)
        st.caption("Click column headers (↑/↓) to sort by size, edge, Kelly, Smart Money label, etc.")

    st.header("Whale Events (≥ whale USD floor)")

    whale_path = os.path.join("data", "whales_log.json")

    if not os.path.exists(whale_path):
        st.info("No whale events logged yet.")
    else:
        with open(whale_path) as f:
            whales = json.load(f)

        df_whales = pd.DataFrame(whales)
        st.dataframe(df_whales, use_container_width=True)


if __name__ == "__main__":
    main()
