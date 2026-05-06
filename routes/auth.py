from fastapi import APIRouter, HTTPException, status
from models.auth import LoginRequest, TokenResponse
from services.auth_service import authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    user = await authenticate_user(request.email, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    token = create_access_token({
        "user_id": user["id"],
        "role": user["role"],
        "school_id": user["school_id"]
    })

    return TokenResponse(
        access_token=token,
        user_id=user["id"],
        role=user["role"],
        full_name=user["full_name"]
    )