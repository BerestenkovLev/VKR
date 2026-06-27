"""Экспорт обращения в форму ресурсов HL7 FHIR (R4).

Возвращается Bundle с тремя ресурсами:
  - Patient        — обезличенный пациент (демо);
  - Encounter      — факт обращения;
  - ServiceRequest — направление на реабилитацию с приоритетом.

Это демонстрирует интеграционную совместимость: такие ресурсы могут быть
переданы во внешнюю медицинскую информационную систему. Данные демонстрационные.
"""

from typing import Dict

PRIORITY_FHIR = {"Высокий": "urgent", "Средний": "routine", "Низкий": "routine"}


def appeal_to_fhir(appeal) -> Dict:
    created = appeal.created_at.isoformat() if appeal.created_at else None

    patient = {
        "resourceType": "Patient",
        "id": f"patient-{appeal.id}",
        "active": True,
        # Реальные ПДн не передаются: только обезличенная демонстрационная метка.
        "extension": [{
            "url": "http://rehabai.demo/age-group",
            "valueString": appeal.age_group,
        }],
    }

    encounter = {
        "resourceType": "Encounter",
        "id": f"encounter-{appeal.id}",
        "status": "in-progress" if appeal.status != "Завершено" else "finished",
        "class": {"code": "VR", "display": "виртуальное обращение"},
        "subject": {"reference": f"Patient/patient-{appeal.id}"},
        "period": {"start": created},
        "reasonCode": [{"text": appeal.request_type}],
    }

    service_request = {
        "resourceType": "ServiceRequest",
        "id": f"servicerequest-{appeal.id}",
        "status": "active",
        "intent": "plan",
        "priority": PRIORITY_FHIR.get(appeal.priority, "routine"),
        "subject": {"reference": f"Patient/patient-{appeal.id}"},
        "encounter": {"reference": f"Encounter/encounter-{appeal.id}"},
        "code": {"text": "Медицинская реабилитация"},
        "orderDetail": [{"text": appeal.route}],
        "note": [{"text": f"Симптом: {appeal.symptom or '—'}; интенсивность: {appeal.severity or '—'}"}],
    }

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [
            {"resource": patient},
            {"resource": encounter},
            {"resource": service_request},
        ],
    }
