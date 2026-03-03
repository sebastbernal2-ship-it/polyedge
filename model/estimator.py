"""
Bayesian probability estimator.
You set a prior, then pass in likelihood ratios from news signals.
Each news item either raises or lowers your probability.
"""

def bayes_update(prior: float, likelihood_ratio: float) -> float:
    """
    Update a probability given new evidence.
    likelihood_ratio > 1 = evidence makes event MORE likely
    likelihood_ratio < 1 = evidence makes event LESS likely
    Example: prior=0.30, lr=1.5 → posterior ≈ 0.39
    """
    prior_odds = prior / (1 - prior)
    posterior_odds = prior_odds * likelihood_ratio
    return posterior_odds / (1 + posterior_odds)

def estimate_from_signals(prior: float, signals: list[dict]) -> float:
    """
    signals = list of {"description": str, "lr": float}
    Chains multiple Bayesian updates together.
    """
    p = prior
    for s in signals:
        p = bayes_update(p, s["lr"])
    return round(p, 4)

# ---- Example priors per market (you update these manually) ----
MARKET_PRIORS = {
    "ceasefire_march_31":     0.20,   # your prior BEFORE news
    "hormuz_march_31":        0.75,
    "regime_fall_march_31":   0.27,
}
