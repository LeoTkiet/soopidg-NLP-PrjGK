"""
Bước 4 (Phần Quốc ngữ): Skeleton chạy OCR cho các trang chữ Quốc ngữ (thư mục vi/).
Theo Quy định đồ án (Trang 3, 7, 11):
- Có thể dùng các mô hình OCR Quốc ngữ / đa năng (PaddleOCR, VietOCR, Vintern, Qwen2.5-VL, Surya...).
- Bounding box trang Quốc ngữ: đánh theo hàng (cột ngang) hoặc theo đoạn, thứ tự từ trái sang phải, từ trên xuống dưới.
"""

from pathlib import Path
from typing import Any, Dict, List


class VietnameseOCREngine:
    """Skeleton cho bộ nhận dạng chữ Quốc ngữ."""

    def __init__(self, model_name: str = "paddleocr_vi") -> None:
        self.model_name = model_name
        # TODO (Thành viên 2): Khởi tạo mô hình OCR Quốc ngữ (ví dụ: PaddleOCR + VietOCR hoặc VLM)

    def recognize_page(self, image_path: Path) -> List[Dict[str, Any]]:
        """
        Chạy OCR trên 1 trang ảnh Quốc ngữ và trả về danh sách các bounding box chuẩn PPOCRLabel:
        [
            {
                "transcription": "Văn bản nhận diện...",
                "points": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
            },
            ...
        ]
        Lưu ý: Loại bỏ số trang, tiêu đề đầu trang, chân trang và chú thích ngoài nội dung chính.
        """
        # TODO (Thành viên 2): Cài đặt pipeline phát hiện vùng chữ (Text Detection) và nhận dạng (Recognition)
        raise NotImplementedError("Chưa cài đặt chi tiết hàm recognize_page cho OCR Quốc ngữ.")

