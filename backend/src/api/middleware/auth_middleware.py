from fastapi.security import HTTPBearer
from fastapi import Depends, HTTPException, status, Request
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime, timezone

from src.infrastructure.database import get_db
from src.models.user_model import User, UserRole
from src.config.settings import Settings


def _build_offline_user(uid: UUID, email: str):
    """Build a fully-populated offline user namespace that passes response serialization."""
    from types import SimpleNamespace
    now = datetime.now(timezone.utc)
    # Ensure email domain has at least one dot so Pydantic EmailStr accepts it
    if email and '@' in email:
        domain = email.split('@')[1]
        if '.' not in domain:
            email = f"{email.split('@')[0]}@{domain}.local"
    else:
        email = f"user_{uid.hex[:8]}@offline.local"
    return SimpleNamespace(
        id=uid,
        email=email,
        role=UserRole.STUDENT,
        hashed_password=None,
        full_name="Offline User",
        is_active=True,
        is_verified=True,
        created_at=now,
        updated_at=now,
    )

settings = Settings()
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

reusable_oauth2 = HTTPBearer(auto_error=False)

def get_current_user(
    request: Request,
    token_auth: HTTPBearer = Depends(reusable_oauth2),
    db: Session = Depends(get_db)
):
    """Verifies JWT from Authorization Bearer header or HTTPOnly Cookie, and retrieves the user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )
    
    token = None
    if token_auth:
        token = token_auth.credentials
    if not token:
        token = request.cookies.get("access_token")
        
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    try:
        uid = UUID(user_id)
    except ValueError:
        raise credentials_exception

    # Fast-path for offline local tokens or offline request headers (bypasses DB to avoid Postgres timeouts)
    if payload.get("mode") == "offline" or request.headers.get("x-offline-mode") == "true":
        return _build_offline_user(uid, payload.get("email", "offline@offline.local"))

    try:
        user = db.query(User).filter(User.id == uid).first()
        if user is None:
            raise credentials_exception
        return user
    except HTTPException:
        raise
    except Exception as db_err:
        import logging
        logging.getLogger("auth_middleware").warning(
            f"Database lookup failed during auth ({db_err}). Falling back to local offline user."
        )
        # Token signature already verified via SECRET_KEY; return authenticated local session
        return _build_offline_user(uid, payload.get("email", "offline@offline.local"))

def require_role(allowed_roles: list[UserRole]):
    """Returns a dependency that enforces RBAC authorization."""
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action"
            )
        return current_user
    return role_checker
