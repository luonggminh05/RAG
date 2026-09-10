from fastapi import APIRouter
from app.modules.health.api.v1.endpoints import router as health_endpoints
from app.modules.chat.api.v1.endpoints import router as chat_endpoints, list_available_models
from app.modules.document.api.v1.endpoints import router as document_endpoints
from app.modules.chat.api.v1.schemas import ModelListResponse
from app.core.config import settings

api_v1_router = APIRouter(prefix=settings.API_V1_STR)

# Register v1 standard routes
api_v1_router.include_router(health_endpoints, prefix="/health", tags=["Health"])
api_v1_router.include_router(chat_endpoints, prefix="/chat", tags=["Chat"])
api_v1_router.include_router(document_endpoints, prefix="/document", tags=["Document"])

# Alias GET /api/v1/models → /api/v1/chat/models (for standalone UI compatibility)
# Chỉ expose endpoint models, không duplicate toàn bộ chat router
api_v1_router.add_api_route(
    "/models",
    list_available_models,
    methods=["GET"],
    response_model=ModelListResponse,
    tags=["Models"],
    summary="List available AI models (alias of /chat/models)",
    include_in_schema=True,
)

# Root and backward-compatible alias routers
root_router = APIRouter()

# 1. Main /api/v1 routes
root_router.include_router(api_v1_router)

# 2. Legacy /health alias
root_router.include_router(health_endpoints, prefix="/health", tags=["Health (Alias)"])

# 3. Legacy /v1/chat/stream alias
root_router.include_router(chat_endpoints, prefix="/v1", tags=["Chat (Legacy Alias)"])

# 4. Legacy /db/* aliases for C# Gateway & legacy frontend compatibility
root_router.include_router(document_endpoints, prefix="/db", tags=["Database (Legacy Alias)"])
