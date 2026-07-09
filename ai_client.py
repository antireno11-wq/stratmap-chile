import os
import logging
import requests

logger = logging.getLogger("stratmap.ai_client")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_FREE_MODEL = "openrouter/free"

def _call_anthropic(api_key: str, prompt: str, system: str = None, max_tokens: int = 1000, model: str = None) -> str:
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


def call_llm(
    prompt: str,
    system: str = None,
    max_tokens: int = 1000,
    model: str = None
) -> str:
    """
    Envía una consulta a la API de IA.
    Prioriza OpenRouter si OPENROUTER_API_KEY está configurada,
    con un fallback automático a Anthropic ante fallos de OpenRouter.
    """
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    
    if openrouter_key:
        model_name = os.getenv("OPENROUTER_MODEL", DEFAULT_FREE_MODEL)
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
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
            # Fallback de emergencia a Anthropic si la key está disponible
            anthropic_key = os.getenv("ANTHROPIC_API_KEY")
            if anthropic_key:
                logger.info("[ai_client] Intentando fallback de emergencia a Anthropic...")
                try:
                    return _call_anthropic(anthropic_key, prompt, system, max_tokens, model)
                except Exception as ae:
                    logger.error(f"[ai_client] Fallback a Anthropic también falló: {ae}")
            raise
    else:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_key:
            raise ValueError("No se encontró OPENROUTER_API_KEY ni ANTHROPIC_API_KEY en las variables de entorno.")
        return _call_anthropic(anthropic_key, prompt, system, max_tokens, model)
