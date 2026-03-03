"""
Whale Monitor for Polymarket CLOB
Tracks large trades on target Iran markets and generates LLM prompts for analysis.

This module runs independently in another terminal and polls the Polymarket CLOB API
for recent fills, filtering for large trades (>= MIN_USD) in target markets.

For each whale trade, it generates:
  1. A one-line human-readable alert.
  2. A structured LLM prompt ready to paste into ChatGPT/Perplexity for probability estimation.

After running the LLM prompt, users can update MARKET_PRIORS in model/estimator.py
and re-run main.py to get fresh edge signals that reflect whale insights.
"""

import os
import requests
import json
import time
from typing import Optional, List, Dict
from dataclasses import dataclass, asdict
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from data.whales import append_whale

# ── CONFIG ────────────────────────────────────────────────────
CLOB_URL = "https://clob.polymarket.com"  # Polymarket CLOB API base
MIN_USD = 10_000.0                         # Only flag trades >= this size
POLL_SECONDS = 30                          # Poll interval

# ── TARGET MARKETS ────────────────────────────────────────────
# Map human-readable labels to explicit market condition IDs.
# IMPORTANT: Replace placeholder ids with real ones from Polymarket.
# You can find them at https://polymarket.com or via the Gamma API.
TARGET_MARKETS = {
    "Iran ceasefire by Mar 7": "PLACEHOLDER_ID_1",
    "US strikes Iran by Mar 7": "PLACEHOLDER_ID_2",
    "Fordow strike": "PLACEHOLDER_ID_3",
    "Iranian regime fall": "PLACEHOLDER_ID_4",
}

# ── TELEGRAM ALERTS (OPTIONAL) ────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# ── DATA MODELS ───────────────────────────────────────────────
@dataclass
class MarketInfo:
    """Info about a target market."""
    id: str
    question: str
    resolution_rules: str


@dataclass
class WhaleTrade:
    """A large trade on a target market."""
    market_id: str
    market_label: str
    question: str
    wallet: str
    size_usd: float
    outcome: str  # "Yes" or "No"
    price: float
    timestamp: str

    def __hash__(self):
        """For deduplication."""
        return hash((self.wallet, self.timestamp, self.market_id, self.price))

    def __eq__(self, other):
        if not isinstance(other, WhaleTrade):
            return False
        return (self.wallet, self.timestamp, self.market_id, self.price) == \
               (other.wallet, other.timestamp, other.market_id, other.price)


# ── API FUNCTIONS ─────────────────────────────────────────────
def get_market_by_id(market_id: str) -> Optional[Dict]:
    """
    Fetch market info from CLOB API by condition ID.
    Returns market JSON or None on error.
    """
    try:
        resp = requests.get(f"{CLOB_URL}/markets/{market_id}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"[ERROR] Could not fetch market {market_id}: {e}")
        return None


def build_target_markets() -> Dict[str, Optional[MarketInfo]]:
    """
    Resolve TARGET_MARKETS ids into MarketInfo.
    Logs warnings if any ids are placeholders or invalid.
    Returns dict mapping label → MarketInfo (or None if fetch failed).
    """
    result = {}
    for label, market_id in TARGET_MARKETS.items():
        if "PLACEHOLDER" in market_id:
            print(f"[WARN] Target market '{label}' still has placeholder ID: {market_id}")
            print(f"       → Please fill in the real condition ID from Polymarket")
            result[label] = None
            continue

        mkt = get_market_by_id(market_id)
        if mkt:
            info = MarketInfo(
                id=market_id,
                question=mkt.get("question", "Unknown"),
                resolution_rules=mkt.get("resolutionRules", "")
            )
            result[label] = info
            print(f"[OK] Loaded '{label}': {info.question[:60]}")
        else:
            print(f"[ERROR] Failed to load market '{label}' (id: {market_id})")
            result[label] = None
    return result


def fetch_recent_fills(limit: int = 200) -> List[Dict]:
    """
    Fetch recent order fills from CLOB API.
    Handles both list and {"fills": [...]} response shapes.
    """
    try:
        resp = requests.get(f"{CLOB_URL}/fills", params={"limit": limit}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        # Handle both direct list and wrapped dict
        if isinstance(data, dict) and "fills" in data:
            return data["fills"]
        elif isinstance(data, list):
            return data
        else:
            print(f"[WARN] Unexpected fills response shape: {type(data)}")
            return []
    except Exception as e:
        print(f"[ERROR] Could not fetch fills: {e}")
        return []


def filter_whale_trades(
    fills: List[Dict],
    markets: Dict[str, Optional[MarketInfo]],
    min_usd: float = MIN_USD
) -> List[WhaleTrade]:
    """
    Filter fills to extract whale trades in target markets.
    
    Market mapping:
      - Outcome 0/"0" → "Yes"
      - Outcome 1/"1" → "No"
      
    Trades with marketId not in TARGET_MARKETS are skipped.
    Trades with usdVolume < min_usd are skipped.
    
    Returns list of WhaleTrade instances.
    """
    trades = []
    
    # Build market_id → label map (only for successfully resolved markets)
    id_to_label = {}
    for label, info in markets.items():
        if info:
            id_to_label[info.id] = label
    
    for fill in fills:
        market_id = fill.get("market")
        
        # Skip if not in target markets
        if market_id not in id_to_label:
            continue
        
        # Check minimum USD volume
        usd_volume = fill.get("usdVolume") or fill.get("usdAmount") or 0
        if usd_volume < min_usd:
            continue
        
        label = id_to_label[market_id]
        market_info = markets[label]
        
        # Parse outcome (handle string and int)
        outcome_raw = fill.get("outcome")
        if str(outcome_raw) in ["0", "Yes"]:
            outcome = "Yes"
        elif str(outcome_raw) in ["1", "No"]:
            outcome = "No"
        else:
            outcome = str(outcome_raw)
        
        trade = WhaleTrade(
            market_id=market_id,
            market_label=label,
            question=market_info.question,
            wallet=fill.get("wallet", "Unknown"),
            size_usd=float(usd_volume),
            outcome=outcome,
            price=float(fill.get("price", 0)),
            timestamp=fill.get("timestamp", datetime.utcnow().isoformat())
        )
        trades.append(trade)
    
    return trades


def format_llm_prompt(trade: WhaleTrade) -> str:
    """
    Generate a structured LLM prompt for analyzing a whale trade.
    
    The prompt asks the LLM to:
      1. Re-explain YES/NO conditions.
      2. Analyze scenarios in next 3-5 days.
      3. Judge edge of following whale for 1-3 day swing.
      4. Propose entry/exit ranges for 100-200% ROI.
    
    Returns a ready-to-paste prompt string.
    """
    prompt = f"""
=== POLYMARKET WHALE TRADE ALERT ===

[TRADE INFO]
Market: {trade.market_label}
Question: {trade.question}
Market ID: {trade.market_id}

Whale Side: {trade.outcome}
Price: {trade.price:.2%}
USD Volume: ${trade.size_usd:,.0f}
Timestamp: {trade.timestamp}
Wallet: {trade.wallet}

[YOUR TASK]
An informed trader (whale) just placed a {trade.size_usd:,.0f} USD bet on {trade.outcome}
at {trade.price:.2%}. Analyze whether this is high-edge for a 1-3 day swing trade.

1. Re-state the resolution conditions for YES and NO clearly.

2. Assess developments in the next 3-5 days that would resolve YES vs NO.
   - What key events or announcements could move the market?
   - How aligned is the whale's side with current geopolitical trends?

3. Judge whether following the whale's side for a 1-3 day hold is:
   HIGH EDGE (>15 ppt likely): whale is ahead of market sentiment
   MEDIUM EDGE (5-15 ppt): whale signal is valid but uncertain
   LOW EDGE (<5 ppt): whale is tracking market, limited opportunity

4. If high or medium edge, propose:
   - Entry range: [price X% to price Y%]
   - Exit target: [entry × 1.5 to entry × 2.0] for 1-3 day hold
   - Stop loss: [entry × 0.8 or key support level]
   - Suggested position size: as % of small bankroll

5. Based on your analysis, what probability estimate would you give for {trade.outcome}?
   Return as single float 0.0-1.0 (used to update the predictive model).

Be concise but specific. Focus on actionable 1-3 day edge.
"""
    return prompt.strip()


def notify_whale(trade: WhaleTrade, market_info: Optional[MarketInfo] = None):
    """
    Print a one-line alert and full LLM prompt to stdout.
    Optionally send via Telegram if credentials are set.
    """
    # One-line alert
    alert = (
        f"🐋 WHALE: {trade.market_label} | "
        f"{trade.outcome.upper()} @ {trade.price:.1%} | "
        f"${trade.size_usd:,.0f} | "
        f"{trade.timestamp}"
    )
    
    print("\n" + "=" * 80)
    print(alert)
    print("=" * 80 + "\n")
    
    # Full LLM prompt
    llm_prompt = format_llm_prompt(trade)
    print(llm_prompt)
    print("\n" + "=" * 80 + "\n")
    
    # Optional Telegram
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": alert
                },
                timeout=5
            )
        except Exception as e:
            print(f"[WARN] Telegram send failed: {e}")


# ── MAIN LOOP ─────────────────────────────────────────────────
def main():
    """
    Poll CLOB API for recent fills.
    Track whale trades and notify when new ones appear.
    """
    print("\n=== POLYMARKET WHALE MONITOR ===\n")
    print(f"Target: {', '.join(TARGET_MARKETS.keys())}")
    print(f"Min USD: ${MIN_USD:,.0f}")
    print(f"Poll interval: {POLL_SECONDS}s\n")
    
    # Resolve target markets
    markets = build_target_markets()
    active_labels = [l for l, info in markets.items() if info is not None]
    
    if not active_labels:
        print("\n[FATAL] No valid target markets. Please fill in the placeholder IDs in TARGET_MARKETS.")
        print("        Edit whale_monitor.py → TARGET_MARKETS dict with real condition IDs from Polymarket.")
        return
    
    print(f"\n[OK] Starting poll with {len(active_labels)} active markets\n")
    
    # Track seen trades for deduplication
    seen_trades = set()
    
    try:
        while True:
            print(f"[{datetime.utcnow().isoformat()}] Polling...")
            fills = fetch_recent_fills(limit=200)
            
            if not fills:
                print("  → No fills returned")
                time.sleep(POLL_SECONDS)
                continue
            
            whale_trades = filter_whale_trades(fills, markets, min_usd=MIN_USD)
            print(f"  → Fetched {len(fills)} fills, found {len(whale_trades)} whale trades")
            
            # Notify on new trades
            for trade in whale_trades:
                if trade not in seen_trades:
                    seen_trades.add(trade)
                    notify_whale(trade, markets.get(trade.market_label))
                    # Persist to whale log (deduplicated by append_whale)
                    try:
                        entry = {
                            "timestamp": trade.timestamp,
                            "market_id": trade.market_id,
                            "market_label": trade.market_label,
                            "side": trade.outcome,
                            "size_usd": trade.size_usd,
                            "price": trade.price,
                            "wallet": trade.wallet,
                        }
                        appended = append_whale(entry)
                        if appended:
                            print(f"[LOG] Appended whale to data/whales_log.json: {entry['market_label']} | ${entry['size_usd']:,.0f}")
                    except Exception as e:
                        print(f"[WARN] Could not append whale to log: {e}")
        print("\n\n[INFO] Whale monitor stopped.")
    except Exception as e:
        print(f"\n[FATAL] Unexpected error: {e}")
        raise


if __name__ == "__main__":
    main()
