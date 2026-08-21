"""Database access layer.

Keeping queries here (rather than inline in the route handlers) means the HTTP
layer stays about HTTP, and this module can be unit-tested on its own.
"""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ShortURL
from app.shortcode import generate_short_code

settings = get_settings()


class ShortCodeGenerationError(RuntimeError):
    """Raised when no unique short code could be generated after N attempts."""


async def get_by_short_code(session: AsyncSession, short_code: str) -> ShortURL | None:
    """Look up a mapping by its short code."""
    result = await session.execute(
        select(ShortURL).where(ShortURL.short_code == short_code)
    )
    return result.scalar_one_or_none()


async def get_by_original_url(session: AsyncSession, original_url: str) -> ShortURL | None:
    """Return an existing mapping for `original_url`, if one exists.

    Used to make POST /shorten idempotent: shortening the same link twice
    returns the same code instead of filling the table with duplicates.
    """
    result = await session.execute(
        select(ShortURL)
        .where(ShortURL.original_url == original_url)
        .order_by(ShortURL.id)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_short_url(session: AsyncSession, original_url: str) -> ShortURL:
    """Create and persist a new mapping with a freshly generated code.

    Random codes can collide. Rather than checking "does this code exist?"
    before inserting -- which is racy, because another worker can insert the
    same code between the check and the write -- we let the UNIQUE constraint
    be the arbiter and retry on IntegrityError.
    """
    last_error: IntegrityError | None = None

    for _ in range(settings.max_generation_attempts):
        record = ShortURL(
            short_code=generate_short_code(settings.short_code_length),
            original_url=original_url,
        )
        session.add(record)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            last_error = exc
            continue
        await session.refresh(record)
        return record

    raise ShortCodeGenerationError(
        f"Could not generate a unique short code in "
        f"{settings.max_generation_attempts} attempts"
    ) from last_error


async def register_visit(session: AsyncSession, short_code: str) -> None:
    """Increment the visit counter for `short_code`.

    The increment is expressed as a single UPDATE evaluated by PostgreSQL
    (`visit_count = visit_count + 1`) rather than a read-modify-write in
    Python, so concurrent redirects cannot lose counts.
    """
    await session.execute(
        update(ShortURL)
        .where(ShortURL.short_code == short_code)
        .values(visit_count=ShortURL.visit_count + 1, last_visited_at=func.now())
    )
    await session.commit()
