from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str

class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None
    school_id: Optional[str] = None