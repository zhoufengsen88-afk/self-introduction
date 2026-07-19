from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "local"
    database_url: str = "postgresql+psycopg://self_intro:self_intro@127.0.0.1:5432/self_intro"
    cors_origins: list[str] = ["http://127.0.0.1:3000", "http://localhost:3000"]
    rag_backend: str = "memory"
    embedding_provider: str = "hashing"
    answer_generator: str = "deterministic"
    llm_provider: str = "openai-compatible"
    llm_base_url: str = ""
    llm_api_key: SecretStr | None = None
    llm_model: str = ""
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 30.0
    llm_prompt_cost_per_1k: float = 0.0
    llm_completion_cost_per_1k: float = 0.0
    lite_llmops_enabled: bool = False
    lite_llmops_base_url: str = "http://127.0.0.1:8001"
    lite_llmops_app_id: int | None = None
    lite_llmops_api_key: SecretStr | None = None
    lite_llmops_model_name: str = "self-introduction-agentic-rag"
    lite_llmops_timeout_seconds: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
