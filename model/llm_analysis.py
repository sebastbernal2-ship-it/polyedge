import json
import re
import os
import requests
from typing import Optional, Dict, Any
from config import LLM_API_KEY, ENABLE_LLM_ANALYSIS, LLM_MODEL, LLM_BASE_URL


def _format_wallet_cred(trade: dict) -> str:
    label = trade.get("_wallet_label", "Unknown")
    wr = trade.get("_wallet_win_rate")
    if not label or label == "Unknown" or wr is None:
        return "Wallet credibility: Unknown (insufficient historical data)."
    try:
        wr_pct = f"{float(wr):.0%}"
    except Exception:
        wr_pct = "unknown"
    return f"Wallet credibility: {label} with historical win rate around {wr_pct} on similar markets."


def _build_prompt(market_info: Dict[str, Any], whale_trade: Dict[str, Any], rules: Optional[str] = None) -> str:
    q = market_info.get("question") if isinstance(market_info, dict) else str(market_info)
    yes_price = market_info.get("yes_price", "unknown") if isinstance(market_info, dict) else "unknown"

    side = whale_trade.get("outcome") or whale_trade.get("side", "?")
    price = float(whale_trade.get("price", 0.5))
    size = float(whale_trade.get("size_usd", whale_trade.get("size", 0.0)))
    wallet_cred = _format_wallet_cred(whale_trade)

    prompt = f"""
You are a prediction market analyst. A large whale trade occurred on Polymarket.

Market: {whale_trade.get('market_label') or q}
Question: {q}
Current market YES price: {yes_price}
Resolution rules: {rules or 'N/A'}

Trade: {side} @ {price:.2f} for ${size:,.0f}
Wallet: {whale_trade.get('wallet')}
{wallet_cred}

Task:
- Given the whale trade direction, size, and wallet credibility, estimate the true probability of YES resolving as a float between 0.0 and 1.0.
- Explain your reasoning briefly.
- Provide a risk summary.
- Optionally suggest entry and exit YES prices if a clear edge exists.

Respond ONLY with valid JSON:
{{"p_yes": 0.0, "edge_comment": "...", "risks": "...", "entry": null, "exit": null}}
""".strip()
    return prompt


def _parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    try:
        if text.strip().startswith("{"):
            return json.loads(text)
        m = re.search(r"\{(?:.|\n)*\}", text)
        if m:
            return json.loads(m.group(0))
    except Exception:
        return None
    return None


def analyze_whale(market_info: Dict[str, Any], whale_trade: Dict[str, Any], rules: Optional[str] = None) -> Dict[str, Any]:
    """Analyze a whale trade via Navigator LLM and return structured output."""
    api_key = LLM_API_KEY or os.environ.get("NAVIGATOR_API_KEY", "")
    if not ENABLE_LLM_ANALYSIS or not api_key:
        return {
            "p_yes": 0.5,
            "edge_comment": "LLM analysis disabled or API key missing.",
            "risks": "no analysis",
            "entry": None,
            "exit": None,
            "raw": None,
        }

    prompt = _build_prompt(market_info, whale_trade, rules)

    try:
        url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "You are a concise prediction market analyst. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        }
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = _parse_json_from_text(text)
        if parsed:
            p = parsed.get("p_yes") or parsed.get("probability") or parsed.get("p")
            try:
                p = float(p) if p is not None else 0.5
            except Exception:
                p = 0.5
            return {
                "p_yes": max(0.0, min(1.0, p)),
                "edge_comment": parsed.get("edge_comment") or parsed.get("comment") or "",
                "risks": parsed.get("risks", ""),
                "entry": parsed.get("entry"),
                "exit": parsed.get("exit"),
                "raw": text,
            }

        m = re.search(r"([01]?(?:\.\d+))", text)
        if m:
            try:
                p = float(m.group(1))
                return {"p_yes": max(0.0, min(1.0, p)), "edge_comment": text[:300], "risks": "", "entry": None, "exit": None, "raw": text}
            except Exception:
                pass

        return {"p_yes": 0.5, "edge_comment": text[:300], "risks": "", "entry": None, "exit": None, "raw": text}

    except Exception as e:
        return {"p_yes": 0.5, "edge_comment": f"LLM call failed: {e}", "risks": "call error", "entry": None, "exit": None, "raw": None}
