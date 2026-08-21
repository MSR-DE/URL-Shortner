"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base shared by all models."""


class ShortURL(Base):
    """A single long-URL -> short-code mapping.

    `short_code` carries a UNIQUE constraint, which is what makes the code
    generation safe under concurrency: two workers that happen to generate the
    same random code cannot both commit, so one gets an IntegrityError and
    retries instead of silently overwriting the other.
    """

    __tablename__ = "short_urls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    short_code: Mapped[str] = mapped_column(
        String(16), unique=True, index=True, nullable=False
    )

    # 2048 chars is the de-facto practical URL length limit in browsers.
    original_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    visit_count: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default="0", default=0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    last_visited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # Supports the de-duplication lookup in crud.get_by_original_url().
        Index("ix_short_urls_original_url", "original_url"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<ShortURL {self.short_code} -> {self.original_url[:50]!r}>"
