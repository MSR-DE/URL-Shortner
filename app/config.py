"""Application configuration, loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings.

    Every field can be overridden with an environment variable of the same
    name (case-insensitive), or by an entry in a local `.env` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SQLAlchemy async connection string. Note the `+asyncpg` driver suffix.
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/urlshortener"
    )

    # Public origin used to build the returned short URL, e.g. "https://sho.rt".
    base_url: str = "http://localhost:8000"

    # Number of base62 characters in a generated short code.
    # 7 chars => 62^7 ~= 3.5 trillion possible codes.
    short_code_length: int = 7

    # How many times to retry when a randomly generated code already exists.
    max_generation_attempts: int = 5

    # Echo SQL statements to stdout. Handy while developing.
    echo_sql: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Caching keeps us from re-reading the .env file on every request and gives
    tests a single place to override configuration.
    """
    return Settings()
