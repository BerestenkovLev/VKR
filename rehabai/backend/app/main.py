"""RehabAI — серверная часть демонстратора.

Запуск (для разработки):  uvicorn app.main:app --reload
Документация API:          /docs  (Swagger UI)

ВАЖНО: система работает на демонстрационных (обезличенных) данных.
Промышленный контур (защищённое хранилище, СКЗИ, интеграция с ЕМИАС,
соответствие 152-ФЗ/323-ФЗ) в работе описывается как целевая архитектура.
"""

import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import fhir, scoring
from .database import Base, SessionLocal, engine, get_db
from .models import Appeal, Decision
from .schemas import AppealCreate, AppealOut, DecisionCreate
from .seed import seed

app = FastAPI(
    title="RehabAI API",
    version="1.0.0",
    description="Демонстратор электронной карты реабилитационного обращения "
                "и маршрутизации. Данные демонстрационные.",
)

# CORS открыт для удобства демонстрации (фронтенд может открываться с file:// или хостинга).
# В целевой архитектуре список источников ограничивается.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    """Создаёт таблицы и наполняет демо-данными при первом запуске."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{str(int(time.time() * 1000))[-6:]}"


def _status_for(action: str) -> str:
    a = action.lower()
    if "заверш" in a:
        return "Завершено"
    if "очн" in a:
        return "Направлен на очный приём"
    if "телемед" in a or "дистанц" in a:
        return "Переведён в телемедицину"
    if "подтвержд" in a:
        return "Маршрут подтверждён"
    return "В работе"


# ---------- Служебное ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "RehabAI API", "time": datetime.now(timezone.utc).isoformat()}


# ---------- Обращения пациентов ----------

@app.post("/api/appeals", response_model=AppealOut)
def create_appeal(payload: AppealCreate, db: Session = Depends(get_db)):
    """Создаёт обращение; приоритет, балл и маршрут рассчитывает сервер."""
    result = scoring.compute(
        payload.age_group, payload.severity, payload.duration,
        payload.request_type, payload.factors,
    )
    appeal = Appeal(
        id=_gen_id("PAT"),
        role="Пациент",
        patient_label=payload.patient_label or "Не идентифицирован",
        age_group=payload.age_group,
        request_type=payload.request_type,
        symptom=payload.symptom,
        duration=payload.duration,
        severity=payload.severity,
        factors=payload.factors,
        priority=result["priority"],
        priority_score=result["score"],
        route=result["route"],
        status="Новое",
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return appeal


@app.get("/api/appeals", response_model=List[AppealOut])
def list_appeals(
    db: Session = Depends(get_db),
    priority: Optional[str] = Query(None, description="Фильтр: Низкий/Средний/Высокий"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
):
    """Список обращений (очередь специалиста), новые сверху, с фильтрами."""
    q = db.query(Appeal)
    if priority:
        q = q.filter(Appeal.priority == priority)
    if status:
        q = q.filter(Appeal.status == status)
    return q.order_by(Appeal.created_at.desc()).all()


@app.get("/api/appeals/{appeal_id}", response_model=AppealOut)
def get_appeal(appeal_id: str, db: Session = Depends(get_db)):
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    return appeal


@app.get("/api/appeals/{appeal_id}/fhir")
def get_appeal_fhir(appeal_id: str, db: Session = Depends(get_db)):
    """Экспорт обращения в виде FHIR-бандла (демонстрация интеграции)."""
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    return fhir.appeal_to_fhir(appeal)


# ---------- Решения специалиста ----------

@app.post("/api/appeals/{appeal_id}/decisions", response_model=AppealOut)
def add_decision(appeal_id: str, payload: DecisionCreate, db: Session = Depends(get_db)):
    """Добавляет решение специалиста и обновляет статус обращения."""
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Обращение не найдено")

    decision = Decision(
        id=_gen_id("DOC"),
        appeal_id=appeal.id,
        action=payload.action,
        note=payload.note,
    )
    db.add(decision)
    appeal.status = _status_for(payload.action)
    db.commit()
    db.refresh(appeal)
    return appeal


# ---------- Аналитика (для дашборда/презентации) ----------

@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    """Сводка по очереди: всего, по приоритету и по статусу."""
    appeals = db.query(Appeal).all()
    by_priority, by_status = {}, {}
    for a in appeals:
        by_priority[a.priority] = by_priority.get(a.priority, 0) + 1
        by_status[a.status] = by_status.get(a.status, 0) + 1
    return {
        "total": len(appeals),
        "by_priority": by_priority,
        "by_status": by_status,
        "decisions_total": db.query(Decision).count(),
    }
