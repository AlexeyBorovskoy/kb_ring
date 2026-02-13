from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from .config import OLLAMA_BASE_URL, OLLAMA_MODEL


@dataclass
class LlmAnswer:
    text: str


async def ollama_chat_completion(system: str, user: str, context: str, temperature: float = 0.1, max_tokens: int = 700) -> Optional[LlmAnswer]:
    """
    Минимальная интеграция с Ollama как fallback (локальные черновики).
    Используем /api/chat, формат совместим с ollama.
    """
    url = f"{OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "user", "content": "context\n" + (context or "")},
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code != 200:
            return None
        data = r.json()
        text = (((data.get("message") or {}).get("content")) or "").strip()
        if not text:
            return None
        return LlmAnswer(text=text)

