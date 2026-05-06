from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from dependencies import get_current_user, role_required
from database import supabase

router = APIRouter(prefix="/goals", tags=["goals"])

class GoalCreate(BaseModel):
    staff_id: str
    title: str
    description: Optional[str] = None
    target_date: Optional[str] = None

class GoalProgressUpdate(BaseModel):
    progress: int  # 0-100

class GoalStatusUpdate(BaseModel):
    status: str  # active, completed, cancelled

@router.get("/")
async def get_goals(
    staff_id: Optional[str] = None,
    status: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    query = supabase.table("goals").select("*")

    if current_user["role"] == "teacher":
        query = query.eq("staff_id", current_user["id"])
    else:
        query = query.eq("school_id", current_user["school_id"])
        if staff_id:
            query = query.eq("staff_id", staff_id)

    if status:
        query = query.eq("status", status)

    result = query.order("target_date").execute()
    return {"data": result.data}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_goal(
    body: GoalCreate,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("goals").insert({
        "school_id": current_user["school_id"],
        "staff_id": body.staff_id,
        "title": body.title,
        "description": body.description,
        "target_date": body.target_date,
        "progress": 0,
        "status": "active"
    }).execute()

    return result.data[0]

@router.patch("/{goal_id}/progress")
async def update_progress(
    goal_id: str,
    body: GoalProgressUpdate,
    current_user = Depends(get_current_user)
):
    if not (0 <= body.progress <= 100):
        raise HTTPException(status_code=400, detail="Progress must be 0-100")

    updates = {"progress": body.progress}

    # Auto-complete if 100%
    if body.progress == 100:
        updates["status"] = "completed"

    result = supabase.table("goals")\
        .update(updates).eq("id", goal_id).execute()

    return result.data[0]

@router.patch("/{goal_id}/status")
async def update_status(
    goal_id: str,
    body: GoalStatusUpdate,
    current_user = Depends(role_required("admin"))
):
    valid = ["active", "completed", "overdue", "cancelled"]
    if body.status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid}")

    result = supabase.table("goals")\
        .update({"status": body.status}).eq("id", goal_id).execute()

    return result.data[0]