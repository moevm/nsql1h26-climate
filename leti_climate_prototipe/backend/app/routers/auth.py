from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.auth import USERS, create_token

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    u = USERS.get(body.username)
    if not u or u["password"] != body.password:
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")
    token = create_token(body.username, u["role"])
    return {"token": token, "user": {"username": body.username, "role": u["role"], "name": u["name"]}}