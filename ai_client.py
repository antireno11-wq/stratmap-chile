import os
import logging
import requests

logger = logging.getLogger("stratmap.ai_client")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_FREE_MODEL = "openrouter/free"

def call_llm(
    prompt: str,
    system: str = None,
    max_tokens: int = 1000,
    model: str = None
) -> str:
    """
    Envía una consulta a la API de IA.
    Prioriza OpenRouter si OPENROUTER_API_KEY está configurada,
    con un fallback compatible hacia Anthropic si se detecta ANTHROPIC_API_KEY.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    is_openrouter = True
    
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No se encontró OPENROUTER_API_KEY ni ANTHROPIC_API_KEY en las variables de entorno.")
        is_openrouter = False

    if is_openrouter:
        model_name = os.getenv("OPENROUTER_MODEL", DEFAULT_FREE_MODEL)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://stratmap.cl",
            "X-Title": "Stratmap",
        }
        
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model_name,
            "messages": messages,
            "max_tokens": max_tokens
        }

        try:
            resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"[ai_client] Error llamando a OpenRouter: {e}")
            raise
    else:
        # Fallback a Anthropic directo
        model_name = model or "claude-haiku-4-5-20251001"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model_name,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=45)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()
        except Exception as e:
            logger.error(f"[ai_client] Error llamando a Anthropic: {e}")
            raise
