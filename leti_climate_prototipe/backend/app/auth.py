import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("JWT_SECRET", "leti-jwt-secret-key-2026")
ALGORITHM  = "HS256"
TOKEN_TTL  = 24  # часы жизни токена

USERS = {
    "admin":  {"password": "admin123",  "role": "admin",  "name": "Администратор"},
    "viewer": {"password": "viewer123", "role": "viewer", "name": "Наблюдатель"},
}

security = HTTPBearer()


def create_token(username: str, role: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "exp":  datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Токен истёк")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Недействительный токен")


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return decode_token(creds.credentials)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Требуются права администратора")
    return user