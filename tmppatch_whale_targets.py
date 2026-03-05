from pathlib import Path

path = Path("dashboard/whalemonitor.py")
text = path.read_text()

old = '''TARGETMARKETS: Dict[str, str] = {
    "Iranian regime fall by March 31": "0x61ce3773237a948584e422de72265f937034af418a8b703e3a860ea62e59ff36",
    "US x Iran ceasefire by March 31": "0x74d513ded76c21815373eae49004f36291d958b034087e7bb3669f156e3d116e",
    "Iran closes Strait of Hormuz by March 31": "0x561cd8d035bac38ed04e23d7882a126da38d7ead9d6679f722ad62c0c9d54ad2",
}
'''

new = '''from data.polymarket import fetch_candidate_markets

def get_all_target_markets() -> Dict[str, str]:
    """
    Build a dynamic mapping from question text -> conditionId
    using fetch_candidate_markets() so we don't maintain IDs by hand.
    """
    markets = fetch_candidate_markets()
    out: Dict[str, str] = {}
    for m in markets:
        mid = m.get("id")
        label = m.get("question")
        if mid and label:
            out[str(label)] = str(mid)
    return out

TARGETMARKETS: Dict[str, str] = get_all_target_markets()
'''

if old not in text:
    raise SystemExit("expected TARGETMARKETS block not found; aborting patch")

text = text.replace(old, new)
path.write_text(text)
print("patched dashboard/whalemonitor.py to use dynamic target markets")
