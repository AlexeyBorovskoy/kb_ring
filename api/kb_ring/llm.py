from dataclasses import dataclass
from typing import Optional

import httpx

from .config import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL


@dataclass
class LlmAnswer:
    text: str


async def openai_chat_completion(system: str, user: str, context: str, temperature: float = 0.1, max_tokens: int = 700) -> Optional[LlmAnswer]:
    """
    Вызов ChatGPT/OpenAI Chat Completions.

    Важно:
    - вызывать LLM только после retrieval;
    - в `context` передавать только top-K чанков (без полного документа);
    - параметры (ключ/модель/base_url) берутся из переменных окружения.
    """
    if not OPENAI_API_KEY:
        return None
    url = f"{OPENAI_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OPENAI_MODEL,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "user", "content": "context\n" + context},
        ],
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        if r.status_code != 200:
            return None
        data = r.json()
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        if not text:
            return None
        return LlmAnswer(text=text)


async def llm_chat_completion(system: str, user: str, context: str, temperature: float = 0.1, max_tokens: int = 700, allow_ollama_fallback: bool = False) -> Optional[LlmAnswer]:
    """
    Единая точка вызова LLM:
    - OpenAI (если есть ключ)
    - (опц.) Ollama fallback (локальные черновики)
    """
    if OPENAI_API_KEY:
        try:
            return await openai_chat_completion(system=system, user=user, context=context, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            # Не роняем API из-за внешнего LLM-провайдера.
            return None
    if allow_ollama_fallback:
        try:
            from .ollama import ollama_chat_completion  # lazy import
        except Exception:
            return None
        try:
            ans = await ollama_chat_completion(system=system, user=user, context=context, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            # Если Ollama недоступна, возвращаем None и позволяем вызывающему отдать fallback-ответ.
            return None
        return LlmAnswer(text=ans.text) if ans else None
    return None
