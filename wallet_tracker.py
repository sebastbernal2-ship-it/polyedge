#!/usr/bin/env python3
"""
wallet_tracker.py — Score whale wallets by historical profitability.
Improvements:
  - Paginates through ALL trades (not just last 500)
  - Computes overall win rate AND geopolitical-specific win rate
  - Labels: Smart Money / Mixed / Retail / Unknown
"""
from dotenv import load_dotenv
load_dotenv(override=True)

import os
import json
import time
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

DATA_API       = "https://data-api.polymarket.com"
WHALE_LOG_PATH = os.path.join("data", "whales_log.json")
SCORES_PATH    = os.path.join("data", "wallet_scores.json")
MIN_TRADES     = 3
RATE_LIMIT     = 0.35
MAX_PAGES      = 10    # max 10 pages x 500 = 5000 trades per wallet

# Keywords that identify geopolitical markets
GEO_KEYWORDS = [
    "iran", "russia", "ukraine", "israel", "gaza", "hezbollah", "hamas",
    "war", "ceasefire", "strike", "military", "regime", "nuclear",
    "strait", "hormuz", "sanctions", "missile", "attack", "invasion",
    "china", "taiwan", "nato", "coup", "election", "president",
    "hostage", "treaty", "diplomatic", "conflict", "troop"
]


@dataclass
class WalletScore:
    wallet: str
    total_trades: int
    overall_win_rate: float
    overall_closed: int
    geo_trades: int
    geo_win_rate: float
    geo_closed: int
    total_volume_usd: float
    avg_trade_size: float
    label: str
    last_updated: int


def fetch_all_wallet_trades(wallet: str) -> List[dict]:
    """Paginate through ALL trades for a wallet (up to MAX_PAGES * 500)."""
    all_trades = []
    offset = 0
    limit = 500

    for page in range(MAX_PAGES):
        try:
            resp = requests.get(
                f"{DATA_API}/trades",
                params={"user": wallet, "limit": limit, "offset": offset},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            all_trades.extend(data)
            if len(data) < limit:
                break  # reached end
            offset += limit
            time.sleep(0.2)
        except Exception as e:
            print(f"    [WARN] Page {page} fetch error for {wallet[:10]}: {e}")
            break

    return all_trades


def is_geo_trade(trade: dict) -> bool:
    """Check if a trade is on a geopolitical market."""
    title = (trade.get("title") or trade.get("market", "")).lower()
    slug  = (trade.get("slug") or trade.get("eventSlug", "")).lower()
    text  = title + " " + slug
    return any(kw in text for kw in GEO_KEYWORDS)


def compute_win_rate(trades: List[dict]) -> Tuple[int, int]:
    """
    Infer win/loss from buy→sell pairs within the same market+asset.
    Returns (profitable_closed, total_closed).
    """
    from collections import defaultdict
    positions: Dict[str, List[dict]] = defaultdict(list)
    for t in trades:
        key = f"{t.get('conditionId','')}-{t.get('asset','')}"
        positions[key].append(t)

    profitable = total_closed = 0
    for key, pos_trades in positions.items():
        buys  = [t for t in pos_trades if t.get("side","").upper() == "BUY"]
        sells = [t for t in pos_trades if t.get("side","").upper() == "SELL"]
        if not buys or not sells:
            continue
        try:
            avg_buy  = sum(float(t.get("price", 0)) for t in buys)  / len(buys)
            avg_sell = sum(float(t.get("price", 0)) for t in sells) / len(sells)
            total_closed += 1
            if avg_sell > avg_buy:
                profitable += 1
        except Exception:
            continue

    return profitable, total_closed


def score_wallet(wallet: str) -> Optional[WalletScore]:
    """Score a wallet on overall and geopolitical-specific win rates."""
    all_trades = fetch_all_wallet_trades(wallet)
    if not all_trades:
        return None

    total_trades = len(all_trades)

    # Overall win rate
    overall_profitable, overall_closed = compute_win_rate(all_trades)
    overall_win_rate = overall_profitable / overall_closed if overall_closed > 0 else 0.0

    # Geopolitical-specific win rate
    geo_trades_list = [t for t in all_trades if is_geo_trade(t)]
    geo_count = len(geo_trades_list)
    geo_profitable, geo_closed = compute_win_rate(geo_trades_list)
    geo_win_rate = geo_profitable / geo_closed if geo_closed > 0 else 0.0

    # Volume stats
    sizes = []
    for t in all_trades:
        try: sizes.append(float(t.get("size", 0)))
        except: pass
    total_volume = sum(sizes)
    avg_size = total_volume / len(sizes) if sizes else 0.0

    # Label — prefer geo win rate if enough geo trades, else overall
    if geo_closed >= MIN_TRADES:
        primary_wr = geo_win_rate
        primary_n  = geo_closed
    elif overall_closed >= MIN_TRADES:
        primary_wr = overall_win_rate
        primary_n  = overall_closed
    else:
        primary_wr = 0.0
        primary_n  = 0

    if primary_n < MIN_TRADES:
        label = "Unknown"
    elif primary_wr >= 0.60:
        label = "Smart Money"
    elif primary_wr >= 0.45:
        label = "Mixed"
    else:
        label = "Retail"

    return WalletScore(
        wallet=wallet,
        total_trades=total_trades,
        overall_win_rate=round(overall_win_rate, 3),
        overall_closed=overall_closed,
        geo_trades=geo_count,
        geo_win_rate=round(geo_win_rate, 3),
        geo_closed=geo_closed,
        total_volume_usd=round(total_volume, 2),
        avg_trade_size=round(avg_size, 2),
        label=label,
        last_updated=int(time.time()),
    )


def load_scores() -> Dict[str, dict]:
    if os.path.exists(SCORES_PATH):
        try:
            with open(SCORES_PATH) as f:
                return {s["wallet"]: s for s in json.load(f)}
        except Exception:
            return {}
    return {}


def save_scores(scores: Dict[str, dict]):
    os.makedirs(os.path.dirname(SCORES_PATH), exist_ok=True)
    with open(SCORES_PATH, "w") as f:
        json.dump(list(scores.values()), f, indent=2)


def get_wallet_score(wallet: str) -> Optional[dict]:
    """Quick lookup for a single wallet. Used by llm_analysis.py."""
    scores = load_scores()
    return scores.get(wallet)


def run_scoring():
    """Score all unique wallets from whales_log.json."""
    if not os.path.exists(WHALE_LOG_PATH):
        print("[ERROR] whales_log.json not found.")
        return

    with open(WHALE_LOG_PATH) as f:
        log = json.load(f)

    wallets = list({t.get("wallet", "") for t in log if t.get("wallet")})
    print(f"\n[WALLET TRACKER] Scoring {len(wallets)} unique wallets (full history + geo filter)...\n")

    scores = load_scores()
    now = int(time.time())
    stale_after = 6 * 3600

    for i, wallet in enumerate(wallets):
        existing = scores.get(wallet)
        if existing and (now - existing.get("last_updated", 0)) < stale_after:
            print(f"  [{i+1}/{len(wallets)}] {wallet[:12]}... cached ({existing['label']})")
            continue

        print(f"  [{i+1}/{len(wallets)}] Scoring {wallet[:12]}...", end=" ", flush=True)
        result = score_wallet(wallet)
        if result:
            scores[wallet] = asdict(result)
            geo_info = f"geo={result.geo_win_rate:.0%}({result.geo_closed})" if result.geo_closed > 0 else "no-geo"
            print(f"→ {result.label} | overall={result.overall_win_rate:.0%}({result.overall_closed}) | {geo_info} | {result.total_trades} total trades")
        else:
            print("→ No data")

        time.sleep(RATE_LIMIT)

    save_scores(scores)
    print(f"\n[DONE] Scores saved to {SCORES_PATH}")

    # Summary
    print("\n=== WALLET INTELLIGENCE SUMMARY ===")
    smart = [(w, s) for w, s in scores.items() if s.get("label") == "Smart Money"]
    smart.sort(key=lambda x: x[1].get("geo_win_rate", x[1].get("overall_win_rate", 0)), reverse=True)
    print(f"\nSmart Money wallets ({len(smart)} total):")
    for wallet, s in smart[:15]:
        geo = f"geo={s.get('geo_win_rate',0):.0%}({s.get('geo_closed',0)})" if s.get("geo_closed",0) > 0 else "no-geo-data"
        print(f"  {wallet[:14]}...  overall={s.get('overall_win_rate',0):.0%}  {geo}  trades={s.get('total_trades',0)}")


if __name__ == "__main__":
    run_scoring()

# ─── Behavior Tracking Over Time ──────────────────────────────────────────────
import json
from pathlib import Path

SNAPSHOT_DIR = Path("data/wallet_snapshots")
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def record_wallet_snapshot(wallet: str, trades: list) -> dict:
    """Record current wallet position snapshot to disk for trend analysis."""
    if not wallet or not trades:
        return {}
    now = int(time.time())
    yes_vol = sum(float(t.get("size_usd", t.get("size", 0))) for t in trades
                  if (t.get("outcome") or t.get("side", "")).lower() == "yes")
    no_vol  = sum(float(t.get("size_usd", t.get("size", 0))) for t in trades
                  if (t.get("outcome") or t.get("side", "")).lower() == "no")
    total   = yes_vol + no_vol
    snapshot = {
        "ts": now,
        "yes_vol": yes_vol,
        "no_vol": no_vol,
        "yes_pct": round(100 * yes_vol / total, 1) if total > 0 else 50.0,
        "total_vol": total,
        "trade_count": len(trades),
    }
    snap_file = SNAPSHOT_DIR / f"{wallet[:20]}.jsonl"
    with open(snap_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
    return snapshot


def get_wallet_history(wallet: str, max_records: int = 100) -> list:
    """Return list of snapshots for a wallet, most recent last."""
    snap_file = SNAPSHOT_DIR / f"{wallet[:20]}.jsonl"
    if not snap_file.exists():
        return []
    lines = snap_file.read_text().strip().splitlines()
    records = []
    for line in lines[-max_records:]:
        try:
            records.append(json.loads(line))
        except Exception:
            pass
    return records


def get_position_drift(wallet: str) -> dict:
    """Compare current position to 24h ago. Returns drift dict."""
    history = get_wallet_history(wallet)
    if not history:
        return {"drift": 0.0, "direction": "flat", "snapshots": 0}
    now = int(time.time())
    current = history[-1]
    # Find snapshot closest to 24h ago
    target_ts = now - 86400
    past = min(history, key=lambda h: abs(h["ts"] - target_ts))
    drift = current["yes_pct"] - past["yes_pct"]
    direction = "bullish" if drift > 5 else "bearish" if drift < -5 else "flat"
    return {
        "drift": round(drift, 1),
        "direction": direction,
        "current_yes_pct": current["yes_pct"],
        "past_yes_pct": past["yes_pct"],
        "snapshots": len(history),
        "current_ts": current["ts"],
        "past_ts": past["ts"],
    }


def get_smart_money_trend(whale_trades: list, lookback_hours: int = 24) -> dict:
    """Aggregate smart money flow trend from recent trades list."""
    if not whale_trades:
        return {"yes_pct_now": 50.0, "trend": "flat", "total_vol": 0}
    now = int(time.time())
    cutoff_recent = now - 3600        # last 1h
    cutoff_old    = now - lookback_hours * 3600

    def _flow(trades):
        yes = sum(float(t.get("size_usd", t.get("size", 0))) for t in trades
                  if (t.get("outcome") or t.get("side", "")).lower() == "yes")
        no  = sum(float(t.get("size_usd", t.get("size", 0))) for t in trades
                  if (t.get("outcome") or t.get("side", "")).lower() == "no")
        total = yes + no
        return (100 * yes / total if total > 0 else 50.0), total

    def _ts(t):
        raw = t.get("timestamp") or t.get("created_at") or t.get("ts") or 0
        try:
            return int(raw)
        except Exception:
            return 0

    recent = [t for t in whale_trades if _ts(t) >= cutoff_recent]
    older  = [t for t in whale_trades if cutoff_old <= _ts(t) < cutoff_recent]

    yes_pct_now, vol_now = _flow(recent if recent else whale_trades)
    yes_pct_old, _       = _flow(older) if older else (yes_pct_now, 0)

    drift = yes_pct_now - yes_pct_old
    trend = "bullish" if drift > 8 else "bearish" if drift < -8 else "flat"

    return {
        "yes_pct_now": round(yes_pct_now, 1),
        "yes_pct_old": round(yes_pct_old, 1),
        "drift": round(drift, 1),
        "trend": trend,
        "total_vol": vol_now,
        "recent_trades": len(recent),
        "older_trades": len(older),
    }
