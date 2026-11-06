"""
Bước 5 & 6: Làm sạch văn bản, nối câu bị ngắt do chuyển trang, tách câu,
và dóng hàng (Alignment) Hán Nôm - Quốc ngữ.
Tuân thủ Quy định chung về dữ liệu văn bản & việc dóng hàng (Trang 8 - 9).
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional

from src.step5_dictionary_loader import HanNomDictionaryIndex


@dataclass
class AlignedSentencePair:
    """Cấu trúc 1 dòng dữ liệu đã dóng hàng chuẩn bị xuất ra .csv và .xlsx."""
    img_id: str          # Ví dụ: Lorem ipsum.024.jpg (không chứa tên thư mục)
    sentence_id: str     # Ví dụ: Lorem ipsum.024.1 (<img_id bỏ đuôi .jpg>.<số thứ tự câu>)
    sino_nom_char: str   # Văn bản Hán Nôm (viết dính liền, dùng dấu câu 、 。 ！ ？ ；)
    chu_qn_txt: str      # Văn bản Quốc ngữ (đúng chính tả, khoảng trắng chuẩn)


def clean_sinonom_text(text: str) -> str:
    """
    Làm sạch văn bản Hán Nôm (Trang 8):
    - Chuẩn hóa NFC.
    - Các chữ viết dính liền, không có khoảng trắng thừa giữa các chữ Hán Nôm.
    - Loại bỏ chỉ mục chú thích như [1], (1) và ký tự rác.
    """
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[\d+\]|\(\d+\)", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip()


def clean_quoc_ngu_text(text: str) -> str:
    """
    Làm sạch văn bản Quốc ngữ (Trang 8):
    - Chuẩn hóa NFC.
    - Loại bỏ chỉ mục chú thích như [1], (1).
    - Chuẩn hóa khoảng trắng sau dấu phẩy, dấu chấm.
    """
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[\d+\]|\(\d+\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_sentence_id(img_id: str, sentence_idx_1based: int) -> str:
    """
    Quy định sentence_id (Trang 8):
    Bắt buộc theo định dạng <img_id bỏ đuôi .jpg>.<số thứ tự câu>
    Ví dụ: img_id = 'Lorem ipsum.024.jpg', câu 1 -> 'Lorem ipsum.024.1'
    """
    stem = img_id[:-4] if img_id.lower().endswith(".jpg") else img_id
    return f"{stem}.{sentence_idx_1based}"


class SinoNomAligner:
    """
    Skeleton bộ dóng hàng Hán Nôm - Quốc ngữ.
    Hỗ trợ các kiểu dóng hàng: 1-1, 1-n, n-1, n-m.
    Đặc biệt với sách dịch âm 1-1: số chữ Quốc ngữ phải bằng số chữ Hán Nôm.
    """

    def __init__(self, dictionary_index: Optional[HanNomDictionaryIndex] = None) -> None:
        self.dictionary_index = dictionary_index

    def align_page_pairs(
        self,
        img_id: str,
        sinonom_lines: List[str],
        quoc_ngu_lines: List[str],
    ) -> List[AlignedSentencePair]:
        """
        TODO (Thành viên 3):
        1. Ghép từ/câu bị ngắt do chuyển trang trước khi tách câu.
        2. Tách câu Hán Nôm và Quốc ngữ dựa trên dấu câu kết hợp độ dài âm tiết & tra cứu từ điển.
        3. Thực hiện thuật toán quy hoạch động (Dynamic Programming / Needleman-Wunsch hoặc Bertalign/SentAlign)
           kết hợp điểm tương đồng âm đọc từ `self.dictionary_index.is_match(...)`.
        """
        raise NotImplementedError("Chưa cài đặt chi tiết thuật toán align_page_pairs.")

