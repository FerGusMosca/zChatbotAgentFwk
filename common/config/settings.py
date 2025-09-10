# common/config/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    # Config de pydantic v2
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== API Keys =====
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"),
    )
    other_service_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OTHER_SERVICE_KEY", "other_service_key"),
    )

    # ===== Bot profile / paths =====
    bot_profile: str = Field(
        default="demo_client",
        validation_alias=AliasChoices("BOT_PROFILE", "bot_profile"),
    )
    faiss_index_path: str = Field(
        default="./vectorstores",
        validation_alias=AliasChoices("FAISS_INDEX_PATH", "faiss_index_path"),
    )

    # ===== Thresholds =====
    retrieval_score_threshold: float = Field(
        default=0.4,
        validation_alias=AliasChoices("RETRIEVAL_SCORE_THRESHOLD", "retrieval_score_threshold"),
    )

    # ===== Misc =====
    debug_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("DEBUG_MODE", "debug_mode"),
    )

    # ===== Twilio =====
    twilio_account_sid: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TWILIO_ACCOUNT_SID", "twilio_account_sid"))
    twilio_auth_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TWILIO_AUTH_TOKEN", "twilio_auth_token"))
    twilio_whatsapp_from: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TWILIO_WHATSAPP_FROM", "twilio_whatsapp_from"))


    custom_logger: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CUSTOM_LOGGER", "custom_logger"))

    intent_detection_logic: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INTENT_DETECTION_LOGIC", "intent_detection_logic"))

    webhook: str | None = Field(
        default=None,
        validation_alias=AliasChoices("WEBHOOK", "WEBHOOK"))

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
