# common/config/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


    management_sentiment_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEPLOY_FILE", "MANAGEMENT_SENTIMENT_URL"))


    deploy_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEPLOY_FILE", "DEPLOY_FILE"))



    port: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PORT", "PORT"))

    #

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
