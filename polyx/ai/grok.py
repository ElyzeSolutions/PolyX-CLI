"""xAI Grok provider."""

from polyx.ai.base import BaseProvider


class GrokProvider(BaseProvider):
    PROVIDER_NAME = "grok"
    BASE_URL = "https://api.x.ai/v1"
    ENV_KEY = "XAI_API_KEY"
    DEFAULT_MODEL = "grok-4-1-fast-reasoning"
