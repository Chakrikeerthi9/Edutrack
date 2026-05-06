from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: str
    password: str
    full_name: str
    role: str
    school_id: str
    department: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    school_id: str
    department: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None