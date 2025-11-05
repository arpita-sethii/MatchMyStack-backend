# backend/app/api/routes/chat.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import verify_token
from app.models.models import User, Project, ChatRoom, Message
from datetime import datetime  # ✅ ADD THIS LINE
from app.services import chat_service
from app.schemas.schemas import (
    ChatRoomOut,
    MessageOut,
    MessageCreate,
    IcebreakerOut,
    TypingIndicatorRequest
)
from typing import List, Optional
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging
import os
from pathlib import Path

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)
security = HTTPBearer()

# File upload configuration
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads" / "chat"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".pdf", ".doc", ".docx", ".txt"}


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> int:
    """Extract user ID from JWT token"""
    token = credentials.credentials
    payload = verify_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return int(user_id)


@router.get("/rooms", response_model=List[ChatRoomOut])
def list_chat_rooms(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Get all chat rooms for the current user.
    Includes rooms where user is participant or project owner.
    """
    try:
        rooms = chat_service.get_user_chat_rooms(db, current_user_id)
        
        # Transform to response format
        result = []
        for room in rooms:
            # Get project info
            project = db.query(Project).filter(Project.id == room.project_id).first()
            
            # Get other participant info
            other_user_id = room.user_id if room.user_id != current_user_id else project.owner_id
            other_user = db.query(User).filter(User.id == other_user_id).first()
            
            # Determine unread count for current user
            is_owner = (current_user_id == project.owner_id)
            unread_count = room.unread_count_owner if is_owner else room.unread_count_user
            
            result.append(ChatRoomOut(
                id=room.id,
                project_id=room.project_id,
                project_title=project.title if project else "Unknown Project",
                other_user_id=other_user_id,
                other_user_name=other_user.name if other_user else "Unknown User",
                last_message_preview=room.last_message_preview,
                last_message_at=room.last_message_at,
                unread_count=unread_count,
                created_at=room.created_at
            ))
        
        return result
    except Exception as e:
        logger.exception(f"Error listing chat rooms: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms/{room_id}", response_model=ChatRoomOut)
def get_chat_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get details of a specific chat room"""
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Chat room not found")
    
    # Verify user has access
    project = db.query(Project).filter(Project.id == room.project_id).first()
    if current_user_id != room.user_id and current_user_id != project.owner_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get other participant
    other_user_id = room.user_id if room.user_id != current_user_id else project.owner_id
    other_user = db.query(User).filter(User.id == other_user_id).first()
    
    is_owner = (current_user_id == project.owner_id)
    unread_count = room.unread_count_owner if is_owner else room.unread_count_user
    
    return ChatRoomOut(
        id=room.id,
        project_id=room.project_id,
        project_title=project.title if project else "Unknown Project",
        other_user_id=other_user_id,
        other_user_name=other_user.name if other_user else "Unknown User",
        last_message_preview=room.last_message_preview,
        last_message_at=room.last_message_at,
        unread_count=unread_count,
        created_at=room.created_at
    )


@router.post("/rooms/{project_id}", response_model=ChatRoomOut, status_code=status.HTTP_201_CREATED)
def create_or_get_chat_room(
    project_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Create a new chat room or get existing one.
    User must have matched with the project first.
    """
    try:
        room = chat_service.get_or_create_chat_room(db, current_user_id, project_id)
        
        project = db.query(Project).filter(Project.id == room.project_id).first()
        other_user = db.query(User).filter(User.id == project.owner_id).first()
        
        return ChatRoomOut(
            id=room.id,
            project_id=room.project_id,
            project_title=project.title if project else "Unknown Project",
            other_user_id=project.owner_id,
            other_user_name=other_user.name if other_user else "Unknown User",
            last_message_preview=room.last_message_preview,
            last_message_at=room.last_message_at,
            unread_count=room.unread_count_user,
            created_at=room.created_at
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(f"Error creating chat room: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rooms/{room_id}/messages", response_model=List[MessageOut])
def get_messages(
    room_id: int,
    limit: int = 50,
    before_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Get messages from a chat room with pagination.
    """
    # Verify room exists and user has access
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Chat room not found")
    
    project = db.query(Project).filter(Project.id == room.project_id).first()
    if current_user_id != room.user_id and current_user_id != project.owner_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get messages
    messages = chat_service.get_room_messages(db, room_id, limit, before_id)
    
    return [
        MessageOut(
            id=msg.id,
            room_id=msg.room_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.name if msg.sender else "Unknown",
            content=msg.content,
            message_type=msg.message_type,
            file_url=msg.file_url,
            file_name=msg.file_name,
            file_size=msg.file_size,
            is_read=msg.is_read,
            created_at=msg.created_at
        )
        for msg in messages
    ]


@router.post("/rooms/{room_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def send_message(
    room_id: int,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Send a message in a chat room"""
    try:
        msg = chat_service.send_message(
            db=db,
            room_id=room_id,
            sender_id=current_user_id,
            content=message.content,
            message_type=message.message_type or "text",
            file_url=message.file_url,
            file_name=message.file_name,
            file_size=message.file_size
        )
        
        return MessageOut(
            id=msg.id,
            room_id=msg.room_id,
            sender_id=msg.sender_id,
            sender_name=msg.sender.name if msg.sender else "Unknown",
            content=msg.content,
            message_type=msg.message_type,
            file_url=msg.file_url,
            file_name=msg.file_name,
            file_size=msg.file_size,
            is_read=msg.is_read,
            created_at=msg.created_at
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rooms/{room_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_as_read(
    room_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Mark all messages in a room as read"""
    try:
        chat_service.mark_messages_as_read(db, room_id, current_user_id)
    except Exception as e:
        logger.exception(f"Error marking messages as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Upload a file for chat (images, documents).
    Returns file URL to be sent in message.
    """
    try:
        # Validate file size
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Generate unique filename
        timestamp = int(datetime.now().timestamp())
        filename = f"{current_user_id}_{timestamp}_{file.filename}"
        file_path = UPLOAD_DIR / filename
        
        # Save file
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Return file URL
        file_url = f"/uploads/chat/{filename}"
        
        logger.info(f"File uploaded: {filename} by user {current_user_id}")
        
        return {
            "file_url": file_url,
            "file_name": file.filename,
            "file_size": len(contents),
            "message": "File uploaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail="File upload failed")


@router.get("/icebreakers", response_model=List[IcebreakerOut])
def get_icebreakers(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get icebreaker suggestions"""
    icebreakers = chat_service.get_icebreakers(db, category)
    
    return [
        IcebreakerOut(
            id=ib.id,
            category=ib.category,
            template_text=ib.template_text
        )
        for ib in icebreakers
    ]


@router.post("/icebreakers/{icebreaker_id}/use", status_code=status.HTTP_204_NO_CONTENT)
def use_icebreaker(
    icebreaker_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Track usage of an icebreaker"""
    chat_service.use_icebreaker(db, icebreaker_id)


@router.post("/rooms/{room_id}/typing", status_code=status.HTTP_204_NO_CONTENT)
def set_typing(
    room_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Set typing indicator for current user"""
    chat_service.set_typing_indicator(db, room_id, current_user_id)


@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Get total unread message count for current user"""
    count = chat_service.get_unread_count_for_user(db, current_user_id)
    return {"unread_count": count}


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Delete a message (soft delete)"""
    try:
        success = chat_service.delete_message(db, message_id, current_user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Message not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.exception(f"Error deleting message: {e}")
        raise HTTPException(status_code=500, detail=str(e))