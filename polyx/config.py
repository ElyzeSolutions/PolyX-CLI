"""Configuration management — env vars and config file support."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv
from yaml import YAMLError

from polyx.exceptions import ConfigurationError


def _env_first(*keys: str) -> str:
    """Return the first non-empty environment value from the provided keys."""
    for key in keys:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _data_dir() -> Path:
    """Return the PolyX data directory, creating it if needed."""
    configured = os.environ.get("POLYX_DATA_DIR", "").strip()
    path = Path(configured) if configured else Path.home() / ".polyx"
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
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    openrouter_api_key: str = ""
    gemini_api_key: str = ""
    disabled_subscription_providers: tuple[str, ...] = ()

    daily_budget: float = 1.0
    cache_ttl: int = 900
    data_dir: Path = field(default_factory=_data_dir)

    @classmethod
    def load(cls) -> Config:
        """Load config from file, then let explicit environment values win."""
        load_dotenv(Path.cwd() / ".env", override=False)
        cfg = cls(
            x_bearer_token=_env_first("X_BEARER_TOKEN"),
            auth_token=_env_first("AUTH_TOKEN", "TWITTER_AUTH_TOKEN"),
            ct0=_env_first("CT0", "TWITTER_CT0"),
            xai_api_key=_env_first("XAI_API_KEY", "GROK_API_KEY"),
            openai_api_key=_env_first("OPENAI_API_KEY"),
            anthropic_api_key=_env_first("ANTHROPIC_API_KEY"),
            openrouter_api_key=_env_first("OPENROUTER_API_KEY"),
            gemini_api_key=_env_first("GOOGLE_API_KEY", "GEMINI_API_KEY"),
            disabled_subscription_providers=tuple(
                item.strip()
                for item in os.environ.get(
                    "POLYX_DISABLED_SUBSCRIPTION_PROVIDERS", ""
                ).split(",")
                if item.strip()
            ),
            daily_budget=float(os.environ.get("POLYX_DAILY_BUDGET", "1.0")),
            cache_ttl=int(os.environ.get("POLYX_CACHE_TTL", "900")),
        )

        config_file = cfg.data_dir / "config.yml"
        if config_file.exists():
            try:
                with open(config_file) as f:
                    data = yaml.safe_load(f) or {}
            except YAMLError as error:
                raise ConfigurationError(f"Invalid YAML in {config_file}") from error
            if not isinstance(data, dict):
                raise ConfigurationError(f"Invalid mapping in {config_file}")
            environment_keys = {
                "x_bearer_token": ("X_BEARER_TOKEN",),
                "auth_token": ("AUTH_TOKEN", "TWITTER_AUTH_TOKEN"),
                "ct0": ("CT0", "TWITTER_CT0"),
                "xai_api_key": ("XAI_API_KEY", "GROK_API_KEY"),
                "openai_api_key": ("OPENAI_API_KEY",),
                "anthropic_api_key": ("ANTHROPIC_API_KEY",),
                "openrouter_api_key": ("OPENROUTER_API_KEY",),
                "gemini_api_key": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
                "disabled_subscription_providers": (
                    "POLYX_DISABLED_SUBSCRIPTION_PROVIDERS",
                ),
                "daily_budget": ("POLYX_DAILY_BUDGET",),
                "cache_ttl": ("POLYX_CACHE_TTL",),
            }
            for key, value in data.items():
                if key == "data_dir":
                    continue
                explicit_environment = any(
                    os.environ.get(name, "").strip()
                    for name in environment_keys.get(key, ())
                )
                if hasattr(cfg, key) and value is not None and not explicit_environment:
                    try:
                        if key == "daily_budget":
                            value = float(value)
                        elif key == "cache_ttl":
                            value = int(value)
                        elif key == "disabled_subscription_providers":
                            if not isinstance(value, (list, tuple)) or any(
                                not isinstance(item, str) for item in value
                            ):
                                raise TypeError
                            value = tuple(value)
                    except (TypeError, ValueError) as error:
                        raise ConfigurationError(
                            f"Invalid {key} value in {config_file}"
                        ) from error
                    setattr(cfg, key, value)

        return cfg

    def save_browser_cookies(self, auth_token: str, ct0: str) -> Path:
        """Persist GraphQL browser cookies in the private PolyX config file."""
        config_file = self.data_dir / "config.yml"
        data: dict[str, object] = {}
        if config_file.exists():
            try:
                with open(config_file) as file:
                    loaded = yaml.safe_load(file) or {}
            except YAMLError as error:
                raise ConfigurationError(f"Invalid YAML in {config_file}") from error
            if not isinstance(loaded, dict):
                raise ConfigurationError(f"Invalid mapping in {config_file}")
            data.update(loaded)
        data.update({"auth_token": auth_token, "ct0": ct0})

        descriptor, temporary_name = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w") as file:
                yaml.safe_dump(data, file, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, config_file)
            os.chmod(config_file, 0o600)
        except Exception:
            with suppress(OSError):
                os.unlink(temporary_name)
            raise
        return config_file

    def save_disabled_subscription_providers(
        self, providers: tuple[str, ...]
    ) -> Path:
        """Persist operator subscription opt-outs without touching credentials."""

        config_file = self.data_dir / "config.yml"
        data: dict[str, object] = {}
        if config_file.exists():
            try:
                with open(config_file) as file:
                    loaded = yaml.safe_load(file) or {}
            except YAMLError as error:
                raise ConfigurationError(f"Invalid YAML in {config_file}") from error
            if not isinstance(loaded, dict):
                raise ConfigurationError(f"Invalid mapping in {config_file}")
            data.update(loaded)
        data["disabled_subscription_providers"] = sorted(set(providers))

        descriptor, temporary_name = tempfile.mkstemp(dir=self.data_dir, suffix=".tmp")
        try:
            with os.fdopen(descriptor, "w") as file:
                yaml.safe_dump(data, file, sort_keys=True)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, config_file)
            os.chmod(config_file, 0o600)
        except Exception:
            with suppress(OSError):
                os.unlink(temporary_name)
            raise
        self.disabled_subscription_providers = tuple(sorted(set(providers)))
        return config_file

    @property
    def cache_dir(self) -> Path:
        configured = os.environ.get("POLYX_CACHE_DIR", "").strip()
        path = Path(configured) if configured else self.data_dir / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def reports_dir(self) -> Path:
        path = self.data_dir / "reports"
        path.mkdir(parents=True, exist_ok=True)
        return path
