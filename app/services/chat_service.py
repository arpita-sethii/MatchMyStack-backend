# backend/app/services/chat_service.py
from sqlalchemy.orm import Session
from app.models.models import ChatRoom, Message, User, Project, Match, Icebreaker, TypingIndicator
from datetime import datetime, timedelta
from typing import List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def get_or_create_chat_room(
    db: Session,
    user_id: int,
    project_id: int,
    match_id: Optional[int] = None
) -> ChatRoom:
    """
    Get existing chat room or create new one.
    Only creates if user has matched (swiped right) on the project.
    """
    # Check if chat room already exists
    room = db.query(ChatRoom).filter(
        ChatRoom.user_id == user_id,
        ChatRoom.project_id == project_id
    ).first()
    
    if room:
        return room
    
    # Verify user has matched with this project
    match = db.query(Match).filter(
        Match.user_id == user_id,
        Match.project_id == project_id,
        Match.action == "match"
    ).first()
    
    if not match:
        raise PermissionError("Cannot create chat room: User has not matched with this project")
    
    # Create new chat room
    room = ChatRoom(
        user_id=user_id,
        project_id=project_id,
        match_id=match.id if match else match_id,
        unread_count_user=0,
        unread_count_owner=0
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    
    logger.info(f"Created chat room {room.id} for user {user_id} and project {project_id}")
    return room


def get_user_chat_rooms(db: Session, user_id: int) -> List[ChatRoom]:
    """
    Get all chat rooms for a user (as participant or project owner).
    Returns rooms sorted by last message time.
    """
    # Get rooms where user is the participant
    user_rooms = db.query(ChatRoom).filter(
        ChatRoom.user_id == user_id
    ).all()
    
    # Get rooms where user owns the project
    user_projects = db.query(Project).filter(Project.owner_id == user_id).all()
    project_ids = [p.id for p in user_projects]
    
    owner_rooms = db.query(ChatRoom).filter(
        ChatRoom.project_id.in_(project_ids)
    ).all() if project_ids else []
    
    # Combine and sort by last message
    all_rooms = list(set(user_rooms + owner_rooms))
    all_rooms.sort(
        key=lambda r: r.last_message_at or r.created_at,
        reverse=True
    )
    
    return all_rooms


def send_message(
    db: Session,
    room_id: int,
    sender_id: int,
    content: str,
    message_type: str = "text",
    file_url: Optional[str] = None,
    file_name: Optional[str] = None,
    file_size: Optional[int] = None
) -> Message:
    """
    Send a message in a chat room.
    Updates room's last message and increments unread count.
    """
    # Verify room exists
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        raise ValueError(f"Chat room {room_id} not found")
    
    # Verify sender is authorized (either user or project owner)
    project = db.query(Project).filter(Project.id == room.project_id).first()
    if sender_id != room.user_id and sender_id != project.owner_id:
        raise PermissionError("User not authorized to send messages in this room")
    
    # Create message
    message = Message(
        room_id=room_id,
        sender_id=sender_id,
        content=content,
        message_type=message_type,
        file_url=file_url,
        file_name=file_name,
        file_size=file_size,
        is_read=False
    )
    db.add(message)
    
    # Update room's last message info
    preview = content[:200] if len(content) <= 200 else content[:197] + "..."
    room.last_message_at = datetime.utcnow()
    room.last_message_preview = preview
    
    # Increment unread count for recipient
    if sender_id == room.user_id:
        # User sent message, increment owner's unread
        room.unread_count_owner += 1
    else:
        # Owner sent message, increment user's unread
        room.unread_count_user += 1
    
    db.add(room)
    db.commit()
    db.refresh(message)
    
    logger.info(f"Message {message.id} sent in room {room_id} by user {sender_id}")
    return message


def get_room_messages(
    db: Session,
    room_id: int,
    limit: int = 50,
    before_id: Optional[int] = None
) -> List[Message]:
    """
    Get messages from a chat room with pagination.
    
    Args:
        room_id: Chat room ID
        limit: Max messages to return
        before_id: Get messages before this message ID (for pagination)
    """
    query = db.query(Message).filter(
        Message.room_id == room_id,
        Message.deleted == False
    )
    
    if before_id:
        query = query.filter(Message.id < before_id)
    
    messages = query.order_by(Message.created_at.desc()).limit(limit).all()
    messages.reverse()  # Return in chronological order
    
    return messages


def mark_messages_as_read(
    db: Session,
    room_id: int,
    user_id: int
) -> int:
    """
    Mark all unread messages in a room as read for a user.
    Returns count of messages marked as read.
    """
    room = db.query(ChatRoom).filter(ChatRoom.id == room_id).first()
    if not room:
        return 0
    
    # Get project to determine if user is owner
    project = db.query(Project).filter(Project.id == room.project_id).first()
    is_owner = (user_id == project.owner_id)
    
    # Find unread messages sent by the other party
    if is_owner:
        # Owner reading messages from user
        unread_messages = db.query(Message).filter(
            Message.room_id == room_id,
            Message.sender_id == room.user_id,
            Message.is_read == False
        ).all()
        
        # Reset owner's unread count
        room.unread_count_owner = 0
    else:
        # User reading messages from owner
        unread_messages = db.query(Message).filter(
            Message.room_id == room_id,
            Message.sender_id == project.owner_id,
            Message.is_read == False
        ).all()
        
        # Reset user's unread count
        room.unread_count_user = 0
    
    # Mark messages as read
    count = 0
    for msg in unread_messages:
        msg.is_read = True
        msg.read_at = datetime.utcnow()
        db.add(msg)
        count += 1
    
    db.add(room)
    db.commit()
    
    logger.info(f"Marked {count} messages as read in room {room_id} for user {user_id}")
    return count


def get_icebreakers(db: Session, category: Optional[str] = None) -> List[Icebreaker]:
    """
    Get icebreaker suggestions.
    """
    query = db.query(Icebreaker).filter(Icebreaker.is_active == True)
    
    if category:
        query = query.filter(Icebreaker.category == category)
    
    return query.order_by(Icebreaker.usage_count.asc()).limit(10).all()


def use_icebreaker(db: Session, icebreaker_id: int) -> None:
    """
    Increment usage count when icebreaker is used.
    """
    icebreaker = db.query(Icebreaker).filter(Icebreaker.id == icebreaker_id).first()
    if icebreaker:
        icebreaker.usage_count += 1
        db.add(icebreaker)
        db.commit()


def set_typing_indicator(
    db: Session,
    room_id: int,
    user_id: int,
    duration_seconds: int = 5
) -> None:
    """
    Set typing indicator for a user in a room.
    Auto-expires after duration_seconds.
    """
    # Remove any existing typing indicator for this user in this room
    db.query(TypingIndicator).filter(
        TypingIndicator.room_id == room_id,
        TypingIndicator.user_id == user_id
    ).delete()
    
    # Create new typing indicator
    expires_at = datetime.utcnow() + timedelta(seconds=duration_seconds)
    indicator = TypingIndicator(
        room_id=room_id,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(indicator)
    db.commit()


def get_typing_users(db: Session, room_id: int, exclude_user_id: int) -> List[User]:
    """
    Get users currently typing in a room (excluding the requesting user).
    Automatically cleans up expired indicators.
    """
    now = datetime.utcnow()
    
    # Remove expired indicators
    db.query(TypingIndicator).filter(
        TypingIndicator.expires_at < now
    ).delete()
    db.commit()
    
    # Get active typing indicators
    indicators = db.query(TypingIndicator).filter(
        TypingIndicator.room_id == room_id,
        TypingIndicator.user_id != exclude_user_id,
        TypingIndicator.expires_at > now
    ).all()
    
    user_ids = [ind.user_id for ind in indicators]
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    
    return users


def get_unread_count_for_user(db: Session, user_id: int) -> int:
    """
    Get total unread message count across all rooms for a user.
    """
    # Get rooms where user is participant
    user_rooms = db.query(ChatRoom).filter(ChatRoom.user_id == user_id).all()
    user_unread = sum(room.unread_count_user for room in user_rooms)
    
    # Get rooms where user is project owner
    user_projects = db.query(Project).filter(Project.owner_id == user_id).all()
    project_ids = [p.id for p in user_projects]
    
    owner_rooms = db.query(ChatRoom).filter(
        ChatRoom.project_id.in_(project_ids)
    ).all() if project_ids else []
    owner_unread = sum(room.unread_count_owner for room in owner_rooms)
    
    return user_unread + owner_unread


def delete_message(db: Session, message_id: int, user_id: int) -> bool:
    """
    Soft delete a message (only sender can delete their own messages).
    """
    message = db.query(Message).filter(Message.id == message_id).first()
    if not message:
        return False
    
    if message.sender_id != user_id:
        raise PermissionError("Can only delete your own messages")
    
    message.deleted = True
    message.content = "[Message deleted]"
    db.add(message)
    db.commit()
    
    return True