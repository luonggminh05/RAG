import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import init_db
from app.core.logging import setup_logging
from app.llmops.langsmith import setup_langsmith
from app.llmops.langfuse import setup_langfuse, flush_langfuse
from app.routers.dependencies import get_document_repository

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    setup_langsmith()
    setup_langfuse()
    logger.info("Initializing Database ORM and Vector Schema...")

    try:
        init_db()
    except Exception as ex:
        logger.warning(f"Failed to initialize ORM database during startup: {ex}")

    try:
        repo = get_document_repository()
        repo.initialize()
        logger.info("[OK] Vector Database and full-text index initialized.")
    except Exception as ex:
        logger.warning(f"Failed to initialize Vector Database during startup: {ex}")

    yield

    # Shutdown
    logger.info("Shutting down RAG Python AI Service...")
    flush_langfuse()
