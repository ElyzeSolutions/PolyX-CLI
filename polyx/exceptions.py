"""PolyX exception hierarchy."""


class PolyXError(Exception):
    """Base exception for all PolyX errors."""


class ConfigurationError(PolyXError):
    """Missing or invalid configuration (API keys, env vars)."""


class AuthenticationError(PolyXError):
    """Authentication failed — invalid or expired credentials."""


class RateLimitError(PolyXError):
    """Rate limit exceeded after all retries."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class NotSupportedError(PolyXError):
    """Operation not supported by the current client."""
