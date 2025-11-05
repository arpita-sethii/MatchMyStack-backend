# backend/app/main.py
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

# Import routers
from app.api.routes import auth, users, resumes, projects, chat
from app.api.routes.match import router as match_router
from app.api.websocket import websocket_endpoint
from app.db.base import Base
from app.db.session import engine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create DB tables in dev
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(title="MatchMyStack - Backend API", version="1.0.0")

# CORS origins
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for uploads
UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
logger.info(f"✓ Static files mounted at /uploads → {UPLOAD_DIR}")

# Register routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resumes.router)
app.include_router(projects.router)
app.include_router(match_router)
app.include_router(chat.router)

# Health check endpoint
@app.get("/ping")
async def ping(request: Request):
    """Lightweight health check endpoint"""
    return {
        "ok": True,
        "origin": request.headers.get("origin"),
        "service": "main"
    }

# WebSocket endpoint
@app.websocket("/ws/chat/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: int, token: str):
    await websocket_endpoint(websocket, room_id, token)

# Custom OpenAPI schema with JWT Bearer auth
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version="1.0.0",
        description="MatchMyStack API",
        routes=app.routes,
    )

    # Add bearer auth scheme
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["bearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi