from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from model_provider import ProviderConfig, normalize_provider


@dataclass
class LabConfig:
    """Shared configuration for paths, memory policy, and model providers."""

    base_dir: Path
    data_dir: Path
    state_dir: Path
    compact_threshold_tokens: int
    compact_keep_messages: int
    model: ProviderConfig
    judge_model: ProviderConfig


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Load environment variables and return a complete lab config."""

    root = (base_dir or Path(__file__).resolve().parent.parent).resolve()

    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv:
        load_dotenv(root / ".env")

    data_dir = Path(os.getenv("LAB_DATA_DIR", root / "data")).resolve()
    state_dir = Path(os.getenv("LAB_STATE_DIR", root / "state")).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)

    provider = normalize_provider(os.getenv("LLM_PROVIDER", "openai"))
    judge_provider = normalize_provider(os.getenv("JUDGE_LLM_PROVIDER", provider))

    defaults = {
        "openai": "gpt-4o-mini",
        "custom": "gpt-4o-mini",
        "gemini": "gemini-1.5-flash",
        "anthropic": "claude-3-5-haiku-latest",
        "ollama": "llama3.1",
        "openrouter": "openai/gpt-4o-mini",
    }

    def api_key_for(selected: str, prefix: str = "") -> str | None:
        env_prefix = f"{prefix}_" if prefix else ""
        if selected == "openai":
            return os.getenv(f"{env_prefix}OPENAI_API_KEY")
        if selected == "custom":
            return os.getenv(f"{env_prefix}CUSTOM_API_KEY") or os.getenv(f"{env_prefix}OPENAI_API_KEY")
        if selected == "gemini":
            return os.getenv(f"{env_prefix}GEMINI_API_KEY") or os.getenv(f"{env_prefix}GOOGLE_API_KEY")
        if selected == "anthropic":
            return os.getenv(f"{env_prefix}ANTHROPIC_API_KEY")
        if selected == "openrouter":
            return os.getenv(f"{env_prefix}OPENROUTER_API_KEY")
        return None

    def base_url_for(selected: str, prefix: str = "") -> str | None:
        env_prefix = f"{prefix}_" if prefix else ""
        if selected == "custom":
            return os.getenv(f"{env_prefix}CUSTOM_BASE_URL")
        if selected == "ollama":
            return os.getenv(f"{env_prefix}OLLAMA_BASE_URL", "http://localhost:11434")
        if selected == "openrouter":
            return os.getenv(f"{env_prefix}OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        return None

    model = ProviderConfig(
        provider=provider,
        model_name=os.getenv("LLM_MODEL", defaults[provider]),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        api_key=api_key_for(provider),
        base_url=base_url_for(provider),
    )
    judge_model = ProviderConfig(
        provider=judge_provider,
        model_name=os.getenv("JUDGE_LLM_MODEL", os.getenv("LLM_MODEL", defaults[judge_provider])),
        temperature=float(os.getenv("JUDGE_LLM_TEMPERATURE", "0")),
        api_key=api_key_for(judge_provider, "JUDGE") or api_key_for(judge_provider),
        base_url=base_url_for(judge_provider, "JUDGE") or base_url_for(judge_provider),
    )

    return LabConfig(
        base_dir=root,
        data_dir=data_dir,
        state_dir=state_dir,
        compact_threshold_tokens=int(os.getenv("COMPACT_THRESHOLD_TOKENS", "900")),
        compact_keep_messages=int(os.getenv("COMPACT_KEEP_MESSAGES", "8")),
        model=model,
        judge_model=judge_model,
    )
