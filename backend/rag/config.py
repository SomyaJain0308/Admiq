from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings): # Defined here used in rag/agent.py, main.py Fetched from .env

    # LLM Configuration
    gemini_api_key: str = ""
    primary_model: str = "gemini-3.5-flash" # NOTE: In production change to deepseek.
    fallback_model: str = "gemini-3.5-flash"
    query_model: str = "gemini-2.5-flash" # NOTE: In production change to deepseek.

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "CollegeChatbot"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    max_primary_retries: int = 2
    max_fallback_retries: int = 2
    max_retrieval_retries: int = 2
    session_token_budget: int = 200000
    retrieval_distance_threshold: float = 0.45

    # Whatsapp Webhook
    whatsapp_verify_token: str
    meta_app_secret: str
    whatsapp_access_token: str

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    

@lru_cache() # Cached settings instance - loaded once, reused everywhere
def get_settings() -> Settings:
    return Settings()