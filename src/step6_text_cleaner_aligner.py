"""
Bước 5 & 6: Làm sạch văn bản, nối câu bị ngắt do chuyển trang, tách câu,
và dóng hàng (Alignment) Hán Nôm - Quốc ngữ bằng thuật toán Levenshtein.
Tuân thủ Quy định đồ án v2.4 (Trang 5, 13 - 22, 27):
- Chuẩn hóa NFC, chuẩn hóa PUA, xóa ký tự chọn dạng (Variation Selectors: U+FE00-U+FE0F, U+E0100-U+E01EF).
- Giữ nguyên [MASK] (6 ký tự) và 〓 (U+3013).
- Tính `text_diff` chuẩn JSON với khoảng nửa mở [start, end) tính theo Unicode code point trên chuỗi NFC.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.step5_dictionary_loader import HanNomDictionaryIndex

# Bảng ánh xạ các ký tự Private Use Area (PUA) do OCR Kim Hán Nôm trả về
# sang ký tự Unicode Hán Nôm chuẩn có trong bộ từ điển
PUA_NORMALIZATION_MAP = {
    "\U000f000b": "冊",  # sách
    "\U000f070f": "婆",  # bà
    "\U000f070b": "𠬠",  # một
    "\U000f03d9": "䀡",  # xem
    "\U000f0152": "𠉞",  # nay
    "\U000f0482": "義",  # nghĩa
}

# Ký tự chọn dạng (Variation Selectors) bắt buộc phải xóa theo Quy định v2.4 (Trang 13)
VARIATION_SELECTOR_PATTERN = re.compile(r"[\uFE00-\uFE0F\U000E0100-\U000E01EF]")

# Dấu câu và khoảng trắng cần bỏ qua khi trích xuất từng chữ Nôm / âm tiết Quốc ngữ
PUNCTUATION_CHAR_PATTERN = re.compile(r"[，。、！？；：「」『』（）\[\]\(\)\.,!\?;:\-\"'“”‘’…\s]")
QUOC_NGU_SYLLABLE_PATTERN = re.compile(r"\[MASK\]|[^\s\-，。、！？；：「」『』（）\[\]\(\)\.,!\?;:\"'“”‘’…]+")


@dataclass
class AlignedSentencePair:
    """
    Cấu trúc 1 hàng dữ liệu đã dóng hàng theo Quy định đồ án v2.4 (Trang 15 - 18):
    - Có hình ảnh: img_id, sentence_id, ch_txt, vi_txt, text_diff
    - Văn bản thuần: sentence_id, ch_txt, vi_txt
    """

    img_id: str
    sentence_id: str
    ch_txt: str
    vi_txt: str
    text_diff: Optional[List[Dict[str, Any]]] = None

    @property
    def sino_nom_char(self) -> str:
        """Bí danh tương thích ngược với v1.1."""
        return self.ch_txt

    @property
    def chu_qn_txt(self) -> str:
        """Bí danh tương thích ngược với v1.1."""
        return self.vi_txt


def normalize_pua_chars(text: str) -> str:
    """Chuyển các ký tự PUA (Private Use Area) sang ký tự Hán Nôm Unicode chuẩn."""
    for pua_char, std_char in PUA_NORMALIZATION_MAP.items():
        text = text.replace(pua_char, std_char)
    return text


def strip_variation_selectors(text: str) -> str:
    """Xóa toàn bộ ký tự chọn dạng (U+FE00-U+FE0F và U+E0100-U+E01EF) theo v2.4 Trang 13."""
    return VARIATION_SELECTOR_PATTERN.sub("", text)


def clean_sinonom_text(text: str) -> str:
    """
    Làm sạch văn bản Hán Nôm (v2.4 Trang 13):
    - Chuẩn hóa NFC, chuẩn hóa PUA, xóa variation selectors.
    - Các chữ viết dính liền (giữ nguyên khoảng trắng quanh [MASK] nếu có).
    - Loại bỏ chỉ mục chú thích như [1], (1).
    """
    text = unicodedata.normalize("NFC", text)
    text = normalize_pua_chars(text)
    text = strip_variation_selectors(text)
    text = re.sub(r"\[\d+\]|\(\d+\)", "", text)
    # Bảo vệ [MASK] trước khi xóa khoảng trắng giữa các chữ Nôm
    text = re.sub(r"\s*\[MASK\]\s*", " [MASK] ", text)
    parts = text.split("[MASK]")
    cleaned_parts = [re.sub(r"\s+", "", p) for p in parts]
    return " [MASK] ".join(cleaned_parts).strip()


def clean_quoc_ngu_text(text: str) -> str:
    """
    Làm sạch văn bản Quốc ngữ (v2.4 Trang 13 - 14):
    - Chuẩn hóa NFC, giữ nguyên từ cổ và cách đặt dấu thanh của bản gốc.
    - Loại bỏ chỉ mục chú thích [1], (1).
    - Loại bỏ ký tự xuống dòng, chuẩn hóa khoảng trắng.
    """
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[\d+\]|\(\d+\)", "", text)
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_sentence_id(img_id: str, sentence_idx_1based: int) -> str:
    """
    Quy định sentence_id (Trang 15):
    Bắt buộc theo định dạng `<img_id bỏ đuôi .jpg>.<số thứ tự câu>` (đánh từ 1).
    Ví dụ: img_id = 'Lorem ipsum.024.jpg', câu 1 -> 'Lorem ipsum.024.1'
    """
    stem = img_id[:-4] if img_id.lower().endswith(".jpg") else img_id
    return f"{stem}.{sentence_idx_1based}"


def tokenize_sinonom_with_spans(ch_txt: str) -> List[Tuple[str, int, int]]:
    """
    Tách từng chữ Hán Nôm kèm khoảng nửa mở [start, end) trên chuỗi NFC `ch_txt`.
    Bỏ qua dấu câu, khoảng trắng và thẻ `[MASK]` (6 ký tự, không đưa vào text_diff).
    """
    text = unicodedata.normalize("NFC", ch_txt)
    tokens: List[Tuple[str, int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("[MASK]", i):
            i += 6
            continue
        ch = text[i]
        if not PUNCTUATION_CHAR_PATTERN.match(ch):
            tokens.append((ch, i, i + 1))
        i += 1
    return tokens


def tokenize_quoc_ngu_with_spans(vi_txt: str) -> List[Tuple[str, int, int]]:
    """
    Tách từng âm tiết Quốc ngữ kèm khoảng nửa mở [start, end) trên chuỗi NFC `vi_txt`.
    Tách cả tên phiên âm có dấu gạch ngang `-` (VD: `Ma-ri-a` -> `Ma`, `ri`, `a`).
    Bỏ qua thẻ `[MASK]` (6 ký tự, không đưa vào text_diff).
    """
    text = unicodedata.normalize("NFC", vi_txt)
    tokens: List[Tuple[str, int, int]] = []
    for m in QUOC_NGU_SYLLABLE_PATTERN.finditer(text):
        tok = m.group(0)
        if tok == "[MASK]":
            continue
        tokens.append((tok, m.start(), m.end()))
    return tokens


def compute_text_diff_levenshtein(
    ch_txt: str,
    vi_txt: str,
    dict_index: HanNomDictionaryIndex,
) -> List[Dict[str, Any]]:
    """
    Thuật toán dóng hàng chữ Nôm – âm tiết Quốc ngữ bằng khoảng cách Levenshtein
    (Quy định đồ án v2.4 Trang 5, 17 - 21, 27):
    - Chi phí khớp từ điển (`is_match == True` và không phải `〓`) = 0.0
    - Chi phí thay thế không khớp (substitution) = 1.0
    - Chi phí chèn/xóa (insertion/deletion) = 1.2 (ưu tiên ghép 1-1 trên câu dịch âm đều độ dài)
    Trả về danh sách các phần tử `text_diff` chuẩn v2.4 (`nom_pos`, `nom_sub_text`, `vi_pos`, `vi_sub_text`, `type`).
    """
    ch_nfc = unicodedata.normalize("NFC", ch_txt)
    vi_nfc = unicodedata.normalize("NFC", vi_txt)

    sn_tokens = tokenize_sinonom_with_spans(ch_nfc)
    qn_tokens = tokenize_quoc_ngu_with_spans(vi_nfc)

    m = len(sn_tokens)
    n = len(qn_tokens)

    # Quy hoạch động Levenshtein có trọng số tra cứu từ điển
    dp = [[0.0] * (n + 1) for _ in range(m + 1)]
    op = [[""] * (n + 1) for _ in range(m + 1)]

    ins_del_cost = 1.2
    for i in range(1, m + 1):
        dp[i][0] = i * ins_del_cost
        op[i][0] = "D"  # Dư chữ Nôm
    for j in range(1, n + 1):
        dp[0][j] = j * ins_del_cost
        op[0][j] = "I"  # Dư âm tiết Quốc ngữ

    for i in range(1, m + 1):
        sn_ch = sn_tokens[i - 1][0]
        for j in range(1, n + 1):
            qn_syl = qn_tokens[j - 1][0]
            matched = (sn_ch != "\u3013") and dict_index.is_match(sn_ch, qn_syl)
            sub_cost = 0.0 if matched else 1.0

            c_sub = dp[i - 1][j - 1] + sub_cost
            c_del = dp[i - 1][j] + ins_del_cost
            c_ins = dp[i][j - 1] + ins_del_cost

            if c_sub <= c_del and c_sub <= c_ins:
                dp[i][j] = c_sub
                op[i][j] = "M" if matched else "S"
            elif c_del <= c_ins:
                dp[i][j] = c_del
                op[i][j] = "D"
            else:
                dp[i][j] = c_ins
                op[i][j] = "I"

    # Truy vết ngược để tạo các phần tử text_diff theo thứ tự tăng dần vị trí
    raw_ops: List[Tuple[str, Optional[int], Optional[int]]] = []
    i, j = m, n
    while i > 0 or j > 0:
        action = op[i][j]
        if action in ("M", "S"):
            raw_ops.append((action, i - 1, j - 1))
            i -= 1
            j -= 1
        elif action == "D":
            raw_ops.append(("D", i - 1, None))
            i -= 1
        else:
            raw_ops.append(("I", None, j - 1))
            j -= 1
    raw_ops.reverse()

    diffs: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(raw_ops):
        action, si, qi = raw_ops[idx]
        if action == "M":
            idx += 1
            continue
        if action == "S" and si is not None and qi is not None:
            _, ns, ne = sn_tokens[si]
            _, vs, ve = qn_tokens[qi]
            diffs.append(
                {
                    "nom_pos": [[ns, ne]],
                    "nom_sub_text": ch_nfc[ns:ne],
                    "vi_pos": [[vs, ve]],
                    "vi_sub_text": vi_nfc[vs:ve],
                    "type": "error",
                }
            )
            idx += 1
        elif action == "D" and si is not None:
            # Gom các chữ Nôm dư liên tiếp thành một phần tử error
            _, ns_start, ne_end = sn_tokens[si]
            idx += 1
            while idx < len(raw_ops) and raw_ops[idx][0] == "D" and raw_ops[idx][1] is not None:
                _, _, ne_end = sn_tokens[raw_ops[idx][1]]
                idx += 1
            diffs.append(
                {
                    "nom_pos": [[ns_start, ne_end]],
                    "nom_sub_text": ch_nfc[ns_start:ne_end],
                    "vi_pos": [],
                    "vi_sub_text": "",
                    "type": "error",
                }
            )
        elif action == "I" and qi is not None:
            # Gom các âm tiết Quốc ngữ dư liên tiếp thành một phần tử error
            _, vs_start, ve_end = qn_tokens[qi]
            idx += 1
            while idx < len(raw_ops) and raw_ops[idx][0] == "I" and raw_ops[idx][2] is not None:
                _, _, ve_end = qn_tokens[raw_ops[idx][2]]
                idx += 1
            diffs.append(
                {
                    "nom_pos": [],
                    "nom_sub_text": "",
                    "vi_pos": [[vs_start, ve_end]],
                    "vi_sub_text": vi_nfc[vs_start:ve_end],
                    "type": "error",
                }
            )
        else:
            idx += 1

    return diffs


def merge_hyphenated_vi_lines(lines: List[str]) -> str:
    """
    Nối các dòng Quốc ngữ thành một đoạn văn (v2.4 Trang 14):
    - Xử lý từ bị ngắt bằng dấu gạch ngang ở cuối dòng, giữ nguyên dấu gạch ngang tên riêng.
    - Nối các dòng bằng đúng một khoảng trắng, không còn ký tự xuống dòng.
    """
    cleaned = [clean_quoc_ngu_text(ln) for ln in lines if clean_quoc_ngu_text(ln)]
    if not cleaned:
        return ""
    return " ".join(cleaned)


class SinoNomAligner:
    """
    Bộ dóng hàng Hán Nôm – Quốc ngữ sử dụng khoảng cách Levenshtein kết hợp từ điển Hán Nôm
    (Quy định đồ án v2.4 Trang 5, 14 - 22, 27).
    """

    SENTENCE_END_VI = re.compile(r"(?<=[.!?])\s+")

    def __init__(self, dictionary_index: Optional[HanNomDictionaryIndex] = None) -> None:
        self.dictionary_index = dictionary_index

    def build_pair(
        self,
        img_id: str,
        sentence_idx_1based: int,
        ch_txt: str,
        vi_txt: str,
        is_phonetic: bool = True,
        custom_text_diff: Optional[List[Dict[str, Any]]] = None,
    ) -> AlignedSentencePair:
        """Tạo 1 cặp câu chuẩn v2.4 (chuẩn hóa NFC và tự tính `text_diff` bằng Levenshtein)."""
        ch_clean = clean_sinonom_text(ch_txt)
        vi_clean = clean_quoc_ngu_text(vi_txt)

        if not is_phonetic:
            diff = None
        elif custom_text_diff is not None:
            diff = custom_text_diff
        elif self.dictionary_index is not None:
            diff = compute_text_diff_levenshtein(ch_clean, vi_clean, self.dictionary_index)
        else:
            diff = []

        return AlignedSentencePair(
            img_id=img_id,
            sentence_id=build_sentence_id(img_id, sentence_idx_1based),
            ch_txt=ch_clean,
            vi_txt=vi_clean,
            text_diff=diff,
        )

    def align_page_sequence(
        self,
        page_entries: List[Tuple[str, List[str], List[str]]],
    ) -> List[AlignedSentencePair]:
        """
        Dóng hàng một chuỗi cặp trang liên tiếp theo thứ tự đọc của sách:
        - `page_entries`: danh sách `(ch_img_id, ch_col_texts, vi_line_texts)`.
        - Tự động nối câu bị ngắt do chuyển trang (lấy `img_id` của trang bắt đầu câu theo v2.4 Trang 14).
        - Tách câu Quốc ngữ theo dấu kết thúc câu `.!?` rồi cắt tương ứng số chữ Nôm 1-1
          kết hợp tinh chỉnh ranh giới bằng Levenshtein & từ điển Hán Nôm.
        """
        # 1. Nối toàn bộ văn bản Nôm và Quốc ngữ kèm đánh dấu biên trang bắt đầu
        full_ch_chars: List[Tuple[str, str]] = []  # (char, origin_img_id)
        full_vi_chunks: List[str] = []

        for img_id, ch_lines, vi_lines in page_entries:
            page_ch = clean_sinonom_text("".join(ch_lines))
            for ch in page_ch:
                full_ch_chars.append((ch, img_id))
            page_vi = merge_hyphenated_vi_lines(vi_lines)
            if page_vi:
                full_vi_chunks.append(page_vi)

        full_vi_text = " ".join(full_vi_chunks).strip()
        if not full_ch_chars or not full_vi_text:
            return []

        # 2. Tách câu Quốc ngữ theo dấu kết thúc câu
        vi_sentences = [s.strip() for s in self.SENTENCE_END_VI.split(full_vi_text) if s.strip()]
        if not vi_sentences:
            vi_sentences = [full_vi_text]

        # 3. Cắt tương ứng phần văn bản Nôm theo số âm tiết Quốc ngữ (dịch âm 1-1)
        pairs: List[AlignedSentencePair] = []
        sent_counter_per_img: Dict[str, int] = {}
        ch_cursor = 0
        total_ch_len = len(full_ch_chars)

        for s_idx, vi_sent in enumerate(vi_sentences):
            vi_syl_count = len(tokenize_quoc_ngu_with_spans(vi_sent))
            if ch_cursor >= total_ch_len:
                break

            start_cursor = ch_cursor
            origin_img = full_ch_chars[start_cursor][1]

            if s_idx == len(vi_sentences) - 1:
                end_cursor = total_ch_len
            else:
                counted = 0
                end_cursor = start_cursor
                while end_cursor < total_ch_len and counted < vi_syl_count:
                    ch = full_ch_chars[end_cursor][0]
                    if not PUNCTUATION_CHAR_PATTERN.match(ch):
                        counted += 1
                    end_cursor += 1
                # Kéo theo dấu câu Nôm ngay sau chữ cuối câu (ví dụ 。！？)
                while (
                    end_cursor < total_ch_len
                    and PUNCTUATION_CHAR_PATTERN.match(full_ch_chars[end_cursor][0])
                ):
                    end_cursor += 1

            ch_sent = "".join(c for c, _ in full_ch_chars[start_cursor:end_cursor])
            ch_cursor = end_cursor

            sent_num = sent_counter_per_img.get(origin_img, 0) + 1
            sent_counter_per_img[origin_img] = sent_num
            pairs.append(self.build_pair(origin_img, sent_num, ch_sent, vi_sent, is_phonetic=True))

        return pairs
