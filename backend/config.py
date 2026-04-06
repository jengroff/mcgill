from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    debug: bool = False
    environment: str = "development"

    # Anthropic
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # LangSmith
    langsmith_api_key: str = ""
    langsmith_project: str = "mcgill"

    # Voyage AI
    voyage_api_key: str = ""

    # PostgreSQL + pgvector
    database_url: str = "postgresql://mcgill:mcgilldev@localhost:5433/mcgill"

    # Auth / JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 1440

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7688"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "mcgilldev"

    # CORS
    allowed_origins: str = ""

    # Scraper
    scraper_delay_sec: float = 1.0
    scraper_headless: bool = True
    scraper_timeout_ms: int = 30000

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
