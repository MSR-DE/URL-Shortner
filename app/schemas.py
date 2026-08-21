"""Pydantic models describing the request and response bodies."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

# Matches the column width of ShortURL.original_url.
MAX_URL_LENGTH = 2048


class ShortenRequest(BaseModel):
    """Body of POST /shorten."""

    url: HttpUrl = Field(
        ...,
        description="The absolute http:// or https:// URL to shorten.",
        examples=["https://www.example.com/some/very/long/path?with=query"],
    )

    @field_validator("url")
    @classmethod
    def url_must_fit_in_column(cls, value: HttpUrl) -> HttpUrl:
        if len(str(value)) > MAX_URL_LENGTH:
            raise ValueError(f"URL must be at most {MAX_URL_LENGTH} characters")
        return value


class ShortURLResponse(BaseModel):
    """Representation of a stored short URL."""

    model_config = ConfigDict(from_attributes=True)

    short_code: str = Field(description="The generated base62 code.")
    short_url: str = Field(description="The full shortened URL, ready to share.")
    original_url: str = Field(description="The URL the code redirects to.")
    visit_count: int = Field(description="How many times the code has been followed.")
    created_at: datetime
    last_visited_at: datetime | None = None


class ErrorResponse(BaseModel):
    """Uniform error body returned for every non-2xx/3xx response."""

    detail: str
