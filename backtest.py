import json, csv, os, random, math

# ============================================================
# PolyEdge Backtest  -  Fixed Simulation
#
# Fixes vs previous version:
#  1. Signal only fires when edge > MIN_EDGE (3%)  -- no negative-edge bets
#  2. Signal direction derived from edge sign, not random
#  3. Bet sized off CURRENT bankroll, not fixed $1000
#  4. Quarter-Kelly applied correctly per trade
# ============================================================

STARTING_BANKROLL  = 1000.0
SEED               = 99
N_MARKETS          = 100
MIN_EDGE           = 0.03   # only trade when |edge| > 3%
QUARTER_KELLY      = 0.25   # use 25% of full Kelly (standard risk management)
SMARTMONEY_ACC    = 0.62   # smart money accuracy when edge exists

random.seed(SEED)
os.makedirs("data", exist_ok=True)


def kelly_fraction(p, b=1.0):
    """Full Kelly fraction for a binary bet.
    p = win probability, b = net odds (1.0 for even-money).
    Returns fraction of bankroll to bet, capped at 25% full Kelly.
    """
    q = 1.0 - p
    f = (b * p - q) / b
    return max(0.0, f)  # raw Kelly -- we apply quarter-Kelly at bet time


market_names = [
    "Iran nuclear deal by Dec 2024?",
    "Iran protests reach capital?",
    "Iran sanctions lifted Q1 2025?",
    "Iran oil exports >2mb/d by year end?",
    "Iran presidential election held on time?",
    "Iran-US direct talks in 2024?",
    "Iran currency collapse?",
    "IAEA inspectors expelled from Iran?",
    "Iran missile test before elections?",
    "Iran internet shutdown >72hrs?",
]

print("Running PolyEdge backtest (fixed)...")
print(f"Bankroll: ${STARTING_BANKROLL:.0f} | Markets: {N_MARKETS} | Min edge: {MIN_EDGE*100:.0f}% | Quarter-Kelly\n")

bankroll = STARTING_BANKROLL
equity   = [round(bankroll, 2)]
results  = []

for i in range(N_MARKETS):
    name = market_names[i % len(market_names)] + f" [{i+1}]"

    # --- Simulate market state ---
    market_price = random.uniform(0.10, 0.90)
    volume       = random.uniform(5_000, 500_000)

    # Whale-implied probability: sometimes they have info, sometimes not
    has_info   = random.random() < 0.55          # 55% of markets have informative whale flow
    raw_edge   = random.uniform(-0.12, 0.18)     # raw deviation before filtering
    if not has_info:
        raw_edge = random.uniform(-0.04, 0.04)   # no info = near-zero edge

    implied_prob = max(0.03, min(0.97, market_price + raw_edge))
    edge         = implied_prob - market_price   # positive = whales lean YES

    # --- Signal logic (Fix 1 & 2) ---
    # Only bet when edge exceeds threshold; direction comes from edge sign
    if edge > MIN_EDGE:
        signal = "Buy Yes"
    elif edge < -MIN_EDGE:
        signal = "Buy No"
        edge   = abs(edge)          # display as positive magnitude
        implied_prob = market_price - abs(implied_prob - market_price)
    else:
        signal = "None"             # edge too small, skip

    # --- Sizing (Fix 3 & 4) ---
    if signal != "None":
        win_p    = SMARTMONEY_ACC + random.uniform(-0.06, 0.06)  # accuracy with noise
        win_p    = max(0.50, min(0.80, win_p))
        raw_f    = kelly_fraction(win_p)
        kelly_f  = raw_f * QUARTER_KELLY          # quarter-Kelly
        kelly_f  = min(kelly_f, 0.20)             # hard cap: never risk >20% per trade
        bet_size = bankroll * kelly_f             # FIX 3: use live bankroll
    else:
        win_p    = 0.50
        raw_f    = 0.0
        kelly_f  = 0.0
        bet_size = 0.0

    # --- Resolution ---
    resolved_yes = random.random() < (win_p if signal != "None" else 0.5)

    if signal == "Buy Yes":
        won = resolved_yes
    elif signal == "Buy No":
        won = not resolved_yes
    else:
        won = None

    # PnL: win = +bet_size, lose = -bet_size (binary market, ~even odds)
    if won is True:
        pnl = bet_size
        bankroll += pnl
    elif won is False:
        pnl = -bet_size
        bankroll += pnl
    else:
        pnl = 0.0

    if signal != "None":
        equity.append(round(bankroll, 2))

    results.append({
        "market":       name,
        "volume":       round(volume, 0),
        "market_price": round(market_price, 3),
        "implied_prob": round(implied_prob, 3),
        "edge":         round(edge, 4),
        "signal":       signal,
        "kelly_pct":    round(kelly_f * 100, 2),
        "bet_size":     round(bet_size, 2),
        "resolved_yes": resolved_yes,
        "won":          won,
        "pnl":          round(pnl, 2),
    })

# --- Save outputs ---
csv_path = "data/backtest_results.csv"
with open(csv_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=results[0].keys())
    w.writeheader()
    w.writerows(results)

with open("data/equity_curve.json", "w") as f:
    json.dump({"equity": equity, "timestamps": list(range(len(equity)))}, f)

# --- Summary ---
signaled  = [r for r in results if r["signal"] != "None"]
won_list  = [r for r in signaled if r["won"] is True]
lost_list = [r for r in signaled if r["won"] is False]
total_pnl = sum(r["pnl"] for r in signaled)
total_bet = sum(r["bet_size"] for r in signaled)
avg_edge  = sum(r["edge"] for r in signaled) / max(len(signaled), 1)

print("=" * 50)
print(f"  BACKTEST SUMMARY ({N_MARKETS} markets)")
print("=" * 50)
print(f"  Signals fired    : {len(signaled)} / {N_MARKETS} ({len(signaled)/N_MARKETS*100:.0f}%)")
print(f"  Wins / Losses    : {len(won_list)} / {len(lost_list)}")
print(f"  Win rate         : {len(won_list)/max(len(signaled),1)*100:.1f}%")
print(f"  Avg edge         : {avg_edge*100:+.2f}%")
print(f"  Total wagered    : ${total_bet:,.2f}")
print(f"  Total P&L        : ${total_pnl:+,.2f}")
print(f"  Return on capital: {total_pnl/STARTING_BANKROLL*100:+.1f}%")
print(f"  Final bankroll   : ${bankroll:,.2f}")
print(f"  Max drawdown     : ${min(equity) - STARTING_BANKROLL:,.2f}")
print("=" * 50)
print(f"\nSaved: {csv_path}  |  data/equity_curve.json")
