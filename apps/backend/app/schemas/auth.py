"""Authentication request/response schemas (Pydantic v2)."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TokenRequest(BaseModel):
    """Login request with email and password."""

    email: EmailStr = Field(..., description="Kullanici e-posta adresi")
    password: str = Field(..., min_length=1, description="Kullanici sifresi")


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str = Field(..., description="Mevcut refresh token")


class TokenResponse(BaseModel):
    """Token response with access and refresh tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token tipi")
    expires_in: int = Field(..., description="Access token gecerlilik suresi (saniye)")


class UserResponse(BaseModel):
    """User information response."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Kullanici UUID")
    email: str = Field(..., description="Kullanici e-posta adresi")
    is_active: bool = Field(..., description="Kullanici aktif mi")
    created_at: str = Field(..., description="Olusturulma zamani (ISO 8601)")


class ProfileResponse(BaseModel):
    """User profile response."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="Kullanici UUID")
    email: str = Field(..., description="Kullanici e-posta adresi")
    display_name: str | None = Field(None, description="Goruntu adi")
    created_at: str = Field(..., description="Olusturulma zamani (ISO 8601)")


class ProfileUpdateRequest(BaseModel):
    """Profile update request."""

    display_name: str | None = Field(None, min_length=1, max_length=255, description="Yeni goruntu adi")
