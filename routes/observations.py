from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import date
from dependencies import get_current_user, role_required
from database import supabase

router = APIRouter(prefix="/observations", tags=["observations"])

class ObservationCreate(BaseModel):
    teacher_id: str
    subject: str
    grade_level: str
    observation_date: str
    strengths: str
    improvements: str
    rating: int

class ObservationUpdate(BaseModel):
    subject: Optional[str] = None
    grade_level: Optional[str] = None
    strengths: Optional[str] = None
    improvements: Optional[str] = None
    rating: Optional[int] = None

# GET all observations
@router.get("/")
async def get_observations(
    status: Optional[str] = None,
    teacher_id: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    current_user = Depends(get_current_user)
):
    query = supabase.table("observations").select("*")

    # Role-based filtering
    if current_user["role"] == "teacher":
        query = query.eq("teacher_id", current_user["id"])
    elif current_user["role"] == "observer":
        query = query.eq("observer_id", current_user["id"])
    else:
        # Admin sees all in their school
        query = query.eq("school_id", current_user["school_id"])

    if status:
        query = query.eq("status", status)
    if teacher_id and current_user["role"] == "admin":
        query = query.eq("teacher_id", teacher_id)

    # Pagination
    offset = (page - 1) * limit
    result = query.order("created_at", desc=True)\
                  .range(offset, offset + limit - 1)\
                  .execute()

    return {"data": result.data, "page": page, "limit": limit}

# GET single observation
@router.get("/{observation_id}")
async def get_observation(
    observation_id: str,
    current_user = Depends(get_current_user)
):
    result = supabase.table("observations")\
        .select("*")\
        .eq("id", observation_id)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Observation not found")

    obs = result.data[0]

    # Row-level auth
    if current_user["role"] == "teacher" and obs["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user["role"] == "observer" and obs["observer_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return obs

# POST create observation
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_observation(
    body: ObservationCreate,
    current_user = Depends(role_required("admin", "observer"))
):
    data = {
        "school_id": current_user["school_id"],
        "observer_id": current_user["id"],
        "teacher_id": body.teacher_id,
        "subject": body.subject,
        "grade_level": body.grade_level,
        "observation_date": body.observation_date,
        "strengths": body.strengths,
        "improvements": body.improvements,
        "rating": body.rating,
        "status": "draft"
    }

    result = supabase.table("observations").insert(data).execute()

    # Log the creation
    supabase.table("observation_logs").insert({
        "observation_id": result.data[0]["id"],
        "changed_by": current_user["id"],
        "from_status": None,
        "to_status": "draft",
        "note": "Observation created"
    }).execute()

    return result.data[0]

# PATCH update observation
@router.patch("/{observation_id}")
async def update_observation(
    observation_id: str,
    body: ObservationUpdate,
    current_user = Depends(role_required("admin", "observer"))
):
    existing = supabase.table("observations")\
        .select("*").eq("id", observation_id).execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Observation not found")

    obs = existing.data[0]

    if obs["status"] not in ["draft", "submitted"]:
        raise HTTPException(
            status_code=400,
            detail="Cannot edit observation in current status"
        )

    updates = {k: v for k, v in body.dict().items() if v is not None}
    result = supabase.table("observations")\
        .update(updates).eq("id", observation_id).execute()

    return result.data[0]

# POST submit observation
@router.post("/{observation_id}/submit")
async def submit_observation(
    observation_id: str,
    current_user = Depends(role_required("admin", "observer"))
):
    existing = supabase.table("observations")\
        .select("*").eq("id", observation_id).execute()

    if not existing.data:
        raise HTTPException(status_code=404, detail="Not found")

    obs = existing.data[0]

    if obs["status"] != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit — current status is {obs['status']}"
        )

    result = supabase.table("observations")\
        .update({"status": "submitted"}).eq("id", observation_id).execute()

    supabase.table("observation_logs").insert({
        "observation_id": observation_id,
        "changed_by": current_user["id"],
        "from_status": "draft",
        "to_status": "submitted"
    }).execute()

    return {"message": "Observation submitted", "status": "submitted"}

# POST complete observation (admin only)
@router.post("/{observation_id}/complete")
async def complete_observation(
    observation_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("observations")\
        .update({"status": "completed"})\
        .eq("id", observation_id).execute()

    supabase.table("observation_logs").insert({
        "observation_id": observation_id,
        "changed_by": current_user["id"],
        "from_status": "submitted",
        "to_status": "completed"
    }).execute()

    return {"message": "Observation completed", "status": "completed"}