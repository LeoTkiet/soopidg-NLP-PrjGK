"""
Bước 6 & 7: Xuất file <Tên sách>.csv, <Tên sách>.xlsx (tô màu theo text_diff)
và tính Độ tương đồng (%) theo đúng Quy định đồ án v2.4 (Trang 15 - 21, 25).

Cấu trúc cột v2.4:
- Có hình ảnh: img_id, sentence_id, ch_txt, vi_txt, text_diff
- Văn bản thuần: sentence_id, ch_txt, vi_txt

Công thức Đánh giá dữ liệu v2.4 (Trang 25):
    độ tương đồng (%) = (1 - (số chữ đỏ / số chữ Nôm tính điểm)) * 100
- Chỉ tính trên các hàng dịch âm (`text_diff` khác `null`).
- `số chữ đỏ`: tổng các phần tử `"error"` trong `text_diff`, mỗi phần tử lấy max(số chữ Nôm, số âm tiết Quốc ngữ).
- `số chữ Nôm tính điểm`: tổng số chữ Nôm của các hàng dịch âm, không tính dấu câu, `[MASK]` và chữ tô màu vàng (`"warn"`).
Yêu cầu: đạt tối thiểu 95% (>= 95%).
"""

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font

from src.step5_dictionary_loader import HanNomDictionaryIndex
from src.step6_text_cleaner_aligner import (
    AlignedSentencePair,
    compute_text_diff_levenshtein,
    tokenize_quoc_ngu_with_spans,
    tokenize_sinonom_with_spans,
)

# Ký tự dấu câu Hán Nôm và Quốc ngữ cần bỏ qua khi đếm chữ/âm tiết
PUNCTUATION_PATTERN = re.compile(r"[，。、！？；：「」『』（）\[\]\(\)\.,!\?;:\-\"'“”‘’…\s]+")

# Bảng mã màu RGB chuẩn theo Quy định đồ án v2.4 (Trang 15 & 19)
COLOR_BLACK_ARGB = "00000000"   # #000000
COLOR_RED_ARGB = "00FF0000"     # #FF0000 (Standard Excel Red)
COLOR_YELLOW_ARGB = "00D99A00"  # #D99A00 (Vàng cam dễ đọc, được chấp nhận chính thức ở v2.4 Trang 15 & 19)


def extract_sinonom_chars(text: str) -> List[str]:
    """Tách danh sách từng chữ Hán Nôm (bỏ qua dấu câu, khoảng trắng và [MASK])."""
    return [tok for tok, _, _ in tokenize_sinonom_with_spans(text)]


def extract_quoc_ngu_syllables(text: str) -> List[str]:
    """Tách danh sách từng âm tiết Quốc ngữ (tách cả dấu gạch ngang '-', bỏ qua [MASK])."""
    return [tok for tok, _, _ in tokenize_quoc_ngu_with_spans(text)]


def serialize_text_diff(text_diff: Optional[List[Dict[str, Any]]]) -> str:
    """
    Chuyển `text_diff` sang chuỗi lưu trong cột `text_diff` của file `.csv`/`.xlsx` (v2.4 Trang 15 & 17):
    - `None` -> chuỗi đúng 4 ký tự `"null"` (không để ô trống).
    - `[]` hoặc danh sách phần tử -> chuỗi JSON UTF-8 chuẩn (dấu phẩy, khóa nháy kép).
    """
    if text_diff is None:
        return "null"
    return json.dumps(text_diff, ensure_ascii=False, separators=(",", ":"))


def _build_rich_text_from_spans(
    text: str,
    colored_spans: List[Tuple[int, int, str]],
) -> Any:
    """
    Tạo `CellRichText` từ chuỗi NFC gốc và danh sách khoảng tô màu `(start, end, type)`.
    Giữ nguyên 100% văn bản gốc (kể cả dấu câu, khoảng trắng, dấu gạch ngang) và tô màu chính xác
    theo khoảng nửa mở [start, end) trong `text_diff` (v2.4 Trang 18).
    """
    text_nfc = unicodedata.normalize("NFC", text)
    if not colored_spans:
        return text_nfc

    font_black = InlineFont(color=COLOR_BLACK_ARGB)
    font_red = InlineFont(color=COLOR_RED_ARGB)
    font_yellow = InlineFont(color=COLOR_YELLOW_ARGB)

    spans_sorted = sorted(colored_spans, key=lambda x: (x[0], x[1]))
    rich = CellRichText()
    cursor = 0
    n = len(text_nfc)

    for start, end, diff_type in spans_sorted:
        s = max(cursor, min(start, n))
        e = max(s, min(end, n))
        if s > cursor:
            rich.append(TextBlock(font_black, text_nfc[cursor:s]))
        if e > s:
            fnt = font_red if diff_type == "error" else font_yellow
            rich.append(TextBlock(fnt, text_nfc[s:e]))
        cursor = e

    if cursor < n:
        rich.append(TextBlock(font_black, text_nfc[cursor:]))

    return rich


def evaluate_pairs_v24(pairs: List[AlignedSentencePair]) -> Dict[str, Any]:
    """
    Tính toán đầy đủ các chỉ số đánh giá theo đúng Quy định đồ án v2.4 (Trang 23 & 25):
    - `similarity_percent = (1 - red_chars / scored_nom_chars) * 100`
    - Thống kê số chữ vàng, tỷ lệ chữ vàng, số hàng null, tỷ lệ hàng null, số phần tử reviewed/unreviewed.
    """
    total_rows = len(pairs)
    null_rows = 0
    total_nom_chars = 0
    warn_nom_chars = 0
    red_chars = 0
    warn_reviewed = 0
    warn_unreviewed = 0

    for p in pairs:
        if p.text_diff is None:
            null_rows += 1
            continue

        row_nom_count = len(extract_sinonom_chars(p.ch_txt))
        total_nom_chars += row_nom_count

        for item in p.text_diff:
            dtype = item.get("type")
            nom_c = len(extract_sinonom_chars(item.get("nom_sub_text", "")))
            vi_c = len(extract_quoc_ngu_syllables(item.get("vi_sub_text", "")))
            if dtype == "error":
                red_chars += max(nom_c, vi_c)
            elif dtype == "warn":
                warn_nom_chars += nom_c
                if item.get("reviewed") == 1:
                    warn_reviewed += 1
                else:
                    warn_unreviewed += 1

    scored_nom_chars = max(0, total_nom_chars - warn_nom_chars)
    black_chars = max(0, scored_nom_chars - red_chars)
    similarity = (
        (1.0 - (red_chars / scored_nom_chars)) * 100.0 if scored_nom_chars > 0 else 0.0
    )
    warn_ratio = (warn_nom_chars / total_nom_chars) * 100.0 if total_nom_chars > 0 else 0.0
    null_ratio = (null_rows / total_rows) * 100.0 if total_rows > 0 else 0.0

    return {
        "total_rows": total_rows,
        "null_rows": null_rows,
        "null_ratio_percent": round(null_ratio, 2),
        "total_chars": total_nom_chars,
        "scored_nom_chars": scored_nom_chars,
        "black_chars": black_chars,
        "red_chars": red_chars,
        "warn_chars": warn_nom_chars,
        "warn_ratio_percent": round(warn_ratio, 2),
        "warn_reviewed": warn_reviewed,
        "warn_unreviewed": warn_unreviewed,
        "similarity_percent": round(similarity, 2),
        "passed_95_threshold": similarity >= 95.0,
    }


def export_aligned_csv(
    pairs: List[AlignedSentencePair],
    csv_path: Path,
    is_pure_text: bool = False,
) -> None:
    """
    Xuất file `<Tên sách>.csv` theo cấu trúc Quy định đồ án v2.4 (Trang 15 & Trang 30):
    - Có hình ảnh: `img_id, sentence_id, ch_txt, vi_txt, text_diff`
    - Văn bản thuần: `sentence_id, ch_txt, vi_txt`
    Lưu UTF-8 có BOM (`utf-8-sig`) để mở bình thường bằng Excel và Google Sheets.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    headers = (
        ["sentence_id", "ch_txt", "vi_txt"]
        if is_pure_text
        else ["img_id", "sentence_id", "ch_txt", "vi_txt", "text_diff"]
    )
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for p in pairs:
            ch_nfc = unicodedata.normalize("NFC", p.ch_txt)
            vi_nfc = unicodedata.normalize("NFC", p.vi_txt)
            if is_pure_text:
                writer.writerow([p.sentence_id, ch_nfc, vi_nfc])
            else:
                writer.writerow(
                    [
                        p.img_id,
                        p.sentence_id,
                        ch_nfc,
                        vi_nfc,
                        serialize_text_diff(p.text_diff),
                    ]
                )


def export_aligned_xlsx_and_evaluate(
    pairs: List[AlignedSentencePair],
    xlsx_path: Path,
    dict_index: Optional[HanNomDictionaryIndex] = None,
    is_pure_text: bool = False,
) -> Dict[str, Any]:
    """
    Xuất file `<Tên sách>.xlsx` chuẩn v2.4 (Trang 15 - 21) với màu chữ khớp 100% với cột `text_diff`:
    - Nếu `p.text_diff` chưa được tính và `dict_index` được truyền vào, tự động tính bằng Levenshtein.
    - Màu đen (`000000`), màu đỏ (`FF0000`), màu vàng (`D99A00`).
    Đồng thời tính và trả về báo cáo độ tương đồng theo công thức v2.4 Trang 25.
    """
    # Đảm bảo text_diff đã sẵn sàng trước khi tô màu
    for p in pairs:
        if not is_pure_text and p.text_diff is None and dict_index is not None:
            p.text_diff = compute_text_diff_levenshtein(p.ch_txt, p.vi_txt, dict_index)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Aligned_Data"

    headers = (
        ["sentence_id", "ch_txt", "vi_txt"]
        if is_pure_text
        else ["img_id", "sentence_id", "ch_txt", "vi_txt", "text_diff"]
    )
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color=COLOR_BLACK_ARGB)

    for p in pairs:
        ch_nfc = unicodedata.normalize("NFC", p.ch_txt)
        vi_nfc = unicodedata.normalize("NFC", p.vi_txt)

        if is_pure_text:
            ws.append([p.sentence_id, ch_nfc, vi_nfc])
            continue

        nom_spans: List[Tuple[int, int, str]] = []
        vi_spans: List[Tuple[int, int, str]] = []
        if p.text_diff:
            for item in p.text_diff:
                dtype = item.get("type", "error")
                for s, e in item.get("nom_pos", []):
                    nom_spans.append((int(s), int(e), dtype))
                for s, e in item.get("vi_pos", []):
                    vi_spans.append((int(s), int(e), dtype))

        ch_cell_val = _build_rich_text_from_spans(ch_nfc, nom_spans)
        vi_cell_val = _build_rich_text_from_spans(vi_nfc, vi_spans)
        ws.append(
            [
                p.img_id,
                p.sentence_id,
                ch_cell_val,
                vi_cell_val,
                serialize_text_diff(p.text_diff),
            ]
        )

    # Định dạng độ rộng cột và wrap text để mở đẹp trên Excel / Google Sheets
    col_widths = {"A": 42, "B": 44, "C": 52, "D": 64, "E": 48}
    for col_letter, width in col_widths.items():
        if col_letter <= chr(ord("A") + len(headers) - 1):
            ws.column_dimensions[col_letter].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    wb.save(str(xlsx_path))
    return evaluate_pairs_v24(pairs)
