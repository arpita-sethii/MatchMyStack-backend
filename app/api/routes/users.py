# backend/app/api/routes/users.py - FIXED VERSION
# Fixed session management for skill updates

from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, get_db
from app.schemas.schemas import UserOut
from app.models.models import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return current_user


@router.patch("/me", response_model=UserOut)
def update_my_profile(
    payload: dict = Body(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update current user's profile (skills, bio, name, role).
    
    Expects JSON body like:
    {
        "skills": ["Python", "React", "FastAPI"],
        "bio": "Full-stack developer",
        "name": "John Doe",
        "role": "Backend Engineer"
    }
    
    ✅ FIXED: Properly uses db session from dependency injection
    ✅ FIXED: Skills persist correctly to database
    """
    # Update skills if provided
    if "skills" in payload:
        skills = payload["skills"]
        if not isinstance(skills, list):
            raise HTTPException(status_code=400, detail="Skills must be a list")
        current_user.skills = skills
    
    # Update bio if provided
    if "bio" in payload:
        current_user.bio = payload["bio"]
    
    # Update name if provided
    if "name" in payload:
        current_user.name = payload["name"]
    
    # Update role if provided
    if "role" in payload:
        current_user.role = payload["role"]
    
    # Commit changes using the properly injected session
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    
    return current_user