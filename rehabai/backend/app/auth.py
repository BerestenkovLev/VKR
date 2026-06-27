"""Авторизация: хэширование паролей и JWT-токены.

Демонстрационный контур. В целевой архитектуре:
  - вход через ЕСИА / корпоративную учётную запись учреждения;
  - секрет подписи токенов — во внешнем защищённом хранилище (не в коде);
  - передача только по HTTPS, токены короткоживущие + refresh.

Здесь:
  - пароли хранятся как PBKDF2-HMAC-SHA256;
  - токены — JWT (HS256) с полями sub (логин), role и сроком действия.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt  # PyJWT
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

# В целевой архитектуре секрет берётся из защищённого хранилища, а не из кода.
SECRET = os.environ.get("REHABAI_SECRET", "dev-insecure-secret-change-me")
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 8
_PBKDF2_ROUNDS = 200_000


# ---------- Пароли ----------

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ROUNDS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(dk).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds_s, salt_b64, hash_b64 = stored.split("$")
        rounds = int(rounds_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ---------- Токены ----------

def create_token(username: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# ---------- Зависимости FastAPI ----------

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    try:
        payload = jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Недействительный или просроченный токен")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=401, detail="Пользователь не найден")
    return user


def require_role(*roles: str):
    """Возвращает зависимость, пропускающую только указанные роли."""
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Недостаточно прав для этого действия")
        return user
    return dependency
