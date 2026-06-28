"""
app/api/auth.py — JWT authentication for the API Gateway.

Endpoints
─────────
POST /auth/register  → create Tenant + User, return JWT
POST /auth/login     → validate credentials, return JWT

FastAPI dependency
─────────────────
get_current_tenant() — extract and validate JWT from Authorization header,
                       return tenant_id string for downstream route injection.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token, decode_token, hash_password, verify_password
from app.memory.operational import Tenant, User

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


# ── Request/Response models ───────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    tenant_name: str

    model_config = {"json_schema_extra": {"example": {
        "email": "demo@xlventures.ai",
        "password": "demo123",
        "tenant_name": "XL Ventures Demo",
    }}}


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: str
    email: str


from fastapi import Request

def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.session_factory


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AuthResponse:
    """Register a new tenant and user, return JWT."""
    async with session_factory() as session:
        # Check email uniqueness
        existing = await session.execute(
            select(User).where(User.email == body.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # Create Tenant
        tenant = Tenant(
            id=uuid.uuid4(),
            name=body.tenant_name,
            email=body.email,
            created_at=datetime.now(timezone.utc),
        )
        session.add(tenant)

        # Create User
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=body.email,
            hashed_password=hash_password(body.password),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        session.add(user)
        await session.commit()

    token = create_access_token({"sub": str(tenant.id), "email": body.email})
    logger.info("user_registered", tenant_id=str(tenant.id), email=body.email)
    return AuthResponse(
        access_token=token,
        tenant_id=str(tenant.id),
        email=body.email,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
) -> AuthResponse:
    """Validate credentials and return JWT."""
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.email == body.email, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token({"sub": str(user.tenant_id), "email": user.email})
    logger.info("user_login", tenant_id=str(user.tenant_id))
    return AuthResponse(
        access_token=token,
        tenant_id=str(user.tenant_id),
        email=user.email,
    )


# ── Dependency ────────────────────────────────────────────────────────────────


async def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """
    FastAPI dependency — validates the Bearer JWT or query param token and returns tenant_id.

    Usage::

        @router.get("/protected")
        async def route(tenant_id: str = Depends(get_current_tenant)):
            ...
    """
    token: str | None = None
    if credentials and credentials.credentials and credentials.credentials not in ("undefined", "null", ""):
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    if not token or token in ("undefined", "null", ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header or query token missing",
        )
    try:
        payload = decode_token(token)
        tenant_id: str | None = payload.get("sub")
        if not tenant_id:
            raise ValueError("no sub claim")
        return tenant_id
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
