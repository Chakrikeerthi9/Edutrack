from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional
from dependencies import get_current_user, role_required
from database import supabase

router = APIRouter(prefix="/reviews", tags=["reviews"])

class ReviewCreate(BaseModel):
    teacher_id: str
    period: str
    instructional_effectiveness: int
    classroom_management: int
    professionalism: int
    collaboration: int
    student_engagement: int
    notes: Optional[str] = None

@router.get("/")
async def get_reviews(
    teacher_id: Optional[str] = None,
    period: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    query = supabase.table("performance_reviews").select("*")

    if current_user["role"] == "teacher":
        query = query.eq("teacher_id", current_user["id"])
    else:
        query = query.eq("school_id", current_user["school_id"])
        if teacher_id:
            query = query.eq("teacher_id", teacher_id)

    if period:
        query = query.eq("period", period)

    result = query.order("created_at", desc=True).execute()
    return {"data": result.data}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_review(
    body: ReviewCreate,
    current_user = Depends(role_required("admin"))
):
    # Calculate overall rating
    scores = [
        body.instructional_effectiveness,
        body.classroom_management,
        body.professionalism,
        body.collaboration,
        body.student_engagement
    ]
    overall = round(sum(scores) / len(scores), 2)

    result = supabase.table("performance_reviews").insert({
        "school_id": current_user["school_id"],
        "reviewer_id": current_user["id"],
        "teacher_id": body.teacher_id,
        "period": body.period,
        "instructional_effectiveness": body.instructional_effectiveness,
        "classroom_management": body.classroom_management,
        "professionalism": body.professionalism,
        "collaboration": body.collaboration,
        "student_engagement": body.student_engagement,
        "overall_rating": overall,
        "notes": body.notes,
        "status": "draft"
    }).execute()

    return result.data[0]

@router.get("/{review_id}")
async def get_review(
    review_id: str,
    current_user = Depends(get_current_user)
):
    result = supabase.table("performance_reviews")\
        .select("*").eq("id", review_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Review not found")

    review = result.data[0]

    if current_user["role"] == "teacher" and \
       review["teacher_id"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return review

@router.post("/{review_id}/lock")
async def lock_review(
    review_id: str,
    current_user = Depends(role_required("admin"))
):
    result = supabase.table("performance_reviews")\
        .update({"status": "locked"})\
        .eq("id", review_id).execute()

    return {"message": "Review locked", "status": "locked"}