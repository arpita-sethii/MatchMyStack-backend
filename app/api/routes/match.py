# backend/app/api/routes/match.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.models import Project
from app.services.matching_engine import MatchingEngineWrapper
from app.services.resume_parser import ImprovedResumeParser, MAX_PDF_BYTES
import json
import logging
from typing import List, Any

router = APIRouter(prefix="/match", tags=["matching"])
logger = logging.getLogger(__name__)

# ✅ FIX: Don't initialize at module level - use lazy loading
_matcher = None
_parser = None

def get_matcher():
    """Lazy load matcher on first use"""
    global _matcher
    if _matcher is None:
        logger.info("🔄 Initializing MatchingEngineWrapper (first use)...")
        _matcher = MatchingEngineWrapper()
        logger.info("✅ MatchingEngineWrapper ready")
    return _matcher

def get_parser():
    """Lazy load parser on first use"""
    global _parser
    if _parser is None:
        logger.info("🔄 Initializing ImprovedResumeParser...")
        _parser = ImprovedResumeParser()
        logger.info("✅ ImprovedResumeParser ready")
    return _parser


@router.get("/ping")
async def ping(request: Request):
    """Health check endpoint for CORS verification"""
    return {
        "ok": True,
        "origin": request.headers.get("origin"),
        "service": "match"
    }


@router.post("/upload_and_match")
async def upload_and_match_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    top_k: int = 10
):
    """Upload resume, parse it, and return matching projects in one call."""

    # ✅ Get instances lazily (loads on first request only)
    parser = get_parser()
    matcher = get_matcher()

    # 1️⃣ Read and validate file
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if MAX_PDF_BYTES and len(content) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large (limit {MAX_PDF_BYTES} bytes)")

    # 2️⃣ Parse the resume
    parsed = parser.parse_resume(pdf_bytes=content)
    if "error" in parsed:
        # Log parsing failure details
        parsing_lib = parsed.get("parsing_library", "unknown")
        parsing_note = parsed.get("parsing_note", "")
        logger.warning(f"⚠ Resume parsing failed: {parsed['error']} (lib={parsing_lib}, note={parsing_note})")
        raise HTTPException(status_code=422, detail=parsed["error"])

    # Extract parsed data
    all_skills = parsed.get("all_skills", []) or []
    raw_text_len = parsed.get("total_text_length", 0)
    parsing_lib = parsed.get("parsing_library", "unknown")
    
    # ONE-LINE SUMMARY LOG
    logger.info(f"✓ Parsed {raw_text_len} chars with {parsing_lib} -> {len(all_skills)} skills found")

    # 3️⃣ Build the user profile from resume
    user_profile = {
        "id": "user_resume",
        "user_id": "user_resume", 
        "name": parsed.get("name", "") or "Resume User",
        "email": parsed.get("contact", {}).get("email"),
        "roles": [str(r).strip().lower() for r in (parsed.get("roles", []) or ["developer"])],
        "skills": [str(s).strip().lower() for s in all_skills],
        "experience_years": parsed.get("experience_years", 0) or 0,
        "bio": f"Resume with {len(all_skills)} skills",
        "timezone": parsed.get("timezone", None)
    }

    # 3.5️⃣ Get embedding for the resume
    user_emb = matcher.ensure_embedding(user_profile, kind="profile")
    if not user_emb or not isinstance(user_emb, list):
        logger.warning("Failed to generate embedding for resume; using default")
        user_profile["embedding"] = [0.1] * 384
    else:
        user_profile["embedding"] = user_emb
        logger.info(f"✓ Computed resume_emb_len={len(user_emb)}")

    # 4️⃣ Fetch all projects from DB
    projects: List[Project] = db.query(Project).all()
    if not projects:
        raise HTTPException(status_code=404, detail="No projects found in database")
    
    logger.info(f"✓ Found {len(projects)} projects in DB")

    # 5️⃣ Prepare projects as "candidates" (projects looking for teammates)
    candidates: List[dict] = []
    project_map: dict = {}
    projects_to_persist: List[Project] = []
    missing_embeddings_count = 0

    for p in projects:
        # Normalize required_skills from DB (it might be stored as JSON string)
        try:
            req_skills: Any = p.required_skills
            if isinstance(req_skills, str):
                req_skills = json.loads(req_skills) if req_skills else []
            if req_skills is None:
                req_skills = []
            # ensure list of lowercased strings
            req_skills = [str(s).strip().lower() for s in req_skills if s is not None]
        except Exception:
            req_skills = []

        # Normalize required_roles too (DB column may be JSON/list or string)
        try:
            req_roles = p.required_roles
            if isinstance(req_roles, str):
                req_roles = json.loads(req_roles) if req_roles else []
            if req_roles is None:
                req_roles = []
            req_roles = [str(r).strip().lower() for r in req_roles if r is not None]
        except Exception:
            req_roles = []

        # Ensure project has embedding; if not, compute and persist later
        project_embedding = getattr(p, "embedding", None)
        
        if not project_embedding:
            missing_embeddings_count += 1
            proj_dict = {
                "id": getattr(p, "id", None),
                "title": p.title or "",
                "description": p.description or "",
                "required_skills": req_skills,
                "required_roles": req_roles,
                "min_experience": getattr(p, "min_experience", 0) or 0,
                "max_experience": getattr(p, "max_experience", 10) or 10,
                "timezone": getattr(p, "timezone", None)
            }
            emb = matcher.ensure_embedding(proj_dict, kind="project")
            if emb and isinstance(emb, list):
                try:
                    p.embedding = emb
                    project_embedding = emb
                    if not getattr(p, "required_roles", None) and req_roles:
                        p.required_roles = req_roles
                    if getattr(p, "min_experience", None) is None:
                        p.min_experience = proj_dict["min_experience"]
                    if getattr(p, "max_experience", None) is None:
                        p.max_experience = proj_dict["max_experience"]
                    if getattr(p, "timezone", None) is None:
                        p.timezone = proj_dict.get("timezone")

                    projects_to_persist.append(p)
                    logger.info(f"✓ Computed embedding for project id={p.id} title={p.title}")
                except Exception as e:
                    logger.exception(f"Failed to assign embedding for project {p.id}: {e}")
                    project_embedding = [0.1] * 384
            else:
                project_embedding = [0.1] * 384
        else:
            # Ensure embedding from DB is a list
            if not isinstance(project_embedding, list):
                try:
                    project_embedding = list(project_embedding)
                except Exception:
                    logger.warning(f"Project {p.id} has invalid embedding, using default")
                    project_embedding = [0.1] * 384

        # Build candidate dict
        candidate = {
            "id": p.id,
            "user_id": p.id,
            "name": p.title or f"Project-{p.id}",
            "email": None,
            "roles": req_roles or [],
            "skills": req_skills,
            "experience_years": 0,
            "embedding": project_embedding,
            "min_experience": getattr(p, "min_experience", 0) or 0,
            "max_experience": getattr(p, "max_experience", 10) or 10,
            "timezone": getattr(p, "timezone", None)
        }

        candidates.append(candidate)
        project_map[p.id] = p

    # persist any new embeddings (single commit)
    if projects_to_persist:
        try:
            for pp in projects_to_persist:
                db.add(pp)
            db.commit()
            for pp in projects_to_persist:
                db.refresh(pp)
            logger.info(f"✓ Persisted {len(projects_to_persist)} project embeddings to DB")
        except Exception as e:
            logger.exception(f"Failed to persist project embeddings: {e}")
            db.rollback()

    # 6️⃣ Match user against projects
    try:
        matches_list = []
        for candidate in candidates:
            match = matcher.matcher.match_user_to_project(
                user_data=user_profile,
                project_data=candidate
            )
            matches_list.append(match)
        
        # Sort by score
        matches_list.sort(key=lambda m: (m.score, len(m.shared_skills) if m.shared_skills else 0), reverse=True)
        ranked_matches = matches_list[:top_k]
        
    except Exception as e:
        logger.exception(f"Matching failed: {e}")
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")

    # ONE-LINE SUMMARY LOG
    logger.info(f"✓ Found {len(projects)} projects ({missing_embeddings_count} missing embeddings); produced {len(ranked_matches)} matches")

    # Debug output
    try:
        logger.info(f"DEBUG — Top {min(5, len(ranked_matches))} matches:")
        for m in ranked_matches[:5]:
            logger.info(f" -> id={getattr(m, 'target_id', None)} score={getattr(m, 'score', 0.0):.4f} shared={getattr(m, 'shared_skills', [])}")
    except Exception as e:
        logger.debug(f"Failed to log debug match list: {e}")

    # 7️⃣ Transform matches to include full project details
    final_matches = []
    for match in ranked_matches:
        # match is a Match object; convert to dict-like
        match_dict = match.to_dict() if hasattr(match, "to_dict") else dict(match)

        # Get project id from match
        project_id = match_dict.get("target_id")
        
        # Convert string id to int if needed
        try:
            if isinstance(project_id, str) and project_id.isdigit():
                project_id = int(project_id)
        except Exception:
            pass

        # Look up the project
        if project_id and project_id in project_map:
            p = project_map[project_id]

            final_match = {
                "project_id": p.id,
                "project_title": p.title,
                "project_description": p.description,
                "required_skills": json.loads(p.required_skills) if isinstance(p.required_skills, str) else (p.required_skills or []),
                "required_roles": json.loads(p.required_roles) if isinstance(getattr(p, "required_roles", None), str) else (getattr(p, "required_roles", None) or []),
                "score": float(match_dict.get("score", 0)),
                "reasons": match_dict.get("reasons", []),
                "shared_skills": match_dict.get("shared_skills", []),
                "complementary_skills": match_dict.get("complementary_skills", []),
                "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else None,
            }

            if getattr(p, "owner", None):
                final_match["owner"] = {
                    "id": getattr(p.owner, "id", None),
                    "name": getattr(p.owner, "name", None),
                    "email": getattr(p.owner, "email", None),
                }

            final_matches.append(final_match)
        else:
            logger.warning(f"Could not find project with id={project_id} in project_map")

    # Final debug/info
    logger.info(f"✓ Returning {len(final_matches)} matches for uploaded resume")

    return {
        "parsed_resume": parsed,
        "matches": final_matches
    }