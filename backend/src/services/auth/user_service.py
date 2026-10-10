from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from jose import jwt, JWTError
from src.config.settings import Settings
from src.models.user_model import User
from src.repositories.postgres.user_repository import UserRepository
from src.schemas.user_schema import UserCreate, TokenResponse
from fastapi import HTTPException, status
from pwdlib import PasswordHash

# Initialize PasswordHash using the recommended configuration (uses Argon2id by default)
password_hash = PasswordHash.recommended()

settings = Settings()

class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return password_hash.verify(plain_password, hashed_password)
        except Exception:
            return False

    def get_password_hash(self, password: str) -> str:
        return password_hash.hash(password)

    def create_access_token(self, subject: str | Any, expires_delta: timedelta | None = None) -> str:
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    def create_refresh_token(self, subject: str | Any) -> str:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode = {"exp": expire, "sub": str(subject), "type": "refresh"}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt

    def refresh_access_token(self, refresh_token: str) -> TokenResponse:
        try:
            payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            if payload.get("type") != "refresh":
                raise HTTPException(status_code=401, detail="Invalid token type")
            user_id = payload.get("sub")
            if user_id is None:
                raise HTTPException(status_code=401, detail="Invalid token")
        except JWTError:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        
        # Optionally, verify user still exists and is active
        user = self.repository.get_by_id(UUID(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found or inactive")

        new_access_token = self.create_access_token(subject=user_id)
        # We can issue a new refresh token or keep the old one depending on policy.
        # Let's issue a new one for rotating refresh tokens.
        new_refresh_token = self.create_refresh_token(subject=user_id)

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            token_type="bearer"
        )

    def register_user(self, user_in: UserCreate) -> User:
        user = self.repository.get_by_email(user_in.email)
        if user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
        hashed_password = self.get_password_hash(user_in.password)
        return self.repository.create(user_in, hashed_password)

    def authenticate_user(self, email: str, password: str) -> TokenResponse:
        user = self.repository.get_by_email(email)
        if not user or not user.hashed_password:
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        
        if not self.verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        
        if not user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")

        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = self.create_access_token(
            subject=str(user.id), expires_delta=access_token_expires
        )
        
        refresh_token = self.create_refresh_token(subject=str(user.id))
        
        # Create a 30-day offline token for desktop-app mode fallback
        offline_token = self.create_access_token(
            subject=str(user.id), expires_delta=timedelta(days=30)
        )

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            offline_token=offline_token,
            token_type="bearer"
        )
