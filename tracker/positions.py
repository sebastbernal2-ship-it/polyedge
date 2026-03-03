import json, os
from datetime import datetime

LOG_FILE = "positions_log.json"

def log_trade(market_id, question, side, price, size, your_prob):
    entry = {
        "timestamp":  datetime.utcnow().isoformat(),
        "market_id":  market_id,
        "question":   question,
        "side":       side,
        "price":      price,
        "size":       size,
        "your_prob":  your_prob,
        "outcome":    None,    # fill in when resolved
        "brier":      None
    }
    log = _load()
    log.append(entry)
    _save(log)

def resolve_trade(market_id, outcome: bool):
    """Call this when a market resolves. Computes Brier score."""
    log = _load()
    for entry in log:
        if entry["market_id"] == market_id and entry["outcome"] is None:
            entry["outcome"] = outcome
            actual = 1 if outcome else 0
            entry["brier"] = round((entry["your_prob"] - actual) ** 2, 4)
    _save(log)

def get_calibration_summary():
    log = _load()
    resolved = [e for e in log if e["brier"] is not None]
    if not resolved:
        return {"trades": 0}
    avg_brier = sum(e["brier"] for e in resolved) / len(resolved)
    return {"trades": len(resolved), "avg_brier": round(avg_brier, 4)}

def _load():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE) as f:
        return json.load(f)

def _save(log):
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)
