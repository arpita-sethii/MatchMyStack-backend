# app/schemas/schemas.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime


# Input model for signup/login
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=72)
    name: Optional[str] = None


# Output model returned to clients (never include password)
class UserOut(BaseModel):
    id: int
    email: EmailStr
    name: Optional[str] = None
    bio: Optional[str] = None
    skills: Optional[List[str]] = None
    role: Optional[str] = None
    created_at: Optional[datetime] = None
    email_verified: Optional[bool] = False

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProjectCreate(BaseModel):
    title: str
    description: Optional[str] = None
    required_skills: Optional[List[str]] = []
    required_roles: Optional[List[str]] = []
    min_experience: Optional[int] = 0
    max_experience: Optional[int] = 10
    timezone: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Schema for updating a project - all fields optional"""
    title: Optional[str] = None
    description: Optional[str] = None
    required_skills: Optional[List[str]] = None
    required_roles: Optional[List[str]] = None
    min_experience: Optional[int] = None
    max_experience: Optional[int] = None
    timezone: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    owner_id: int
    title: str
    description: Optional[str]
    required_skills: Optional[List[str]]
    required_roles: Optional[List[str]] = None
    min_experience: Optional[int] = None
    max_experience: Optional[int] = None
    timezone: Optional[str] = None
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    owner: Optional[UserOut] = None  # Include owner details

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class InterestedUser(BaseModel):
    """Schema for users who showed interest in a project"""
    id: int
    name: Optional[str]
    email: str
    bio: Optional[str] = None
    skills: List[str] = []
    role: Optional[str] = None
    matched_at: Optional[str] = None  # ISO format timestamp

    class Config:
        from_attributes = True


class MatchItem(BaseModel):
    user_id: int
    score: float
    reason: Optional[str] = None
    user: Optional[Any] = None


class MatchesOut(BaseModel):
    project_id: int
    matches: List[MatchItem]


# ----- OTP related schemas -----

class OTPRequest(BaseModel):
    """
    Request an OTP to be sent to `email`.
    Example: POST /auth/request_otp
    """
    email: EmailStr


class OTPVerifyRequest(BaseModel):
    """
    Verify an OTP that was sent to the email.
    Example: POST /auth/verify_otp
    """
    email: EmailStr
    otp: str = Field(..., min_length=4, max_length=16)


class ResendOTPRequest(BaseModel):
    """
    Optional request model for resending OTP (same as OTPRequest).
    """
    email: EmailStr


class OTPResponse(BaseModel):
    """
    Generic OTP response used for both send and verify endpoints.
    """
    success: bool
    message: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True


# ----- NEW: Password Reset schemas -----

class ForgotPasswordRequest(BaseModel):
    """Request a password reset link"""
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Reset password using token"""
    token: str = Field(..., min_length=32)
    new_password: str = Field(..., min_length=6, max_length=72)


class PasswordResetResponse(BaseModel):
    """Response for password reset operations"""
    success: bool
    message: str

    class Config:
        from_attributes = True

# Add to existing schemas.py

from datetime import datetime
from typing import Optional
from pydantic import BaseModel

# Chat Schemas
class ChatRoomOut(BaseModel):
    id: int
    project_id: int
    project_title: str
    other_user_id: int
    other_user_name: str
    last_message_preview: Optional[str]
    last_message_at: Optional[datetime]
    unread_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    content: str
    message_type: Optional[str] = "text"
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None


class MessageOut(BaseModel):
    id: int
    room_id: int
    sender_id: int
    sender_name: str
    content: str
    message_type: str
    file_url: Optional[str]
    file_name: Optional[str]
    file_size: Optional[int]
    is_read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class IcebreakerOut(BaseModel):
    id: int
    category: str
    template_text: str
    
    class Config:
        from_attributes = True


class TypingIndicatorRequest(BaseModel):
    room_id: int