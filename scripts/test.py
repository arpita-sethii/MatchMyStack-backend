# tools/test_match_flow.py
"""
Test script to simulate uploading a resume and getting matches
Run from backend folder: .venv\Scripts\python.exe tools\test_match_flow.py
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.services.resume_parser import ImprovedResumeParser
from app.services.matching_engine import MatchingEngineWrapper
from app.db.session import SessionLocal
from app.models.models import Project
import json


def test_match_flow():
    print("="*60)
    print("TESTING MATCH FLOW")
    print("="*60)
    
    # Sample resume text (you can also test with actual PDF bytes)
    sample_resume = """
    Jane Smith
    jane.smith@example.com | github.com/janesmith | +1-555-123-4567
    
    Senior Full-Stack Developer with ML Experience
    
    TECHNICAL SKILLS:
    - Frontend: React, TypeScript, Tailwind CSS, JavaScript
    - Backend: Python, FastAPI, Node.js, PostgreSQL
    - Machine Learning: PyTorch, TensorFlow, scikit-learn, NLP
    - DevOps: Docker, Kubernetes, AWS, CI/CD
    
    EXPERIENCE:
    Software Engineer at TechCorp (2019 - Present)
    - Built ML-powered recommendation system using Python and PyTorch
    - Developed full-stack web applications with React and FastAPI
    - 5 years of professional experience
    
    ACHIEVEMENTS:
    - 1st place winner at HackMIT 2023
    - 2nd place at MLH hackathon 2022
    - Contributed to open-source ML projects
    """
    
    # Step 1: Parse the resume
    print("\n1️⃣  Parsing resume...")
    parser = ImprovedResumeParser()
    parsed = parser.parse_resume(text=sample_resume)
    
    if "error" in parsed:
        print(f"❌ Parsing failed: {parsed['error']}")
        return
    
    skills = parsed.get("all_skills", [])
    roles = parsed.get("roles", [])
    exp = parsed.get("experience_years", 0)
    
    print(f"✓ Parsed successfully:")
    print(f"  - Name: {parsed.get('name', 'N/A')}")
    print(f"  - Skills ({len(skills)}): {skills}")
    print(f"  - Roles: {roles}")
    print(f"  - Experience: {exp} years")
    print(f"  - Parsing library: {parsed.get('parsing_library', 'N/A')}")
    
    # Step 2: Build resume as project for matching
    print("\n2️⃣  Building user profile...")
    resume_as_project = {
        "id": "resume",
        "title": parsed.get("name", "Test Resume"),
        "description": f"Resume with {len(skills)} skills",
        "required_skills": [s.lower() for s in skills],
        "required_roles": [r.lower() for r in roles] or ["developer"],
        "min_experience": exp,
        "max_experience": exp + 5,
    }
    
    # Step 3: Get embedding
    print("\n3️⃣  Generating embedding...")
    matcher = MatchingEngineWrapper()
    resume_emb = matcher.ensure_embedding(resume_as_project, kind="project")
    
    if not resume_emb or not isinstance(resume_emb, list):
        print(f"⚠ Warning: Embedding generation returned {type(resume_emb)}")
        resume_emb = [0.1] * 384
    
    resume_as_project["embedding"] = resume_emb
    print(f"✓ Generated embedding (length: {len(resume_emb)})")
    
    # Step 4: Load projects from database
    print("\n4️⃣  Loading projects from database...")
    db = SessionLocal()
    try:
        projects = db.query(Project).all()
        print(f"✓ Found {len(projects)} projects")
        
        if not projects:
            print("❌ No projects in database! Run seed script first:")
            print("   .venv\\Scripts\\python.exe scripts/seed_db.py")
            return
        
        # Step 5: Prepare candidates
        print("\n5️⃣  Preparing candidates...")
        candidates = []
        
        for p in projects:
            # Normalize skills from DB
            try:
                req_skills = p.required_skills
                if isinstance(req_skills, str):
                    req_skills = json.loads(req_skills) if req_skills else []
                req_skills = [str(s).strip().lower() for s in (req_skills or [])]
            except Exception:
                req_skills = []
            
            # Normalize roles
            try:
                req_roles = p.required_roles
                if isinstance(req_roles, str):
                    req_roles = json.loads(req_roles) if req_roles else []
                req_roles = [str(r).strip().lower() for r in (req_roles or [])]
            except Exception:
                req_roles = []
            
            # Get or generate embedding
            project_emb = getattr(p, "embedding", None)
            if not project_emb or not isinstance(project_emb, list):
                proj_dict = {
                    "id": p.id,
                    "title": p.title,
                    "description": p.description,
                    "required_skills": req_skills,
                    "required_roles": req_roles,
                }
                project_emb = matcher.ensure_embedding(proj_dict, kind="project")
                if not isinstance(project_emb, list):
                    project_emb = [0.1] * 384
            
            candidate = {
                "id": p.id,
                "user_id": p.id,
                "name": p.title,
                "email": None,
                "roles": req_roles,
                "skills": req_skills,
                "experience_years": 0,
                "embedding": project_emb,
                "min_experience": getattr(p, "min_experience", 0) or 0,
                "max_experience": getattr(p, "max_experience", 10) or 10,
            }
            candidates.append(candidate)
        
        print(f"✓ Prepared {len(candidates)} candidates")
        
        # Step 6: Rank candidates
        print("\n6️⃣  Ranking matches...")
        ranked_matches = matcher.matcher.rank_candidates(
            candidates=candidates,
            project_data=resume_as_project,
            top_k=5
        )
        
        print(f"✓ Generated {len(ranked_matches)} matches")
        
        # Step 7: Display results
        print("\n" + "="*60)
        print("TOP 5 MATCHES:")
        print("="*60)
        
        for i, match in enumerate(ranked_matches[:5], 1):
            project = next((p for p in projects if p.id == int(match.target_id)), None)
            
            print(f"\n{i}. {project.title if project else f'Project {match.target_id}'}")
            print(f"   Score: {match.score:.4f}")
            print(f"   Shared skills ({len(match.shared_skills)}): {match.shared_skills}")
            if match.complementary_skills:
                print(f"   Bonus skills ({len(match.complementary_skills)}): {match.complementary_skills[:5]}")
            print(f"   Reasons: {', '.join(match.reasons)}")
            
            if project:
                try:
                    proj_skills = project.required_skills
                    if isinstance(proj_skills, str):
                        proj_skills = json.loads(proj_skills)
                    print(f"   Project needs: {proj_skills[:5]}{'...' if len(proj_skills) > 5 else ''}")
                except Exception:
                    pass
        
        print("\n" + "="*60)
        print("✅ TEST COMPLETE!")
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error during matching: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    test_match_flow()