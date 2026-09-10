import asyncio
from collections import deque
import logging
import time
from typing import Dict, Optional, Tuple
from app.core.config import settings

logger = logging.getLogger(__name__)

# Keywords cho 6 bậc phân quyền (RBAC 6-Tier)
_MASTER_KEYWORDS = {"admin", "administrator", "sysadmin", "superadmin", "master"}
_COLEADER_KEYWORDS = {"co-leader", "coleader", "vice master", "vicemaster", "pho bang"}
_TIER3_KEYWORDS = {
    "officer", "hau can", "haucan", "hau_can", "logistics",
    "staff", "nhan su", "nhansu", "nhan_su", "hr",
    "raid leader", "raidleader", "chien thuat", "chienthuat", "chien_thuat", "tactics",
}
_ELITE_KEYWORDS = {"elite", "tinh anh", "tinhanh", "manager", "lead", "approver", "director", "giamdoc", "truongphong"}
_MEMBER_KEYWORDS = {"member", "thanh vien", "thanhvien"}
_RECRUIT_KEYWORDS = {"recruit", "tan binh", "tanbinh", "guest", "user"}


def resolve_role_for_rate_limit(user_roles: Optional[str]) -> str:
    """Xác định role tier để áp dụng ngưỡng RPM và Concurrency tương ứng."""
    if not user_roles:
        return "Recruit"
    roles_lower = [r.strip().lower() for r in user_roles.split(",") if r.strip()]

    if any(any(kw in r for kw in _MASTER_KEYWORDS) for r in roles_lower):
        return "Master"
    if any(any(kw in r for kw in _COLEADER_KEYWORDS) for r in roles_lower):
        return "Co-Leader"
    if any(any(kw in r for kw in _TIER3_KEYWORDS) for r in roles_lower):
        return "Officer"
    if any(any(kw in r for kw in _ELITE_KEYWORDS) for r in roles_lower):
        return "Elite"
    if any(any(kw in r for kw in _MEMBER_KEYWORDS) for r in roles_lower):
        return "Member"
    return "Recruit"


class RateLimiter:
    """
    Sliding Window Counter In-Memory Rate Limiter theo RFC 6585
    kết hợp Concurrency Limiter (kiểm soát số lượng tác vụ đồng thời).
    Hỗ trợ 6 bậc vai trò: Master, Co-Leader, Officer, Elite, Member, Recruit.
    """

    def __init__(self):
        self._windows: Dict[str, deque] = {}
        self._inflight: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _get_rpm_limit_for_role(self, role: str) -> int:
        if role == "Master":
            return getattr(settings, "rate_limit_master_rpm", 240)
        elif role == "Co-Leader":
            return getattr(settings, "rate_limit_coleader_rpm", 180)
        elif role == "Officer":
            return getattr(settings, "rate_limit_tier3_rpm", 120)
        elif role == "Elite":
            return getattr(settings, "rate_limit_elite_rpm", 60)
        elif role == "Member":
            return getattr(settings, "rate_limit_member_rpm", 30)
        return getattr(settings, "rate_limit_recruit_rpm", 20)

    def get_concurrency_limit(self, role: str) -> int:
        if role == "Master":
            return getattr(settings, "chat_concurrency_master", 15)
        elif role == "Co-Leader":
            return getattr(settings, "chat_concurrency_coleader", 10)
        elif role == "Officer":
            return getattr(settings, "chat_concurrency_tier3", 5)
        elif role == "Elite":
            return getattr(settings, "chat_concurrency_elite", 3)
        elif role == "Member":
            return getattr(settings, "chat_concurrency_member", 2)
        return getattr(settings, "chat_concurrency_recruit", 1)

    async def check_and_acquire(
        self,
        identifier: str,
        user_roles: Optional[str] = None,
    ) -> Tuple[bool, int, int, int, str]:
        """
        Kiểm tra lưu lượng RPM và số lượng request đồng thời (Concurrency).
        Nếu hợp lệ, tự động tăng số tác vụ đang chạy (+1 inflight).
        Trả về: (is_allowed, limit, remaining, reset_seconds, error_detail)
        """
        role = resolve_role_for_rate_limit(user_roles)
        rpm_limit = self._get_rpm_limit_for_role(role)
        conc_limit = self.get_concurrency_limit(role)
        now = time.time()
        window_start = now - 60.0

        key = f"{identifier}:{role}"

        async with self._lock:
            # 1. Kiểm tra Concurrency (luồng đồng thời)
            current_inflight = self._inflight.get(identifier, 0)
            if current_inflight >= conc_limit:
                logger.warning(
                    f"[CONCURRENCY_LIMIT] Client '{identifier}' (role={role}) reached max concurrency {conc_limit}."
                )
                return False, conc_limit, 0, 1, f"Đã đạt giới hạn xử lý đồng thời ({conc_limit} câu hỏi cùng lúc). Vui lòng đợi câu trả lời trước hoàn tất."

            # 2. Kiểm tra RPM (sliding window)
            if key not in self._windows:
                self._windows[key] = deque()

            window = self._windows[key]
            while window and window[0] <= window_start:
                window.popleft()

            current_count = len(window)
            if current_count >= rpm_limit:
                oldest_timestamp = window[0]
                reset_seconds = max(1, int(oldest_timestamp + 60.0 - now))
                logger.warning(
                    f"[RATE_LIMIT] Client '{identifier}' (role={role}) exceeded limit {rpm_limit} RPM."
                )
                return False, rpm_limit, 0, reset_seconds, f"Bạn đã gửi quá giới hạn số câu hỏi ({rpm_limit} câu/phút). Vui lòng thử lại sau {reset_seconds} giây."

            # 3. Ghi nhận request và tăng inflight
            window.append(now)
            self._inflight[identifier] = current_inflight + 1
            remaining = rpm_limit - len(window)
            return True, rpm_limit, remaining, 60, ""

    async def release(self, identifier: str) -> None:
        """Giải phóng 1 slot inflight khi request hoàn tất hoặc bị hủy."""
        async with self._lock:
            if identifier in self._inflight:
                self._inflight[identifier] -= 1
                if self._inflight[identifier] <= 0:
                    del self._inflight[identifier]

    async def check_rate_limit(
        self,
        identifier: str,
        user_roles: Optional[str] = None,
    ) -> Tuple[bool, int, int, int]:
        """Tương thích ngược kiểm tra chỉ RPM."""
        allowed, limit, remaining, reset_secs, _ = await self.check_and_acquire(identifier, user_roles)
        if allowed:
            # Nếu chỉ gọi check_rate_limit thì không giữ inflight
            await self.release(identifier)
        return allowed, limit, remaining, reset_secs


_global_rate_limiter: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter
