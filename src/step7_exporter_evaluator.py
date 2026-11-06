"""
Bước 6 & 7: Xuất file <Tên sách>.csv, <Tên sách>.xlsx (có tô màu từng chữ đen/đỏ)
và tính Độ tương đồng (%) theo đúng Quy định đồ án (Trang 8, 9, 10).

Công thức Đánh giá dữ liệu (Trang 10):
    độ tương đồng (%) = (1 - (tổng số chữ không tương đồng (chữ đỏ) / tổng số chữ)) * 100
Yêu cầu: đạt tối thiểu 95% (>= 95%).
"""

import csv
import re
from pathlib import Path
from typing import Dict, List, Tuple

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont

from src.step5_dictionary_loader import HanNomDictionaryIndex
from src.step6_text_cleaner_aligner import AlignedSentencePair

# Ký tự dấu câu Hán Nôm và Quốc ngữ cần bỏ qua khi đối chiếu từng chữ
PUNCTUATION_PATTERN = re.compile(r"[，。、！？；：「」『』（）\[\]\(\)\.,!\?;:\-\"'“”‘’…\s]+")


def extract_sinonom_chars(text: str) -> List[str]:
    """Tách danh sách từng chữ Hán Nôm (bỏ qua dấu câu và khoảng trắng)."""
    return [ch for ch in text if not PUNCTUATION_PATTERN.match(ch)]


def extract_quoc_ngu_syllables(text: str) -> List[str]:
    """Tách danh sách các âm tiết Quốc ngữ (loại bỏ dấu câu dính kèm)."""
    raw_tokens = text.strip().split()
    syllables = []
    for tok in raw_tokens:
        clean_tok = PUNCTUATION_PATTERN.sub("", tok)
        if clean_tok:
            syllables.append(clean_tok)
    return syllables


def export_aligned_csv(
    pairs: List[AlignedSentencePair],
    csv_path: Path,
    is_pure_text: bool = False,
) -> None:
    """
    Xuất file <Tên sách>.csv theo cấu trúc quy định (Trang 8 & Trang 16):
    - Có hình ảnh: img_id, sentence_id, SinoNom_Char, ChuQN_txt
    - Văn bản thuần: sentence_id, SinoNom_Char, ChuQN_txt
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = (
        ["sentence_id", "SinoNom_Char", "ChuQN_txt"]
        if is_pure_text
        else ["img_id", "sentence_id", "SinoNom_Char", "ChuQN_txt"]
    )
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in pairs:
            if is_pure_text:
                writer.writerow([p.sentence_id, p.sino_nom_char, p.chu_qn_txt])
            else:
                writer.writerow([p.img_id, p.sentence_id, p.sino_nom_char, p.chu_qn_txt])


def export_aligned_xlsx_and_evaluate(
    pairs: List[AlignedSentencePair],
    xlsx_path: Path,
    dict_index: HanNomDictionaryIndex,
    is_pure_text: bool = False,
) -> Dict[str, float]:
    """
    Xuất file <Tên sách>.xlsx với RichText tô màu từng chữ:
    - Màu đen (#000000): Chữ Nôm và chữ Quốc ngữ giống nhau về nghĩa/âm trong từ điển.
    - Màu đỏ (#FF0000): Chữ Nôm và chữ Quốc ngữ khác nhau hoặc không có trong từ điển.
    Đồng thời tính toán và trả về báo cáo độ tương đồng (%).
    """
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Aligned_Data"

    headers = (
        ["sentence_id", "SinoNom_Char", "ChuQN_txt"]
        if is_pure_text
        else ["img_id", "sentence_id", "SinoNom_Char", "ChuQN_txt"]
    )
    ws.append(headers)

    font_black = InlineFont(color="00000000")
    font_red = InlineFont(color="00FF0000")

    total_chars = 0
    red_chars = 0

    for p in pairs:
        sn_chars = extract_sinonom_chars(p.sino_nom_char)
        qn_words = extract_quoc_ngu_syllables(p.chu_qn_txt)

        sn_rich = CellRichText()
        qn_rich = CellRichText()

        max_len = max(len(sn_chars), len(qn_words))
        for idx in range(max_len):
            sn_c = sn_chars[idx] if idx < len(sn_chars) else ""
            qn_w = qn_words[idx] if idx < len(qn_words) else ""

            matched = bool(sn_c and qn_w and dict_index.is_match(sn_c, qn_w))
            total_chars += 1
            if not matched:
                red_chars += 1

            color_font = font_black if matched else font_red
            if sn_c:
                sn_rich.append(TextBlock(color_font, sn_c))
            if qn_w:
                prefix = " " if idx > 0 else ""
                qn_rich.append(TextBlock(color_font, f"{prefix}{qn_w}"))

        if is_pure_text:
            ws.append([p.sentence_id, sn_rich, qn_rich])
        else:
            ws.append([p.img_id, p.sentence_id, sn_rich, qn_rich])

    wb.save(str(xlsx_path))

    similarity = (1.0 - (red_chars / total_chars)) * 100.0 if total_chars > 0 else 0.0
    return {
        "total_chars": total_chars,
        "red_chars": red_chars,
        "black_chars": total_chars - red_chars,
        "similarity_percent": round(similarity, 2),
        "passed_95_threshold": similarity >= 95.0,
    }

