from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # One env file for the whole project (repo root); backend/.env can override locally.
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "EstateFlow"
    environment: Literal["development", "test", "production"] = "development"
    api_prefix: str = "/api/v1"
    public_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # MongoDB (Atlas recommended: vector search + transactions)
    mongo_url: str = Field(
        "mongodb://localhost:27017/?directConnection=true",
        validation_alias=AliasChoices("MONGO_URL", "MONGODB_URL"),
    )
    db_name: str = Field("estateflow", validation_alias=AliasChoices("DB_NAME", "MONGO_DB"))
    # RAG chunks (text + embedding) live here.
    chunks_collection: str = Field(
        "chunks", validation_alias=AliasChoices("COLLECTION_NAME", "CHUNKS_COLLECTION")
    )
    # "atlas" uses $vectorSearch; "exact" scores in Python (local dev without Atlas Search).
    vector_search_mode: Literal["atlas", "exact"] = "atlas"
    vector_index_name: str = "chunks_vector"

    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = Field(
        "change-me-in-production", validation_alias=AliasChoices("SECRET_KEY", "JWT_SECRET")
    )
    jwt_refresh_secret: str = Field(
        "", validation_alias=AliasChoices("REFRESH_SECRET_KEY", "JWT_REFRESH_SECRET")
    )
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    # Browser sessions use httpOnly cookies. Secure is forced on in production.
    cookie_secure: bool = False
    cookie_domain: str | None = None
    # Read the client IP from X-Forwarded-For (only behind a proxy you control).
    trust_proxy_headers: bool = False
    # Fernet key used to encrypt per-tenant secrets (WhatsApp tokens) at rest.
    encryption_key: str = ""

    # WhatsApp Cloud API
    whatsapp_api_version: str = "v21.0"
    whatsapp_verify_token: str = "change-me"
    whatsapp_app_secret: str = ""
    whatsapp_graph_base: str = "https://graph.facebook.com"
    max_inbound_media_mb: int = 16

    # Google Gemini (chat, embeddings, speech-to-text, image description)
    gemini_api_key: str | None = Field(
        None, validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY")
    )
    gemini_llm_model: str = "gemini-3.6-flash"
    gemini_media_model: str = "gemini-3.6-flash"
    gemini_embedding_model: str = "gemini-embedding-2"
    # Smart paste (form filling from pasted text): a fast model keeps it near-instant.
    gemini_extract_model: str = "gemini-3.5-flash-lite"
    # "minimal" | "low" | "medium" | "high": deeper thinking is slower and costs more.
    gemini_thinking_level: str = "low"
    # Per attempt. A buyer is waiting on WhatsApp, so fail over to a human quickly.
    gemini_timeout_seconds: float = 30

    # LLM choice: Gemini by default; Claude is available as an alternative.
    llm_provider: Literal["gemini", "anthropic"] = "gemini"
    llm_max_tokens: int = 1024
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_tool_iterations: int = 6
    agent_history_turns: int = 20

    # Media understanding (set to false to skip the extra Gemini calls)
    transcribe_voice_notes: bool = True
    describe_images: bool = True

    # gemini-embedding-2 supports 128–3072; changing it needs `make reindex`.
    embedding_dim: int = 768
    chunk_size: int = 900
    chunk_overlap: int = 150

    # Storage
    upload_dir: str = "uploads"
    max_upload_mb: int = 25

    # Scheduling
    booking_horizon_days: int = 14
    booking_min_lead_minutes: int = 120

    @model_validator(mode="after")
    def _finalize(self) -> "Settings":
        if not self.jwt_refresh_secret:
            self.jwt_refresh_secret = self.jwt_secret
        if self.environment == "production":
            self.cookie_secure = True
            weak = len(self.jwt_secret) < 32 or self.jwt_secret == "change-me-in-production"
            missing = [
                name
                for name, value in (
                    ("ENCRYPTION_KEY", self.encryption_key),
                    ("WHATSAPP_APP_SECRET", self.whatsapp_app_secret),
                )
                if not value
            ]
            if weak or missing or self.whatsapp_verify_token == "change-me":
                raise ValueError(
                    "Refusing to start in production with default secrets: set SECRET_KEY "
                    "(32+ chars), WHATSAPP_VERIFY_TOKEN and " + ", ".join(missing or ["-"])
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
