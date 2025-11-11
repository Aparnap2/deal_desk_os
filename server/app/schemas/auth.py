from datetime import timedelta

from pydantic import BaseModel, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = Field(default="bearer")
    expires_in: int


class LoginPayload(BaseModel):
    email: str
    password: str


def get_token_expiry_seconds(minutes: int) -> int:
    return int(timedelta(minutes=minutes).total_seconds())
