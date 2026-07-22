import io
import math
from typing import Optional, Tuple, List
from PIL import Image, ImageOps

class ImageUtilities:
    @staticmethod
    def try_get_dimensions(image_bytes: bytes) -> Optional[Tuple[int, int]]:
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                return img.width, img.height
        except Exception:
            return None

    @staticmethod
    def should_skip_ocr(width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            return True
        min_side = min(width, height)
        max_side = max(width, height)
        return width < 20 or height < 20 or min_side * 15 < max_side

    @staticmethod
    def prepare_for_ocr(image_bytes: bytes, min_readable_width=1200, max_width=3200, max_height=3200) -> bytes:
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                source_width, source_height = img.width, img.height
                upscale = min_readable_width / source_width if source_width < min_readable_width else 1.0
                max_scale = min(max_width / source_width, max_height / source_height)
                scale = max(1.0, min(upscale, max_scale))
                
                if scale == 1.0 and img.format == "PNG":
                    return image_bytes
                    
                target_width = max(1, int(round(source_width * scale)))
                target_height = max(1, int(round(source_height * scale)))
                
                resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                
                # Make sure we save as PNG
                out = io.BytesIO()
                resized.save(out, format="PNG")
                return out.getvalue()
        except Exception:
            return image_bytes

    @staticmethod
    def prepare_ocr_variants(image_bytes: bytes) -> List[bytes]:
        variants = []
        
        # 1. Baseline upscale
        baseline_bytes = ImageUtilities.prepare_for_ocr(image_bytes)
        variants.append(baseline_bytes)
        
        try:
            with Image.open(io.BytesIO(baseline_bytes)) as img:
                width, height = img.width, img.height
                
                # 2. Padded upscale (40px white margin all around)
                padding = 40
                padded_w = width + padding * 2
                padded_h = height + padding * 2
                
                padded_img = Image.new("RGB", (padded_w, padded_h), "white")
                padded_img.paste(img, (padding, padding))
                
                out = io.BytesIO()
                padded_img.save(out, format="PNG")
                variants.append(out.getvalue())
                
                # Convert to Grayscale for Otsu thresholding
                gray_img = img.convert("L")
                hist = gray_img.histogram()
                total = width * height
                
                # Compute Otsu threshold
                sum_total = sum(i * hist[i] for i in range(256))
                sum_b = 0
                w_b = 0
                var_max = 0.0
                otsu_threshold = 127
                
                for t in range(256):
                    w_b += hist[t]
                    if w_b == 0:
                        continue
                    w_f = total - w_b
                    if w_f == 0:
                        break
                    sum_b += t * hist[t]
                    m_b = sum_b / w_b
                    m_f = (sum_total - sum_b) / w_f
                    var_between = w_b * w_f * (m_b - m_f) ** 2
                    if var_between > var_max:
                        var_max = var_between
                        otsu_threshold = t
                
                # 3. Apply Threshold
                fn = lambda x: 0 if x < otsu_threshold else 255
                thresh_img = gray_img.point(fn, mode="1")
                out1 = io.BytesIO()
                thresh_img.save(out1, format="PNG")
                variants.append(out1.getvalue())
                
                # 4. Apply Inverted Threshold
                fn_inv = lambda x: 255 if x < otsu_threshold else 0
                inv_img = gray_img.point(fn_inv, mode="1")
                out2 = io.BytesIO()
                inv_img.save(out2, format="PNG")
                variants.append(out2.getvalue())
                
        except Exception:
            # Fallback if any PIL step fails
            pass
            
        return variants

    @staticmethod
    def compress_for_vision(image_bytes: bytes, max_width=2560, max_height=1440, quality=95) -> bytes:
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                scale = min(1.0, min(max_width / img.width, max_height / img.height))
                if scale == 1.0:
                    out = io.BytesIO()
                    img.convert("RGB").save(out, format="JPEG", quality=quality)
                    return out.getvalue()
                    
                target_width = max(1, int(round(img.width * scale)))
                target_height = max(1, int(round(img.height * scale)))
                
                resized = img.resize((target_width, target_height), Image.Resampling.BILINEAR)
                out = io.BytesIO()
                resized.convert("RGB").save(out, format="JPEG", quality=quality)
                return out.getvalue()
        except Exception:
            return image_bytes
