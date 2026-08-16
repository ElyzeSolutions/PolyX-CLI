"""OpenAI API-key provider."""

from polyx.ai.base import BaseProvider


class OpenAIProvider(BaseProvider):
    PROVIDER_NAME = "openai"
    BASE_URL = "https://api.openai.com/v1"
    ENV_KEY = "OPENAI_API_KEY"
    DEFAULT_MODEL = "gpt-5.6-luna"
