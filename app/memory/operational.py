"""
SQLAlchemy ORM models + async base repository.

Tables
------
- agent_runs      : top-level planner run record
- hitl_queue      : human-in-the-loop review queue
- icp_configs     : tenant ICP rule sets
- audit_log       : immutable append-only event log
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

import structlog
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    Uuid,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentRun(Base):
    """Top-level record for a single planner agent execution."""

    __tablename__ = "agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | running | completed | failed
    plan_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AgentRun id={self.id} tenant={self.tenant_id} status={self.status}>"


class HitlQueue(Base):
    """Human-in-the-loop review queue entry."""

    __tablename__ = "hitl_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | approved | rejected
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HitlQueue id={self.id} run={self.run_id} status={self.status}>"


class IcpConfig(Base):
    """Tenant-specific Ideal Customer Profile configuration."""

    __tablename__ = "icp_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    persona_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<IcpConfig id={self.id} tenant={self.tenant_id} name={self.name}>"


class AuditLog(Base):
    """Immutable append-only audit log entry."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AuditLog id={self.id} agent={self.agent_name} event={self.event_type}>"
        )


# ---------------------------------------------------------------------------
# Generic async base repository
# ---------------------------------------------------------------------------

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Lightweight async CRUD base.  Subclass and set ``model`` class variable.

    Example::

        class AgentRunRepository(BaseRepository[AgentRun]):
            model = AgentRun
    """

    model: type[ModelT]

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ── helpers ─────────────────────────────────────────────────────────────

    def _log(self, **kw: Any) -> structlog.BoundLogger:
        return logger.bind(repository=self.__class__.__name__, **kw)

    # ── public API ───────────────────────────────────────────────────────────

    async def get(self, record_id: uuid.UUID) -> ModelT | None:
        """Fetch a single record by primary key."""
        log = self._log(record_id=str(record_id))
        async with self._session_factory() as session:
            result = await session.get(self.model, record_id)
            log.debug("repository_get", found=result is not None)
            return result

    async def create(self, **kwargs: Any) -> ModelT:
        """Insert a new record and return the persisted instance."""
        log = self._log()
        async with self._session_factory() as session:
            instance = self.model(**kwargs)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            log.info("repository_create", record_id=str(instance.id))
            return instance

    async def update(self, record_id: uuid.UUID, **kwargs: Any) -> ModelT | None:
        """Partial-update an existing record; returns None if not found."""
        log = self._log(record_id=str(record_id))
        async with self._session_factory() as session:
            instance = await session.get(self.model, record_id)
            if instance is None:
                log.warning("repository_update_not_found")
                return None
            for key, value in kwargs.items():
                setattr(instance, key, value)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            log.info("repository_update_ok")
            return instance

    async def list_by(self, **filters: Any) -> list[ModelT]:
        """Return all records matching simple equality filters."""
        log = self._log(filters=filters)
        async with self._session_factory() as session:
            stmt = select(self.model)
            for attr, value in filters.items():
                stmt = stmt.where(getattr(self.model, attr) == value)
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            log.debug("repository_list_by", count=len(rows))
            return rows


# ---------------------------------------------------------------------------
# Concrete repositories
# ---------------------------------------------------------------------------


class AgentRunRepository(BaseRepository[AgentRun]):
    model = AgentRun


class HitlQueueRepository(BaseRepository[HitlQueue]):
    model = HitlQueue

    async def get_pending_for_run(self, run_id: uuid.UUID) -> list[HitlQueue]:
        async with self._session_factory() as session:
            stmt = (
                select(HitlQueue)
                .where(HitlQueue.run_id == run_id)
                .where(HitlQueue.status == "pending")
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())


class IcpConfigRepository(BaseRepository[IcpConfig]):
    model = IcpConfig

    async def get_active_for_tenant(self, tenant_id: str) -> list[IcpConfig]:
        return await self.list_by(tenant_id=tenant_id, is_active=True)


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def append(
        self,
        run_id: uuid.UUID | None,
        agent_name: str,
        event_type: str,
        details: dict[str, Any],
    ) -> AuditLog:
        """Convenience method for fire-and-forget audit writes."""
        return await self.create(
            run_id=run_id,
            agent_name=agent_name,
            event_type=event_type,
            details_json=details,
        )
