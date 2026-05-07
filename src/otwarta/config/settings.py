from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    llm_api_key: SecretStr
    database_url: str = "sqlite:///./data/raw/otwarta.db"
    log_level: str = "INFO"
    rate_limit_dorzeczy: float = 2.0
    rate_limit_pch24: float = 1.0
    max_analysis_workers: int = 8
