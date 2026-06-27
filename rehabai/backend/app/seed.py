"""Наполнение базы демонстрационными (синтетическими) данными.

Все записи вымышлены и не содержат реальных персональных данных.
Используются только для демонстрации работы системы.
"""

from datetime import datetime, timedelta, timezone

from .models import Appeal
from . import scoring

# Каждый кортеж: (age_group, request_type, symptom, duration, severity, factors)
_DEMO = [
    ("60+", "Восстановление после травмы или операции",
     "Ограничение движения после перелома", "несколько недель", "Высокая", "нарушение движения"),
    ("18–59 лет", "Первичная запись на реабилитацию",
     "Боли в спине", "несколько дней", "Средняя", ""),
    ("До 18 лет", "Нарушение движения, речи или самообслуживания",
     "Задержка речевого развития", "несколько месяцев", "Средняя", "нарушение речи"),
    ("18–59 лет", "Дистанционное сопровождение реабилитации",
     "Контроль выполнения упражнений", "несколько недель", "Низкая", ""),
    ("60+", "Нарушение движения, речи или самообслуживания",
     "Снижение самообслуживания после инсульта", "несколько месяцев", "Высокая",
     "нарушение движения, нарушение речи"),
    ("18–59 лет", "Восстановление после травмы или операции",
     "Восстановление после операции на колене", "несколько недель", "Средняя", "после операции"),
    ("До 18 лет", "Первичная запись на реабилитацию",
     "Нарушение осанки", "несколько месяцев", "Низкая", ""),
]


def seed(db) -> int:
    """Заполняет таблицу обращений, если она пуста. Возвращает число добавленных."""
    if db.query(Appeal).count() > 0:
        return 0

    now = datetime.now(timezone.utc)
    added = 0
    for i, (age, request, symptom, duration, severity, factors) in enumerate(_DEMO):
        result = scoring.compute(age, severity, duration, request, factors, symptom)
        appeal = Appeal(
            id=f"PAT-{100001 + i}",
            created_at=now - timedelta(hours=i * 7),
            role="Пациент",
            patient_label=f"Демо-пациент {i + 1}",
            age_group=age,
            request_type=request,
            symptom=symptom,
            duration=duration,
            severity=severity,
            factors=factors or None,
            priority=result["priority"],
            priority_score=result["score"],
            route=result["route"],
            status="Новое",
            owner="demo",
        )
        db.add(appeal)
        added += 1

    db.commit()
    return added


# Демонстрационные учётные записи (логин, пароль, роль, ФИО).
# Пароли заданы в открытом виде ТОЛЬКО для демонстрации входа.
_DEMO_USERS = [
    ("patient", "patient123", "pacient", "Демо-пациент"),
    ("doctor", "doctor123", "specialist", "Демо-специалист (врач ЛФК)"),
]


def seed_users(db) -> int:
    """Создаёт демо-аккаунты, если их ещё нет. Возвращает число добавленных."""
    from .models import User
    from .auth import hash_password

    added = 0
    for username, password, role, full_name in _DEMO_USERS:
        if db.get(User, username) is None:
            db.add(User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                full_name=full_name,
            ))
            added += 1
    if added:
        db.commit()
    return added
