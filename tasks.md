# PolyEdge Build Tasks

Status legend:
- [ ] Not started
- [/] In progress
- [x] Complete

---

## Phase 1 – Environment & Core Setup (DONE)

- [x] Project structure (`data/`, `model/`, `tracker/`, `dashboard/`, scripts)
- [x] `requirements.txt` and dependency install
- [x] Secrets configured (NewsAPI / Polymarket)
- [x] `python main.py` produces core edge signals
- [x] `streamlit run dashboard/app.py` runs without errors

---

## Phase 2 – Model, Tracker & Whale Monitor (DONE)

- [x] Bayesian estimator (`model/estimator.py`) with `MARKET_PRIORS`
- [x] Edge & Kelly sizing (`model/edge.py`) using `EDGE_THRESHOLD`
- [x] Position tracker (`tracker/positions.py`) with Brier scores
- [x] Whale monitor (`whale_monitor.py`) polling CLOB and printing LLM prompts
- [x] README and dashboard text updated for contest and whale usage

---

## Phase 3 – Contest Configuration (ALMOST DONE)

- [/] Fill real market IDs in `whale_monitor.py::TARGET_MARKETS`
- [/] Set actual `BANKROLL` and confirm `EDGE_THRESHOLD`, `KELLY_FRACTION`,
    `MAX_BET_FRACTION` in `config.py` match contest risk appetite
- [ ] Quick smoke test:
    - [ ] `python main.py` (signals ok)
    - [ ] `python whale_monitor.py` (sees at least one test whale or handles idle cleanly)

---

## Phase 4 – In-App Whale Integration (NEW)

Goal: make the whole workflow live inside the Streamlit app (no manual “paste prompt into chat”).

### 4A. Whale Event Logging

- [ ] Extend `whale_monitor.py` to:
    - [ ] Append each whale trade to `data/whales_log.json`
          (fields: timestamp, market_id, market_label, side, size_usd, price, wallet)
    - [ ] Ensure JSON append is robust and deduplicates by `(wallet, timestamp, market_id, price)`
- [ ] Add a loader helper in a new or existing module, e.g. `data/whales.py`:
    - [ ] `load_recent_whales(limit: int = 50) -> list[dict]`

### 4B. Dashboard “Recent Whales” Panel

- [ ] Modify `dashboard/app.py` to:
    - [ ] Import `load_recent_whales`
    - [ ] Add a “Recent Whales” section:
          - Table with time, market label, side, size, price, wallet (truncated)
          - Optional filter by market label
    - [ ] Auto-refresh this section when Streamlit reruns

---

## Phase 5 – LLM Analysis Module (In-App)

Goal: have the app call an LLM for whale analysis and return a structured probability.

- [ ] Add config entries in `config.py`:
    - [ ] `LLM_API_KEY` (read from env), `LLM_MODEL` / provider name, and a toggle `ENABLE_LLM_ANALYSIS`
- [ ] Create `model/llm_analysis.py`:
    - [ ] Function `analyze_whale(market_info, whale_trade, rules) -> dict` that:
          - Builds the same logical prompt as `format_llm_prompt`
          - Calls the chosen LLM API (mock or real depending on key)
          - Parses response into a dict with:
            - `p_yes: float`
            - `edge_comment: str`
            - `risks: str`
            - `entry: Optional[float]`
            - `exit: Optional[float]`
    - [ ] Graceful fallback: if no `LLM_API_KEY`, return a dummy response and warn in logs

---

## Phase 6 – Runtime Priors & Trade Sizing in the App

Goal: let the app update priors and recompute edges live when an LLM result is accepted.

- [ ] In `model/estimator.py`:
    - [ ] Add `OVERRIDE_PRIORS: Dict[str, float] = {}` (in-memory, plus optional JSON persistence)
    - [ ] Add `get_effective_prior(market_id: str) -> float`:
          - Returns `OVERRIDE_PRIORS.get(market_id, MARKET_PRIORS.get(market_id))`
    - [ ] Add helper `set_override_prior(market_id: str, p: float)` that updates dict and optionally writes to `data/priors_overrides.json`
- [ ] Update any code that uses `MARKET_PRIORS` directly in edge calculations to use `get_effective_prior` instead.

- [ ] In `dashboard/app.py`:
    - [ ] Allow selecting a market + whale row and clicking “Run LLM analysis”
    - [ ] Display returned `p_yes`, comments, risks, entry/exit from `analyze_whale`
    - [ ] Provide a button “Apply as new prior” that calls `set_override_prior` and triggers recomputation of edges/bet sizes
    - [ ] Display both original prior and current effective prior in the main signals table

---

## Phase 7 – Final Contest Playbook & Polish

- [ ] Add `docs/CONTEST_PLAYBOOK.md` or expand `README.md` to describe:
    - [ ] How to use:
          - Core signals
          - Recent whales
          - LLM analysis
          - Prior overrides
    - [ ] Trade rule: only act when `edge ≥ EDGE_THRESHOLD` and liquidity is reasonable
    - [ ] How percentage-return focus affects number of positions and bet size

- [ ] Final end-to-end test:
    - [ ] Start Streamlit dashboard
    - [ ] Start whale monitor
    - [ ] Simulate at least one whale event and run LLM analysis in-app
    - [ ] Confirm priors update, edges change, and recommended bet size adjusts

