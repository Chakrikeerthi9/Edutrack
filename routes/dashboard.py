from fastapi import APIRouter, Depends
from dependencies import get_current_user, role_required
from database import supabase

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/stats")
async def get_admin_stats(
    current_user = Depends(role_required("admin"))
):
    school_id = current_user["school_id"]

    # Total staff
    staff = supabase.table("users")\
        .select("id", count="exact")\
        .eq("school_id", school_id)\
        .in_("role", ["teacher", "observer"])\
        .execute()

    # Observations this month
    obs = supabase.table("observations")\
        .select("id,rating,status")\
        .eq("school_id", school_id)\
        .execute()

    all_obs = obs.data or []
    completed_obs = [o for o in all_obs if o["status"] == "completed"]
    pending_obs = [o for o in all_obs if o["status"] in ["submitted", "under_review"]]

    # Average rating
    ratings = [o["rating"] for o in completed_obs if o["rating"]]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 0

    # Pending reviews
    reviews = supabase.table("performance_reviews")\
        .select("id", count="exact")\
        .eq("school_id", school_id)\
        .in_("status", ["draft", "submitted"])\
        .execute()

    # Goals stats
    goals = supabase.table("goals")\
        .select("id,status,progress")\
        .eq("school_id", school_id)\
        .execute()

    all_goals = goals.data or []
    overdue_goals = [g for g in all_goals if g["status"] == "overdue"]
    active_goals = [g for g in all_goals if g["status"] == "active"]

    # Unread messages
    messages = supabase.table("messages")\
        .select("id", count="exact")\
        .eq("recipient_id", current_user["id"])\
        .eq("status", "unread")\
        .execute()

    return {
        "total_staff": staff.count or 0,
        "total_observations": len(all_obs),
        "pending_observations": len(pending_obs),
        "completed_observations": len(completed_obs),
        "avg_rating": avg_rating,
        "pending_reviews": reviews.count or 0,
        "total_goals": len(all_goals),
        "overdue_goals": len(overdue_goals),
        "active_goals": len(active_goals),
        "unread_messages": messages.count or 0
    }

@router.get("/teacher")
async def get_teacher_dashboard(
    current_user = Depends(role_required("teacher"))
):
    teacher_id = current_user["id"]

    # My observations
    obs = supabase.table("observations")\
        .select("*")\
        .eq("teacher_id", teacher_id)\
        .order("created_at", desc=True)\
        .limit(5)\
        .execute()

    # My goals
    goals = supabase.table("goals")\
        .select("*")\
        .eq("staff_id", teacher_id)\
        .execute()

    # My latest review
    review = supabase.table("performance_reviews")\
        .select("*")\
        .eq("teacher_id", teacher_id)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    # Unread messages
    messages = supabase.table("messages")\
        .select("id", count="exact")\
        .eq("recipient_id", teacher_id)\
        .eq("status", "unread")\
        .execute()

    return {
        "recent_observations": obs.data,
        "goals": goals.data,
        "latest_review": review.data[0] if review.data else None,
        "unread_messages": messages.count or 0
    }

@router.get("/student")
async def get_student_dashboard(
    current_user = Depends(role_required("student"))
):
    student_id = current_user["id"]

    # My grades
    grades = supabase.table("grades")\
        .select("*")\
        .eq("student_id", student_id)\
        .eq("shared_with_student", True)\
        .execute()

    # Announcements for students
    announcements = supabase.table("announcements")\
        .select("*")\
        .eq("school_id", current_user["school_id"])\
        .in_("audience", ["students", "all"])\
        .order("created_at", desc=True)\
        .limit(5)\
        .execute()

    # Leave requests
    leaves = supabase.table("leave_requests")\
        .select("*")\
        .eq("student_id", student_id)\
        .order("created_at", desc=True)\
        .execute()

    return {
        "grades": grades.data,
        "announcements": announcements.data,
        "leave_requests": leaves.data
    }