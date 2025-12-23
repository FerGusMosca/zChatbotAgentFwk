# common/config/settings.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    #

    session_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("SESSION_KEY", "SESSION_KEY"))


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

    ranking_fallback_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RANKING_FALLBACK_URL", "RANKING_FALLBACK_URL"))

    funds_reports_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("FUNDS_REPORTS_URL", "FUNDS_REPORTS_URL"))

    news_reports_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_REPORTS_URL", "NEWS_REPORTS_URL"))


    documents_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DOCUMENTS_PATH", "DOCUMENTS_PATH"))

    commands_ini_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("COMMANDS_INI_PATH", "COMMANDS_INI_PATH"))

    news_folder_rel_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_FOLDER_REL_PATH", "NEWS_FOLDER_REL_PATH"))


    news_chunks_rel_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_CHUNKS_REL_PATH", "NEWS_CHUNKS_REL_PATH"))


    news_vendor: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_VENDOR", "NEWS_VENDOR"))

    docker_process_news_cmd: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DOCKER_CONTAINER_PROCESS_NEWS", "DOCKER_CONTAINER_PROCESS_NEWS"))

    docker_ingest_news_cmd: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DOCKER_CONTAINER_INGEST_NEWS", "DOCKER_CONTAINER_INGEST_NEWS"))


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
