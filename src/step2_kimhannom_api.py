"""
Bước 4 (Phần Nôm): Client gọi Bộ API Kim Hán Nôm (https://kimhannom.fit.hcmus.edu.vn)
Tuân thủ nghiêm ngặt tài liệu "Hướng dẫn sử dụng API Kim Hán Nôm" (Phiên bản 2026-10-10):
1. POST /api/web/clc-sinonom/image-upload
2. POST /api/web/clc-sinonom/structure-classification
3. POST /api/web/clc-sinonom/image-ocr
4. POST /api/web/clc-sinonom/image-rec

Giới hạn số lượt gọi (Rate Limits):
- Phút: 25 lượt
- Giờ: 50 lượt
- Ngày: 200 lượt
- Tuần: 600 lượt
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional
import requests

from src.config import DEFAULT_USER_AGENT


class KimHanNomAPIClient:
    """Client giao tiếp với hệ thống Kim Hán Nôm kèm bộ đếm Rate Limit và lưu Cache."""

    def __init__(
        self,
        bearer_token: str,
        base_url: str = "https://kimhannom.fit.hcmus.edu.vn",
        user_agent: str = DEFAULT_USER_AGENT,
        min_delay_seconds: float = 3.0,
        usage_log_path: Optional[Path] = None,
    ) -> None:
        if user_agent.lower().startswith("python-requests"):
            raise ValueError(
                "User-Agent KHÔNG được bắt đầu bằng 'python-requests' theo quy định API!"
            )
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token.strip()
        self.user_agent = user_agent
        self.min_delay_seconds = min_delay_seconds
        self.usage_log_path = usage_log_path or Path("cache/api_usage_log.json")
        self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_request_ts = 0.0

    def _get_headers(self, is_json: bool = True) -> Dict[str, str]:
        """Tạo header bắt buộc gồm User-Agent và Authorization: Bearer <token>."""
        headers = {
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {self.bearer_token}",
        }
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    def _respect_rate_limit(self) -> None:
        """
        Đảm bảo độ trễ tối thiểu giữa các request và kiểm tra giới hạn:
        25/phút, 50/giờ, 200/ngày, 600/tuần.
        """
        now = time.time()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_delay_seconds:
            time.sleep(self.min_delay_seconds - elapsed)

        # Đọc lịch sử gọi API để cảnh báo/chặn nếu chạm ngưỡng
        history = []
        if self.usage_log_path.exists():
            try:
                history = json.loads(self.usage_log_path.read_text(encoding="utf-8"))
            except Exception:
                history = []

        now = time.time()
        last_min = [t for t in history if now - t <= 60]
        last_hour = [t for t in history if now - t <= 3600]
        last_day = [t for t in history if now - t <= 86400]
        last_week = [t for t in history if now - t <= 7 * 86400]

        if len(last_min) >= 25:
            raise RuntimeError("Chạm giới hạn API Kim Hán Nôm: 25 lượt/phút!")
        if len(last_hour) >= 50:
            raise RuntimeError("Chạm giới hạn API Kim Hán Nôm: 50 lượt/giờ!")
        if len(last_day) >= 200:
            raise RuntimeError("Chạm giới hạn API Kim Hán Nôm: 200 lượt/ngày!")
        if len(last_week) >= 600:
            raise RuntimeError("Chạm giới hạn API Kim Hán Nôm: 600 lượt/tuần!")

        last_week.append(now)
        self.usage_log_path.write_text(json.dumps(last_week), encoding="utf-8")
        self._last_request_ts = now

    @staticmethod
    def _parse_envelope(response: requests.Response) -> Dict[str, Any]:
        """Kiểm tra ResponseEnvelope chuẩn: {is_success, code, message, data}."""
        response.raise_for_status()
        payload = response.json()
        if not payload.get("is_success") or payload.get("code") != "000000":
            raise RuntimeError(
                f"Kim Hán Nôm API trả về lỗi (code={payload.get('code')}): {payload.get('message')}"
            )
        return payload.get("data", {})

    def upload_image(self, image_path: Path) -> str:
        """
        1. Tải ảnh lên: POST /api/web/clc-sinonom/image-upload
        Trả về file_name tạm trên máy chủ (ví dụ: 'tempd561fba0e59e48dbaaeac2189a9deef8.jpg').
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-upload"
        with open(image_path, "rb") as img_file:
            files = {"image_file": (image_path.name, img_file, "image/jpeg")}
            resp = requests.post(
                url,
                headers=self._get_headers(is_json=False),
                files=files,
                timeout=60,
            )
        data = self._parse_envelope(resp)
        return data["file_name"]

    def classify_structure(self, server_file_name: str) -> Dict[str, Any]:
        """
        2. Phân loại cấu trúc ảnh: POST /api/web/clc-sinonom/structure-classification
        Trả về: {ocr_id, lang_type, reading_direction, is_sino_nom}
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/structure-classification"
        body = {"file_name": server_file_name}
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=60
        )
        return self._parse_envelope(resp)

    def ocr_image(
        self,
        server_file_name: str,
        ocr_id: int = 1,
        lang_type: int = 2,
        reading_direction: int = 1,
        epitaph: int = 0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        3. OCR ảnh chữ Hán Nôm: POST /api/web/clc-sinonom/image-ocr
        Tham số:
        - ocr_id: 1 (Thông thường, chiều dọc), 2 (Hành chính), 3 (Ngoại cảnh), 4 (Thông thường, chiều ngang)
        - lang_type: 0 (Chưa biết), 1 (Chữ Hán), 2 (Chữ Nôm)
        - reading_direction: 1 (Dọc - mặc định), 2 (Ngang)
        - epitaph: 0 (Văn bản thông thường), 1 (Văn bia)
        - tag: null hoặc model_id chuyên biệt
        Trả về: {result_file_name, result_ocr_text, result_bbox}
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-ocr"
        body = {
            "ocr_id": ocr_id,
            "lang_type": lang_type,
            "reading_direction": reading_direction,
            "epitaph": epitaph,
            "tag": tag,
            "file_name": server_file_name,
        }
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=120
        )
        return self._parse_envelope(resp)

    def recognize_cropped_image(
        self,
        server_file_name: str,
        ocr_id: int = 1,
        lang_type: int = 2,
        reading_direction: int = 1,
    ) -> Dict[str, Any]:
        """
        4. Nhận dạng ảnh đã cắt từ bounding box: POST /api/web/clc-sinonom/image-rec
        Dùng khi image-ocr trả về bounding box không hợp lệ.
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-rec"
        body = {
            "ocr_id": ocr_id,
            "lang_type": lang_type,
            "reading_direction": reading_direction,
            "file_name": server_file_name,
        }
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=60
        )
        return self._parse_envelope(resp)

