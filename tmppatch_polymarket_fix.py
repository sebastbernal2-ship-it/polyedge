from pathlib import Path
import textwrap

path = Path("data/polymarket.py")
text = path.read_text()

old = '''GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_candidate_markets(deadline=None) -> list[dict]:
    """Fetch a broad set of active markets from Polymarket (no strict filters)."""
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
'''
new = '''GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_candidate_markets(deadline=None) -> list[dict]:
    """Fetch a broad set of active markets from Polymarket (no strict filters)."""
    params = {
        "limit": 500,
        "active": True,
        "closed": False,
        "order": "volume",
    }
    r = requests.get(f"{GAMMA_API}/markets", params=params, timeout=10)
    r.raise_for_status()
    markets = r.json()
    if not isinstance(markets, list) or not markets:
        return []
'''

if old not in text:
    raise SystemExit("expected block not found; aborting patch")

text = text.replace(old, new)
path.write_text(text)
print("fixed fetch_candidate_markets in data/polymarket.py")
