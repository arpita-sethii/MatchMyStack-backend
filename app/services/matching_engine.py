import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def normalize_skill(skill: str) -> str:
    """Normalize skill for case-insensitive, punctuation-insensitive comparison"""
    return skill.lower().strip().replace('.', '').replace(' ', '').replace('-', '').replace('_', '')


@dataclass
class Match:
    """Represents a match between user and project"""
    target_id: str
    score: float
    reasons: List[str]
    shared_skills: List[str]
    complementary_skills: List[str]

    def to_dict(self):
        return {
            "target_id": self.target_id,
            "score": self.score,
            "reasons": self.reasons,
            "shared_skills": self.shared_skills,
            "complementary_skills": self.complementary_skills,
            "user": {"id": self.target_id},  # compatibility for existing frontend
        }


class MatchingEngine:
    def __init__(self, embedding_engine):
        self.embedding_engine = embedding_engine

        # Tunable weights (raise skill_overlap to favor exact matches)
        self.WEIGHTS = {
            "skill_overlap": 0.45,          # dominant: direct skill matches
            "embedding_similarity": 0.25,   # semantic similarity still matters
            "role_match": 0.15,             # secondary
            "experience_fit": 0.06,
            "hackathon_bonus": 0.05,
            "availability": 0.04,
        }

    # ---------------------------- UTILS ----------------------------
    def calculate_embedding_score(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Cosine similarity between embeddings"""
        if emb1 is None or emb2 is None:
            return 0.0
        try:
            return float(self.embedding_engine.cosine_similarity(emb1, emb2))
        except Exception:
            return 0.0

    def calculate_role_match(self, user_roles: List[str], required_roles: List[str]) -> Tuple[float, List[str]]:
        """Role overlap ratio"""
        if not required_roles:
            return 1.0, []
        user_set = set(r.lower() for r in (user_roles or []))
        req_set = set(r.lower() for r in required_roles)
        matched = list(user_set & req_set)
        ratio = len(matched) / len(req_set) if req_set else 0.0
        return ratio, matched

    def normalize_skill(skill: str) -> str:
        """Normalize for better matching"""
        return skill.lower().replace('.', '').replace(' ', '').replace('-', '').replace('_', '')

    def calculate_skill_overlap(self, user_skills: List[str],
                            required_skills: List[str]) -> Tuple[float, List[str], List[str]]:
        """Calculate skill overlap with normalization"""
        if not required_skills:
            return 0.5, [], []
        
        # Normalize for matching
        user_normalized = {normalize_skill(s): s for s in user_skills}
        req_normalized = {normalize_skill(s): s for s in required_skills}
        
        shared_keys = set(user_normalized.keys()) & set(req_normalized.keys())
        comp_keys = set(user_normalized.keys()) - set(req_normalized.keys())
        
        shared = [req_normalized[k] for k in shared_keys]
        complementary = [user_normalized[k] for k in comp_keys]
        
        overlap_ratio = len(shared_keys) / len(req_normalized)
        complementary_bonus = min(len(comp_keys) * 0.05, 0.2)
        
        score = min(overlap_ratio + complementary_bonus, 1.0)
        return score, shared, complementary

    def calculate_experience_fit(self, user_exp: int, required_exp_min: int = 0, required_exp_max: int = 10) -> float:
        """Score experience level fit"""
        if user_exp < required_exp_min:
            gap = required_exp_min - user_exp
            return max(0.5, 1.0 - (gap * 0.15))
        elif user_exp > required_exp_max:
            gap = user_exp - required_exp_max
            return max(0.7, 1.0 - (gap * 0.05))
        return 1.0

    def calculate_availability_score(self, user_tz: str, project_tz: str) -> float:
        """Simple timezone compatibility"""
        if not user_tz or not project_tz:
            return 1.0
        return 1.0 if user_tz == project_tz else 0.8

    # ---------------------------- CORE MATCH ----------------------------
    def match_user_to_project(self, user_data: Dict, project_data: Dict) -> Match:
        """Calculate final weighted score"""
        # 1. Skill overlap
        skill_score, shared_skills, complementary = self.calculate_skill_overlap(
            user_data.get("skills", []),
            project_data.get("required_skills", []),
        )

        # 2. Embedding similarity
        emb_score = self.calculate_embedding_score(
            user_data.get("embedding"), project_data.get("embedding")
        ) if (user_data.get("embedding") and project_data.get("embedding")) else 0.5

        # 3. Role match
        role_score, matched_roles = self.calculate_role_match(
            user_data.get("roles", []),
            project_data.get("required_roles", []),
        )

        # 4. Experience
        exp_score = self.calculate_experience_fit(
            user_data.get("experience_years", 0),
            project_data.get("min_experience", 0),
            project_data.get("max_experience", 10),
        )

        # 5. Availability
        avail_score = self.calculate_availability_score(
            user_data.get("timezone", ""), project_data.get("timezone", "")
        )

        # Weighted final score
        final_score = (
            skill_score * self.WEIGHTS["skill_overlap"]
            + emb_score * self.WEIGHTS["embedding_similarity"]
            + role_score * self.WEIGHTS["role_match"]
            + exp_score * self.WEIGHTS["experience_fit"]
            + avail_score * self.WEIGHTS["availability"]
        )

        # additive boost: more shared skills = higher rank in ties
        try:
            final_score += min(len(shared_skills) * 0.02, 0.12)
            final_score = max(0.0, min(1.0, final_score))
        except Exception:
            pass

        # Human-friendly reasons
        reasons = []
        shared_count = len(shared_skills)
        required_count = len(project_data.get("required_skills", []))
        if shared_count > 0:
            reasons.append(f"{shared_count}/{required_count} required skills matched")
        if shared_count >= max(1, required_count * 0.8):
            reasons.append("Strong skill match!")
        if matched_roles:
            reasons.append(f"Role fit: {', '.join(matched_roles)}")
        if complementary and len(complementary) >= 3:
            reasons.append(f"+{len(complementary)} bonus skills")
        if emb_score > 0.7:
            reasons.append(f"Profile similarity: {emb_score:.0%}")

        return Match(
            target_id=str(project_data.get("id", "unknown")),
            score=final_score,
            reasons=reasons,
            shared_skills=shared_skills,
            complementary_skills=complementary,
        )

    # ---------------------------- RANKING ----------------------------
    def rank_candidates(self, candidates: List[Dict], project_data: Dict, top_k: int = 20) -> List[Match]:
        """Rank multiple candidates for a project"""
        matches = []
        for candidate in candidates:
            try:
                m = self.match_user_to_project(candidate, project_data)
                matches.append(m)
            except Exception as e:
                logger.error(f"Error matching candidate {candidate.get('id', 'unknown')}: {e}")
        # Sort by score, then shared skills (tie-breaker)
        matches.sort(key=lambda mm: (mm.score, len(mm.shared_skills) if mm.shared_skills else 0), reverse=True)
        return matches[:top_k]


# ---------------------------- WRAPPER ----------------------------
class MatchingEngineWrapper:
    """Wrapper to handle embedding generation and matching"""

    def __init__(self):
        try:
            from app.services.embedding_engine import EmbeddingEngine
            self.embedding_engine = EmbeddingEngine()
        except Exception as e:
            logger.warning(f"Failed to load EmbeddingEngine: {e}")
            self.embedding_engine = None
        self.matcher = MatchingEngine(self.embedding_engine) if self.embedding_engine else None

    def ensure_embedding(self, data_dict: Dict, kind: str = "profile") -> List[float]:
        """Generate or reuse embedding for profile/project"""
        if not self.embedding_engine:
            return [0.1] * 384
        try:
            if kind == "profile":
                emb = self.embedding_engine.embed_profile(data_dict)
            else:
                emb = self.embedding_engine.embed_project(data_dict)
            if hasattr(emb, "tolist"):
                return emb.tolist()
            return list(emb)
        except Exception as e:
            logger.error(f"Error generating embedding for {kind}: {e}", exc_info=True)
            return [0.1] * 384


# ---------------------------- DEBUG HELPER ----------------------------
def debug_score_user_against_candidates(wrapper: MatchingEngineWrapper, user_profile: dict, candidates: list, top_k: int = 10):
    """Print per-component scores for quick debugging"""
    results = []
    for c in candidates:
        m = wrapper.matcher.match_user_to_project(user_profile, c)
        results.append({
            "candidate_id": c.get("id"),
            "score": m.score,
            "shared": m.shared_skills,
            "reasons": m.reasons,
        })
    results.sort(key=lambda r: (r["score"], len(r["shared"])), reverse=True)
    for r in results[:top_k]:
        print(f"ID: {r['candidate_id']} | Score: {r['score']:.3f} | Shared: {r['shared']} | Reasons: {r['reasons']}")
    return results
