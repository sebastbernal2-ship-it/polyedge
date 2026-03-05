from data.polymarket import fetch_candidate_markets
from model.estimator import estimate_edge

markets = fetch_candidate_markets()
print("markets fetched:", len(markets))

override_priors = {}
use_llm = True
use_news = True

for m in markets[:5]:
    market_prob = m.get("yes_price") or m.get("probability")
    if market_prob is None:
        continue
    market_prob = float(market_prob)

    est = estimate_edge(
        market_info=m,
        market_prob=market_prob,
        override_priors=override_priors,
        use_llm=use_llm,
        use_news=use_news,
    )
    our_prob = est.get("our_prob")
    edge = est.get("edge")

    print("----")
    print("Q:", m.get("question") or m.get("title") or m.get("name"))
    print("market_prob:", market_prob)
    print("our_prob:", our_prob)
    print("edge:", edge)
