from fastapi import APIRouter
from app.models.api_models import HealthResponse

router = APIRouter()

@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="healthy", message="RAG API service is running.")
