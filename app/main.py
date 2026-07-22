import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api import health, database, chat
from app.dependencies import repository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the SQL Server database schema and indices
    logger.info("Initializing vector database...")
    try:
        repository.initialize()
    except Exception as ex:
        logger.error(f"Failed to initialize database during startup: {ex}", exc_info=True)
        # We don't crash, but log it so developers can troubleshoot connectivity
    
    yield
    # Shutdown: Clean up resources if necessary
    logger.info("Shutting down RAG API service...")

app = FastAPI(
    title="Rag Python AI Service",
    description="Python FastAPI replacement for the C# Host Chatbot service, running RAG pipeline and SSE streaming.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
allowed_origins = settings.frontend_cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi import Request
from fastapi.responses import JSONResponse

@app.middleware("http")
async def api_key_auth_middleware(request: Request, call_next):
    # Allow OPTIONS preflight, health checks, and API docs
    if request.method == "OPTIONS" or request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
        return await call_next(request)
        
    if settings.required_api_key:
        api_key = request.headers.get("X-Internal-Api-Key")
        if api_key != settings.required_api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized: Invalid or missing X-Internal-Api-Key"}
            )
            
    return await call_next(request)


# Register routers
app.include_router(health.router, tags=["Health"])
app.include_router(database.router, prefix="/db", tags=["Database"])
app.include_router(chat.router, prefix="/v1", tags=["Chat"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=True)
