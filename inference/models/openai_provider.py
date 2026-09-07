from __future__ import annotations

import time

from .base import LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise ImportError("pip install openai") from e
        self.client = AsyncOpenAI(api_key=api_key)
        self.model_name = model

    async def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> LLMResponse:
        start = time.time()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        latency_ms = (time.time() - start) * 1000
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        input_tokens = usage.prompt_tokens if usage else len(prompt) // 4
        output_tokens = usage.completion_tokens if usage else len(content) // 4
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_name,
            latency_ms=latency_ms,
        )
