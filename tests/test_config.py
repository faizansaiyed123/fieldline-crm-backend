from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()
    assert settings.app_name == "Fieldline CRM"
    assert settings.api_prefix == "/api/v1"
    assert settings.database_url.startswith("postgresql+psycopg://")
