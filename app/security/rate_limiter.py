import asyncio
from collections import deque
import logging
import time
from typing import Dict, Optional, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

_ADMIN_KEYWORDS = {"admin", "administrator", "sysadmin", "superadmin"}
_ELITE_KEYWORDS = {"elite", "manager", "approver", "lead", "director", "giamdoc", "truongphong"}

def resolve_role_for_rate_limit(user_roles: Optional[str]) -> str:
    """Xác định role tier để áp dụng ngưỡng RPM tương ứng."""
    if not user_roles:
        return "Officer"
    roles_lower = [r.strip().lower() for r in user_roles.split(",") if r.strip()]
    if any(any(kw in r for kw in _ADMIN_KEYWORDS) for r in roles_lower):
        return "Admin"
    if any(any(kw in r for kw in _ELITE_KEYWORDS) for r in roles_lower):
        return "Elite"
    return "Officer"

class RateLimiter:
    """
    Sliding Window Counter In-Memory Rate Limiter theo RFC 6585.
    Hỗ trợ kiểm tra lưu lượng request per minute (RPM) theo Role và Client IP.
    """

    def __init__(self):
        self._windows: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    def _get_limit_for_role(self, role: str) -> int:
        if role == "Admin":
            return getattr(settings, "rate_limit_admin_rpm", 240)
        elif role == "Elite":
            return getattr(settings, "rate_limit_elite_rpm", 120)
        return getattr(settings, "rate_limit_officer_rpm", 60)

    async def check_rate_limit(
        self,
        identifier: str,
        user_roles: Optional[str] = None,
    ) -> Tuple[bool, int, int, int]:
        """
        Kiểm tra lưu lượng request.
        Trả về: (is_allowed, limit, remaining, reset_seconds)
        """
        role = resolve_role_for_rate_limit(user_roles)
        limit = self._get_limit_for_role(role)
        now = time.time()
        window_start = now - 60.0

        key = f"{identifier}:{role}"

        async with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()

            window = self._windows[key]

            # Xóa các timestamps đã quá 60 giây
            while window and window[0] <= window_start:
                window.popleft()

            current_count = len(window)

            if current_count >= limit:
                # Quá ngưỡng giới hạn
                oldest_timestamp = window[0]
                reset_seconds = max(1, int(oldest_timestamp + 60.0 - now))
                logger.warning(
                    f"[RATE_LIMIT] Client '{identifier}' (role={role}) exceeded limit {limit} RPM."
                )
                return False, limit, 0, reset_seconds

            # Cho phép và ghi nhận request mới
            window.append(now)
            remaining = limit - len(window)
            reset_seconds = 60
            return True, limit, remaining, reset_seconds


_global_rate_limiter: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter
