from pathlib import Path

from dotenv import load_dotenv as real_load_dotenv

from polyx import config as config_module


def test_config_loads_local_dotenv_without_overriding_environment(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        "X_BEARER_TOKEN=dotenv-token\nPOLYX_DAILY_BUDGET=0.75\n"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("X_BEARER_TOKEN", "exported-token")
    monkeypatch.delenv("POLYX_DAILY_BUDGET", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", real_load_dotenv)

    config = config_module.Config.load()

    assert config.x_bearer_token == "exported-token"
    assert config.daily_budget == 0.75


def test_empty_directory_values_in_example_keep_private_defaults(monkeypatch, tmp_path):
    example = Path(__file__).parents[1] / ".env.example"
    (tmp_path / ".env").write_text(example.read_text())
    private_home = tmp_path / "home"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("POLYX_DATA_DIR", raising=False)
    monkeypatch.delenv("POLYX_CACHE_DIR", raising=False)
    monkeypatch.setattr(config_module.Path, "home", classmethod(lambda cls: private_home))
    monkeypatch.setattr(config_module, "load_dotenv", real_load_dotenv)

    config = config_module.Config.load()

    assert config.data_dir == private_home / ".polyx"
    assert config.cache_dir == private_home / ".polyx" / "cache"


def test_explicit_environment_overrides_imported_cookie_config(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "auth_token: imported-auth\nct0: imported-csrf\n"
    )
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AUTH_TOKEN", "environment-auth")
    monkeypatch.setenv("CT0", "environment-csrf")

    config = config_module.Config.load()

    assert config.auth_token == "environment-auth"
    assert config.ct0 == "environment-csrf"


def test_config_file_cannot_redirect_credential_storage(monkeypatch, tmp_path):
    (tmp_path / "config.yml").write_text(
        "data_dir: elsewhere\nauth_token: imported-auth\nct0: imported-csrf\n"
    )
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))

    config = config_module.Config.load()
    destination = config.save_browser_cookies("new-auth", "new-csrf")

    assert config.data_dir == tmp_path
    assert destination == tmp_path / "config.yml"
    assert config_module.Config.load().auth_token == "new-auth"


def test_subscription_opt_out_is_private_and_persistent(monkeypatch, tmp_path):
    monkeypatch.setenv("POLYX_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("POLYX_DISABLED_SUBSCRIPTION_PROVIDERS", raising=False)
    config = config_module.Config.load()

    destination = config.save_disabled_subscription_providers(
        ("claude-subscription", "claude-subscription")
    )

    assert destination.stat().st_mode & 0o077 == 0
    assert config_module.Config.load().disabled_subscription_providers == (
        "claude-subscription",
    )
