# common/config/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


    management_sentiment_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MANAGEMENT_SENTIMENT_URL", "MANAGEMENT_SENTIMENT_URL"))


    management_competition_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MANAGEMENT_COMPETITION_URL", "MANAGEMENT_COMPETITION_URL"))

    sentiment_ranking_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SENTIMENT_RANKING_URL", "SENTIMENT_RANKING_URL"))

    news_indexed_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_INDEXED_URL", "NEWS_INDEXED_URL"))


    deploy_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEPLOY_FILE", "DEPLOY_FILE"))



    port: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PORT", "PORT"))


    research_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEARCH_CONNECTION_STRING", "RESEARCH_CONNECTION_STRING"))



    #

@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
