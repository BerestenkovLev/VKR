"""RehabAI — серверная часть демонстратора.

Запуск (для разработки):  uvicorn app.main:app --reload
Документация API:          /docs  (Swagger UI, есть кнопка Authorize)
Веб-интерфейс:             /      (статический файл app/static/index.html)

Авторизация и роли — демонстрационные (JWT + разграничение пациент/специалист).
Промышленный контур (ЕСИА/корпоративный вход, защищённое хранилище, СКЗИ,
интеграция с ЕМИАС, соответствие 152-ФЗ/323-ФЗ) описывается как целевая архитектура.
Система работает на демонстрационных (обезличенных) данных.
"""

import os
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import auth, fhir, scoring
from .database import Base, SessionLocal, engine, get_db
from .models import Appeal, Decision, User
from .schemas import (
    AppealCreate, AppealOut, DecisionCreate,
    LoginIn, RegisterIn, TokenOut, UserOut,
)
from .seed import seed, seed_users

app = FastAPI(
    title="RehabAI API",
    version="1.2.0",
    description="Демонстратор электронной карты реабилитационного обращения, "
                "маршрутизации и ролевого доступа. Данные демонстрационные.",
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
    """Создаёт таблицы, демо-аккаунты и демо-данные при первом запуске."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_users(db)
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


def _can_see(user: User, appeal: Appeal) -> bool:
    return user.role == "specialist" or appeal.owner == user.username


# ---------- Служебное ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "RehabAI API", "time": datetime.now(timezone.utc).isoformat()}


# ---------- Авторизация ----------

@app.post("/api/auth/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    """Самостоятельная регистрация пациента. Роль специалиста так не выдаётся."""
    if db.get(User, payload.username) is not None:
        raise HTTPException(status_code=400, detail="Логин уже занят")
    user = User(
        username=payload.username,
        password_hash=auth.hash_password(payload.password),
        role="pacient",
        full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    token = auth.create_token(user.username, user.role)
    return TokenOut(access_token=token, username=user.username, role=user.role, full_name=user.full_name)


@app.post("/api/auth/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.get(User, payload.username)
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = auth.create_token(user.username, user.role)
    return TokenOut(access_token=token, username=user.username, role=user.role, full_name=user.full_name)


@app.get("/api/auth/me", response_model=UserOut)
def me(user: User = Depends(auth.get_current_user)):
    return user


# ---------- Расчёт приоритета (без сохранения) ----------

@app.post("/api/score")
def score(payload: AppealCreate, user: User = Depends(auth.get_current_user)):
    """Возвращает приоритет, балл и маршрут по данным обращения, ничего не сохраняя."""
    return scoring.compute(
        payload.age_group, payload.severity, payload.duration,
        payload.request_type, payload.factors, payload.symptom,
    )


# ---------- Обращения пациентов ----------

@app.post("/api/appeals", response_model=AppealOut)
def create_appeal(payload: AppealCreate, user: User = Depends(auth.get_current_user),
                  db: Session = Depends(get_db)):
    """Создаёт обращение; приоритет, балл и маршрут рассчитывает сервер.
    Владельцем записи становится текущий пользователь."""
    result = scoring.compute(
        payload.age_group, payload.severity, payload.duration,
        payload.request_type, payload.factors, payload.symptom,
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
        specialist=payload.specialist,
        priority=result["priority"],
        priority_score=result["score"],
        route=result["route"],
        status="Новое",
        owner=user.username,
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return appeal


@app.get("/api/appeals", response_model=List[AppealOut])
def list_appeals(
    user: User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
    priority: Optional[str] = Query(None, description="Фильтр: Низкий/Средний/Высокий"),
    status: Optional[str] = Query(None, description="Фильтр по статусу"),
):
    """Специалист видит всю очередь; пациент — только свои обращения."""
    q = db.query(Appeal)
    if user.role != "specialist":
        q = q.filter(Appeal.owner == user.username)
    if priority:
        q = q.filter(Appeal.priority == priority)
    if status:
        q = q.filter(Appeal.status == status)
    return q.order_by(Appeal.created_at.desc()).all()


@app.get("/api/appeals/{appeal_id}", response_model=AppealOut)
def get_appeal(appeal_id: str, user: User = Depends(auth.get_current_user),
               db: Session = Depends(get_db)):
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if not _can_see(user, appeal):
        raise HTTPException(status_code=403, detail="Нет доступа к этому обращению")
    return appeal


@app.get("/api/appeals/{appeal_id}/fhir")
def get_appeal_fhir(appeal_id: str, user: User = Depends(auth.get_current_user),
                    db: Session = Depends(get_db)):
    """Экспорт обращения в виде FHIR-бандла (демонстрация интеграции)."""
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise HTTPException(status_code=404, detail="Обращение не найдено")
    if not _can_see(user, appeal):
        raise HTTPException(status_code=403, detail="Нет доступа к этому обращению")
    return fhir.appeal_to_fhir(appeal)


# ---------- Решения специалиста (только роль specialist) ----------

@app.post("/api/appeals/{appeal_id}/decisions", response_model=AppealOut)
def add_decision(appeal_id: str, payload: DecisionCreate,
                 user: User = Depends(auth.require_role("specialist")),
                 db: Session = Depends(get_db)):
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


# ---------- Аналитика и обслуживание (только роль specialist) ----------

@app.get("/api/stats")
def stats(user: User = Depends(auth.require_role("specialist")), db: Session = Depends(get_db)):
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


@app.post("/api/admin/reset")
def reset(user: User = Depends(auth.require_role("specialist")), db: Session = Depends(get_db)):
    """Сброс обращений к демонстрационным данным (учётные записи сохраняются).
    В целевой архитектуре операция доступна только администратору."""
    db.query(Decision).delete()
    db.query(Appeal).delete()
    db.commit()
    n = seed(db)
    return {"reset": True, "seeded": n}


# ---------- Статический веб-интерфейс ----------
# Монтируется последним, чтобы не перекрывать /api/* и /docs.
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
