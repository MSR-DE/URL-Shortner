"""FastAPI application: routes, lifespan, and error handling."""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.config import get_settings
from app.database import engine, get_session
from app.models import Base
from app.schemas import ErrorResponse, ShortenRequest, ShortURLResponse
from app.shortcode import ALPHABET

logger = logging.getLogger("url_shortener")
settings = get_settings()

_ALPHABET_SET = frozenset(ALPHABET)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables on startup and dispose of the connection pool on shutdown.

    `create_all` is intentionally simple for an assignment of this size. A
    production deployment would run Alembic migrations instead, so that schema
    changes are versioned and reversible.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database ready")
    yield
    await engine.dispose()


app = FastAPI(
    title="URL Shortener API",
    description=(
        "A small URL shortening service built with FastAPI and PostgreSQL.\n\n"
        "`POST /shorten` stores a long URL and returns a short code; "
        "`GET /{short_code}` redirects to the original URL."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Return every error in the same `{"detail": ...}` shape."""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def _to_response(record) -> ShortURLResponse:
    """Build the API representation of a stored mapping."""
    return ShortURLResponse(
        short_code=record.short_code,
        short_url=f"{settings.base_url.rstrip('/')}/{record.short_code}",
        original_url=record.original_url,
        visit_count=record.visit_count,
        created_at=record.created_at,
        last_visited_at=record.last_visited_at,
    )


# --------------------------------------------------------------------------
# Routes
#
# Order matters. `GET /{short_code}` is a catch-all, so every fixed path must
# be declared before it or it would never be reached.
# --------------------------------------------------------------------------


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return 200 while the process is serving requests."""
    return {"status": "ok"}


@app.post(
    "/shorten",
    response_model=ShortURLResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["links"],
    summary="Shorten a long URL",
    responses={
        422: {"model": ErrorResponse, "description": "The submitted URL is invalid"},
        503: {"model": ErrorResponse, "description": "Could not allocate a short code"},
    },
)
async def shorten(
    payload: ShortenRequest,
    session: AsyncSession = Depends(get_session),
) -> ShortURLResponse:
    """Store a long URL and return its short form.

    The operation is idempotent: submitting a URL that has already been
    shortened returns the existing code rather than creating a second one.
    """
    original_url = str(payload.url)

    existing = await crud.get_by_original_url(session, original_url)
    if existing is not None:
        return _to_response(existing)

    try:
        record = await crud.create_short_url(session, original_url)
    except crud.ShortCodeGenerationError:
        logger.exception("Short code generation exhausted its retries")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not allocate a short code, please retry.",
        ) from None

    logger.info("Created %s -> %s", record.short_code, original_url)
    return _to_response(record)


@app.get(
    "/stats/{short_code}",
    response_model=ShortURLResponse,
    tags=["links"],
    summary="Inspect a short code without following it",
    responses={404: {"model": ErrorResponse, "description": "Unknown short code"}},
)
async def stats(
    short_code: str = Path(..., max_length=16),
    session: AsyncSession = Depends(get_session),
) -> ShortURLResponse:
    """Return the stored mapping and its visit count, without redirecting."""
    record = await _load_or_404(session, short_code)
    return _to_response(record)


@app.get(
    "/{short_code}",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    tags=["links"],
    summary="Redirect to the original URL",
    response_class=RedirectResponse,
    responses={
        307: {"description": "Redirect to the original URL"},
        404: {"model": ErrorResponse, "description": "Unknown short code"},
    },
)
async def redirect_to_original(
    short_code: str = Path(..., max_length=16),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    """Follow a short code to the URL it was created from.

    A 307 (temporary) redirect is used rather than 301 (permanent) on purpose:
    browsers cache a 301 aggressively and would stop calling the service
    altogether, which would both freeze the visit counter and make a link
    impossible to retire.
    """
    record = await _load_or_404(session, short_code)
    await crud.register_visit(session, short_code)
    return RedirectResponse(
        url=record.original_url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


async def _load_or_404(session: AsyncSession, short_code: str):
    """Fetch a mapping, raising a 404 for unknown or malformed codes."""
    if not short_code or not _ALPHABET_SET.issuperset(short_code):
        # Anything outside the base62 alphabet cannot be a code we issued,
        # so answer 404 rather than making the database look for it.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found",
        )

    record = await crud.get_by_short_code(session, short_code)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found",
        )
    return record
