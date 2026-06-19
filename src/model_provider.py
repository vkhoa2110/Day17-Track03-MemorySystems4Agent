from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ProviderConfig:
    """Provider configuration shared by the agents."""

    provider: str
    model_name: str
    temperature: float
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    """Normalize provider names and common typos."""

    normalized = (value or "openai").strip().lower().replace("_", "-")
    aliases = {
        "anthorpic": "anthropic",
        "claude": "anthropic",
        "google": "gemini",
        "google-genai": "gemini",
        "google-generative-ai": "gemini",
        "gpt": "openai",
        "open-ai": "openai",
        "openrouter.ai": "openrouter",
        "local": "ollama",
        "openai-compatible": "custom",
    }
    provider = aliases.get(normalized, normalized)
    supported = {"openai", "custom", "gemini", "anthropic", "ollama", "openrouter"}
    if provider not in supported:
        raise ValueError(f"Unsupported provider '{value}'. Supported providers: {sorted(supported)}")
    return provider


def build_chat_model(config: ProviderConfig):
    """Instantiate a LangChain chat model for the selected provider.

    The lab's tests and offline benchmark do not require network access. This
    function is intentionally lazy so missing optional SDK packages only matter
    when live mode is actually used.
    """

    provider = normalize_provider(config.provider)

    if provider in {"openai", "custom"}:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise ImportError("Install langchain-openai to use OpenAI/custom providers.") from exc

        kwargs = {
            "model": config.model_name,
            "temperature": config.temperature,
        }
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if provider == "custom" and config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOpenAI(**kwargs)

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise ImportError("Install langchain-google-genai to use Gemini.") from exc

        kwargs = {"model": config.model_name, "temperature": config.temperature}
        if config.api_key:
            kwargs["google_api_key"] = config.api_key
        return ChatGoogleGenerativeAI(**kwargs)

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise ImportError("Install langchain-anthropic to use Anthropic.") from exc

        kwargs = {"model": config.model_name, "temperature": config.temperature}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        return ChatAnthropic(**kwargs)

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise ImportError("Install langchain-ollama to use Ollama.") from exc

        kwargs = {"model": config.model_name, "temperature": config.temperature}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        return ChatOllama(**kwargs)

    if provider == "openrouter":
        try:
            from langchain_openrouter import ChatOpenRouter
        except ImportError:
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as exc:
                raise ImportError(
                    "Install langchain-openrouter or langchain-openai to use OpenRouter."
                ) from exc

            return ChatOpenAI(
                model=config.model_name,
                temperature=config.temperature,
                api_key=config.api_key,
                base_url=config.base_url or "https://openrouter.ai/api/v1",
            )

        kwargs = {"model": config.model_name, "temperature": config.temperature}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        return ChatOpenRouter(**kwargs)

    raise ValueError(f"Unsupported provider '{config.provider}'.")
