import pytest
from pydantic_core import ValidationError

from otwarta.config.settings import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    s = Settings()
    assert s.gemini_api_key.get_secret_value() == "test-key"
    assert s.database_url == "sqlite:///test.db"
    assert s.rate_limit_dorzeczy == 2.0
    assert s.rate_limit_pch24 == 1.0
    assert s.max_analysis_workers == 8


def test_settings_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
