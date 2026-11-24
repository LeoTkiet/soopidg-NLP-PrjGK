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
# sang ký tự Unicode Hán Nôm chuẩn (Nhóm A: đã có điểm mã Unicode hợp lệ trong Ext-B/Ext-H & từ điển)
PUA_NORMALIZATION_MAP = {
    # 6 mã từ tập mẫu ban đầu
    "\U000f000b": "冊",  # sách
    "\U000f070f": "婆",  # bà
    "\U000f070b": "𠬠",  # một
    "\U000f03d9": "䀡",  # xem
    "\U000f0152": "𠉞",  # nay
    "\U000f0482": "義",  # nghĩa
    # 19 mã khớp 100% hình nét (glyph outline) với Unicode CJK Extension H (U+31350..U+323AF)
    "\U000f047c": "𱺵",  # U+31EB5: là (x728 trong book_1)
    "\U000f000e": "𱍸",  # U+31378: ấy (x112)
    "\U000f07ef": "𱻌",  # U+31ECC: dường (x48)
    "\U000f0833": "𱏫",  # U+313EB: đâu (x23)
    "\U000f006e": "𱑏",  # U+3144F: cử (x19)
    "\U000f0602": "𲈾",  # U+3223E: cửa (x13)
    "\U000f0087": "𱒢",  # U+314A2: ví (x12)
    "\U000f02c7": "𱥯",  # U+3196F: mấy (x8)
    "\U000f0629": "𲋄",  # U+322C4: phong (x7)
    "\U000f07e8": "𱐬",  # U+3142C: thế (x7)
    "\U000f15ae": "𱽐",  # U+31F50: bông / buông (x5)
    "\U000f025f": "𱼫",  # U+31F2B: đài (x4)
    "\U000f0821": "𱽇",  # U+31F47: gian (x3)
    "\U000f0029": "𱎹",  # U+313B9: nghi (x1)
    "\U000f004f": "𱐍",  # U+3140D: u (x1)
    "\U000f01f5": "𱠍",  # U+3180D: buông (x1)
    "\U000f1072": "𲃪",  # U+320EA: đuổi (x1)
    "\U000f12d9": "𱔫",  # U+3152B: ghẹo (x1)
    "\U000f030e": "𱪵",  # U+31AB5: lô (x1)
    # 4 mã dị thể nét khắc của chữ Unicode chuẩn đã có trong từ điển & dv.jsonl
    "\U000f061a": "𩈘",  # U+29218: mặt (x38, dv.jsonl ghi chung forms với 𩈘)
    "\U000f084e": "𠁑",  # U+20051: dưới (x8)
    "\U000f0742": "𱟴",  # U+317F4: đem / dặm (x2)
    "\U000f0832": "𱏫",  # U+313EB: đâu (x1, biến thể chân 匕/儿 của U+F0833)
}

# Nhóm B (Quy định đồ án v2.6 Trang 12-14 & 17): Các ký tự PUA thực sự chưa có điểm mã Unicode chuẩn
# -> Bắt buộc thay bằng 〓 (U+3013) và ghi vết vào `<Tên sách>_placeholder_map.json`
PUA_PLACEHOLDER_METADATA: Dict[str, Dict[str, Optional[str]]] = {
    "\U000f07ba": {
        "ids": "⿰氵⿱日土",
        "note": "PUA gốc U+F07BA (âm đọc ngữ cảnh: nát/nết; biến thể 涅)",
    },
    "\U000f0761": {
        "ids": "⿱宀冘",
        "note": "PUA gốc U+F0761 (âm đọc ngữ cảnh: đem/đâm; BTCN #191, chưa có Unicode chuẩn)",
    },
    "\U000f0803": {
        "ids": "⿱穴刀",
        "note": "PUA gốc U+F0803 (âm đọc ngữ cảnh: cùng; biến thể 穷 viết 穴+刀)",
    },
    "\U000f0341": {
        "ids": "⿰牜高",
        "note": "PUA gốc U+F0341 (âm đọc ngữ cảnh: rỗi/rồi; biến thể 犒 trong dv.jsonl)",
    },
    "\U000f04f3": {
        "ids": "⿱艹⿰罒戍",
        "note": "PUA gốc U+F04F3 (âm đọc ngữ cảnh: mót/miệt; biến thể 蔑 trong dv.jsonl)",
    },
    "\U000f0816": {
        "ids": "⿰忄𣀦",
        "note": "PUA gốc U+F0816 (âm đọc ngữ cảnh: run; biến thể 憞/惇)",
    },
    "\U000f0c65": {
        "ids": "⿰糹⿱厽彡",
        "note": "PUA gốc U+F0C65 (âm đọc ngữ cảnh: tóm; biến thể 縿)",
    },
    "\U000f0810": {
        "ids": "⿰忄⿱宀冘",
        "note": "PUA gốc U+F0810 (âm đọc ngữ cảnh: thầm; bộ 忄 + U+F0761)",
    },
}

# Biểu thức phát hiện mọi ký tự thuộc vùng dùng riêng (Private Use Area) theo v2.6 Trang 14 & 17
PUA_CHAR_PATTERN = re.compile(r"[\uE000-\uF8FF\U000F0000-\U000FFFFD\U00100000-\U0010FFFD]")

# Ký tự chọn dạng (Variation Selectors) bắt buộc phải xóa theo Quy định v2.4/v2.6 (Trang 17)
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


def normalize_pua_chars(text: str, replace_unknown_with_placeholder: bool = True) -> str:
    """
    Chuyển các ký tự PUA (Private Use Area) sang ký tự Hán Nôm Unicode chuẩn (Nhóm A).
    Theo Quy định đồ án v2.6 (Trang 12-14 & 17):
    Mọi ký tự PUA còn lại chưa có điểm mã Unicode chuẩn (Nhóm B) bắt buộc thay bằng 〓 (U+3013)
    và theo dõi trong `<Tên sách>_placeholder_map.json`.
    """
    for pua_char, std_char in PUA_NORMALIZATION_MAP.items():
        if pua_char in text:
            text = text.replace(pua_char, std_char)
    if replace_unknown_with_placeholder and PUA_CHAR_PATTERN.search(text):
        text = PUA_CHAR_PATTERN.sub("\u3013", text)
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

    def _align_tokens_dp(
        self,
        sn_tokens: List[Tuple[str, int, int]],
        qn_tokens: List[Tuple[str, int, int]],
    ) -> List[Tuple[Optional[int], Optional[int]]]:
        """
        Dóng hàng chỉ số token Nôm <-> âm tiết Quốc ngữ bằng quy hoạch động Levenshtein
        có trọng số từ điển (dùng banded DP khi trang dài để chạy rất nhanh và không bị trôi lệch).
        Trả về danh sách các cặp `(sn_idx_or_None, qn_idx_or_None)` theo thứ tự tăng dần.
        """
        m = len(sn_tokens)
        n = len(qn_tokens)
        if m == 0 and n == 0:
            return []
        if m == 0:
            return [(None, j) for j in range(n)]
        if n == 0:
            return [(i, None) for i in range(m)]

        band = max(45, abs(m - n) + 30)
        use_band = (m * n > 60000) and (band < min(m, n))
        ins_del = 1.2
        inf = 1e9

        if not use_band:
            dp = [[0.0] * (n + 1) for _ in range(m + 1)]
            op = [[0] * (n + 1) for _ in range(m + 1)]
            for i in range(1, m + 1):
                dp[i][0] = i * ins_del
                op[i][0] = 1
            for j in range(1, n + 1):
                dp[0][j] = j * ins_del
                op[0][j] = 2
            for i in range(1, m + 1):
                sn_ch = sn_tokens[i - 1][0]
                for j in range(1, n + 1):
                    qn_syl = qn_tokens[j - 1][0]
                    matched = (
                        self.dictionary_index is not None
                        and sn_ch != "\u3013"
                        and self.dictionary_index.is_match(sn_ch, qn_syl)
                    )
                    c_sub = dp[i - 1][j - 1] + (0.0 if matched else 1.0)
                    c_del = dp[i - 1][j] + ins_del
                    c_ins = dp[i][j - 1] + ins_del
                    if c_sub <= c_del and c_sub <= c_ins:
                        dp[i][j] = c_sub
                        op[i][j] = 0
                    elif c_del <= c_ins:
                        dp[i][j] = c_del
                        op[i][j] = 1
                    else:
                        dp[i][j] = c_ins
                        op[i][j] = 2
            res: List[Tuple[Optional[int], Optional[int]]] = []
            i, j = m, n
            while i > 0 or j > 0:
                a = op[i][j]
                if a == 0:
                    res.append((i - 1, j - 1))
                    i -= 1
                    j -= 1
                elif a == 1:
                    res.append((i - 1, None))
                    i -= 1
                else:
                    res.append((None, j - 1))
                    j -= 1
            res.reverse()
            return res

        # Banded DP quanh đường chéo (m / n) cho đoạn văn dài
        dp_d: Dict[Tuple[int, int], float] = {(0, 0): 0.0}
        op_d: Dict[Tuple[int, int], int] = {}
        for i in range(1, min(m, band) + 1):
            dp_d[(i, 0)] = i * ins_del
            op_d[(i, 0)] = 1
        for j in range(1, min(n, band) + 1):
            dp_d[(0, j)] = j * ins_del
            op_d[(0, j)] = 2
        ratio = n / max(1, m)
        for i in range(1, m + 1):
            sn_ch = sn_tokens[i - 1][0]
            center = int(round(i * ratio))
            j_lo = max(1, center - band)
            j_hi = min(n, center + band)
            for j in range(j_lo, j_hi + 1):
                qn_syl = qn_tokens[j - 1][0]
                matched = (
                    self.dictionary_index is not None
                    and sn_ch != "\u3013"
                    and self.dictionary_index.is_match(sn_ch, qn_syl)
                )
                c_sub = dp_d.get((i - 1, j - 1), inf) + (0.0 if matched else 1.0)
                c_del = dp_d.get((i - 1, j), inf) + ins_del
                c_ins = dp_d.get((i, j - 1), inf) + ins_del
                if c_sub <= c_del and c_sub <= c_ins:
                    dp_d[(i, j)] = c_sub
                    op_d[(i, j)] = 0
                elif c_del <= c_ins:
                    dp_d[(i, j)] = c_del
                    op_d[(i, j)] = 1
                else:
                    dp_d[(i, j)] = c_ins
                    op_d[(i, j)] = 2
        res = []
        i, j = m, n
        while i > 0 or j > 0:
            a = op_d.get((i, j), 0)
            if a == 0:
                res.append((i - 1, j - 1))
                i -= 1
                j -= 1
            elif a == 1:
                res.append((i - 1, None))
                i -= 1
            else:
                res.append((None, j - 1))
                j -= 1
        res.reverse()
        return res

    def _split_chunk_into_sentence_pairs(
        self,
        ch_chars: List[Tuple[str, str]],
        vi_text: str,
        sent_counter_per_img: Dict[str, int],
    ) -> List[AlignedSentencePair]:
        """
        Tách một khối đã khóa cặp trang (1 trang hoặc vài trang có câu vắt trang) thành từng câu
        bằng cách cắt văn bản Nôm bám chính xác theo đường dóng hàng Levenshtein + từ điển,
        bảo toàn 100% ký tự của cả `ch_chars` lẫn `vi_text`.
        """
        ch_full = "".join(c for c, _ in ch_chars)
        vi_full = clean_quoc_ngu_text(vi_text)
        if not ch_full or not vi_full:
            return []

        vi_sentences = [s.strip() for s in self.SENTENCE_END_VI.split(vi_full) if s.strip()]
        if len(vi_sentences) <= 1:
            origin_img = ch_chars[0][1]
            sent_num = sent_counter_per_img.get(origin_img, 0) + 1
            sent_counter_per_img[origin_img] = sent_num
            return [self.build_pair(origin_img, sent_num, ch_full, vi_full, is_phonetic=True)]

        sn_tokens = tokenize_sinonom_with_spans(ch_full)
        qn_tokens = tokenize_quoc_ngu_with_spans(vi_full)
        if not sn_tokens or not qn_tokens:
            origin_img = ch_chars[0][1]
            sent_num = sent_counter_per_img.get(origin_img, 0) + 1
            sent_counter_per_img[origin_img] = sent_num
            return [self.build_pair(origin_img, sent_num, ch_full, vi_full, is_phonetic=True)]

        # Dóng hàng toàn bộ khối bằng Levenshtein có trọng số từ điển
        aligned = self._align_tokens_dp(sn_tokens, qn_tokens)

        # Với mỗi âm tiết Quốc ngữ j, tìm chỉ số ký tự cuối cùng của chữ Nôm khớp gần nhất <= j
        qn_to_ch_end: List[int] = [0] * len(qn_tokens)
        last_ch_end = 0
        for si, qi in aligned:
            if si is not None:
                last_ch_end = sn_tokens[si][2]
            if qi is not None:
                qn_to_ch_end[qi] = last_ch_end

        # Cắt ranh giới từng câu Quốc ngữ khớp theo `qn_to_ch_end`
        pairs: List[AlignedSentencePair] = []
        ch_cursor = 0
        qn_cursor = 0
        total_ch_len = len(ch_full)

        pending_vi: List[str] = []
        for s_idx, vi_sent in enumerate(vi_sentences):
            n_syl = len(tokenize_quoc_ngu_with_spans(vi_sent))
            next_qn_cursor = min(len(qn_tokens), qn_cursor + n_syl)
            is_last = s_idx == len(vi_sentences) - 1

            if is_last:
                target_end = total_ch_len
            else:
                target_end = qn_to_ch_end[next_qn_cursor - 1] if next_qn_cursor > 0 else ch_cursor
                # Kéo theo dấu câu Nôm ngay sau chữ cuối câu (。！？、；)
                while (
                    target_end < total_ch_len
                    and PUNCTUATION_CHAR_PATTERN.match(ch_full[target_end])
                ):
                    target_end += 1

            # Tránh tạo hàng rỗng một vế (v2.4/v2.6 Trang 19): nếu ch_sent rỗng, gộp sang câu kế
            ch_slice = ch_full[ch_cursor:target_end]
            if not is_last and not ch_slice.strip():
                pending_vi.append(vi_sent)
                qn_cursor = next_qn_cursor
                continue

            if pending_vi:
                vi_sent = " ".join(pending_vi + [vi_sent])
                pending_vi = []

            if is_last and not ch_slice.strip() and pairs:
                # Nếu câu cuối bị hết chữ Nôm, gộp vào câu trước đó để không có hàng rỗng vế
                prev = pairs.pop()
                merged_vi = f"{prev.vi_txt} {vi_sent}".strip()
                pairs.append(
                    AlignedSentencePair(
                        img_id=prev.img_id,
                        sentence_id=prev.sentence_id,
                        ch_txt=prev.ch_txt,
                        vi_txt=merged_vi,
                        text_diff=compute_text_diff_levenshtein(
                            prev.ch_txt, merged_vi, self.dictionary_index
                        )
                        if self.dictionary_index is not None
                        else [],
                    )
                )
                break

            origin_img = ch_chars[min(ch_cursor, len(ch_chars) - 1)][1]
            ch_cursor = target_end
            qn_cursor = next_qn_cursor

            sent_num = sent_counter_per_img.get(origin_img, 0) + 1
            sent_counter_per_img[origin_img] = sent_num
            pairs.append(self.build_pair(origin_img, sent_num, ch_slice, vi_sent, is_phonetic=True))

        return pairs

    def align_page_sequence(
        self,
        page_entries: List[Tuple[str, List[str], List[str]]],
    ) -> List[AlignedSentencePair]:
        """
        Dóng hàng một chuỗi cặp trang liên tiếp theo thứ tự đọc của sách (`image_map.json`):
        - Khóa neo từng cặp trang bằng Levenshtein có trọng số từ điển để **chống trôi lệch (drift)**
          qua nhiều trang (kể cả khi trang bìa/mục lục đầu sách có độ dài chênh lệch).
        - Tự động gom các cặp trang liên tiếp khi cuối trang Quốc ngữ chưa kết thúc câu (ghép câu vắt trang
          và lấy `img_id` của trang bắt đầu câu theo v2.4/v2.6 Trang 14), giới hạn khối tối đa 4 trang
          để luôn tái khóa neo đều đặn.
        """
        pairs: List[AlignedSentencePair] = []
        sent_counter_per_img: Dict[str, int] = {}

        buf_ch: List[Tuple[str, str]] = []
        buf_vi: List[str] = []
        buf_pages = 0

        for idx, (img_id, ch_lines, vi_lines) in enumerate(page_entries):
            page_ch = clean_sinonom_text("".join(ch_lines))
            page_vi = merge_hyphenated_vi_lines(vi_lines)
            if not page_ch and not page_vi:
                continue

            for ch in page_ch:
                buf_ch.append((ch, img_id))
            if page_vi:
                buf_vi.append(page_vi)
            buf_pages += 1

            is_last_page = idx == len(page_entries) - 1
            # Kiểm tra trang Quốc ngữ hiện tại có kết thúc câu hay vắt sang trang sau
            ends_sentence = bool(re.search(r"[.!?\"”'»]\s*$", page_vi))
            # Trang có độ chênh lệch số chữ lớn (như trang bìa/mục lục) nên chốt riêng để không ảnh hưởng trang nội dung sau
            ch_cnt_p = len(tokenize_sinonom_with_spans(page_ch))
            vi_cnt_p = len(tokenize_quoc_ngu_with_spans(page_vi))
            is_divergent_page = abs(ch_cnt_p - vi_cnt_p) > max(20, int(0.25 * max(1, ch_cnt_p, vi_cnt_p)))

            if is_last_page or ends_sentence or is_divergent_page or buf_pages >= 4:
                if buf_ch and buf_vi:
                    pairs.extend(
                        self._split_chunk_into_sentence_pairs(
                            buf_ch, " ".join(buf_vi), sent_counter_per_img
                        )
                    )
                    buf_ch = []
                    buf_vi = []
                    buf_pages = 0

        return pairs
