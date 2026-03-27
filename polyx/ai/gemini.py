"""Google Gemini provider."""

from polyx.ai.base import BaseProvider


class GeminiProvider(BaseProvider):
    PROVIDER_NAME = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
    ENV_KEY = "GOOGLE_API_KEY"
    DEFAULT_MODEL = "gemini-flash-lite-latest"
