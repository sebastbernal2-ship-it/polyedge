# polyedge

A prediction-market trading system for Polymarket that combines:
- **PolyEdge Core:** Bayesian probability estimation + edge-based position sizing (Kelly-fractional)
- **Whale Monitor:** Tracks large trades on target markets and generates LLM prompts for deeper analysis

---

## Quick Start

### 1. Set up

```bash
pip install -r requirements.txt
```

Set environment variables in `.env`:
```
NEWS_API_KEY=<your newsapi key>
NAVIGATOR_KEY=<optional, for LLM scoring>
TELEGRAM_BOT_TOKEN=<optional>
TELEGRAM_CHAT_ID=<optional>
```

### 2. Configure for your contest

Edit `config.py`:
- Set `BANKROLL` to your actual contest bankroll
- Confirm `EDGE_THRESHOLD = 0.15` (only trade edge ≥ 15 ppts)
- Adjust `KELLY_FRACTION` and `MAX_BET_FRACTION` for your risk tolerance

### 3. Run core signals

```bash
python main.py
```

Displays terminal output of high-edge trades based on your probability estimates.

### 4. Run the dashboard

```bash
streamlit run dashboard/app.py
```

Live edge table, news feed, calibration metrics, and whale integration guide.

### 5. Run whale monitor (separate terminal)

```bash
python whale_monitor.py
```

Polls CLOB API every 30 seconds for large trades in target Iran markets.

---

## Whale Monitor Setup

The whale monitor is **disabled by default** because it requires real market IDs.

### Fill in target market IDs

Edit `whale_monitor.py` → `TARGET_MARKETS` dict:

```python
TARGET_MARKETS = {
    "Iran ceasefire by Mar 7": "0xABC123...",  # Replace with real condition ID
    "US strikes Iran by Mar 7": "0xDEF456...",
    "Fordow strike": "0x789GHI...",
    "Iranian regime fall": "0xJKL012...",
}
```

Find condition IDs at:
- [Polymarket.com](https://polymarket.com) (URL bar or CLOB API)
- Or use the Gamma API: `https://gamma-api.polymarket.com/markets`

### Run and analyze whale trades

When you run `python whale_monitor.py`, it will:
1. Check all target markets for recent large trades (≥ $10k USD)
2. Print a one-line alert + a structured LLM prompt
3. (Optional) Send Telegram notification if `TELEGRAM_BOT_TOKEN` is set

Example alert:
```
🐋 WHALE: Iran ceasefire by Mar 7 | NO @ 35% | $15,000 | 2026-03-03T...

=== POLYMARKET WHALE TRADE ALERT ===

[TRADE INFO]
Market: Iran ceasefire by Mar 7
Question: Will Iran agree to a ceasefire with the US by March 7?
Whale Side: No
Price: 35.0%
USD Volume: $15,000
...

[YOUR TASK]
An informed trader (whale) just placed a $15,000 USD bet on No at 35%. 
Analyze whether this is high-edge for a 1-3 day swing trade.

1. Re-state the resolution conditions for YES and NO clearly.
...
```

### Integrate with PolyEdge

1. Copy the full LLM prompt into ChatGPT/Claude/Perplexity
2. Paste your question: *"Based on this whale trade, what's your probability estimate?"*
3. LLM returns a probability (e.g., 0.42 for "No" side)
4. Update `MARKET_PRIORS` in `model/estimator.py`:
   ```python
   MARKET_PRIORS["0xABC123..."] = 0.42  # Updated from whale analysis
   ```
5. Refresh the dashboard (or re-run `python main.py`)
6. New edge signals will reflect your updated probability

**Trading Philosophy:**
- PolyEdge is the gatekeeper: only trade when edge ≥ 15 percentage points
- Whales are a *confirming signal*:
  - Whale aligned with your signal → consider sizing slightly larger
  - Whale opposite your signal → re-examine or fade based on credibility
- Contest is 14 days, ranked by percentage return → concentrate on fewer, higher-edge trades

---

## PolyEdge Core Architecture

### `model/estimator.py`

Probability estimation using:
- Domain-based prior (e.g., "ceasefire" → 35% base rate)
- News sentiment from NewsAPI + keyword analysis
- (Optional) LLM scoring via Navigator API

Outputs: Bayesian updated probability + reasoning

### `model/edge.py`

Edge calculation:
$$\text{edge} = \text{your\_prob} - \text{market\_prob}$$

Kelly-fractional sizing:
$$\text{size} = \min\left(\text{quarter Kelly}, \text{MAX\_BET\_FRACTION} \times \text{BANKROLL}\right)$$

### `tracker/positions.py`

Log trades with your probability estimate, resolve when market settles, compute Brier scores for calibration.

### `data/`

- `polymarket.py`: Fetch Iran markets from Gamma API
- `news.py`: NewsAPI headlines for keyword/sentiment analysis

### `dashboard/app.py`

Streamlit UI with:
- Live edge signals sorted by |edge|
- Manual prior overrides
- Price history charts
- News feed
- Calibration (Brier score, resolved count)
- Whale integration guide

---

## Configuration (config.py)

```python
EDGE_THRESHOLD = 0.15       # Only trade edge ≥ 15 ppts
KELLY_FRACTION = 0.25       # Use 1/4 Kelly for safety
MAX_BET_FRACTION = 0.40     # Never bet > 40% of bankroll per trade
BANKROLL = 100.0            # Set to your actual contest bankroll
DOMAINS = [...]             # Keywords for news filtering
```

All configurable for your risk tolerance and bankroll.

---

## Contest Strategy (14-Day Polymarket)

1. **Concentrate on high-edge trades** (edge ≥ 15 ppts) rather than many small bets
2. **Monitor whale trades** for confirmation and hidden information
3. **Log and resolve trades** promptly to track calibration (Brier scores)
4. **Re-calibrate priors** as new market data and whale insights arrive
5. **Focus on percentage return**, not absolute PnL — your ranking depends on % gain

---

## Key Files

- `main.py` – Core signal loop (terminal output)
- `whale_monitor.py` – CLOB API poller for large trades (PRE-CONTEST: fill in market IDs)
- `config.py` – Bankroll, edge threshold, Kelly sizing
- `dashboard/app.py` – Streamlit dashboard (run in browser)
- `model/estimator.py` – Probability estimation + LLM scoring
- `model/edge.py` – Edge and Kelly sizing logic
- `tracker/positions.py` – Trade log and Brier score calibration
- `data/polymarket.py` – Gamma API client
- `data/news.py` – NewsAPI and Gemini sentiment
