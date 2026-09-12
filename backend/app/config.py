from pydantic_settings import BaseSettings, SettingsConfigDict

from functools import lru_cache
from pydantic import SecretStr


class Settings(BaseSettings): # Defined here used in rag/agent.py, main.py Fetched from .env

    # LLM Configuration
    gemini_api_key: str = ""
    primary_model: str = "gemini-2.5-flash" # NOTE: In production change to deepseek.
    fallback_model: str = "gemini-2.5-flash"
    query_model: str = "gemini-2.5-flash" # NOTE: In production change to deepseek.
    contextual_retrieval_model: str = "gemini-2.5-flash"
    embedding_model: str = "models/gemini-embedding-001"

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_tracing_key: str
    langchain_api_key: str = ""
    langchain_project: str = "CollegeChatbot"

    # Retrieval
    vector_size: int = 768
    min_cache_tokens: int = 4096
    chunk_size: int = 1000
    chunk_overlap: int = 150
    batch_size: int = 25
    cache_ttl_seconds: str = "600s"


    # Cost tracking (backend/app/services/cost_service.py)
    # $ per 1,000,000 tokens, standard (non-batch) tier. Verify against
    # https://ai.google.dev/gemini-api/docs/pricing before trusting reports -
    # these are point-in-time defaults (checked Sep 2026 for gemini-2.5-flash
    # and gemini-embedding-001) and Google revises them periodically. If
    # primary/fallback/query_model or embedding_model are changed away from
    # their current defaults, add/update the matching entry in
    # cost_service.LLM_PRICING_PER_MILLION_TOKENS / EMBEDDING_PRICING_PER_MILLION_TOKENS
    # too - an unpriced model silently costs $0 in every report below.
    #
    # WhatsApp costs aren't modeled per-message here: Meta's Cloud API pricing
    # depends on conversation category (marketing/utility/service/authentication)
    # and destination country, which this codebase doesn't currently track per
    # send. whatsapp_utility_conversation_cost_usd is a flat per-conversation
    # placeholder used only for template-triggered sends (staff-initiated
    # replies outside the 24h window, reengagement nudges) - set it to your
    # actual rate from Meta Business Manager > WhatsApp Manager > Overview >
    # pricing for your market. Free-form replies inside the 24h session
    # window are billed by Meta as "service" conversations, which are free in
    # most markets as of the 2025 per-message pricing shift - left at 0.0
    # below; update if that's no longer true for your account.
    llm_cost_tracking_enabled: bool = True
    whatsapp_session_message_cost_usd: float = 0.0
    whatsapp_utility_conversation_cost_usd: float = 0.0
    whatsapp_marketing_conversation_cost_usd: float = 0.0

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

    # Outside WhatsApp's 24-hour customer service window (i.e. more than 24h
    # since the student's last inbound message), only a pre-approved template
    # message can be sent - free-form text is rejected by the API. These two
    # values name the template staff-initiated sends (direct messages,
    # low-confidence-queue replies) fall back to when that window has closed.
    # PLACEHOLDER: "staff_followup_v1" is not a real approved template - it
    # must be created and approved in Meta Business Manager first (with a
    # single body text variable, since that's what the fallback fills with
    # the staff member's message), then swapped in here via env vars.
    whatsapp_staff_template_name: str = "staff_followup_v1"
    whatsapp_staff_template_language_code: str = "en_US"

    # Database
    database_url: str = ""
    redis_url: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = "" # Server-side only, bypasses RLS - never expose this to a frontend
    storage_bucket: str = "college-documents"

    # Security
    model_config = SettingsConfigDict(env_file="backend/.env", env_file_encoding="utf-8", extra="ignore")
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Internal Schedules Tasks
    internal_task_token: str = ""

    # Cost reporting (backend/app/api/v1/routers/costs.py) - deliberately a
    # SEPARATE secret from internal_task_token (rather than reusing it) so
    # rotating one doesn't affect the other, and separate from every
    # college-staff auth path (verify_college_access / JWTs) on purpose:
    # this data is your internal margin information, not something any
    # college's staff account should ever be able to reach, so it must
    # never be wired into the staff-facing dashboard/frontend.
    cost_reporting_token: str = ""

    frontend_url: str = "https://admiq-v1.vercel.app"

    # Resend (email.resend.com) - free tier, used for password reset and staff
    # invite emails. resend_from_email must be on a domain verified in your
    # Resend dashboard, OR the default below ("onboarding@resend.dev") which
    # works with zero setup but can only deliver to the email address you
    # signed up to Resend with - fine for testing, not for real staff invites.
    resend_api_key: str = ""
    resend_from_email: str = "onboarding@resend.dev"


    @property
    def is_production(self) -> bool:
        return self.app_env == "production"
    

@lru_cache() # Cached settings instance - loaded once, reused everywhere
def get_settings() -> Settings:
    return Settings()