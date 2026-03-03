import json
import re
import requests
import os
from typing import Optional, Dict, Any
from config import LLM_API_KEY, ENABLE_LLM_ANALYSIS, LLM_PROVIDER, LLM_MODEL


def _build_prompt(market_info: Dict[str, Any], whale_trade: Dict[str, Any], rules: Optional[str] = None) -> str:
    q = market_info.get("question") if isinstance(market_info, dict) else str(market_info)
    prompt = f"""
You are a market analyst. A large trade occurred on Polymarket.
Market: {whale_trade.get('market_label')} (id: {whale_trade.get('market_id')})
Question: {q}
Resolution rules: {rules or 'N/A'}

Trade: {whale_trade.get('side')} @ {whale_trade.get('price'):.2%} for ${whale_trade.get('size_usd'):,.0f}
Wallet: {whale_trade.get('wallet')}
Timestamp: {whale_trade.get('timestamp')}

Task:
- Provide a short probability estimate for the traded side as a float between 0.0 and 1.0 and explain reasoning.
- Provide short risk summary and a brief comment describing any perceived edge.
- Optionally suggest entry and exit prices (absolute YES prices) if relevant.

Respond preferably with JSON containing keys: p_yes, edge_comment, risks, entry (optional), exit (optional).
""".strip()
    return prompt


def _parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    # Try to locate a JSON block inside text
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
    """Analyze a whale trade via an LLM and return structured output.

    Returns dict:
      - p_yes: float
      - edge_comment: str
      - risks: str
      - entry: Optional[float]
      - exit: Optional[float]

    If LLM disabled or key missing, returns a dummy response and logs a warning.
    """
    if not ENABLE_LLM_ANALYSIS or not LLM_API_KEY:
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
        if LLM_PROVIDER.lower() == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
            payload = {
                "model": LLM_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a concise market analyst."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 400,
            }
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            text = data["choices"][0]["message"]["content"].strip()
        else:
            # Unknown provider — fallback to a thin request if supported
            return {
                "p_yes": 0.5,
                "edge_comment": f"Provider {LLM_PROVIDER} not implemented.",
                "risks": "provider not implemented",
                "entry": None,
                "exit": None,
                "raw": None,
            }

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

        # If no JSON, try to extract a lone probability float from the text
        m = re.search(r"([01]?(?:\.\d+))", text)
        if m:
            try:
                p = float(m.group(1))
                return {"p_yes": max(0.0, min(1.0, p)), "edge_comment": text[:300], "risks": "", "entry": None, "exit": None, "raw": text}
            except Exception:
                pass

        # fallback dummy
        return {"p_yes": 0.5, "edge_comment": text[:300], "risks": "", "entry": None, "exit": None, "raw": text}

    except Exception as e:
        return {"p_yes": 0.5, "edge_comment": f"LLM call failed: {e}", "risks": "call error", "entry": None, "exit": None, "raw": None}
