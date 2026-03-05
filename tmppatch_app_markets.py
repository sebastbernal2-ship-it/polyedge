from pathlib import Path

path = Path("dashboard/app.py")
text = path.read_text()

# 1) Import fetch_candidate_markets instead of getiranmarkets
text = text.replace(
    "from data.polymarket import getiranmarkets",
    "from data.polymarket import fetch_candidate_markets",
)

# 2) Replace the block that assigns markets
old_block = "with st.spinner(\"Fetching markets...\"):\n    markets = getiranmarkets()\n"
new_block = "with st.spinner(\"Fetching markets...\"):\n    markets = fetch_candidate_markets()\n"
if old_block not in text:
    raise SystemExit("expected getiranmarkets block not found; aborting patch")

text = text.replace(old_block, new_block)

path.write_text(text)
print("patched dashboard/app.py to use fetch_candidate_markets")
