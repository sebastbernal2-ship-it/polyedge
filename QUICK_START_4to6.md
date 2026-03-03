# PolyEdge Phases 4–6: Quick Start

## What Changed?

✅ **Whale trades are now logged** to `data/whales_log.json` automatically.
✅ **Dashboard shows Recent Whales** panel with all logged trades.
✅ **In-app LLM analysis** – select a whale and get instant probability/edge analysis.
✅ **One-click prior override** – apply LLM results directly; dashboard recalculates edges.
✅ **Persistent overrides** saved to `data/priors_overrides.json`.

---

## Run the System End-to-End

### Terminal 1: Dashboard
```bash
streamlit run dashboard/app.py
```

Visits http://localhost:8501 automatically (or manual visit).
Shows edge signals and recent whales panel.

### Terminal 2: Whale Monitor
```bash
python whale_monitor.py
```

Polls Polymarket CLOB every 30 seconds.
Prints whale alerts to console.
Auto-appends trades to `data/whales_log.json`.

---

## Using LLM Whale Analysis

1. **Set LLM API Key** (required for in-app LLM):
   ```bash
   export LLM_API_KEY="sk-..."  # OpenAI key or compatible provider
   export LLM_PROVIDER="openai"
   export LLM_MODEL="gpt-4o-mini"
   ```

2. **In Dashboard:**
   - Scroll to **"Recent Whales"** section.
   - Select a whale from the dropdown.
   - Click **"Run LLM analysis on selected whale"**.
   - Review: probability, edge comment, risks, entry, exit.

3. **Apply Override:**
   - Click **"Apply as new prior"**.
   - Dashboard reruns instantly.
   - **Live Edge Signals** table updates with new effective priors.

---

## How Prior Overrides Work

```
Whale Trade Detected
    → LLM analyzes → p_yes = 0.62
    → You click "Apply as new prior"
    → Saved to data/priors_overrides.json
    → get_effective_prior(market_id) returns 0.62 (not domain prior)
    → Edge recalculated with 0.62 instead of old prior
    → Bet sizes updated in Live Edge Signals
```

**Persistence:** Overrides survive app restarts (loaded from JSON on startup).

---

## Key Files

| File | Purpose |
|------|---------|
| `data/whales.py` | Whale log manager (append, load recent) |
| `model/llm_analysis.py` | LLM whale analysis engine |
| `model/estimator.py` | Now has override priors + `get_effective_prior()` |
| `dashboard/app.py` | New "Recent Whales" panel + LLM UI |
| `whale_monitor.py` | Now appends to whale log automatically |
| `config.py` | New LLM config (API_KEY, PROVIDER, MODEL) |

---

## Environment Variables

```bash
# LLM Analysis (optional, but needed for whale analysis in dashboard)
export LLM_API_KEY="your-openai-key"
export LLM_PROVIDER="openai"
export LLM_MODEL="gpt-4o-mini"

# Optional: for News & Navigator scoring
export NEWSAPI_KEY="..."
export NAVIGATOR_KEY="..."

# Optional: for Telegram alerts
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
```

---

## Workflow Comparison

### Before (Phases 1–3)
1. Run whale monitor → copy LLM prompt to ChatGPT manually.
2. Get answer outside app.
3. Edit `model/estimator.py` code → change `MARKET_PRIORS`.
4. Refresh dashboard.

### After (Phases 4–6)
1. Run whale monitor & dashboard side-by-side.
2. Dashboard auto-loads whales.
3. Select whale → click "Run LLM analysis".
4. Click "Apply as new prior" → dashboard updates instantly.
5. No code edits, no manual copy/paste.

---

## Troubleshooting

**Q: Whales not showing in dashboard?**
- Check `data/whales_log.json` exists.
- Make sure whale monitor is running and detecting trades (check console output).
- Dashboard auto-refreshes every 5–30 min (configurable).

**Q: LLM analysis returns dummy response?**
- Check `LLM_API_KEY` is set and valid.
- Check `dashboard/app.py` import of `analyze_whale` is present.

**Q: Override prior not applying?**
- Check `data/priors_overrides.json` was created.
- Restart dashboard (clear browser cache if needed).
- Verify market_id passed to `set_override_prior()` matches market ID in signals table.

**Q: Got runtime error in `model/estimator.py`?**
- Ensure `data/` directory exists.
- Try deleting `data/priors_overrides.json` and re-run (will recreate on first override).

---

## Next: Phase 7 (Contest Playbook)

Once Phases 4–6 are live and tested, Phase 7 will add:
- Final `docs/CONTEST_PLAYBOOK.md` with trading rules.
- End-to-end testing with real Polymarket data.

---

## Summary

All whale analysis is now **inside the Streamlit app**. No more manual prompts, no code edits. Just:
1. Whale monitor detects trades → logs them.
2. Dashboard fetches & displays them.
3. Click "Analyze" → LLM scores.
4. Click "Apply" → prior updates & edges recalculate.

**Ready to trade!**
