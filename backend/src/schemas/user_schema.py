from pydantic import BaseModel, EmailStr, ConfigDict
from uuid import UUID
from datetime import datetime
from src.models.user_model import UserRole

# ----------------- User Schemas -----------------
class UserBase(BaseModel):
    email: EmailStr
    full_name: str | None = None
    role: UserRole = UserRole.STUDENT
    is_active: bool = True
    is_verified: bool = False

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
    role: UserRole | None = None

# ----------------- Auth/Token Schemas -----------------
class TokenRefreshRequest(BaseModel):
    refresh_token: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    offline_token: str | None = None
    token_type: str = "bearer"

class EmailOtpCreate(BaseModel):
    email: EmailStr
    purpose: str

class EmailOtpVerify(BaseModel):
    email: EmailStr
    otp: str
    purpose: str
