from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from src.api.db.models import StudentProfile, User, UserRole
from src.api.db.session import get_db
from src.api.security.auth import (
    create_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginPayload(BaseModel):
    username: str
    password: str
    device_id: Optional[str] = "api-client"


class RegisterPayload(BaseModel):
    username: str
    email: str
    password: str
    full_name: str
    device_id: Optional[str] = "api-client"


def get_templates() -> Jinja2Templates:
    from src.api.main import templates
    return templates


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: Optional[str] = None):
    return get_templates().TemplateResponse(request=request, name="auth/login.html", context={"error": error})


@router.post("/login")
def login_submit(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    device_id: str = Form(""),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter((User.username == username) | (User.email == username))
        .first()
    )

    if not user or not verify_password(password, user.hashed_password):
        return get_templates().TemplateResponse(
            request=request,
            name="auth/login.html",
            context={"error": "Invalid username or password."},
            status_code=400,
        )

    # Bind new device_id for Single-Device Lockdown
    client_device_id = device_id.strip() or "dev-unknown"
    user.active_device_id = client_device_id
    db.commit()

    token = create_access_token(user_id=user.id, role=user.role.value, device_id=client_device_id)

    target_redirect = "/admin" if user.role == UserRole.ADMIN else "/student"
    res = RedirectResponse(url=target_redirect, status_code=status.HTTP_303_SEE_OTHER)
    # Set secure HttpOnly cookie with 10-day expiration (86400 * 10 seconds)
    res.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=864000,
        samesite="lax",
    )
    return res


@router.post("/api/login")
def api_login_submit(
    payload: LoginPayload,
    db: Session = Depends(get_db),
):
    """Programmatic JSON login endpoint returning signed JWT access token."""
    user = (
        db.query(User)
        .filter((User.username == payload.username) | (User.email == payload.username))
        .first()
    )

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )

    client_device_id = (payload.device_id or "api-client").strip()
    user.active_device_id = client_device_id
    db.commit()

    token = create_access_token(user_id=user.id, role=user.role.value, device_id=client_device_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id,
        "username": user.username,
        "device_id": client_device_id,
    }


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return get_templates().TemplateResponse(request=request, name="auth/register.html", context={"error": None})


@router.post("/register")
def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    device_id: str = Form(""),
    db: Session = Depends(get_db),
):
    existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
    if existing:
        return get_templates().TemplateResponse(
            request=request,
            name="auth/register.html",
            context={"error": "Username or email already in use."},
            status_code=400,
        )

    client_device_id = device_id.strip() or "dev-unknown"
    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        hashed_password=hash_password(password),
        role=UserRole.STUDENT,
        active_device_id=client_device_id,
    )
    db.add(user)
    db.flush()

    profile = StudentProfile(
        user_id=user.id,
        full_name=full_name.strip(),
    )
    db.add(profile)
    db.commit()

    token = create_access_token(user_id=user.id, role=user.role.value, device_id=client_device_id)
    res = RedirectResponse(url="/student", status_code=status.HTTP_303_SEE_OTHER)
    res.set_cookie(key="access_token", value=token, httponly=True, max_age=864000, samesite="lax")
    return res


@router.post("/api/register")
def api_register_submit(
    payload: RegisterPayload,
    db: Session = Depends(get_db),
):
    """Programmatic JSON registration endpoint returning signed JWT access token."""
    existing = db.query(User).filter((User.username == payload.username) | (User.email == payload.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already in use.",
        )

    client_device_id = (payload.device_id or "api-client").strip()
    user = User(
        username=payload.username.strip(),
        email=payload.email.strip().lower(),
        hashed_password=hash_password(payload.password),
        role=UserRole.STUDENT,
        active_device_id=client_device_id,
    )
    db.add(user)
    db.flush()

    profile = StudentProfile(
        user_id=user.id,
        full_name=payload.full_name.strip(),
    )
    db.add(profile)
    db.commit()

    token = create_access_token(user_id=user.id, role=user.role.value, device_id=client_device_id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": user.id,
        "username": user.username,
        "device_id": client_device_id,
    }


@router.get("/logout")
def logout():
    res = RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)
    res.delete_cookie(key="access_token")
    return res
