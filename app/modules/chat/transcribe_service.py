"""
Service xử lý Speech-to-Text (STT) sử dụng Google Gemini Multimodal Audio API
hoặc OpenAI Audio Transcriptions API.
Chuyển đổi âm thanh ghi từ trình duyệt (.webm, .wav, .mp3, .mp4, .ogg) thành văn bản tiếng Việt chính xác.
"""

import base64
import logging
from typing import Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TranscribeService:
    """Service chuyển đổi âm thanh thành văn bản qua Gemini / Whisper API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or getattr(settings, "gemini_api_key", None) or getattr(settings, "llm_api_key", None)

    async def transcribe(self, audio_bytes: bytes, content_type: str = "audio/webm") -> str:
        """
        Gửi audio bytes lên Gemini Multimodal Audio API để trích xuất văn bản tiếng Việt.
        """
        if not audio_bytes or len(audio_bytes) < 100:
            logger.warning("[STT] Audio bytes too small or empty (len=%d)", len(audio_bytes) if audio_bytes else 0)
            return ""

        gemini_key = getattr(settings, "gemini_api_key", None) or (self.api_key if self.api_key and self.api_key.startswith("AIzaSy") else None)

        if not gemini_key:
            logger.info("[STT] GEMINI_API_KEY chưa được cấu hình. Bỏ qua phiên âm trực tuyến.")
            return ""

        # Chuẩn hóa MimeType tương thích với Gemini
        mime_type = "audio/webm"
        ct_lower = content_type.lower()
        if "wav" in ct_lower:
            mime_type = "audio/wav"
        elif "mp4" in ct_lower or "m4a" in ct_lower or "aac" in ct_lower:
            mime_type = "audio/mp4"
        elif "mp3" in ct_lower or "mpeg" in ct_lower:
            mime_type = "audio/mp3"
        elif "ogg" in ct_lower:
            mime_type = "audio/ogg"
        elif "webm" in ct_lower:
            mime_type = "audio/webm"

        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        prompt = (
            "Bạn là hệ thống chuyển đổi giọng nói tiếng Việt thành văn bản (Speech-to-Text).\n"
            "NHIỆM VỤ: Lắng nghe đoạn âm thanh được cung cấp và phiên âm chính xác thành văn bản tiếng Việt.\n"
            "QUY TẮC BẮT BUỘC:\n"
            "1. Nếu đoạn âm thanh là khoảng lặng, im lặng, chỉ có tiếng thở, tiếng rè microphone, tạp âm môi trường hoặc KHÔNG CÓ TIẾNG NGƯỜI NÓI RÕ RÀNG: BẮT BUỘC chỉ trả về duy nhất từ khóa: [NO_SPEECH]. Tuyệt đối không suy đoán, không bịa từ, không lặp lại bất kỳ từ ngữ nào trong hướng dẫn này.\n"
            "2. Nếu có tiếng người nói thực sự: Hãy phiên âm trung thực, chuẩn chính tả tiếng Việt. Nếu người nói nhắc đến các thuật ngữ chuyên ngành (như gAMSPro, quy trình, tờ trình, PO, hợp đồng, ngân sách, phân bổ, khấu hao...) thì viết đúng thuật ngữ đó.\n"
            "3. Chỉ trả về nội dung phiên âm (hoặc [NO_SPEECH]), không thêm lời chào, không giải thích, không kèm dấu ngoặc kép hay ghi chú thừa."
        )

        configured_model = getattr(settings, "gemini_model", "gemini-2.5-flash") or "gemini-2.5-flash"
        models_to_try = [
            configured_model,
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ]
        models_to_try = list(dict.fromkeys(models_to_try))

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_audio,
                            }
                        },
                        {
                            "text": prompt,
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 2048,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": gemini_key,
        }

        silence_tokens = {
            "", "[no_speech]", "no_speech", "<noise>", "[blank_audio]",
            "none", "n/a", "...", "null", "[silence]", "silence",
            "im lặng", "không có tiếng nói", "không nghe rõ"
        }

        last_error = None
        async with httpx.AsyncClient(timeout=35.0) as client:
            for model_name in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                try:
                    logger.info("[STT] Calling Gemini model '%s' (audio size: %d bytes, mime: %s)", model_name, len(audio_bytes), mime_type)
                    response = await client.post(url, json=payload, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text_result = "".join(p.get("text", "") for p in parts).strip()

                            if text_result.startswith(('"', "'", "`")) and text_result.endswith(('"', "'", "`")) and len(text_result) > 2:
                                text_result = text_result[1:-1].strip()

                            cleaned_lower = text_result.lower().strip()
                            if cleaned_lower in silence_tokens:
                                logger.info("[STT] Model '%s' detected silence / no speech in audio.", model_name)
                                return ""

                            if text_result:
                                logger.info("[STT] Transcribe success with '%s': '%s'", model_name, text_result[:100])
                                return text_result
                    else:
                        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                except Exception as ex:
                    last_error = str(ex)

        if last_error:
            logger.warning("[STT] All Gemini models attempted. Error: %s", last_error)
        return ""
