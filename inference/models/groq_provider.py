from __future__ import annotations

import time

from .base import LLMProvider, LLMResponse


class GroqProvider(LLMProvider):
    """Groq API provider (OpenAI-compatible). Uses openai AsyncOpenAI with Groq base_url.

    Supports models like:
    - llama-3.3-70b-versatile
    - llama-3.1-70b-versatile
    - mixtral-8x7b-32768
    - gemma2-9b-it
    - llama3-70b-8192
    Env: GROQ_API_KEY, GROQ_MODEL
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        if not api_key:
            raise ValueError("GROQ_API_KEY not set")
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise ImportError("pip install openai  (Groq uses OpenAI-compatible client)") from e
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
        input_tokens = usage.prompt_tokens if usage and usage.prompt_tokens else len(prompt) // 4
        output_tokens = usage.completion_tokens if usage and usage.completion_tokens else len(content) // 4
        return LLMResponse(
            content=content,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self.model_name,
            latency_ms=latency_ms,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        # Groq pricing (approx, varies by model). Use conservative estimate:
        # llama-3.3-70b: ~$0.59 / 1M input, $0.79 / 1M output
        # fallback to generic if model specific not known
        pricing = {
            "llama-3.3-70b-versatile": (0.59, 0.79),
            "llama-3.1-70b-versatile": (0.59, 0.79),
            "llama3-70b-8192": (0.59, 0.79),
            "llama-3.1-8b-instant": (0.05, 0.08),
            "mixtral-8x7b-32768": (0.24, 0.24),
            "gemma2-9b-it": (0.20, 0.20),
            "openai/gpt-oss-120b" : (0.15,0.60)
        }
        inp, out = pricing.get(self.model_name, (0.59, 0.79))
        return (input_tokens * inp + output_tokens * out) / 1_000_000
