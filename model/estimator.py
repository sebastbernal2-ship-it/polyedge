import os
import json
import requests
import datetime
from dotenv import load_dotenv

load_dotenv()

NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")
NAVIGATOR_KEY = os.getenv("NAVIGATOR_KEY", "")
NAVIGATOR_BASE = "https://api.ai.it.ufl.edu/v1"
NAVIGATOR_MODEL = "llama-3.3-70b-instruct"

# ── MARKET PRIORS (CRITICAL FOR WHALE INTEGRATION) ──────────────────────
# These are your baseline probability estimates for key markets.
# 
# HOW TO UPDATE FROM WHALE ALERTS:
# ────────────────────────────────────────────────────────────────────────
# 1. Run: python whale_monitor.py (in another terminal)
# 2. When a whale trade alert appears, you'll see a structured LLM prompt.
# 3. Copy that prompt into ChatGPT/Perplexity.
# 4. The LLM will analyze the whale trade and propose a probability estimate.
# 5. If you trust the LLM's reasoning, update the relevant prior by market ID:
#
#    Example: LLM says "Iran ceasefire now 45% (was 35%), whale aligned, high edge"
#             → Update MARKET_PRIORS["0x1234..."] = 0.45
#             → Re-run main.py to get fresh edge signals reflecting whale insight
#
# 6. The PolyEdge core (main.py) will use the updated prior to recalculate edge.
#    If updated_prob = 0.45 and market_price = 0.30, edge = +0.15 (buy YES).
#
# For manual market IDs in the dashboard, update override_priors in dashboard/app.py

DOMAIN_PRIORS = {
    "ceasefire": 0.35,
    "nuclear": 0.20,
    "strait": 0.08,
    "attack": 0.15,
    "sanctions": 0.55,
    "diplomatic": 0.40,
    "default": 0.30,
}

# ── MARKET PRIORS BY CONDITION ID ──────────────────────────────────────
# If you prefer to set priors directly by Polymarket condition ID,
# populate this dict. Entries here override DOMAIN_PRIORS in estimate_edge().
# 
# Format: market_id → probability
# Example after whale analysis:
#   MARKET_PRIORS["0x1234abc..."] = 0.55  # Updated from whale signal
#
MARKET_PRIORS = {}

# Runtime overrides persisted to data/priors_overrides.json
OVERRIDE_PRIORS = {}
_OVERRIDES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'priors_overrides.json'))

# Load persisted overrides on import if available
try:
    if os.path.exists(_OVERRIDES_PATH):
        with open(_OVERRIDES_PATH, 'r', encoding='utf-8') as _f:
            _loaded = json.load(_f)
            if isinstance(_loaded, dict):
                OVERRIDE_PRIORS.update({k: float(v) for k, v in _loaded.items()})
except Exception:
    OVERRIDE_PRIORS = {}


def get_effective_prior(market_id: str):
    """Return override prior for market_id, else MARKET_PRIORS entry, else None."""
    if not market_id:
        return None
    if market_id in OVERRIDE_PRIORS:
        return OVERRIDE_PRIORS[market_id]
    if market_id in MARKET_PRIORS:
        return MARKET_PRIORS[market_id]
    return None


def set_override_prior(market_id: str, p: float):
    """Set an override prior (in-memory + persist to data/priors_overrides.json)."""
    try:
        OVERRIDE_PRIORS[market_id] = float(p)
        os.makedirs(os.path.dirname(_OVERRIDES_PATH), exist_ok=True)
        with open(_OVERRIDES_PATH, 'w', encoding='utf-8') as _f:
            json.dump(OVERRIDE_PRIORS, _f, indent=2)
        return True
    except Exception as e:
        print(f"[WARN] Could not write priors overrides: {e}")
        return False

DOMAIN_KEYWORDS = {
    "ceasefire": ["ceasefire", "truce", "peace deal", "halt", "agreement"],
    "nuclear": ["nuclear", "enrichment", "iaea", "uranium", "bomb", "warhead"],
    "strait": ["strait of hormuz", "hormuz", "tanker", "shipping lane", "blockade"],
    "attack": ["strike", "attack", "bomb", "missile", "airstrike", "retaliation"],
    "sanctions": ["sanctions", "embargo", "oil ban", "export ban", "treasury"],
    "diplomatic": ["diplomacy", "talks", "negotiations", "envoy", "summit"],
}


def classify_domain(question: str) -> str:
    q = question.lower()
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in kws):
            return domain
    return "default"


def fetch_news(query: str, days_back: int = 3) -> list:
    if not NEWSAPI_KEY:
        return []
    from_date = (datetime.date.today() - datetime.timedelta(days=days_back)).isoformat()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "sortBy": "relevancy",
        "pageSize": 5,
        "language": "en",
        "apiKey": NEWSAPI_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("articles", [])
    except Exception as e:
        print(f"[NewsAPI error] {e}")
        return []


def summarize_articles(articles: list) -> str:
    snippets = []
    for a in articles[:5]:
        title = a.get("title", "")
        desc = a.get("description", "") or ""
        snippets.append(f"- {title}: {desc[:120]}")
    return "\n".join(snippets) if snippets else "No recent news found."


def llm_score(
    question: str,
    news_summary: str,
    domain: str,
    prior: float,
    use_llm: bool = True,
) -> tuple:
    if not use_llm or not NAVIGATOR_KEY:
        return keyword_fallback(question, news_summary, prior)

    system_prompt = (
        "You are a geopolitical prediction market analyst. "
        "Given a yes/no market question, recent news, and a domain base rate, "
        "output a JSON object with keys: probability (float 0-1) and "
        "reasoning (1-2 sentences). Be concise and calibrated."
    )
    example = '{"probability": 0.42, "reasoning": "..."}'
    user_prompt = (
        f"Question: {question}\n"
        f"Domain: {domain} (base rate: {prior:.0%})\n"
        f"Recent news:\n{news_summary}\n\n"
        f"Respond ONLY with valid JSON like: {example}"
    )

    headers = {
        "Authorization": f"Bearer {NAVIGATOR_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": NAVIGATOR_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 200,
    }

    try:
        r = requests.post(
            f"{NAVIGATOR_BASE}/chat/completions",
            headers=headers,
            json=payload,
            timeout=25,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        prob = max(0.01, min(0.99, float(data["probability"])))
        return prob, data.get("reasoning", "LLM scored.")
    except Exception as e:
        print(f"[Navigator error] {e}")
        return keyword_fallback(question, news_summary, prior)


def keyword_fallback(question: str, news_summary: str, prior: float) -> tuple:
    positive = ["agreement", "ceasefire", "deal", "progress", "talks", "confirmed"]
    negative = ["collapsed", "failed", "escalat", "strike", "attack", "war"]
    text = (question + " " + news_summary).lower()
    pos = sum(text.count(w) for w in positive)
    neg = sum(text.count(w) for w in negative)
    delta = (pos - neg) * 0.04
    prob = max(0.01, min(0.99, prior + delta))
    return prob, f"Keyword fallback: +{pos} positive, -{neg} negative (delta={delta:+.2f})"


def estimate_edge(
    question: str,
    market_prob: float,
    end_date=None,
    use_llm: bool = True,
    use_news: bool = True,
    market_id: str = None,
) -> dict:
    domain = classify_domain(question)
    # Prefer a market-specific effective prior if available (override persistence handled separately)
    prior = None
    try:
        from model.estimator import get_effective_prior  # local import to avoid circular at module load
        if market_id:
            prior = get_effective_prior(market_id)
    except Exception:
        prior = None

    if prior is None:
        prior = DOMAIN_PRIORS[domain]

    news_articles = fetch_news(f"Iran {question[:60]}") if use_news else []
    news_summary = summarize_articles(news_articles)
    our_prob, reasoning = llm_score(question, news_summary, domain, prior, use_llm)
    edge = our_prob - market_prob
    abs_edge = abs(edge)
    if abs_edge >= 0.15:
        signal = "STRONG"
    elif abs_edge >= 0.08:
        signal = "MODERATE"
    elif abs_edge >= 0.04:
        signal = "WEAK"
    else:
        signal = "NONE"
    direction = "BUY YES" if edge > 0 else "BUY NO"
    days_left = None
    if end_date:
        try:
            ed = datetime.date.fromisoformat(str(end_date)[:10])
            days_left = (ed - datetime.date.today()).days
        except Exception:
            pass
    return {
        "question": question,
        "domain": domain,
        "prior": prior,
        "market_prob": market_prob,
        "our_prob": our_prob,
        "edge": edge,
        "signal": signal,
        "direction": direction if signal != "NONE" else "HOLD",
        "reasoning": reasoning,
        "news_summary": news_summary,
        "end_date": end_date,
        "days_left": days_left,
        "use_llm": use_llm,
        "use_news": use_news,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


def auto_update_priors(articles: list, market_priors: dict) -> dict:
    updated = dict(market_priors)
    pos_words = ["deal", "agreement", "progress", "ceasefire"]
    neg_words = ["collapse", "failed", "escalat", "strike"]
    for a in articles:
        text = (
            (a.get("title") or "") + " " + (a.get("description") or "")
        ).lower()
        pos = sum(text.count(w) for w in pos_words)
        neg = sum(text.count(w) for w in neg_words)
        delta = (pos - neg) * 0.01
        for mid in updated:
            updated[mid] = max(0.01, min(0.99, updated[mid] + delta))
    return updated


def explain_updates(articles: list, market_priors: dict) -> dict:
    """
    Returns an audit trail showing how news moved each market's prior.
    Result shape: {market_id: {"label": str, "final_prob": float, "steps": list}}
    """
    pos_words = ["deal", "agreement", "progress", "ceasefire", "talks"]
    neg_words = ["collapse", "failed", "escalat", "strike", "attack"]
    audit = {}
    for mid, base_p in market_priors.items():
        steps = [{"source": "domain prior", "delta": 0.0, "prob": base_p}]
        current = base_p
        for a in articles:
            text = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
            pos = sum(text.count(w) for w in pos_words)
            neg = sum(text.count(w) for w in neg_words)
            delta = (pos - neg) * 0.01
            if delta != 0:
                current = max(0.01, min(0.99, current + delta))
                steps.append({
                    "source": (a.get("title") or "article")[:60],
                    "delta": round(delta, 3),
                    "prob": round(current, 3),
                })
        audit[mid] = {
            "label": str(mid)[:30],
            "final_prob": round(current, 3),
            "steps": steps,
        }
    return audit

def classify_generic_category(m: dict) -> str:
    """Broad category classification for generic priors."""
    # Try tags/category/slug for hints
    tags = " ".join(m.get("tags", [])).lower()
    question = (m.get("question") or m.get("title") or m.get("name") or "").lower()
    slug = (m.get("slug") or m.get("eventSlug") or "").lower()
    text = " ".join([tags, question, slug])

    if any(w in text for w in ["president", "election", "primary", "senate", "house", "governor", "party"]):
        return "politics"
    if any(w in text for w in ["fed", "interest rate", "cpi", "inflation", "gdp", "unemployment"]):
        return "macro"
    if any(w in text for w in ["bitcoin", "ethereum", "solana", "xrp", "crypto", "btc", "eth"]):
        return "crypto"
    if any(w in text for w in ["vs.", "vs ", "mlb", "nba", "nfl", "nhl", "premier league", "liga", "match", "spread", "total", "over/under", "o/u"]):
        return "sports"
    if any(w in text for w in ["stock", "close above", "price of", "meta", "amazon", "palantir"]):
        return "stocks"
    return "other"


GENERIC_CATEGORY_PRIORS = {
    "politics": 0.50,
    "macro":    0.50,
    "crypto":   0.50,
    "sports":   0.50,
    "stocks":   0.50,
    "other":    0.50,
}


def estimate_edge_generic(
    market_info: dict,
    market_prob: float,
    override_priors: dict = None,
    use_llm: bool = True,
    use_news: bool = False,
) -> dict:
    """
    Generic, domain-agnostic edge estimator for any Polymarket market.

    Inputs:
      - market_info: full market dict from fetch_candidate_markets()
      - market_prob: implied YES probability (0-1)
      - override_priors: optional dict market_id -> prior probability
      - use_llm/use_news: kept for API compatibility; defaults conservative

    Returns:
      dict with keys: question, our_prob, edge, prior, market_prob, signal, direction, reasoning, ...
    """
    question = market_info.get("question") or market_info.get("title") or market_info.get("name") or ""
    market_id = market_info.get("id")
    end_date = market_info.get("end_date")

    # 1) Prior: per-market override, else generic category prior
    # Try runtime overrides (from OVERRIDE_PRIORS/set_override_prior)
    prior = None
    if market_id:
        p_eff = get_effective_prior(market_id)
        if p_eff is not None:
            prior = p_eff

    if prior is None:
        cat = classify_generic_category(market_info)
        prior = GENERIC_CATEGORY_PRIORS.get(cat, 0.50)
    else:
        cat = classify_generic_category(market_info)

    # 2) Optional news / LLM tilt (disabled by default for generic)
    # You can turn these on later by passing use_news/use_llm=True from caller.
    news_summary = ""
    reasoning = ""
    our_prob = prior

    if use_news:
        try:
            articles = fetch_news(question[:80])
            news_summary = summarize_articles(articles)
        except Exception:
            news_summary = ""
    else:
        news_summary = "News integration disabled for generic estimator."

    if use_llm and NAVIGATOR_KEY:
        try:
            # Re-use llm_score but feed generic category as 'domain'
            our_prob, reasoning = llm_score(question, news_summary, cat, prior, use_llm=True)
        except Exception as e:
            print(f"[generic llm_score error] {e}")
            our_prob = prior
            reasoning = "LLM failed, using prior only."
    else:
        # Simple deterministic tilt based on market price:
        # if market is far from 50%, assume some wisdom-of-crowds and nudge toward market_prob.
        # This keeps our_prob reasonable even without LLM/news.
        delta = market_prob - prior
        # shrink factor to avoid overfitting to price
        shrink = 0.5
        our_prob = max(0.01, min(0.99, prior + shrink * delta))
        reasoning = (
            f"Generic estimator: base prior={prior:.2f}, "
            f"nudged {shrink:.2f} toward market_prob={market_prob:.2f}."
        )

    # 3) Edge and signal strength
    edge = our_prob - market_prob
    abs_edge = abs(edge)
    if abs_edge >= 0.15:
        signal = "STRONG"
    elif abs_edge >= 0.08:
        signal = "MODERATE"
    elif abs_edge >= 0.04:
        signal = "WEAK"
    else:
        signal = "NONE"

    direction = "BUY YES" if edge > 0 else "BUY NO"

    # 4) Days to expiry (if available)
    days_left = None
    if end_date:
        try:
            ed = datetime.date.fromisoformat(str(end_date)[:10])
            days_left = (ed - datetime.date.today()).days
        except Exception:
            pass

    return {
        "question": question,
        "domain": cat,
        "prior": prior,
        "market_prob": market_prob,
        "our_prob": our_prob,
        "edge": edge,
        "signal": signal,
        "direction": direction if signal != "NONE" else "HOLD",
        "reasoning": reasoning,
        "news_summary": news_summary,
        "end_date": end_date,
        "days_left": days_left,
        "use_llm": use_llm,
        "use_news": use_news,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


def estimate_edge_smart_money(
    market_info: dict,
    market_prob: float,
    bankroll: float,
) -> dict:
    """Placeholder smart-money estimator.

    For now this just returns a minimal dict so callers can be wired up
    without breaking anything. Later we will have it call
    model.market_flow.get_smart_money_view once whale trades are available.
    """
    question = market_info.get("question") or market_info.get("title") or market_info.get("name") or ""
    return {
        "question": question,
        "our_prob": None,
        "edge": None,
        "source": "smart_money",
    }
