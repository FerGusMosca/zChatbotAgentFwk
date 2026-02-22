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


    dynamic_query_ranking_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DYNAMIC_QUERY_RANKING_URL", "DYNAMIC_QUERY_RANKING_URL"))


    standard_llm_query_bot: str | None = Field(
        default=None,
        validation_alias=AliasChoices("STANDARD_LLM_QUERY_BOT_URL", "STANDARD_LLM_QUERY_BOT_URL"))

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

    reports_mcp_server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("REPORTS_MCP_SERVER", "REPORTS_MCP_SERVER"))

    ingest_mcp_server: str | None = Field(
        default=None,
        validation_alias=AliasChoices("INGEST_MCP_SERVER", "INGEST_MCP_SERVER"))


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

    news_embedding_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEWS_EMBEDDING_MODEL", "NEWS_EMBEDDING_MODEL"))


    zh_processed_folders_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ZH_PROCESSED_FOLDERS_FILE", "ZH_PROCESSED_FOLDERS_FILE"))


    deploy_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DEPLOY_FILE", "DEPLOY_FILE"))



    port: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PORT", "PORT"))


    research_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEARCH_CONNECTION_STRING", "RESEARCH_CONNECTION_STRING"))


    #Neo4j
    neo4j_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEO4J_URI", "NEO4J_URI"))
    neo4j_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEO4J_USER", "NEO4J_USER"))
    neo4j_pwd: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEO4J_PASS", "NEO4J_PASS"))


    #TradingView
    tw_user: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRADING_VIEW_USER", "TRADING_VIEW_USER"))
    tw_pwd: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRADING_VIEW_PWD", "TRADING_VIEW_PWD"))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
