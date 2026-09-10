from fastapi import APIRouter
from app.modules.chat.api.v1.endpoints import router as v1_router

router = APIRouter()
router.include_router(v1_router, tags=["Chat"])
