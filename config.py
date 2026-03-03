import os

"""
PolyEdge Configuration
contest-ready settings for 14-day Polymarket contest.
Ranking is based on percentage return, so concentrate on high-edge trades.
"""

DOMAINS = ["Iran", "ceasefire", "Hormuz", "regime", "strikes"]

# ── EDGE THRESHOLD ────────────────────────────────────────────
# Only trade when edge (your probability - market probability) >= this value.
# Contest strategy: focus on concentration in a few high-edge opportunities
# rather than many small commissions. Typically set to 0.15 (15 ppts).
EDGE_THRESHOLD = 0.15

# ── KELLY SIZING ──────────────────────────────────────────────
# KELLY_FRACTION = fraction of full Kelly to use (e.g. 0.25 = quarter Kelly)
# MAX_BET_FRACTION = hard cap per bet as fraction of total bankroll
# Example: BANKROLL=100, MAX_BET_FRACTION=0.40 means no single bet > $40
KELLY_FRACTION = 0.25        # quarter Kelly for safety
MAX_BET_FRACTION = 0.40      # never more than 40% of bankroll per bet

# ── BANKROLL ──────────────────────────────────────────────────
# Set this to your actual Polymarket contest bankroll.
# For 14-day contest, percentage return is what matters for ranking.
BANKROLL = 100.00            # USD (UPDATE THIS to your actual contest bankroll)

# ── LLM CONFIG ───────────────────────────────────────────────
# Read API key and provider from environment. If key missing, analysis is disabled.
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
ENABLE_LLM_ANALYSIS = bool(LLM_API_KEY)
