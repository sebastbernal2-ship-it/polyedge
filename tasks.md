# PolyEdge — Build Tasks

This file is the source of truth for what has been built, what is in progress,
and what is next. Update status as each task is completed.

---

## Status Legend
- [ ] Not started
- [~] In progress
- [x] Complete

---

## Phase 1 — Project Setup
- [x] Create project folder structure (`data/`, `model/`, `tracker/`, `dashboard/`)
- [x] Create and populate `requirements.txt`
- [x] Create `.env` file with `NEWS_API_KEY` and `POLYMARKET_PRIVATE_KEY`
- [x] Create `config.py` with constants (domains, thresholds, bankroll, Kelly fraction)
- [ ] Set up and activate Python virtual environment
- [ ] Run `pip install -r requirements.txt` successfully

---

## Phase 2 — Data Layer
- [ ] `data/polymarket.py` — `get_iran_markets()` pulls active Iran markets from Gamma API
- [ ] `data/polymarket.py` — `get_price_history()` pulls CLOB price history per token
- [ ] `data/news.py` — `get_latest_headlines()` pulls headlines per domain keyword via NewsAPI
- [ ] Verify Gamma API returns live markets with correct yes/no prices
- [ ] Verify NewsAPI returns fresh articles for Iran/ceasefire/Hormuz/regime keywords

---

## Phase 3 — Model Layer
- [ ] `model/estimator.py` — `bayes_update()` single prior + likelihood ratio → posterior
- [ ] `model/estimator.py` — `estimate_from_signals()` chains multiple updates together
- [ ] `model/estimator.py` — `MARKET_PRIORS` dict populated with current Iran market priors
- [ ] `model/edge.py` — `calc_edge()` computes your probability minus market price
- [ ] `model/edge.py` — `kelly_size()` computes fractional Kelly bet size in dollars
- [ ] `model/edge.py` — `get_trade_signals()` compares all markets against your priors, filters by threshold, returns ranked signals

---

## Phase 4 — Position Tracker
- [ ] `tracker/positions.py` — `log_trade()` writes a new trade entry to `positions_log.json`
- [ ] `tracker/positions.py` — `resolve_trade()` marks outcome and computes Brier score
- [ ] `tracker/positions.py` — `get_calibration_summary()` returns avg Brier and trade count
- [ ] Manually log the 3 current trade ideas (Hormuz YES, Ceasefire NO, Regime fall YES)
- [ ] Confirm `positions_log.json` is writing and reading correctly

---

## Phase 5 — Dashboard
- [ ] `dashboard/app.py` — Live edge signals table (question, side, market prob, your prob, edge %, bet size)
- [ ] `dashboard/app.py` — Latest news feed panel (title, source, date, url)
- [ ] `dashboard/app.py` — Calibration metrics panel (trade count, avg Brier score)
- [ ] Run `streamlit run dashboard/app.py` without errors
- [ ] Confirm all three panels populate with live data

---

## Phase 6 — Entry Point
- [ ] `main.py` — loads `.env`, runs market fetch, runs edge scan, prints signals to terminal
- [ ] `main.py` — prints latest news headlines
- [ ] Run `python main.py` end to end without errors

---

## Phase 7 — Refinements (after MVP is running)
- [ ] Add `data/polymarket.py` — price history chart per market in dashboard
- [ ] Add `model/estimator.py` — auto-parse news headlines into likelihood ratios using keyword rules
- [ ] Add `tracker/positions.py` — ROI tracker (total bankroll over time)
- [ ] Add `dashboard/app.py` — manual prior override sliders per market
- [ ] Add `dashboard/app.py` — auto-refresh every N minutes
- [ ] Add alert system — print or notify when a new edge above threshold appears
- [ ] Expand beyond Iran — add `DOMAINS` tags for crypto and macro markets

---

## Current Priors (update as news comes in)

| Market | Your Estimate | Market Price | Edge | Side | Bet |
|--------|--------------|-------------|------|------|-----|
| US x Iran ceasefire by March 31 | 20% | 44% | +23pts NO | NO | $4 |
| Iran closes Hormuz by March 31 | 75% | 60% | +15pts YES | YES | $4 |
| Iranian regime fall by March 31 | 27% | 16% | +11pts YES | YES | $2 |

---

## Notes
- Polymarket Gamma API is fully public, no auth needed for market data
- CLOB API needs wallet private key only for placing orders, not reading prices
- NewsAPI free tier = 100 requests/day, enough for hourly scans
- `MARKET_PRIORS` in `model/estimator.py` must be updated manually when significant news breaks
- Brier score: 0 = perfect, 0.25 = random guessing, lower is better
