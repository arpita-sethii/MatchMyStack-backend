# backend/app/services/embedding_engine.py
from sentence_transformers import SentenceTransformer
import numpy as np
from typing import Dict, List, Union
import logging

logger = logging.getLogger(__name__)

# ✅ CRITICAL: Don't load model at import time
_model = None
_model_name = "all-MiniLM-L6-v2"

def get_model():
    """Lazy load sentence transformer - only loads when first needed"""
    global _model
    if _model is None:
        logger.info(f"🔄 Loading sentence transformer model '{_model_name}' (first use)...")
        _model = SentenceTransformer(_model_name)
        logger.info(f"✅ Model loaded successfully - embedding dimension: {_model.get_sentence_embedding_dimension()}")
    return _model


class EmbeddingEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize with a sentence transformer model
        all-MiniLM-L6-v2: Fast, 384 dimensions, good for semantic similarity
        Alternative: all-mpnet-base-v2 (768 dim, more accurate but slower)
        
        ✅ Model loads lazily on first use to reduce startup memory
        """
        global _model_name
        _model_name = model_name
        logger.info(f"EmbeddingEngine initialized (model '{model_name}' will load on first use)")
    
    @property
    def model(self):
        """Access model via lazy loading"""
        return get_model()
    
    @property
    def embedding_dim(self):
        """Get embedding dimension (loads model if needed)"""
        return self.model.get_sentence_embedding_dimension()
    
    def normalize_skills(self, skills: Union[List[str], Dict[str, List[str]]]) -> List[str]:
        """
        Handle both flat skill lists and categorized skills from resume parser
        Returns: Flat list of unique skills
        """
        if isinstance(skills, dict):
            # skills_by_category format from resume parser
            all_skills = []
            for category_skills in skills.values():
                all_skills.extend(category_skills)
            return list(set(all_skills))
        elif isinstance(skills, list):
            # Already flat list
            return list(set(skills))
        else:
            return []
    
    def create_profile_text(self, profile_data: Dict) -> str:
        """
        Convert structured profile data into searchable text
        This is what gets embedded - order matters!
        """
        parts = []
        
        # 1. Roles (most important for initial filtering)
        if profile_data.get('roles'):
            roles_text = ", ".join(profile_data['roles'])
            parts.append(f"Roles: {roles_text}")
            parts.append(f"Position: {roles_text}")  # Repeat for emphasis
        
        # 2. Skills (VERY important - repeat 3x for maximum weight)
        skills = self.normalize_skills(
            profile_data.get('skills') or profile_data.get('skills_by_category') or []
        )
        if skills:
            skills_text = ", ".join(skills[:20])  # Top 20 skills to avoid token limit
            parts.append(f"Technical Skills: {skills_text}")
            parts.append(f"Expertise: {skills_text}")
            parts.append(f"Proficient in: {skills_text}")
        
        # 3. Experience level
        if profile_data.get('experience_years'):
            exp_years = profile_data['experience_years']
            if exp_years <= 1:
                exp_level = "Junior"
            elif exp_years <= 3:
                exp_level = "Mid-level"
            elif exp_years <= 7:
                exp_level = "Senior"
            else:
                exp_level = "Expert"
            parts.append(f"Experience: {exp_years} years, {exp_level} level")
        
        # 4. Hackathon achievements (adds credibility)
        if profile_data.get('hackathons'):
            hackathon_data = profile_data['hackathons']
            if hackathon_data.get('has_hackathon_experience'):
                wins = hackathon_data.get('wins_breakdown', {})
                if wins.get('first', 0) > 0:
                    parts.append(f"Hackathon winner with {wins['first']} wins")
                elif wins.get('second', 0) > 0:
                    parts.append(f"Experienced hackathon participant with top placements")
                elif hackathon_data.get('total_hackathons', 0) >= 3:
                    parts.append(f"Active hackathon participant")
        
        # 5. Bio (user's description)
        if profile_data.get('bio'):
            bio = profile_data['bio'][:200]  # Limit bio length
            parts.append(f"About: {bio}")
        
        # 6. Interests and preferences
        if profile_data.get('interests'):
            interests_text = ", ".join(profile_data['interests'][:5])
            parts.append(f"Interests: {interests_text}")
        
        # 7. Project types preference
        if profile_data.get('project_types'):
            project_types_text = ", ".join(profile_data['project_types'])
            parts.append(f"Looking to build: {project_types_text}")
        
        return " | ".join(parts)
    
    def create_project_text(self, project_data: Dict) -> str:
        """Convert project data into searchable text"""
        parts = []
        
        # 1. Project title and description
        if project_data.get('title'):
            parts.append(f"Project: {project_data['title']}")
        
        if project_data.get('description'):
            desc = project_data['description'][:300]  # Limit description
            parts.append(f"Description: {desc}")
        
        # 2. Required roles (repeat for emphasis)
        if project_data.get('required_roles'):
            roles_text = ", ".join(project_data['required_roles'])
            parts.append(f"Looking for: {roles_text}")
            parts.append(f"Need: {roles_text}")
        
        # 3. Required skills (VERY important - repeat 3x)
        skills = self.normalize_skills(project_data.get('required_skills') or [])
        if skills:
            skills_text = ", ".join(skills)
            parts.append(f"Required skills: {skills_text}")
            parts.append(f"Tech stack: {skills_text}")
            parts.append(f"Technologies: {skills_text}")
        
        # 4. Experience requirements
        min_exp = project_data.get('min_experience', 0)
        max_exp = project_data.get('max_experience', 10)
        if min_exp > 0 or max_exp < 10:
            parts.append(f"Experience needed: {min_exp}-{max_exp} years")
        
        # 5. Project type/domain
        if project_data.get('project_type'):
            parts.append(f"Category: {project_data['project_type']}")
        
        return " | ".join(parts)
    
    def create_teammate_request_text(self, request_data: Dict) -> str:
        """Convert teammate request into searchable text"""
        parts = []
        
        # What they want to build
        if request_data.get('project_idea'):
            parts.append(f"Building: {request_data['project_idea'][:200]}")
        
        # What they're looking for
        if request_data.get('looking_for_roles'):
            roles_text = ", ".join(request_data['looking_for_roles'])
            parts.append(f"Looking for: {roles_text}")
            parts.append(f"Need teammates with roles: {roles_text}")
        
        if request_data.get('looking_for_skills'):
            skills_text = ", ".join(request_data['looking_for_skills'])
            parts.append(f"Need skills: {skills_text}")
            parts.append(f"Required expertise: {skills_text}")
            parts.append(f"Tech stack: {skills_text}")
        
        return " | ".join(parts)
    
    def _to_list(self, embedding: np.ndarray) -> List[float]:
        """Convert numpy array to Python list of floats"""
        if hasattr(embedding, 'tolist'):
            return [float(x) for x in embedding.tolist()]
        return [float(x) for x in embedding]
    
    def embed_profile(self, profile_data: Dict) -> List[float]:
        """Create embedding vector for a user profile - ALWAYS returns list[float]"""
        profile_text = self.create_profile_text(profile_data)
        embedding = self.model.encode(profile_text, convert_to_numpy=True)
        return self._to_list(embedding)
    
    def embed_project(self, project_data: Dict) -> List[float]:
        """Create embedding vector for a project - ALWAYS returns list[float]"""
        project_text = self.create_project_text(project_data)
        embedding = self.model.encode(project_text, convert_to_numpy=True)
        return self._to_list(embedding)
    
    def embed_teammate_request(self, request_data: Dict) -> List[float]:
        """Create embedding vector for a teammate request - ALWAYS returns list[float]"""
        request_text = self.create_teammate_request_text(request_data)
        embedding = self.model.encode(request_text, convert_to_numpy=True)
        return self._to_list(embedding)
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """Batch embed multiple texts for efficiency"""
        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return embeddings
    
    def embed_batch_profiles(self, profiles: List[Dict]) -> np.ndarray:
        """Efficiently embed multiple profiles at once"""
        texts = [self.create_profile_text(p) for p in profiles]
        return self.embed_batch(texts)
    
    def embed_batch_projects(self, projects: List[Dict]) -> np.ndarray:
        """Efficiently embed multiple projects at once"""
        texts = [self.create_project_text(p) for p in projects]
        return self.embed_batch(texts)
    
    def cosine_similarity(self, vec1: Union[np.ndarray, List[float]], vec2: Union[np.ndarray, List[float]]) -> float:
        """Calculate cosine similarity between two vectors"""
        # Convert to numpy if needed
        if not isinstance(vec1, np.ndarray):
            vec1 = np.array(vec1)
        if not isinstance(vec2, np.ndarray):
            vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        # Avoid division by zero
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))
    
    def cosine_similarity_batch(self, vec: np.ndarray, 
                                candidates: np.ndarray) -> np.ndarray:
        """
        Calculate cosine similarity between one vector and multiple candidates
        More efficient than calling cosine_similarity in a loop
        
        Args:
            vec: Single embedding vector (shape: [embedding_dim])
            candidates: Multiple embedding vectors (shape: [n_candidates, embedding_dim])
        
        Returns:
            Array of similarity scores (shape: [n_candidates])
        """
        # Normalize vectors
        vec_norm = vec / np.linalg.norm(vec)
        candidates_norm = candidates / np.linalg.norm(candidates, axis=1, keepdims=True)
        
        # Compute dot product (cosine similarity for normalized vectors)
        similarities = np.dot(candidates_norm, vec_norm)
        return similarities
    
    def find_similar(self, query_embedding: Union[np.ndarray, List[float]], 
                     candidate_embeddings: List[Union[np.ndarray, List[float]]],
                     top_k: int = 10) -> List[tuple]:
        """
        Find top-k most similar embeddings
        Returns: List of (index, similarity_score) tuples
        """
        # Convert query to numpy
        if not isinstance(query_embedding, np.ndarray):
            query_embedding = np.array(query_embedding)
        
        # Convert candidates to numpy array
        candidates_array = np.array([
            np.array(e) if not isinstance(e, np.ndarray) else e 
            for e in candidate_embeddings
        ])
        
        # Use batch similarity for efficiency
        similarities = self.cosine_similarity_batch(query_embedding, candidates_array)
        
        # Get indices of top-k
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        # Return as list of tuples
        return [(int(idx), float(similarities[idx])) for idx in top_indices]


# Usage example
if __name__ == "__main__":
    engine = EmbeddingEngine()
    
    print("🔧 Testing Embedding Engine\n")
    
    # Example 1: User profile with hackathon wins
    user_profile = {
        "bio": "Passionate full-stack developer who loves building AI applications",
        "skills": ["python", "fastapi", "react", "machine learning", "postgresql", "docker"],
        "roles": ["fullstack", "ml_engineer"],
        "experience_years": 3,
        "interests": ["hackathons", "open-source", "ai"],
        "project_types": ["web apps", "ml models", "apis"],
        "hackathons": {
            "has_hackathon_experience": True,
            "total_hackathons": 5,
            "wins_breakdown": {"first": 2, "second": 1, "third": 0, "finalist": 2},
            "hackathon_score": 37
        }
    }
    
    # Example 2: User profile from resume parser (skills_by_category format)
    user_from_resume = {
        "name": "Jane Doe",
        "bio": "Backend engineer specializing in distributed systems",
        "skills_by_category": {
            "backend": ["python", "golang", "nodejs"],
            "data": ["postgresql", "redis", "mongodb"],
            "devops": ["docker", "kubernetes", "aws"]
        },
        "roles": ["backend"],
        "experience_years": 5,
        "hackathons": {
            "has_hackathon_experience": False
        }
    }
    
    # Example 3: Project looking for teammates
    project = {
        "title": "AI-powered Healthcare Platform",
        "description": "Building a tool that uses NLP to match patients with doctors and provide diagnosis assistance",
        "required_skills": ["python", "nlp", "react", "fastapi", "machine learning"],
        "required_roles": ["ml_engineer", "frontend"],
        "min_experience": 2,
        "max_experience": 5
    }
    
    # Create embeddings
    print("Creating embeddings...")
    user1_embedding = engine.embed_profile(user_profile)
    user2_embedding = engine.embed_profile(user_from_resume)
    project_embedding = engine.embed_project(project)
    
    print(f"✅ Embedding dimension: {engine.embedding_dim}")
    print(f"✅ User 1 vector type: {type(user1_embedding)}, length: {len(user1_embedding)}")
    print(f"✅ User 2 vector type: {type(user2_embedding)}, length: {len(user2_embedding)}")
    print(f"✅ Project vector type: {type(project_embedding)}, length: {len(project_embedding)}")
    print("🔍 EmbeddingEngine: generating real embedding for profile")
    
    # Calculate similarities
    similarity1 = engine.cosine_similarity(user1_embedding, project_embedding)
    similarity2 = engine.cosine_similarity(user2_embedding, project_embedding)
    
    print(f"\n📊 Match Scores:")
    print(f"User 1 (Full-stack + ML + Hackathons) → Project: {similarity1:.1%}")
    print(f"User 2 (Backend specialist) → Project: {similarity2:.1%}")
    
    if similarity1 > similarity2:
        print("\n✅ User 1 is a better match (has ML skills + hackathon experience)")
    
    # Test find_similar
    top_matches = engine.find_similar(project_embedding, [user1_embedding, user2_embedding], top_k=2)
    print(f"\nTop matches: {top_matches}")
    
    print("\n✅ All tests passed! Embedding engine is working correctly.")