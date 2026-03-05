def get_prior_or_market(question: str, market_price: float) -> dict:
    return {"prob": market_price, "source": "market", "is_market_fallback": True}
