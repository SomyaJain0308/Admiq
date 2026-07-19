from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):

    # LLM Configuration
    gemini_api_key: str
    primary_model: str = "gemini-3.5-flash"
    fallback_model: str = "gemini-2.5-flash"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "CollegeChatbot"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    rate_limit: str = "20/minute"
    cache_ttl_seconds: int = 300
    max_retries: int = 3

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