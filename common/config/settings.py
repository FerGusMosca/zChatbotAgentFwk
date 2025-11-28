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

    bot_profile_root_path: str = Field(
        default="demo_client",
        validation_alias=AliasChoices("BOT_PROFILE_ROOT_PATH", "bot_profile_root_path"),
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

    deploy_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEPLOY_FILE", "DEPLOY_FILE"))

    cache_enabled: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CACHE_ENABLED", "CACHE_ENABLED"))

    cache_type: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CACHE_TYPE", "CACHE_TYPE"))

    redis_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REDIS_URL", "REDIS_URL"))

    chat_prompt: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CHAT_PROMPT", "CHAT_PROMPT"))

    bot_logic: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BOT_LOGIC", "BOT_LOGIC"))

    model_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MODEL_NAME", "MODEL_NAME"))

    model_temperature: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MODEL_TEMPERATURE", "MODEL_TEMPERATURE"))

    model_final_k: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FINAL_K", "FINAL_K"))

    index_files_root_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INDEX_FILES_ROOT_PATH", "INDEX_FILES_ROOT_PATH"))

    port: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PORT", "PORT"))

    grafana_on: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("GRAFANA_ON", "GRAFANA_ON"))





    #

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
