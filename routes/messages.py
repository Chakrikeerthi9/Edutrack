from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from typing import Optional
from dependencies import get_current_user
from database import supabase

router = APIRouter(prefix="/messages", tags=["messages"])

class MessageCreate(BaseModel):
    recipient_id: str
    subject: str
    body: str
    message_type: str = "general"
    parent_message_id: Optional[str] = None

@router.get("/")
async def get_messages(
    msg_status: Optional[str] = None,
    message_type: Optional[str] = None,
    current_user = Depends(get_current_user)
):
    query = supabase.table("messages")\
        .select("*")\
        .eq("recipient_id", current_user["id"])

    if msg_status:
        query = query.eq("status", msg_status)
    if message_type:
        query = query.eq("message_type", message_type)

    result = query.order("created_at", desc=True).execute()
    return {"data": result.data}

@router.post("/", status_code=status.HTTP_201_CREATED)
async def send_message(
    body: MessageCreate,
    current_user = Depends(get_current_user)
):
    result = supabase.table("messages").insert({
        "school_id": current_user["school_id"],
        "sender_id": current_user["id"],
        "recipient_id": body.recipient_id,
        "subject": body.subject,
        "body": body.body,
        "message_type": body.message_type,
        "parent_message_id": body.parent_message_id,
        "status": "unread"
    }).execute()

    return result.data[0]

@router.patch("/{message_id}/read")
async def mark_read(
    message_id: str,
    current_user = Depends(get_current_user)
):
    result = supabase.table("messages")\
        .update({"status": "read"})\
        .eq("id", message_id)\
        .eq("recipient_id", current_user["id"])\
        .execute()

    return {"message": "Marked as read"}