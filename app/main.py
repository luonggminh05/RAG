import os
import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.middleware import register_middlewares
from app.lifespan import lifespan
from app.routers.router import root_router

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Python FastAPI RAG & Multimodal AI Service với DDD Clean Architecture và Giao Diện Web Standalone Gemini.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Configuration
allowed_origins = settings.frontend_cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Core Middlewares (Logging & API Key Auth)
register_middlewares(app)

# Include All Routers (v1 + backward compatibility aliases)
app.include_router(root_router)

# Mount Static UI Folder
ui_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
if not os.path.exists(ui_dir):
    ui_dir = os.path.abspath("ui")

if os.path.exists(ui_dir):
    app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")


@app.get("/", include_in_schema=False)
async def serve_ui_root():
    """Phục vụ trang giao diện người dùng chính phong cách Gemini Google Chat."""
    index_path = os.path.join(ui_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "message": f"Welcome to {settings.PROJECT_NAME}",
        "status": "online",
        "docs_url": "/docs",
        "health_check": f"{settings.API_V1_STR}/health",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
