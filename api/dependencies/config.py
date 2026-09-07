from __future__ import annotations

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_mock: bool = True
    llm_provider: str = "mock"  # mock | groq | openai
    # Groq (primary for this project)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # OpenAI (kept for backward compat)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    sandbox_mode: str = "auto"  # auto | docker | local
    workdir: str = r"C:\Users\PRIYAN~1\AppData\Local\Temp\repopilot"
    docker_image: str = "python:3.11-slim"
    docker_memory_limit: str = "1g"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    model_config = SettingsConfigDict(
        env_file = ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Allow LLM_MOCK env to override
    mock_env = os.getenv("LLM_MOCK")
    s = Settings()
    if mock_env is not None:
        s.llm_mock = mock_env.lower() in ("1", "true", "yes")
        if s.llm_mock:
            s.llm_provider = "mock"
    return s
