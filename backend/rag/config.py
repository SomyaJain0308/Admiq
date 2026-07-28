from pydantic_settings import BaseSettings

from functools import lru_cache
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / "../.env"

class Settings(BaseSettings): # Defined here used in rag/agent.py, main.py Fetched from .env

    # LLM Configuration
    gemini_api_key: str = ""
    primary_model: str = "gemini-3.5-flash" # NOTE: In production change to deepseek.
    fallback_model: str = "gemini-3.5-flash"
    query_model: str = "gemini-2.5-flash" # NOTE: In production change to deepseek.
    contextual_retrieval_model: str = "gemini-3.5-flash"
    embedding_model: str = "models/gemini-embedding-001"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "CollegeChatbot"

    # Retrieval
    vector_size: int = 768
    min_cache_tokens: int = 4096
    chunk_size: int = 1000
    chunk_overlap: int = 150
    batch_size: int = 25
    cache_ttl: str = "600s"


    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    max_primary_retries: int = 2
    max_fallback_retries: int = 2
    max_retrieval_retries: int = 2
    session_token_budget: int = 200000
    retrieval_distance_threshold: float = 0.45

    # Whatsapp Webhook
    whatsapp_verify_token: str = ""
    meta_app_secret: str = ""
    whatsapp_access_token: str = ""

    # Database
    redis_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = "" # Server-side only, bypasses RLS - never expose this to a frontend
    storage_bucket: str = "college_documents"
    
    model_config = {"env_file": ENV_PATH, "extra": "ignore"}

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    

@lru_cache() # Cached settings instance - loaded once, reused everywhere
def get_settings() -> Settings:
    return Settings()