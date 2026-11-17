"""Autenticación (JWT en cookie httpOnly o encabezado Bearer) y control de roles."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Auditoria, User

COOKIE_NAME = "asesor_token"
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "rol": user.rol,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.token_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o vencida") from None
    user = db.get(User, int(payload["sub"]))
    if not user or not user.activo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo")
    return user


def require_docente(user: User = Depends(current_user)) -> User:
    if user.rol != "docente":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el docente puede realizar esta acción")
    return user


def can_see_student(user: User, estudiante_id: int) -> bool:
    return user.rol == "docente" or user.id == estudiante_id


class LoginRateLimiter:
    """Limita intentos de login por IP+correo (protección básica contra fuerza bruta)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        s = get_settings()
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > s.login_window_seconds:
            hits.popleft()
        if len(hits) >= s.login_max_attempts:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Espere unos minutos.")

    def fail(self, key: str) -> None:
        self._hits[key].append(time.monotonic())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


login_limiter = LoginRateLimiter()


def audit(db: Session, user: User | None, accion: str, entidad: str, entidad_id: int | None = None, **detalle) -> None:
    db.add(
        Auditoria(
            usuario_id=user.id if user else None,
            accion=accion,
            entidad=entidad,
            entidad_id=entidad_id,
            detalle=detalle,
        )
    )
