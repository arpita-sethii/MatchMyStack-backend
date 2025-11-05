import json
import sys
import os
from datetime import datetime

# ensure project package importable when running from backend folder
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

try:
    from app.db.session import SessionLocal, engine, Base
    from app.models.models import User, Project
    from app.core.security import hash_password
except Exception as e:
    print("Failed to import project modules. Check PYTHONPATH and relative imports.", e)
    sys.exit(1)

# optional embedding/matching wrapper (will fall back to mock if missing)
try:
    from app.services.matching_engine import MatchingEngineWrapper
    matcher_wrapper = MatchingEngineWrapper()
except Exception as e:
    print("Warning: MatchingEngineWrapper import failed. Embeddings will be skipped or mocked.", e)
    matcher_wrapper = None

# create tables if not present (safe - doesn't drop)
Base.metadata.create_all(bind=engine)

# --- Sample seed data ---
SAMPLE_USERS = [
    {
        "email": "alice@example.com",
        "name": "Alice Johnson",
        "password": "password123",
        "roles": ["fullstack", "ml_engineer"],
        "skills": ["python", "fastapi", "react", "pytorch"],
        "experience_years": 3,
        "bio": "Passionate full-stack dev building ML apps",
        "timezone": "UTC+5:30",
        "hackathons": {"has_hackathon_experience": True, "hackathon_score": 30}
    },
    {
        "email": "bob@example.com",
        "name": "Bob Kumar",
        "password": "password123",
        "roles": ["backend"],
        "skills": ["python", "django", "postgresql", "docker"],
        "experience_years": 5,
        "bio": "Backend engineer",
        "timezone": "UTC+5:30"
    },
    {
        "email": "carol@example.com",
        "name": "Carol Singh",
        "password": "password123",
        "roles": ["frontend"],
        "skills": ["react", "typescript", "tailwind"],
        "experience_years": 2,
        "bio": "Frontend dev and UI lover",
        "timezone": "UTC+1:00"
    },
]

SAMPLE_PROJECTS = [
    {
        "title": "AI-Powered Chatbot Platform",
        "description": "Build an intelligent chatbot using LLMs and vector databases for context-aware conversations with RAG pipeline",
        "required_skills": ["Python", "LangChain", "OpenAI", "Pinecone", "FastAPI", "Redis"],
        "required_roles": ["ml_engineer", "backend"],
        "min_experience": 2,
        "max_experience": 5,
        "timezone": "UTC+5:30"
    },
    {
        "title": "E-commerce Platform",
        "description": "Full-stack e-commerce site with payment integration, inventory management, and admin dashboard",
        "required_skills": ["React", "Node.js", "PostgreSQL", "Stripe", "Tailwind", "Redis"],
        "required_roles": ["fullstack", "backend", "frontend"],
        "min_experience": 2,
        "max_experience": 6,
        "timezone": "UTC+5:30"
    },
    # ... other projects (unchanged) ...
]

# helpers
def set_attr_safe(obj, key, value):
    """Set attribute only if the model has it. If list/dict and DB expects string, fallback to JSON."""
    if hasattr(obj, key):
        try:
            setattr(obj, key, value)
            return True
        except Exception:
            try:
                setattr(obj, key, json.dumps(value))
                return True
            except Exception:
                return False
    return False

def normalize_list(items):
    if not items:
        return []
    return [str(i).strip() for i in items]

def normalize_skills(skills):
    if not skills:
        return []
    return [str(s).strip().lower() for s in skills]

def normalize_roles(roles):
    if not roles:
        return []
    return [str(r).strip().lower() for r in roles]

def find_or_create_user(db, email: str, name: str = "Seed User", password: str = "password123"):
    """
    Find existing user by email or create a new one.
    Returns the user ORM object (uncommitted/committed as appropriate).
    """
    user = db.query(User).filter(getattr(User, "email") == email).first()
    if user:
        print(f"User already exists: {email} (id={getattr(user, 'id', None)})")
        return user

    user = User()
    set_attr_safe(user, "email", email)
    set_attr_safe(user, "name", name)
    hashed = hash_password(password)
    # try common hashed password column names
    if not set_attr_safe(user, "hashed_password", hashed):
        set_attr_safe(user, "password", hashed)
    # optional extra fields
    set_attr_safe(user, "created_at", datetime.utcnow())

    db.add(user)
    # flush to get id without committing (so we can assign owner_id to projects)
    db.flush()
    print(f"Created user (flushed): {email} (id={getattr(user, 'id', None)})")
    return user

def create_seed_data():
    db = SessionLocal()
    created_users = []
    created_projects = []
    try:
        # --- Users: create or reuse ---
        for u in SAMPLE_USERS:
            try:
                user = db.query(User).filter(getattr(User, "email") == u["email"]).first()
            except Exception:
                user = None

            if user:
                created_users.append(user)
                continue

            # create new user with minimal required fields
            new_user = User()
            set_attr_safe(new_user, "email", u["email"])
            set_attr_safe(new_user, "name", u["name"])
            hashed = hash_password(u["password"])
            if not set_attr_safe(new_user, "hashed_password", hashed):
                set_attr_safe(new_user, "password", hashed)

            # optional fields (many of these may not be present on your User model; set_attr_safe handles that)
            set_attr_safe(new_user, "bio", u.get("bio"))
            set_attr_safe(new_user, "skills", normalize_skills(u.get("skills")))
            set_attr_safe(new_user, "created_at", datetime.utcnow())
            # timezone/hackathons are optional
            try:
                if u.get("timezone"):
                    set_attr_safe(new_user, "timezone", u.get("timezone"))
            except Exception:
                pass

            db.add(new_user)
            db.flush()   # assign ID now
            db.commit()  # commit user so relationships can reference it
            db.refresh(new_user)
            print(f"Created user: {u['email']} (id={getattr(new_user, 'id', None)})")
            created_users.append(new_user)

            # try embedding if wrapper available & user model has column
            try:
                if matcher_wrapper is not None:
                    profile_dict = {
                        "id": getattr(new_user, "id"),
                        "email": getattr(new_user, "email", None),
                        "name": getattr(new_user, "name", None),
                        "roles": normalize_roles(u.get("roles")),
                        "skills": normalize_skills(u.get("skills")),
                        "experience_years": u.get("experience_years"),
                        "bio": u.get("bio"),
                    }
                    emb = matcher_wrapper.ensure_embedding(profile_dict, kind="profile")
                    if emb is not None and set_attr_safe(new_user, "embedding", emb):
                        db.add(new_user)
                        db.commit()
                        db.refresh(new_user)
                        print(f" -> Added embedding for user id {new_user.id}")
            except Exception as e:
                print(" -> embedding step failed for user:", getattr(new_user, "email", None), e)

        # --- Projects: ensure at least one valid owner_id is present ---
        owner = None
        try:
            owner = db.query(User).filter(getattr(User, "email") == "alice@example.com").first()
        except Exception:
            pass
        if not owner and created_users:
            owner = created_users[0]
        if not owner:
            raise RuntimeError("No user available to assign as project owner. Seed users first.")

        for p in SAMPLE_PROJECTS:
            # skip if project with same title exists
            existing = db.query(Project).filter(getattr(Project, "title") == p["title"]).first()
            if existing:
                print(f"Project already exists: {p['title']} (id={getattr(existing, 'id', None)})")
                created_projects.append(existing)
                continue

            proj = Project()
            set_attr_safe(proj, "title", p.get("title"))
            set_attr_safe(proj, "description", p.get("description"))

            # Normalize skills & roles before storing
            normalized_sk = normalize_skills(p.get("required_skills"))
            normalized_roles = normalize_roles(p.get("required_roles"))

            set_attr_safe(proj, "required_skills", normalized_sk)
            set_attr_safe(proj, "required_roles", normalized_roles)
            set_attr_safe(proj, "min_experience", p.get("min_experience"))
            set_attr_safe(proj, "max_experience", p.get("max_experience"))
            set_attr_safe(proj, "timezone", p.get("timezone"))
            set_attr_safe(proj, "created_at", datetime.utcnow())

            # IMPORTANT: ensure owner_id is set (avoids NOT NULL constraint)
            if not set_attr_safe(proj, "owner_id", getattr(owner, "id", None)):
                try:
                    if hasattr(proj, "owner"):
                        setattr(proj, "owner", owner)
                except Exception:
                    pass

            db.add(proj)
            db.flush()
            db.commit()
            db.refresh(proj)
            print(f"Created project: {p.get('title')} (id={getattr(proj, 'id', None)}, owner_id={getattr(proj, 'owner_id', None)})")
            created_projects.append(proj)

            # try embedding for project (use normalized skills & roles)
            try:
                if matcher_wrapper is not None:
                    project_dict = {
                        "id": getattr(proj, "id"),
                        "title": getattr(proj, "title"),
                        "description": getattr(proj, "description"),
                        "required_skills": normalized_sk,
                        "required_roles": normalized_roles,
                        "min_experience": getattr(proj, "min_experience", 0) or 0,
                        "max_experience": getattr(proj, "max_experience", 10) or 10,
                    }
                    emb = matcher_wrapper.ensure_embedding(project_dict, kind="project")
                    if emb is not None and set_attr_safe(proj, "embedding", emb):
                        db.add(proj)
                        db.commit()
                        db.refresh(proj)
                        print(f" -> Added embedding for project id {proj.id}")
            except Exception as e:
                print(" -> embedding step failed for project:", getattr(proj, "title", None), e)

    except Exception as e:
        db.rollback()
        print("Error during seeding:", e)
        raise

    # summary print (BEFORE closing db session)
    print("\n" + "="*60)
    print("SEED COMPLETE!")
    print("="*60)
    print(f"\nCreated/Found {len(created_users)} users and {len(created_projects)} projects:\n")
    for u in created_users:
        print(f" 👤 USER: {getattr(u, 'name', 'N/A')} ({getattr(u, 'email', 'N/A')})")
    print()
    for p in created_projects:
        skills_count = len(p.required_skills) if isinstance(p.required_skills, list) else (len(json.loads(p.required_skills)) if isinstance(p.required_skills, str) else 0)
        print(f" 🚀 PROJECT: {getattr(p, 'title', 'N/A')} ({skills_count} skills)")
    print("\n" + "="*60)

    db.close()


if __name__ == "__main__":
    create_seed_data()
