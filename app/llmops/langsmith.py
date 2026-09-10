import os
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

def setup_langsmith() -> None:
    if getattr(settings, "langsmith_tracing", False):
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        if getattr(settings, "langsmith_api_key", None):
            os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        if getattr(settings, "langsmith_project", None):
            os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        logger.info(f"[LLMOPS] LangSmith tracing enabled for project '{settings.langsmith_project}'")
