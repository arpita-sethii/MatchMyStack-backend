import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Match:
    """Represents a match between user and project/user"""
    target_id: str
    score: float
    reasons: List[str]
    shared_skills: List[str]
    complementary_skills: List[str]

class MatchingEngine:
    def __init__(self, embedding_engine):
        self.embedding_engine = embedding_engine
        
        # Tunable weights for scoring
        self.WEIGHTS = {
            'embedding_similarity': 0.35,  # How similar profiles/projects are
            'role_match': 0.25,            # Do roles align with needs?
            'skill_overlap': 0.20,         # Shared skills
            'experience_fit': 0.08,        # Experience level match
            'hackathon_bonus': 0.07,       # Hackathon experience bonus
            'availability': 0.05           # Timezone/availability
        }
    
    def calculate_embedding_score(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Cosine similarity between embeddings"""
        return self.embedding_engine.cosine_similarity(emb1, emb2)
    
    def calculate_role_match(self, user_roles: List[str], 
                            required_roles: List[str]) -> Tuple[float, List[str]]:
        """
        Check if user's roles match project needs
        Returns: (score, matched_roles)
        """
        if not required_roles:
            return 1.0, []
        
        user_roles_set = set(user_roles)
        required_roles_set = set(required_roles)
        
        matched_roles = list(user_roles_set & required_roles_set)
        match_ratio = len(matched_roles) / len(required_roles_set)
        
        return match_ratio, matched_roles
    
    def calculate_skill_overlap(self, user_skills: List[str],
                               required_skills: List[str]) -> Tuple[float, List[str], List[str]]:
        """
        Calculate skill overlap and complementarity
        Returns: (score, shared_skills, complementary_skills)
        """
        if not required_skills:
            return 0.5, [], []
        
        user_skills_set = set([s.lower() for s in user_skills])
        required_skills_set = set([s.lower() for s in required_skills])
        
        shared = list(user_skills_set & required_skills_set)
        complementary = list(user_skills_set - required_skills_set)
        
        # Score based on how many required skills are covered
        overlap_ratio = len(shared) / len(required_skills_set)
        
        # Bonus for having complementary skills
        complementary_bonus = min(len(complementary) * 0.05, 0.2)
        
        score = min(overlap_ratio + complementary_bonus, 1.0)
        return score, shared, complementary
    
    def calculate_experience_fit(self, user_exp: int, 
                                 required_exp_min: int = 0,
                                 required_exp_max: int = 10) -> float:
        """
        Score experience level fit
        Penalize being way over/under qualified
        """
        if user_exp < required_exp_min:
            # Under-qualified, but not terrible if close
            gap = required_exp_min - user_exp
            return max(0.5, 1.0 - (gap * 0.15))
        elif user_exp > required_exp_max:
            # Over-qualified, slight penalty
            gap = user_exp - required_exp_max
            return max(0.7, 1.0 - (gap * 0.05))
        else:
            # Perfect fit
            return 1.0
    
    def calculate_availability_score(self, user_timezone: str,
                                    project_timezone: str) -> float:
        """
        Simple timezone compatibility
        In production, use proper timezone overlap calculation
        """
        if not user_timezone or not project_timezone:
            return 1.0
        
        # Simplified: same region is better
        if user_timezone == project_timezone:
            return 1.0
        elif abs(hash(user_timezone) - hash(project_timezone)) % 12 < 4:
            return 0.8  # Similar timezones
        else:
            return 0.6  # Very different
    
    def match_user_to_project(self, user_data: Dict, project_data: Dict) -> Match:
        """
        Main matching function: calculate comprehensive match score
        """
        # 1. Embedding similarity
        user_emb = user_data.get('embedding')
        project_emb = project_data.get('embedding')
        
        if user_emb is None or project_emb is None:
            raise ValueError("Missing embeddings")
        
        emb_score = self.calculate_embedding_score(user_emb, project_emb)
        
        # 2. Role match
        role_score, matched_roles = self.calculate_role_match(
            user_data.get('roles', []),
            project_data.get('required_roles', [])
        )
        
        # 3. Skill overlap
        skill_score, shared_skills, complementary = self.calculate_skill_overlap(
            user_data.get('skills', []),
            project_data.get('required_skills', [])
        )
        
        # 4. Experience fit
        exp_score = self.calculate_experience_fit(
            user_data.get('experience_years', 0),
            project_data.get('min_experience', 0),
            project_data.get('max_experience', 10)
        )
        
        # 5. Availability
        avail_score = self.calculate_availability_score(
            user_data.get('timezone', ''),
            project_data.get('timezone', '')
        )
        
        # Weighted final score
        final_score = (
            emb_score * self.WEIGHTS['embedding_similarity'] +
            role_score * self.WEIGHTS['role_match'] +
            skill_score * self.WEIGHTS['skill_overlap'] +
            exp_score * self.WEIGHTS['experience_fit'] +
            avail_score * self.WEIGHTS['availability']
        )
        
        # Generate human-readable reasons
        reasons = []
        if emb_score > 0.7:
            reasons.append(f"Strong profile match ({emb_score:.0%})")
        if matched_roles:
            reasons.append(f"Role fit: {', '.join(matched_roles)}")
        if len(shared_skills) >= 3:
            reasons.append(f"{len(shared_skills)} shared skills")
        if exp_score > 0.8:
            reasons.append("Experience level matches")
        
        return Match(
            target_id=project_data.get('id', 'unknown'),
            score=final_score,
            reasons=reasons,
            shared_skills=shared_skills,
            complementary_skills=complementary
        )
    
    def rank_candidates(self, candidates: List[Dict],
                       project_data: Dict,
                       top_k: int = 20) -> List[Match]:
        """
        Rank multiple candidates for a project
        Returns top-k matches
        """
        matches = []
        for candidate in candidates:
            try:
                match = self.match_user_to_project(candidate, project_data)
                matches.append(match)
            except Exception as e:
                print(f"Error matching candidate: {e}")
                continue
        
        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches[:top_k]


# Usage example
if __name__ == "__main__":
    from backend.embedding_engine import EmbeddingEngine
    
    engine = EmbeddingEngine()
    matcher = MatchingEngine(engine)
    
    # Mock user
    user = {
        "id": "user123",
        "roles": ["fullstack", "ml_engineer"],
        "skills": ["python", "react", "fastapi", "pytorch"],
        "experience_years": 3,
        "timezone": "UTC+5:30",
        "bio": "Love building AI apps"
    }
    user['embedding'] = engine.embed_profile(user)
    
    # Mock project
    project = {
        "id": "proj456",
        "required_roles": ["ml_engineer", "frontend"],
        "required_skills": ["python", "machine learning", "react"],
        "min_experience": 2,
        "max_experience": 5,
        "timezone": "UTC+5:30",
        "description": "Building an ML-powered matching platform"
    }
    project['embedding'] = engine.embed_project(project)
    
    # Match!
    match = matcher.match_user_to_project(user, project)
    
    print(f"Match Score: {match.score:.2%}")
    print(f"Reasons: {', '.join(match.reasons)}")
    print(f"Shared Skills: {', '.join(match.shared_skills)}")
    print(f"Additional Skills: {', '.join(match.complementary_skills[:3])}")