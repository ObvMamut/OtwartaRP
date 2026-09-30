from otwarta.config.settings import Settings


def test_settings_loads_defaults():
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.database_url == "sqlite:///./data/raw/otwarta.db"
    assert s.rate_limit_dorzeczy == 2.0
    assert s.rate_limit_pch24 == 1.0
    assert s.max_analysis_workers == 4
    assert s.ollama_base_url == "http://localhost:11434"
    assert s.primary_model == "llama3.1"
    assert s.secondary_model == "mistral-nemo"


def test_settings_overrides_from_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://myhost:11434")
    monkeypatch.setenv("PRIMARY_MODEL", "llama3.2")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
    s = Settings()
    assert s.ollama_base_url == "http://myhost:11434"
    assert s.primary_model == "llama3.2"
    assert s.database_url == "sqlite:///test.db"
