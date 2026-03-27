"""Configuration management — env vars and config file support."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


def _env_first(*keys: str) -> str:
    """Return the first non-empty environment value from the provided keys."""
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _data_dir() -> Path:
    """Return the PolyX data directory, creating it if needed."""
    path = Path(os.environ.get("POLYX_DATA_DIR", Path.home() / ".polyx"))
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class Config:
    """PolyX runtime configuration."""

    # X API v2
    x_bearer_token: str = ""

    # GraphQL (cookie-based)
    auth_token: str = ""
    ct0: str = ""

    # AI providers
    xai_api_key: str = ""
    openrouter_api_key: str = ""
    gemini_api_key: str = ""

    daily_budget: float = 1.0
    cache_ttl: int = 900
    data_dir: Path = field(default_factory=_data_dir)

    @classmethod
    def load(cls) -> Config:
        """Load config from env vars, then overlay with config file if present."""
        cfg = cls(
            x_bearer_token=_env_first("X_BEARER_TOKEN"),
            auth_token=_env_first("AUTH_TOKEN", "TWITTER_AUTH_TOKEN"),
            ct0=_env_first("CT0", "TWITTER_CT0"),
            xai_api_key=_env_first("XAI_API_KEY", "GROK_API_KEY"),
            openrouter_api_key=_env_first("OPENROUTER_API_KEY"),
            gemini_api_key=_env_first("GOOGLE_API_KEY", "GEMINI_API_KEY"),
            daily_budget=float(os.environ.get("POLYX_DAILY_BUDGET", "1.0")),
            cache_ttl=int(os.environ.get("POLYX_CACHE_TTL", "900")),
        )

        config_file = cfg.data_dir / "config.yml"
        if config_file.exists():
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
            for key, value in data.items():
                if hasattr(cfg, key) and value is not None:
                    setattr(cfg, key, value)

        return cfg

    @property
    def cache_dir(self) -> Path:
        path = Path(os.environ.get("POLYX_CACHE_DIR", self.data_dir / "cache"))
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reports_dir(self) -> Path:
        path = self.data_dir / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path
