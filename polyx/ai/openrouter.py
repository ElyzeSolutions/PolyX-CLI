"""OpenRouter provider."""

from polyx.ai.base import BaseProvider


class OpenRouterProvider(BaseProvider):
    PROVIDER_NAME = "openrouter"
    BASE_URL = "https://openrouter.ai/api/v1"
    ENV_KEY = "OPENROUTER_API_KEY"
    DEFAULT_MODEL = "openai/gpt-5-nano"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        if model == "free":
            model = "openrouter/free"
        super().__init__(api_key, model=model)
