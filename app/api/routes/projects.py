# backend/app/api/routes/projects.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.api.deps import get_db, get_current_user
from app.models.models import Project, User, Resume, Match
from app.schemas.schemas import ProjectCreate, ProjectOut, ProjectUpdate, MatchesOut, MatchItem, InterestedUser
from app.services.embedding_engine import EmbeddingEngine
from app.services.matching_engine import MatchingEngineWrapper
import logging

router = APIRouter(prefix="/projects", tags=["projects"])
matcher = MatchingEngineWrapper()
logger = logging.getLogger(__name__)


# Action request model
class ActionRequest(BaseModel):
    action: str  # "match" or "pass"


@router.get("", response_model=List[ProjectOut])
def get_all_projects(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Get all projects for the current user.
    Returns projects owned by the user.
    """
    projects = (
        db.query(Project)
        .filter(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    
    logger.info(f"User {current_user.id} fetched {len(projects)} projects")
    return projects


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific project by ID"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return project


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new project"""
    # Build a profile text for the project to embed
    profile_text = " ".join(filter(None, [payload.title, payload.description, " ".join(payload.required_skills or [])]))
    embedder = EmbeddingEngine()
    embedding = None
    try:
        emb = embedder.embed_project({
            "title": payload.title,
            "description": payload.description,
            "required_skills": payload.required_skills or []
        })
        embedding = list(emb) if emb else None
    except Exception as e:
        logger.warning(f"Failed to generate embedding for project: {e}")
        embedding = None

    project = Project(
        owner_id=current_user.id,
        title=payload.title,
        description=payload.description,
        required_skills=payload.required_skills,
        required_roles=payload.required_roles,
        min_experience=payload.min_experience,
        max_experience=payload.max_experience,
        timezone=payload.timezone,
        embedding=embedding
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    logger.info(f"User {current_user.id} created project {project.id}: {project.title}")
    return project




@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a project (owner only)"""
    project = db.query(Project).filter(Project.id == project_id).first()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Only owner can update
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this project")
    
    # Update fields
    if payload.title is not None:
        project.title = payload.title
    if payload.description is not None:
        project.description = payload.description
    if payload.required_skills is not None:
        project.required_skills = payload.required_skills
    if payload.required_roles is not None:
        project.required_roles = payload.required_roles
    if payload.min_experience is not None:
        project.min_experience = payload.min_experience
    if payload.max_experience is not None:
        project.max_experience = payload.max_experience
    if payload.timezone is not None:
        project.timezone = payload.timezone
    
    # Regenerate embedding if content changed
    if payload.title or payload.description or payload.required_skills:
        try:
            embedder = EmbeddingEngine()
            emb = embedder.embed_project({
                "title": project.title,
                "description": project.description,
                "required_skills": project.required_skills or []
            })
            project.embedding = list(emb) if emb else None
        except Exception as e:
            logger.warning(f"Failed to regenerate embedding: {e}")
    
    db.commit()
    db.refresh(project)
    
    logger.info(f"User {current_user.id} updated project {project.id}")
    return project


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a project (owner only)"""
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Only owner can delete
        if project.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this project")
        
        # ✅ DELETE RELATED MATCHES FIRST to avoid FK constraint violation
        db.query(Match).filter(Match.project_id == project_id).delete()
        
        # Now delete the project
        db.delete(project)
        db.commit()
        
        logger.info(f"User {current_user.id} deleted project {project_id}")
        return {"success": True, "message": "Project deleted successfully"}
    
    except HTTPException:
        # Re-raise HTTP exceptions (404, 403)
        raise
    except Exception as e:
        # Catch any other errors
        db.rollback()
        logger.error(f"Error deleting project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")


@router.post("/{project_id}/action")
def handle_project_action(
    project_id: int,
    action_req: ActionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Handle swipe action (match or pass) on a project.
    Stores the action in the database.
    """
    action = action_req.action.lower()
    
    if action not in ["match", "pass"]:
        raise HTTPException(status_code=400, detail="Action must be 'match' or 'pass'")
    
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Check if action already exists
    existing_match = db.query(Match).filter(
        Match.user_id == current_user.id,
        Match.project_id == project_id
    ).first()
    
    if existing_match:
        # Update existing action
        existing_match.action = action
        logger.info(f"User {current_user.id} updated action to {action} for project {project_id}")
    else:
        # Create new match record
        new_match = Match(
            user_id=current_user.id,
            project_id=project_id,
            action=action
        )
        db.add(new_match)
        logger.info(f"User {current_user.id} {action}ed project {project_id}")
    
    db.commit()
    
    return {
        "success": True,
        "project_id": project_id,
        "action": action,
        "message": f"Successfully {action}ed project"
    }


@router.get("/{project_id}/interested", response_model=List[InterestedUser])
def get_interested_users(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get all users who matched (showed interest) in this project.
    Only project owner can access this.
    """
    # Verify project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Only owner can see interested users
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only project owner can view interested users")
    
    # Get all users who matched this project
    matches = (
        db.query(Match)
        .filter(Match.project_id == project_id, Match.action == "match")
        .order_by(Match.created_at.desc())
        .all()
    )
    
    interested_users = []
    for match in matches:
        user = match.user
        if user:
            interested_users.append({
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "bio": user.bio,
                "skills": user.skills or [],
                "role": user.role,
                "matched_at": match.created_at.isoformat() if match.created_at else None
            })
    
    logger.info(f"Project {project_id} has {len(interested_users)} interested users")
    return interested_users


@router.get("/{project_id}/matches", response_model=MatchesOut)
def get_project_matches(
    project_id: int,
    top_k: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get matching users for a project"""
    # load project
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Only owner can request matches (change policy if you want)
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    project_emb = project.embedding
    if not project_emb:
        raise HTTPException(status_code=400, detail="Project has no embedding")

    # gather candidates: load users with embeddings and at least one resume
    users = db.query(User).filter(User.embedding != None).all()
    candidates = []
    for u in users:
        # optional: attach parsed_json from their latest resume
        latest_resume = db.query(Resume).filter(Resume.user_id == u.id).order_by(Resume.created_at.desc()).first()
        candidates.append({
            "user_id": u.id,
            "embedding": u.embedding,
            "parsed_json": latest_resume.parsed_json if latest_resume else None,
            "user": {"id": u.id, "email": u.email, "name": u.name}
        })

    ranked = matcher.rank_candidates(project_emb, candidates, top_k=top_k)
    items = []
    for r in ranked:
        items.append(MatchItem(user_id=r["user_id"], score=float(r["score"]), reason=r.get("reason"), user=r.get("user")))
    return MatchesOut(project_id=project_id, matches=items)