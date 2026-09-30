from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/raw/otwarta.db"
    log_level: str = "INFO"
    rate_limit_dorzeczy: float = 2.0
    rate_limit_pch24: float = 1.0
    max_analysis_workers: int = 4
    ollama_base_url: str = "http://localhost:11434"
    primary_model: str = "llama3.1"
    secondary_model: str = "mistral-nemo"
