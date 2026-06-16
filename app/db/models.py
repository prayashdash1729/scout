"""ORM models: User (one per Telegram account) and Job (one per surfaced job)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base
from app.enums import JobStatus


class User(Base):
    __tablename__ = "users"

    # Telegram user id — stable across username changes; our primary key.
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[Optional[str]] = mapped_column(String(255))
    name: Mapped[Optional[str]] = mapped_column(String(255))

    cv_text: Mapped[Optional[str]] = mapped_column(Text)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    target_roles: Mapped[list] = mapped_column(JSON, default=list)
    target_cities: Mapped[list] = mapped_column(JSON, default=list)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    # Source-registry names this user hunts with. Empty = all available sources.
    enabled_sources: Mapped[list] = mapped_column(JSON, default=list)

    # Rate-limit bookkeeping (persisted so limits survive restarts).
    last_hunt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    hunt_day: Mapped[Optional[date]] = mapped_column(Date)
    hunts_today: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="user")

    @property
    def is_onboarded(self) -> bool:
        return bool(self.cv_text and self.target_roles and self.target_cities)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # A given job is deduped per-user (the same posting can matter to two users).
        UniqueConstraint("user_id", "job_key", name="uq_user_jobkey"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), index=True
    )

    job_key: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    company: Mapped[str] = mapped_column(String(512), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    apply_link: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="other")

    score: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    posting_date: Mapped[Optional[str]] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), default=JobStatus.PENDING.value)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="jobs")
