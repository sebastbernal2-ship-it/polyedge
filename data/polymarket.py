import requests

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL  = "https://clob.polymarket.com"

def get_iran_markets():
    """Pull all active Iran-tagged markets with current prices."""
    resp = requests.get(f"{GAMMA_URL}/markets", params={
        "limit": 100,
        "active": True,
        "closed": False,
        "tag": "Iran",
        "order": "volume"
    })
    resp.raise_for_status()
    markets = resp.json()
    parsed = []
    for m in markets:
        parsed.append({
            "id":        m.get("conditionId"),
            "question":  m.get("question"),
            "yes_price": float(m.get("outcomePrices", ["0","1"])[0]),
            "no_price":  float(m.get("outcomePrices", ["1","0"])[1]),
            "volume":    float(m.get("volume", 0)),
            "end_date":  m.get("endDate"),
            "token_ids": m.get("clobTokenIds", []),
        })
    return parsed

def get_price_history(token_id: str, interval="1h"):
    """Pull price history for a single token."""
    resp = requests.get(f"{CLOB_URL}/prices-history", params={
        "market": token_id,
        "interval": interval,
        "fidelity": 60
    })
    resp.raise_for_status()
    return resp.json().get("history", [])
