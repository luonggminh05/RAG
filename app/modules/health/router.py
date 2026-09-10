from fastapi import APIRouter
from app.modules.health.api.v1.endpoints import router as v1_router

router = APIRouter()
router.include_router(v1_router, prefix="/health", tags=["Health"])
