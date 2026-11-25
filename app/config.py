"""App settings.

All settings come from environment variables or the .env file.
Never write secrets (like API keys) directly in the code.
"""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    # Which AI to use: "claude" (paid, best), "gemini" (free plan, cloud), or "ollama" (free, your computer)
    llm_provider: Literal["claude", "gemini", "ollama"] = "claude"

    # Claude settings
    anthropic_api_key: str | None = None  # if empty, the SDK reads ANTHROPIC_API_KEY itself
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "medium"  # low | medium | high  (more effort = smarter but slower/costlier)
    llm_max_tokens: int = 16000

    # Gemini settings (free key: https://aistudio.google.com/apikey)
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"  # always points to Google's newest fast "Flash" model

    # Ollama settings
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"  # small (3B) model, works on 8-16 GB RAM

    # Where industry config files live (one YAML file = one industry)
    industries_dir: Path = BASE_DIR / "industries"

    # Safety limit: max characters in one user message
    max_message_chars: int = 8000


settings = Settings()
