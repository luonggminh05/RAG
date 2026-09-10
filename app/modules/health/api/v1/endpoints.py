from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    message: str

@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        message="RAG Python AI Service is running healthy with DDD Enterprise Architecture."
    )
