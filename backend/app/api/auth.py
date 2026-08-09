"""Authentication endpoints and JWT utilities."""

from datetime import datetime, timedelta

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.login_event import LoginEvent
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    """Real client IP — nginx in front populates X-Forwarded-For. Falls back
    to the direct peer when the header is absent (e.g. local dev without nginx).
    The leftmost XFF entry is the original client; the rest are proxy hops."""
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


@router.post("/signup", response_model=UserResponse, status_code=201)
async def signup(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="이미 등록된 아이디입니다")

    # First user becomes admin automatically
    user_count = await db.execute(select(User))
    is_first = len(user_count.scalars().all()) == 0

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role="admin" if is_first else "worker",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(data: UserLogin, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

    # Audit trail — admin reviews who logged in from where via the "로그인 기록"
    # tab. Successes only (per user decision); failures are NOT recorded.
    ua = (request.headers.get("user-agent") or "")[:500]
    db.add(LoginEvent(user_id=user.id, ip=_client_ip(request), user_agent=ua))
    await db.commit()

    token = create_access_token({"sub": str(user.id)})
    return Token(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/login-events")
async def list_login_events(
    user_id: int | None = None,
    limit: int = 100,
    days: int | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Recent login events for admin monitoring. Newest first.

    Filters:
    - `user_id` — restrict to one account (omit for all)
    - `limit`   — caps at 500
    - `days`    — restrict to the last N days

    Admin check is inline (not `require_admin` from categories.py) to avoid the
    circular import auth ⇄ categories.
    """
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin 권한이 필요합니다")

    capped = max(1, min(limit, 500))

    stmt = (
        select(LoginEvent, User.username)
        .join(User, User.id == LoginEvent.user_id)
        .order_by(LoginEvent.occurred_at.desc())
        .limit(capped)
    )
    if user_id is not None:
        stmt = stmt.where(LoginEvent.user_id == user_id)
    if days is not None and days > 0:
        cutoff = datetime.now() - timedelta(days=days)
        stmt = stmt.where(LoginEvent.occurred_at >= cutoff)

    rows = (await db.execute(stmt)).all()
    return {
        "events": [
            {
                "id": ev.id,
                "user_id": ev.user_id,
                "username": username,
                "ip": ev.ip,
                "user_agent": ev.user_agent,
                "occurred_at": ev.occurred_at.isoformat(),
            }
            for ev, username in rows
        ],
    }
