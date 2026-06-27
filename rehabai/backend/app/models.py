"""ORM-модели данных.

Сущности намеренно близки к ресурсам HL7 FHIR, чтобы экспорт в FHIR
(см. fhir.py) был прямым отображением, а не «натягиванием»:
  - Appeal   -> Encounter + ServiceRequest (+ Patient)
  - Decision -> запись о клиническом решении специалиста
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Appeal(Base):
    """Реабилитационное обращение пациента (структурированный профиль)."""

    __tablename__ = "appeals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    role: Mapped[str] = mapped_column(String, default="Пациент")
    patient_label: Mapped[str] = mapped_column(String, default="Не идентифицирован")
    age_group: Mapped[str] = mapped_column(String, default="—")
    request_type: Mapped[str] = mapped_column(String, default="—")

    symptom: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    severity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    factors: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    specialist: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Поля ниже рассчитываются сервером (см. scoring.py) — клиент их не задаёт.
    priority: Mapped[str] = mapped_column(String, default="Низкий")
    priority_score: Mapped[int] = mapped_column(Integer, default=0)
    route: Mapped[str] = mapped_column(String, default="—")
    status: Mapped[str] = mapped_column(String, default="Новое")

    decisions: Mapped[List["Decision"]] = relationship(
        back_populates="appeal",
        cascade="all, delete-orphan",
        order_by="Decision.created_at",
    )


class Decision(Base):
    """Решение специалиста по конкретному обращению."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    appeal_id: Mapped[str] = mapped_column(ForeignKey("appeals.id"))

    action: Mapped[str] = mapped_column(String)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    appeal: Mapped["Appeal"] = relationship(back_populates="decisions")
