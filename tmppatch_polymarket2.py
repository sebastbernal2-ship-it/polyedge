import textwrap, pathlib

path = pathlib.Path("data/polymarket.py")
text = path.read_text()

insert = textwrap.dedent("""
# ---- Auto-discovery helpers (loose) ----

import requests

GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_candidate_markets(deadline=None) -> list[dict]:
    \"\"\"Fetch a broad set of active markets from Polymarket (no strict filters).\"\"\"
    params = {
        "active": "true",
        "closed": "false",
        "limit": "500",
        "offset": "0",
    }
    r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    markets = data.get("markets") if isinstance(data, dict) else data
    if not markets:
        return []

    out = []
    for m in markets:
        if not isinstance(m, dict):
            continue

        m_id = m.get("conditionId") or m.get("id")
        label = m.get("title") or m.get("question") or m.get("name")
        prices = m.get("outcomePrices") or m.get("prices")
        yes_price = None
        if isinstance(prices, (list, tuple)) and len(prices) >= 1:
            try:
                yes_price = float(prices[0])
            except Exception:
                yes_price = None

        if not m_id or not label or yes_price is None:
            continue

        out.append(
            {
                "id": str(m_id),
                "question": str(label),
                "yes_price": float(yes_price),
                "resolve_time": None,
            }
        )

    return out
""")

# wipe previous auto-discovery block if needed
if "fetch_candidate_markets(" in text:
    # crude: keep everything up to first occurrence, then append new block
    base = text.split("# ---- Auto-discovery helpers", 1)[0].rstrip()
    text = base + "\n\n" + insert
else:
    text = text.rstrip() + "\n\n" + insert

path.write_text(text)
print("repatched data/polymarket.py")
