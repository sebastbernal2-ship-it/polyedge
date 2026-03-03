from config import EDGE_THRESHOLD, BANKROLL
from tracker.positions import get_calibration_summary, log_trade, _load, resolve_trade
from model.estimator import auto_update_priors, DOMAIN_PRIORS, explain_updates
from model.edge import get_trade_signals
from data.news import get_latest_headlines
from data.polymarket import get_iran_markets, get_price_history
from streamlit_autorefresh import st_autorefresh
import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
import sys
import os
sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
             '..')))

load_dotenv()


st.set_page_config(page_title="PolyEdge", layout="wide")
st.title("PolyEdge — Iran Signal Dashboard")

# ── Auto-refresh ──────────────────────────────────────────────
refresh_interval = st.sidebar.selectbox(
    "Auto-refresh interval (minutes)", [0, 1, 5, 10, 30], index=3
)
if refresh_interval > 0:
    st_autorefresh(interval=refresh_interval * 60 * 1000, key="autorefresh")

# ── Fetch news first so auto-priors can use it ────────────────
with st.spinner("Fetching news..."):
    articles = get_latest_headlines()

# ── Auto-update priors from news ──────────────────────────────
auto_priors = auto_update_priors(articles, DOMAIN_PRIORS)

# — Signal controls ————————————————————
st.sidebar.header("Signal Controls")
use_llm = st.sidebar.checkbox("Use LLM Scoring (Navigator/Llama)", value=True)
use_news = st.sidebar.checkbox("Use News Signals (NewsAPI)", value=True)
pre_deadline_only = st.sidebar.checkbox(
    "Only pre-March 16, 2026 markets", value=True)
st.sidebar.markdown("---")

# ── Manual prior overrides on top of auto values ─────────────
st.sidebar.header("Adjust Your Priors")
prior_labels = {
    "0x3c3c46ea0d48ea0e3049ee04bdfe1e4e9071721ec9146d492cd16c657df9ab92": "Iran/Hezbollah strike Cyprus by Mar 7",
    "0x7c3f9482e5c8d1c00ad849581324b5e224f5e960476f535453e04c1f55d4ea49": "Gulf State strikes Iran by Mar 7",
    "0x65c08331b9d3fe9c2142f15389960fff5f5e70f8230026170337ed257cbde9b5": "US seizes Iran tanker by Mar 7",
    "0x74686395e62a73a6b59cf1a6f2132af745224b5c8cf0d5ee053e4c59c7930d81": "US seizes another tanker by Mar 7",
    "0xed8049df11e16381d806ccb24226585bf2d314fcebe7c9cd723d6a073622fb30": "War powers resolution by Mar 13",
}

override_priors = {}
for market_id, label in prior_labels.items():
    auto_val = auto_priors.get(market_id, 0.5)
    override_priors[market_id] = st.sidebar.slider(
        f"{label} (auto: {auto_val:.0%})",
        0.0, 1.0, float(auto_val), 0.01
    )

# ── Live markets ──────────────────────────────────────────────
st.header("Live Edge Signals")
with st.spinner("Fetching markets..."):
    markets = get_iran_markets()
    if pre_deadline_only:
        deadline = datetime.date(2026, 3, 16)
        markets = [m for m in markets if m.get("end_date") and
                   str(m["end_date"])[:10] <= str(deadline)]
        st.caption(f"{len(markets)} markets resolve before March 16")

    signals = get_trade_signals(markets, override_priors, EDGE_THRESHOLD, use_llm=use_llm, use_news=use_news)

if signals:
    df = pd.DataFrame(signals)
    df["edge_%"]        = (df["edge"] * 100).round(1)
    df["market_prob_%"] = (df["market_prob"] * 100).round(1)
    df["your_prob_%"]   = (df["your_prob"] * 100).round(1)
    df["volume_$"]      = df["volume"].apply(lambda x: f"${x:,.0f}")
    st.dataframe(
        df[["question","side","market_prob_%","your_prob_%",
            "edge_%","bet_size","volume_$","end_date","domain","reasoning"]],
        width="stretch"
    )

    # ── Log trade button ──────────────────────────────────────
    st.subheader("Log a Trade")
    selected = st.selectbox("Select signal to log", [s["question"] for s in signals])
    if st.button("Log this trade"):
        match = next(s for s in signals if s["question"] == selected)
        mkt   = next(m for m in markets if m["question"] == selected)
        log_trade(
            market_id=mkt["id"],
            question=match["question"],
            side=match["side"],
            price=match["market_prob"],
            size=match["bet_size"],
            your_prob=match["your_prob"]
        )
        st.success(f"Logged: {match['side']} {match['question']} @ {match['market_prob']:.0%}")
else:
    st.info("No edges above threshold right now.")

# ── Price history chart ───────────────────────────────────────
st.header("Price History")
if signals:
    chart_market = st.selectbox("Select market to chart", [s["question"] for s in signals])
    match_mkt    = next(m for m in markets if m["question"] == chart_market)
    token_ids    = match_mkt.get("token_ids", [])
    if token_ids:
        with st.spinner("Loading price history..."):
            history = get_price_history(token_ids[0])
        if history:
            hist_df = pd.DataFrame(history)
            hist_df["t"] = pd.to_datetime(hist_df["t"], unit="s")
            hist_df = hist_df.rename(columns={"t": "time", "p": "YES price"})
            st.line_chart(hist_df.set_index("time")["YES price"])
        else:
            st.info("No price history available for this market.")
    else:
        st.info("No token ID for this market.")

# ── Probability audit trail ───────────────────────────────────
st.header("How Were These Probabilities Calculated?")
audit = explain_updates(articles, DOMAIN_PRIORS)
for market_id, result in audit.items():
    with st.expander(f"{result['label']} — final estimate: {result['final_prob']:.0%}"):
        steps_df = pd.DataFrame(result["steps"])
        st.dataframe(steps_df, width="stretch")

# ── News feed ─────────────────────────────────────────────────
st.header("Latest News Signals")
NOISE_KEYWORDS = ["cricket", "lunar", "eclipse", "bollywood", "recipe",
                  "grahan", "paint stock", "gold silver", "zipline"]
filtered = [
    a for a in articles
    if not any(nk in a["title"].lower() for nk in NOISE_KEYWORDS)
]
for a in filtered[:20]:
    st.markdown(
        f"**[{a['title']}]({a['url']})** — *{a['source']}* ({a['published'][:10]})"
    )

# ── Calibration ───────────────────────────────────────────────
st.header("Your Calibration")
cal  = get_calibration_summary()
col1, col2 = st.columns(2)
col1.metric("Resolved Trades", cal["trades"])
if cal["trades"] > 0:
    col2.metric(
        "Avg Brier Score", cal["avg_brier"],
        help="Lower = better. Perfect = 0, Random = 0.25"
    )

# ── Resolve a trade ───────────────────────────────────────────
st.subheader("Resolve a Trade")
open_trades = [e for e in _load() if e["outcome"] is None]
if open_trades:
    resolve_q = st.selectbox(
        "Select trade to resolve",
        [f"{e['question']} ({e['side']})" for e in open_trades]
    )
    outcome = st.radio("Outcome", ["YES won", "NO won"])
    if st.button("Submit resolution"):
        match = next(
            e for e in open_trades
            if f"{e['question']} ({e['side']})" == resolve_q
        )
        resolved = outcome == "YES won"
        resolve_trade(match["market_id"], resolved)
        st.success("Trade resolved and Brier score recorded.")
else:
    st.info("No open trades to resolve yet.")
