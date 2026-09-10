import secrets
from fastapi import Header, HTTPException, status
from app.core.config import settings

def verify_api_key(
    x_internal_api_key: str | None = Header(None, alias="X-Internal-Api-Key"),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> str | None:
    """Dependency xác thực API Key trên từng route cụ thể nếu cần."""
    required = settings.effective_api_key
    if not required:
        return None

    provided = x_internal_api_key or x_api_key
    if not provided or not secrets.compare_digest(provided, required):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid API key.",
        )
    return provided
