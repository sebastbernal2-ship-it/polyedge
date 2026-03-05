import textwrap, os, pathlib

path = pathlib.Path("data/polymarket.py")
text = path.read_text()

# 1) Ensure imports
if "from datetime import datetime, timezone" not in text:
    text = "from datetime import datetime, timezone\n" + text
if "from typing import List, Dict, Any" not in text:
    text = "from typing import List, Dict, Any\n" + text

# 2) Add helpers at end of file
append_block = textwrap.dedent("""
\n
# ---- Auto-discovery helpers ----

import requests

GAMMA_API = "https://gamma-api.polymarket.com"

def _fetch_all_markets(limit: int = 500) -> list[dict]:
    \"\"\"Fetch a broad list of active markets from Polymarket Gamma API.\"\"\"
    params = {
        "active": "true",
        "closed": "false",
        "limit": str(limit),
        "offset": "0",
    }
    r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    # Gamma returns { "markets": [...] } per docs
    markets = data.get("markets") if isinstance(data, dict) else data
    return markets or []

def fetch_candidate_markets(deadline: datetime) -> List[Dict[str, Any]]:
    \"\"\"Return many active binary markets with YES price and resolve time.

    Filters:
    - active & not closed
    - binary Yes/No (formatType == 'scalar' will be skipped)
    - resolves on/before deadline if upperBoundDate/umaEndDate present
    \"\"\"
    raw = _fetch_all_markets()
    out: List[Dict[str, Any]] = []

    for m in raw:
        if not isinstance(m, dict):
            continue

        # Skip clearly non-binary formats
        fmt = m.get("formatType") or m.get("marketType")
        if fmt and str(fmt).lower() not in ("binary", "categorical"):
            continue

        m_id = m.get("conditionId") or m.get("id")
        label = m.get("title") or m.get("question") or m.get("name")
        # outcomePrices is list like ["0.23","0.77"] YES first
        prices = m.get("outcomePrices") or m.get("prices")
        yes_price = None
        if isinstance(prices, (list, tuple)) and len(prices) >= 1:
            try:
                yes_price = float(prices[0])
            except Exception:
                yes_price = None

        closed = m.get("closed") or (not m.get("active", True))
        if closed or not m_id or not label or yes_price is None:
            continue

        resolve_ts = (
            m.get("upperBoundDate")
            or m.get("umaEndDate")
            or m.get("endDate")
        )
        rt = None
        if resolve_ts:
            try:
                rt = datetime.fromisoformat(str(resolve_ts).replace("Z", "+00:00"))
            except Exception:
                rt = None

        if rt is not None and rt > deadline:
            continue

        out.append(
            {
                "id": str(m_id),
                "question": str(label),
                "yes_price": float(yes_price),
                "resolve_time": rt,
            }
        )

    return out
""")

if "fetch_candidate_markets" not in text:
    text = text.rstrip() + append_block

path.write_text(text)
print("patched data/polymarket.py")
