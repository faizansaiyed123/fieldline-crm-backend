import pytest

from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "Fieldline CRM"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_settings_accept_token_lifetime_boundaries() -> None:
    lower = Settings(access_token_expire_minutes=5, refresh_token_expire_days=1)
    upper = Settings(access_token_expire_minutes=60, refresh_token_expire_days=30)

    assert lower.access_token_expire_minutes == 5
    assert lower.refresh_token_expire_days == 1
    assert upper.access_token_expire_minutes == 60
    assert upper.refresh_token_expire_days == 30


@pytest.mark.parametrize(
    ("setting_name", "value"),
    [
        ("access_token_expire_minutes", 4),
        ("access_token_expire_minutes", 61),
        ("refresh_token_expire_days", 0),
        ("refresh_token_expire_days", 31),
    ],
)
def test_settings_reject_token_lifetimes_outside_supported_range(
    setting_name: str, value: int
) -> None:
    with pytest.raises(ValueError):
        Settings(**{setting_name: value})
