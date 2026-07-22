import base64
import logging
import httpx
import asyncio
from typing import Dict, Any, Optional
from app.config import settings
from app.ingestion.image_utils import ImageUtilities

logger = logging.getLogger(__name__)

class VisionService:
    def __init__(self):
        self.enabled = settings.ingestion_enable_vision_caption
        self.api_url = settings.ingestion_vision_api_url
        self.api_key = settings.ingestion_vision_api_key
        self.model = settings.ingestion_vision_model
        
        # Concurrency limiter semaphore (similar to SemaphoreSlim in C#)
        # Default concurrency level is 2
        self._semaphore = asyncio.Semaphore(2)

    async def generate_caption(
        self,
        image_bytes: bytes,
        metadata: Dict[str, Any],
        ocr_text: Optional[str]
    ) -> Optional[str]:
        if not self.enabled or not self.api_url:
            return None

        dims = ImageUtilities.try_get_dimensions(image_bytes)
        if not dims:
            logger.warning(f"Vision skipped: could not get dimensions for {metadata.get('source')}")
            return None

        width, height = dims
        if width < settings.ingestion_min_vision_image_width or height < settings.ingestion_min_vision_image_height:
            logger.debug(f"Vision skipped small image from {metadata.get('source')}: {width}x{height}px.")
            return None

        # Compress image for vision to speed up transfer and reduce tokens
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
                # Configured timeout
                async with httpx.AsyncClient(timeout=float(settings.ingestion_vision_timeout_seconds)) as client:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    res_data = response.json()
                    
                    caption = res_data["choices"][0]["message"]["content"]
                    return caption.strip() if caption else None
            except Exception as ex:
                logger.error(f"Vision service API error for image from {metadata.get('source')}: {ex}")
                return None

    async def describe_screenshot(
        self,
        image_bytes: bytes,
        user_question: Optional[str]
    ) -> Optional[str]:
        if not self.api_url:
            return None

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
                async with httpx.AsyncClient(timeout=float(settings.ingestion_vision_timeout_seconds)) as client:
                    response = await client.post(self.api_url, json=payload, headers=headers)
                    response.raise_for_status()
                    res_data = response.json()
                    
                    caption = res_data["choices"][0]["message"]["content"]
                    return caption.strip() if caption else None
            except Exception as ex:
                logger.error(f"Failed to generate description for screenshot: {ex}")
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
            "- Đối với bảng điều kiện tìm kiếm hoặc bộ lọc (ví dụ: \"Điều kiện tìm kiếm\"): Liệt kê chi tiết tên tất cả các trường/nhãn (ví dụ: Loại tờ trình, Người lập, Từ ngày, Đến ngày...).\n"
            "- Đối với danh sách hoặc bảng dữ liệu: Liệt kê tên tất cả các cột dữ liệu từ trái sang phải.\n"
            "- Đối với các nút bấm/hành động (ví dụ: Thêm, Chỉnh sửa, Xóa, Tìm kiếm, Xem chi tiết, Excel...): Ghi rõ tên nút và vị trí của chúng.\n\n"
            "3. VĂN BẢN QUAN TRỌNG NHÌN THẤY:\n"
            "- Trích xuất chính xác các nhãn, tiêu đề, thông báo lỗi hoặc các đoạn văn bản quan trọng có trên ảnh.\n\n"
            "4. TÓM TẮT TÌM KIẾM (SEARCHABLE SUMMARY):\n"
            "- Viết từ 4-8 câu mô tả tự nhiên bằng tiếng Việt tóm tắt nội dung màn hình này (gồm menu đang mở, các nút bấm chính, các trường tìm kiếm có thể nhập, và tên bảng dữ liệu) để phục vụ cho việc tìm kiếm ngữ nghĩa sau này.\n"
            "Preserve Vietnamese text from the image exactly as visible."
        )

        if ocr_text and ocr_text.strip():
            prompt += f"\n\nVăn bản OCR hỗ trợ (có thể bị thiếu hoặc sai lệch chính tả, hãy dùng để đối chiếu): {ocr_text[:3000]}"

        return prompt
