"""Схемы запросов и ответов API (Pydantic v2)."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class AppealCreate(BaseModel):
    """Данные, которые присылает клиент при создании обращения.
    Приоритет, балл и маршрут клиент НЕ задаёт — их считает сервер."""
    patient_label: Optional[str] = "Не идентифицирован"
    age_group: str
    request_type: str
    symptom: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[str] = None
    factors: Optional[str] = None
    specialist: Optional[str] = None


class DecisionCreate(BaseModel):
    action: str
    note: Optional[str] = None


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    action: str
    note: Optional[str] = None


class AppealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    role: str
    patient_label: str
    age_group: str
    request_type: str
    symptom: Optional[str] = None
    duration: Optional[str] = None
    severity: Optional[str] = None
    factors: Optional[str] = None
    specialist: Optional[str] = None
    priority: str
    priority_score: int
    route: str
    status: str
    owner: Optional[str] = None
    decisions: List[DecisionOut] = []


# ---------- Авторизация ----------

class LoginIn(BaseModel):
    username: str
    password: str


class RegisterIn(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    username: str
    role: str
    full_name: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    full_name: Optional[str] = None
