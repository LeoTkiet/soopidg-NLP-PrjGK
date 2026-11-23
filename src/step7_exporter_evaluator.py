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
    SinoNomAligner,
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


def load_ppocr_label_file(label_path: Path) -> Dict[str, List[Dict[str, Any]]]:
    """Đọc file `Label.txt` chuẩn PPOCRLabel thành dict `{image_filename: [boxes...]}`."""
    label_map: Dict[str, List[Dict[str, Any]]] = {}
    if not label_path.exists():
        return label_map
    for line in label_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or "\t" not in line:
            continue
        rel_path, raw_json = line.split("\t", 1)
        img_name = rel_path.split("/", 1)[-1]
        try:
            label_map[img_name] = json.loads(raw_json)
        except Exception:
            continue
    return label_map


def load_aligned_csv(csv_path: Path) -> List[AlignedSentencePair]:
    """Đọc file `<Tên sách>.csv` chuẩn v2.4 (5 cột) thành danh sách `AlignedSentencePair`."""
    pairs: List[AlignedSentencePair] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            raw_diff = (row.get("text_diff") or "").strip()
            parsed_diff: Optional[List[Dict[str, Any]]]
            if raw_diff == "null" or not raw_diff:
                parsed_diff = None
            else:
                try:
                    parsed_diff = json.loads(raw_diff)
                except Exception:
                    parsed_diff = []
            pairs.append(
                AlignedSentencePair(
                    img_id=(row.get("img_id") or "").strip(),
                    sentence_id=(row.get("sentence_id") or "").strip(),
                    ch_txt=unicodedata.normalize("NFC", row.get("ch_txt") or ""),
                    vi_txt=unicodedata.normalize("NFC", row.get("vi_txt") or ""),
                    text_diff=parsed_diff,
                )
            )
    return pairs


def export_red_error_report(
    pairs: List[AlignedSentencePair],
    report_path: Path,
) -> int:
    """
    Xuất danh sách toàn bộ các chữ tô màu đỏ (`type == 'error'`) ra file CSV riêng
    (`cache/reports/<Tên sách>_red_report.csv`) để nhóm rà soát sửa lỗi OCR nhanh chóng.
    Trả về tổng số phần tử lỗi đã ghi.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    error_count = 0
    with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["img_id", "sentence_id", "nom_sub_text", "vi_sub_text", "ch_txt", "vi_txt"]
        )
        for p in pairs:
            if not p.text_diff:
                continue
            for item in p.text_diff:
                if item.get("type") == "error":
                    writer.writerow(
                        [
                            p.img_id,
                            p.sentence_id,
                            item.get("nom_sub_text", ""),
                            item.get("vi_sub_text", ""),
                            p.ch_txt,
                            p.vi_txt,
                        ]
                    )
                    error_count += 1
    return error_count


def _load_dictionary_from_cfg(cfg: Dict[str, Any]) -> HanNomDictionaryIndex:
    """Nạp chỉ mục từ điển Hán Nôm từ cache `.pkl` theo cấu hình `config.yaml`."""
    entries_dir = Path(cfg["paths"]["dictionary_entries_dir"])
    cache_path = Path(cfg["paths"]["cache_dir"]) / "dict_index.pkl"
    sources = (
        cfg.get("dictionaries", {}).get("primary_sources", [])
        + cfg.get("dictionaries", {}).get("variant_sources", [])
    )
    dict_index = HanNomDictionaryIndex(entries_dir=entries_dir)
    from_cache = dict_index.load_or_build_cache(sources, cache_path=cache_path)
    print(
        f"- Từ điển Hán Nôm: {'nạp từ cache ' + cache_path.name if from_cache else 'đã xây dựng mới ' + cache_path.name}"
    )
    return dict_index


def _print_eval_summary(book_id: str, book_name: str, report: Dict[str, Any], red_report_path: Path, n_red_items: int) -> None:
    status = "ĐẠT (>= 95%)" if report["passed_95_threshold"] else "CHƯA ĐẠT (< 95%)"
    print(
        f"  + [{book_id}] {book_name}:\n"
        f"      Câu dóng hàng : {report['total_rows']} câu (hàng null: {report['null_rows']} - {report['null_ratio_percent']}%)\n"
        f"      Chữ tính điểm : {report['scored_nom_chars']} | Đen: {report['black_chars']} | "
        f"Đỏ: {report['red_chars']} | Vàng: {report['warn_chars']} ({report['warn_ratio_percent']}%)\n"
        f"      Độ tương đồng : {report['similarity_percent']}% -> {status}\n"
        f"      Báo cáo chữ đỏ: {red_report_path} ({n_red_items} mục cần rà soát)"
    )


def run_align_pipeline(
    cfg: Dict[str, Any],
    book_filter: Optional[str] = None,
) -> None:
    """
    Đọc `ch/Label.txt`, `vi/Label.txt` và `<Tên sách>_image_map.json`, chạy dóng hàng Levenshtein
    (`SinoNomAligner`), xuất `<Tên sách>.csv`, `<Tên sách>.xlsx` (tô màu chuẩn v2.4)
    và báo cáo danh sách chữ đỏ `cache/reports/<Tên sách>_red_report.csv`.
    """
    out_root = Path(cfg["paths"]["output_dir"])
    cache_root = Path(cfg["paths"]["cache_dir"])
    print("=== DÓNG HÀNG SONG NGỮ & XUẤT CSV/XLSX CHUẨN v2.4 (--step align) ===")
    dict_index = _load_dictionary_from_cfg(cfg)
    aligner = SinoNomAligner(dictionary_index=dict_index)

    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        book_name = Path(fname).stem
        if book_filter and book_filter not in (book_id, fname, book_name):
            continue

        book_dir = out_root / book_name
        ch_labels = load_ppocr_label_file(book_dir / "ch" / "Label.txt")
        vi_labels = load_ppocr_label_file(book_dir / "vi" / "Label.txt")
        if not ch_labels or not vi_labels:
            print(
                f"  [BỎ QUA] [{book_id}] {book_name}: Thiếu ch/Label.txt ({len(ch_labels)} trang) "
                f"hoặc vi/Label.txt ({len(vi_labels)} trang)."
            )
            continue

        map_path = book_dir / f"{book_name}_image_map.json"
        if not map_path.exists():
            print(
                f"  [LỖI] [{book_id}] {book_name}: Không tìm thấy {map_path.name}. "
                "Hãy chạy `python main.py --step image-map` trước!"
            )
            continue

        image_map = json.loads(map_path.read_text(encoding="utf-8"))
        page_entries: List[Tuple[str, List[str], List[str]]] = []
        skipped_pairs = 0
        for pr in image_map.get("pairs", []):
            ch_list = pr.get("ch", [])
            vi_list = pr.get("vi", [])
            if not ch_list or not vi_list:
                skipped_pairs += 1
                continue
            if all(fn in ch_labels for fn in ch_list) and all(fn in vi_labels for fn in vi_list):
                ch_lines = [
                    str(box.get("transcription", "")).strip()
                    for fn in ch_list
                    for box in ch_labels[fn]
                    if str(box.get("transcription", "")).strip()
                ]
                vi_lines = [
                    str(box.get("transcription", "")).strip()
                    for fn in vi_list
                    for box in vi_labels[fn]
                    if str(box.get("transcription", "")).strip()
                ]
                if ch_lines and vi_lines:
                    page_entries.append((ch_list[0], ch_lines, vi_lines))
                else:
                    skipped_pairs += 1
            else:
                skipped_pairs += 1

        if not page_entries:
            print(
                f"  [BỎ QUA] [{book_id}] {book_name}: Chưa có cặp trang nào đủ cả ch/Label.txt và vi/Label.txt."
            )
            continue

        if skipped_pairs > 0:
            print(
                f"  [Lưu ý] [{book_id}] Đang dóng hàng {len(page_entries)} cặp trang đã có OCR "
                f"(bỏ qua {skipped_pairs} cặp chưa OCR đủ 2 vế)."
            )

        pairs = aligner.align_page_sequence(page_entries)
        csv_path = book_dir / f"{book_name}.csv"
        xlsx_path = book_dir / f"{book_name}.xlsx"
        export_aligned_csv(pairs, csv_path, is_pure_text=False)
        report = export_aligned_xlsx_and_evaluate(pairs, xlsx_path, dict_index, is_pure_text=False)

        red_report_path = cache_root / "reports" / f"{book_name}_red_report.csv"
        n_red_items = export_red_error_report(pairs, red_report_path)
        _print_eval_summary(book_id, book_name, report, red_report_path, n_red_items)


def run_evaluate_pipeline(
    cfg: Dict[str, Any],
    book_filter: Optional[str] = None,
    keep_diff: bool = False,
) -> None:
    """
    Đọc `<Tên sách>.csv` hiện có (thường sau khi thành viên đã sửa lỗi chính tả/OCR),
    tính lại `text_diff` bằng Levenshtein (trừ khi `keep_diff=True`), cập nhật lại `.csv` & `.xlsx`
    tô màu chuẩn v2.4, xuất báo cáo chữ đỏ và in kết quả đánh giá độ tương đồng (>= 95%).
    """
    out_root = Path(cfg["paths"]["output_dir"])
    cache_root = Path(cfg["paths"]["cache_dir"])
    mode_str = "giữ nguyên text_diff trong CSV" if keep_diff else "tính lại text_diff bằng Levenshtein + từ điển"
    print(f"=== ĐÁNH GIÁ ĐỘ TƯƠNG ĐỒNG & TÔ MÀU XLSX CHUẨN v2.4 (--step evaluate | {mode_str}) ===")
    dict_index = None if keep_diff else _load_dictionary_from_cfg(cfg)

    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        book_name = Path(fname).stem
        if book_filter and book_filter not in (book_id, fname, book_name):
            continue

        book_dir = out_root / book_name
        csv_path = book_dir / f"{book_name}.csv"
        if not csv_path.exists():
            print(f"  [BỎ QUA] [{book_id}] {book_name}: Chưa có file {csv_path.name}. Hãy chạy --step align trước!")
            continue

        pairs = load_aligned_csv(csv_path)
        if not keep_diff and dict_index is not None:
            for p in pairs:
                if p.text_diff is not None:
                    p.text_diff = compute_text_diff_levenshtein(p.ch_txt, p.vi_txt, dict_index)
            export_aligned_csv(pairs, csv_path, is_pure_text=False)

        xlsx_path = book_dir / f"{book_name}.xlsx"
        report = export_aligned_xlsx_and_evaluate(pairs, xlsx_path, dict_index=None, is_pure_text=False)
        red_report_path = cache_root / "reports" / f"{book_name}_red_report.csv"
        n_red_items = export_red_error_report(pairs, red_report_path)
        _print_eval_summary(book_id, book_name, report, red_report_path, n_red_items)
