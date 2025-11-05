# backend/app/api/routes/__init__.py
from . import auth
from . import users
from . import resumes
from . import projects

__all__ = ["auth", "users", "resumes", "projects"]
