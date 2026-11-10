from __future__ import annotations

from app.config import load_settings


def test_features_default_to_all_modules() -> None:
    settings = load_settings({"LCS_PROFILE": "test", "LCS_RELOAD": "false"})
    assert settings.features == ("chat", "account", "admin", "devices", "blog", "support")


def test_features_can_be_restricted() -> None:
    settings = load_settings(
        {
            "LCS_PROFILE": "test",
            "LCS_RELOAD": "false",
            "LCS_FEATURES": "chat, account, admin",
        }
    )
    assert settings.features == ("chat", "account", "admin")
