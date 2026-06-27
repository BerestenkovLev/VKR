"""Прозрачный расчёт приоритета и маршрута обращения.

Алгоритм намеренно простой и объяснимый: итоговый балл складывается из
понятных составляющих, каждая из которых возвращается в breakdown.
Это НЕ клиническая система поддержки принятия решений и не предназначено
для маршрутизации реальных пациентов — это демонстрационная эвристика для
структурирования обращения и расстановки приоритетов в очереди.

Балл = интенсивность + длительность + возрастной фактор + факторы риска.
Пороги: <= 3 — Низкий, 4–5 — Средний, >= 6 — Высокий.
"""

from typing import Dict, Optional


def _match_score(value: Optional[str], mapping: Dict[str, int], default: int = 1) -> int:
    """Ищет первое ключевое слово из mapping в строке (без учёта регистра)."""
    text = (value or "").lower()
    for key, score in mapping.items():
        if key in text:
            return score
    return default


# Интенсивность: поддерживаются формулировки интерфейса (Лёгкая/Умеренная/Сильная)
# и обобщённые (низкая/средняя/высокая) — порядок важен, проверяется по подстроке.
SEVERITY = {
    "сильн": 3, "выс": 3,
    "умерен": 2, "сред": 2,
    "легк": 1, "низ": 1,
}

# Длительность: "Более 3 дней" весомее, чем "Менее суток"/"1–3 дня".
DURATION = {
    "более": 2, "месяц": 3, "год": 3, "недел": 2,
    "сутк": 1, "дн": 1,
}

# Факторы риска. Острое ухудшение — сильнее (+2), прочие значимые признаки — +1.
ACUTE_FLAGS = ("резк", "ухудшени")
RISK_FLAGS = (
    "хроническ", "осложн", "движени", "ходьб", "реч", "памят",
    "координац", "самообслуж", "операц", "инсульт", "невролог", "паден", "глотани",
)


def _age_factor(age_group: Optional[str]) -> int:
    """Уязвимые возрастные группы (дети и пожилые) получают +1."""
    age = (age_group or "").lower()
    if "до 18" in age or "60" in age:
        return 1
    return 0


def _flag_factor(text: str) -> int:
    t = (text or "").lower()
    if any(k in t for k in ACUTE_FLAGS):
        return 2
    if any(k in t for k in RISK_FLAGS):
        return 1
    return 0


def _route_for(request_type: Optional[str], priority: str) -> str:
    """Базовый маршрут по типу обращения + модификатор по приоритету."""
    r = (request_type or "").lower()
    if "первичн" in r:
        base = "Подбор программы медицинской реабилитации"
    elif "травм" in r or "операц" in r:
        base = "Посттравматическая / послеоперационная реабилитация"
    elif "функциональн" in r or "движени" in r or "реч" in r:
        base = "Функциональная реабилитация (мультидисциплинарная бригада)"
    elif "дистанцион" in r:
        base = "Дистанционное сопровождение (телемедицина)"
    else:
        base = "Маршрутизация на восстановительное лечение"

    if priority == "Высокий":
        return base + " — очный приём в приоритетном порядке"
    if priority == "Средний":
        return base + " — плановый очный приём"
    return base + " — возможен дистанционный формат"


def compute(
    age_group: Optional[str],
    severity: Optional[str],
    duration: Optional[str],
    request_type: Optional[str],
    factors: Optional[str],
    symptom: Optional[str] = None,
) -> Dict:
    """Возвращает {score, priority, route, breakdown} по данным обращения."""
    s_sev = _match_score(severity, SEVERITY, default=1)
    s_dur = _match_score(duration, DURATION, default=1)
    s_age = _age_factor(age_group)

    # Факторы риска оцениваем по совокупности: указанные факторы + симптом + тип обращения.
    flag_text = " ".join(filter(None, [factors, symptom, request_type]))
    s_flag = _flag_factor(flag_text)

    score = s_sev + s_dur + s_age + s_flag

    if score >= 6:
        priority = "Высокий"
    elif score >= 4:
        priority = "Средний"
    else:
        priority = "Низкий"

    route = _route_for(request_type, priority)

    breakdown = {
        "интенсивность": s_sev,
        "длительность": s_dur,
        "возрастной_фактор": s_age,
        "факторы_риска": s_flag,
    }

    return {"score": score, "priority": priority, "route": route, "breakdown": breakdown}
