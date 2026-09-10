import base64
import hashlib
import logging
import httpx
import asyncio
from typing import Dict, Any, Optional
from cachetools import TTLCache
from app.core.config import settings
from app.ai.vision.image_utils import ImageUtilities

logger = logging.getLogger(__name__)

class VisionService:
    def __init__(self):
        self.enabled = getattr(settings, "ingestion_enable_vision_caption", True)
        self.api_url = getattr(settings, "ingestion_vision_api_url", "http://localhost:11434/v1/chat/completions")
        self.api_key = getattr(settings, "ingestion_vision_api_key", "ollama")
        self.model = getattr(settings, "ingestion_vision_model", "qwen2.5vl:7b")
        self._semaphore = asyncio.Semaphore(2)
        # Cache kết quả caption và describe theo SHA-256 (P5.3)
        self._caption_cache = TTLCache(maxsize=512, ttl=86400)
        self._screenshot_cache = TTLCache(maxsize=512, ttl=86400)

    async def generate_caption(
        self,
        image_bytes: bytes,
        metadata: Dict[str, Any],
        ocr_text: Optional[str]
    ) -> Optional[str]:
        if not self.enabled or not self.api_url or not image_bytes:
            return None

        # Check cache bằng SHA-256 (P5.3)
        image_hash = hashlib.sha256(image_bytes).hexdigest()[:16]
        if image_hash in self._caption_cache:
            logger.debug(f"[VISION] Caption cache hit for hash={image_hash}")
            return self._caption_cache[image_hash]

        dims = ImageUtilities.try_get_dimensions(image_bytes)
        if not dims:
            logger.warning(f"[VISION] Skipped: could not get dimensions for {metadata.get('source')}")
            return None

        width, height = dims
        max_side = max(width, height)
        total_pixels = width * height

        min_w = getattr(settings, "ingestion_min_vision_image_width", 100)
        min_h = getattr(settings, "ingestion_min_vision_image_height", 100)
        if width < min_w or height < min_h:
            logger.debug(f"[VISION] Skipped small image from {metadata.get('source')}: {width}x{height}px.")
            return None

        large_side = getattr(settings, "ingestion_vision_large_image_min_side", 1200)
        large_pixels = getattr(settings, "ingestion_vision_large_image_min_pixels", 1000000)
        is_large_image = (max_side >= large_side or total_pixels >= large_pixels)
        is_ui_screenshot = metadata.get("image_role") == "Screenshot" or metadata.get("content_kind") == "image_ui_description"

        if not is_large_image and not is_ui_screenshot:
            logger.debug(f"[VISION] Skipped moderate non-UI image from {metadata.get('source')}, relying on OCR.")
            return None

        compressed = ImageUtilities.compress_for_vision(image_bytes)
        img_b64 = base64.b64encode(compressed).decode("utf-8")
        prompt = self._build_prompt(ocr_text)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.0,
            "max_tokens": 1000
        }

        headers = {}
        if self.api_key and self.api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with self._semaphore:
            try:
                timeout = float(getattr(settings, "ingestion_vision_timeout_seconds", 160))
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    res_data = response.json()
                    caption = res_data["choices"][0]["message"]["content"]
                    result = caption.strip() if caption else None
                    if result:
                        self._caption_cache[image_hash] = result
                    return result
            except Exception as ex:
                logger.error(f"[VISION] Service API error for image from {metadata.get('source')}: {repr(ex)}")
                return None

    async def describe_screenshot(
        self,
        image_bytes: bytes,
        user_question: Optional[str]
    ) -> Optional[str]:
        if not self.api_url or not image_bytes:
            return None

        # Check screenshot cache bằng SHA-256 (P5.3)
        q_bytes = (user_question or "").encode("utf-8")
        cache_key = hashlib.sha256(image_bytes + q_bytes).hexdigest()[:16]
        if cache_key in self._screenshot_cache:
            logger.debug(f"[VISION] Screenshot cache hit for key={cache_key}")
            return self._screenshot_cache[cache_key]

        compressed = ImageUtilities.compress_for_vision(image_bytes)
        img_b64 = base64.b64encode(compressed).decode("utf-8")

        prompt_parts = [
            "Bạn là trợ lý AI hỗ trợ người dùng thao tác trên phần mềm. User vừa gửi ảnh chụp màn hình.",
            "Hãy mô tả ngắn gọn bằng tiếng Việt:",
            "1. Đây là màn hình gì, thuộc module hay hệ thống nào?",
            "2. Trạng thái hiện tại (đang nhập liệu, đang xem danh sách, có thông báo lỗi hay trạng thái nào đáng chú ý không?)",
            "3. Các nút bấm, hành động chính, hoặc trường thông tin nổi bật đang hiển thị.",
            "4. Nếu có văn bản quan trọng như tiêu đề hoặc thông báo lỗi, hãy trích xuất nguyên văn.",
            "Trả lời ngắn gọn, tập trung vào mô tả giao diện trực quan, tối đa 300 từ."
        ]

        if user_question:
            prompt_parts.append(f"\nCâu hỏi của user: \"{user_question}\"")
            prompt_parts.append("Hãy tập trung mô tả chi tiết các phần giao diện có liên quan trực tiếp đến câu hỏi này để giúp hệ thống trả lời chính xác.")

        prompt = "\n".join(prompt_parts)

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": 0.0,
            "max_tokens": 1000
        }

        headers = {}
        if self.api_key and self.api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {self.api_key}"

        async with self._semaphore:
            try:
                timeout = float(getattr(settings, "ingestion_vision_timeout_seconds", 160))
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    res_data = response.json()
                    caption = res_data["choices"][0]["message"]["content"]
                    result = caption.strip() if caption else None
                    if result:
                        self._screenshot_cache[cache_key] = result
                    return result
            except Exception as ex:
                logger.error(f"[VISION] Failed to generate description for screenshot: {repr(ex)}")
                return None

    def _build_prompt(self, ocr_text: Optional[str]) -> str:
        prompt = (
            "Bạn là một trợ lý AI phân tích ảnh giao diện phần mềm phục vụ cho hệ thống tìm kiếm câu hỏi đáp (RAG Chatbot).\n"
            "Hãy đọc trực tiếp ảnh giao diện và mô tả chi tiết bằng tiếng Việt theo cấu trúc sau:\n\n"
            "1. LOẠI GIAO DIỆN & TÊN HỆ THỐNG:\n"
            "- Xác định đây là màn hình gì (màn hình tìm kiếm, biểu mẫu nhập liệu, danh sách dữ liệu, email, báo cáo, hay sơ đồ...).\n"
            "- Ghi rõ tên hệ thống, module hoặc menu đang hiển thị nếu có.\n\n"
            "2. CHI TIẾT CÁC PANEL & KHỐI CHỨC NĂNG:\n"
            "- Mô tả cách bố trí các khu vực chính (thanh công cụ bên trên, menu bên trái, bảng dữ liệu bên dưới...).\n"
            "- Liệt kê chi tiết tên tất cả các trường/nhãn tìm kiếm, các cột dữ liệu, các nút bấm thao tác.\n\n"
            "3. VĂN BẢN QUAN TRỌNG NHÌN THẤY:\n"
            "- Trích xuất chính xác các nhãn, tiêu đề, thông báo lỗi có trên ảnh.\n\n"
            "4. TÓM TẮT TÌM KIẾM (SEARCHABLE SUMMARY):\n"
            "- Viết từ 4-8 câu mô tả tự nhiên bằng tiếng Việt tóm tắt nội dung màn hình này để phục vụ tìm kiếm ngữ nghĩa."
        )

        if ocr_text and ocr_text.strip():
            prompt += f"\n\nVăn bản OCR hỗ trợ: {ocr_text[:3000]}"

        return prompt
