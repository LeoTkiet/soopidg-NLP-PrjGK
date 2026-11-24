"""
Bước 8: Bộ kiểm tra tự động bắt buộc trước khi nộp (Mandatory Automated Validator)
và đóng gói file ZIP theo đúng Quy định đồ án v2.4 (Trang 6, 10, 14, 15 - 19, 25).

Các hạng mục kiểm tra tự động bắt buộc (v2.4):
1. File ảnh & PPOCRLabel (`ch/Label.txt`, `ch/fileState.txt`, `vi/Label.txt`, `vi/fileState.txt`):
   - Mỗi box có đúng 4 điểm, mọi dòng `fileState.txt` là `1`, mọi ảnh trong thư mục đều có nhãn.
2. File ánh xạ ảnh `<Tên sách>_image_map.json` (nếu có):
   - JSON hợp lệ, mọi tên ảnh tồn tại, không trùng tên trong cùng 1 vế, không có cặp nào cả 2 vế đều rỗng.
3. File dóng hàng `<Tên sách>.csv`:
   - Đúng 5 cột `img_id, sentence_id, ch_txt, vi_txt, text_diff`, mỗi hàng đều có `ch_txt` và `vi_txt` khác rỗng.
   - Không có ký tự chọn dạng (Variation Selectors) trong `ch_txt`, chuẩn hóa NFC.
   - `text_diff` là JSON hợp lệ hoặc `"null"`: `nom_sub_text`/`vi_sub_text` khớp tuyệt đối lát cắt theo `pos`,
     các khoảng không chồng nhau và không vượt độ dài chuỗi, `reviewed` chỉ có trên `"warn"` (0 hoặc 1),
     KHÔNG còn phần tử `"warn"` nào có trường `"suggest"` khi nộp.
4. Đồng bộ `Label.txt` <-> `.csv`:
   - Chuỗi nối `transcription` trong `Label.txt` khớp với chuỗi nối trong `.csv`
     (bỏ qua khoảng trắng, và với Quốc ngữ bỏ qua dấu gạch ngang `-`).
5. Đồng bộ `.xlsx` <-> `.csv` (`text_diff` và bảng mã màu chuẩn Excel v2.4):
   - Mã màu chỉ thuộc `{000000, FF0000, D32F2F, FFFF00, D99A00}`.
   - Từng ký tự trong `ch_txt` và `vi_txt` của `.xlsx` có màu khớp tuyệt đối với `text_diff`.
6. Đánh giá độ tương đồng v2.4 (>= 95%).
"""

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
from openpyxl.cell.rich_text import CellRichText

from src.step6_text_cleaner_aligner import (
    AlignedSentencePair,
    PUA_CHAR_PATTERN,
    VARIATION_SELECTOR_PATTERN,
)
from src.step7_exporter_evaluator import evaluate_pairs_v24

ALLOWED_RED_RGB = {"FF0000", "D32F2F"}
ALLOWED_YELLOW_RGB = {"FFFF00", "D99A00"}
ALLOWED_BLACK_RGB = {"000000", ""}


def _extract_rgb6(color_obj: Any) -> str:
    """Trích xuất mã màu RGB 6 ký tự hex viết hoa từ đối tượng Color của openpyxl."""
    if color_obj is None:
        return "000000"
    rgb = getattr(color_obj, "rgb", None)
    if not isinstance(rgb, str) or not rgb:
        return "000000"
    rgb = rgb.upper()
    if len(rgb) == 8:
        return rgb[2:]
    if len(rgb) == 6:
        return rgb
    return "000000"


def _cell_to_text_and_colors(cell_val: Any) -> Tuple[str, List[str]]:
    """Tách nội dung 1 ô `.xlsx` thành chuỗi văn bản và mảng mã màu RGB6 cho từng ký tự."""
    if cell_val is None:
        return "", []
    if isinstance(cell_val, CellRichText):
        chars: List[str] = []
        colors: List[str] = []
        for block in cell_val:
            if isinstance(block, str):
                chars.append(block)
                colors.extend(["000000"] * len(block))
            else:
                txt = block.text or ""
                rgb6 = _extract_rgb6(block.font.color if block.font else None)
                chars.append(txt)
                colors.extend([rgb6] * len(txt))
        return "".join(chars), colors
    s = str(cell_val)
    return s, ["000000"] * len(s)


def _validate_ppocr_folder(folder_dir: Path, errors: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Kiểm tra cặp file `Label.txt` & `fileState.txt` trong thư mục `ch/` hoặc `vi/`."""
    folder_name = folder_dir.name
    label_path = folder_dir / "Label.txt"
    state_path = folder_dir / "fileState.txt"
    jpg_files = {p.name for p in folder_dir.glob("*.jpg")}

    if not label_path.exists():
        errors.append(f"Thiếu file bắt buộc: {label_path}")
        return {}
    if not state_path.exists():
        errors.append(f"Thiếu file bắt buộc: {state_path}")
        return {}

    label_map: Dict[str, List[Dict[str, Any]]] = {}
    for ln_no, line in enumerate(label_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            errors.append(f"{folder_name}/Label.txt dòng {ln_no}: thiếu ký tự TAB ngăn cách.")
            continue
        rel_path, raw_json = parts
        if not rel_path.startswith(f"{folder_name}/"):
            errors.append(f"{folder_name}/Label.txt dòng {ln_no}: đường dẫn '{rel_path}' sai tiền tố thư mục.")
        img_name = rel_path.split("/", 1)[-1]
        try:
            boxes = json.loads(raw_json)
        except Exception as exc:
            errors.append(f"{folder_name}/Label.txt dòng {ln_no}: JSON không hợp lệ ({exc}).")
            continue
        for b_idx, b in enumerate(boxes):
            pts = b.get("points")
            if "transcription" not in b or not isinstance(pts, list) or len(pts) != 4:
                errors.append(
                    f"{folder_name}/Label.txt dòng {ln_no} box #{b_idx + 1}: phải có transcription và đúng 4 điểm."
                )
        label_map[img_name] = boxes

    state_map: Dict[str, str] = {}
    for ln_no, line in enumerate(state_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            errors.append(f"{folder_name}/fileState.txt dòng {ln_no}: sai định dạng TAB.")
            continue
        img_name = parts[0].split("/", 1)[-1]
        state_val = parts[1].strip()
        if state_val != "1":
            errors.append(f"{folder_name}/fileState.txt dòng {ln_no}: trạng thái phải là '1' (hiện tại '{state_val}').")
        state_map[img_name] = state_val

    missing_in_label = jpg_files - set(label_map.keys())
    if missing_in_label:
        errors.append(f"{folder_name}/Label.txt thiếu nhãn cho {len(missing_in_label)} ảnh: {sorted(missing_in_label)[:3]}")
    missing_in_state = jpg_files - set(state_map.keys())
    if missing_in_state:
        errors.append(f"{folder_name}/fileState.txt thiếu trạng thái cho {len(missing_in_state)} ảnh.")

    return label_map


def _validate_image_map(book_dir: Path, book_name: str, errors: List[str]) -> Optional[Dict[str, Any]]:
    """Kiểm tra file `<Tên sách>_image_map.json` theo v2.4 Trang 10."""
    map_path = book_dir / f"{book_name}_image_map.json"
    if not map_path.exists():
        return None
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{map_path.name}: JSON không hợp lệ ({exc}).")
        return None

    pairs = data.get("pairs")
    if not isinstance(pairs, list):
        errors.append(f"{map_path.name}: thiếu mảng 'pairs'.")
        return None

    seen_ch = set()
    seen_vi = set()
    for idx, pair in enumerate(pairs, start=1):
        ch_list = pair.get("ch", [])
        vi_list = pair.get("vi", [])
        if not ch_list and not vi_list:
            errors.append(f"{map_path.name} cặp #{idx}: cả hai vế ch và vi đều rỗng.")
        for fname in ch_list:
            if fname in seen_ch:
                errors.append(f"{map_path.name}: ảnh ch trùng lặp '{fname}'.")
            seen_ch.add(fname)
            if not (book_dir / "ch" / fname).exists() and not (book_dir / "missing" / "ch" / fname).exists():
                errors.append(f"{map_path.name}: không tìm thấy ảnh ch '{fname}'.")
        for fname in vi_list:
            if fname in seen_vi:
                errors.append(f"{map_path.name}: ảnh vi trùng lặp '{fname}'.")
            seen_vi.add(fname)
            if not (book_dir / "vi" / fname).exists() and not (book_dir / "missing" / "vi" / fname).exists():
                errors.append(f"{map_path.name}: không tìm thấy ảnh vi '{fname}'.")
    return data


def _validate_spans(
    text: str,
    pos_list: List[List[int]],
    sub_text: str,
    side_label: str,
    row_ref: str,
    used_indices: set,
    errors: List[str],
) -> None:
    """Kiểm tra pos hợp lệ, không vượt biên, không chồng nhau và cắt đúng sub_text."""
    sliced_parts: List[str] = []
    n = len(text)
    for span in pos_list:
        if not isinstance(span, list) or len(span) != 2:
            errors.append(f"{row_ref} ({side_label}): span không hợp lệ {span}.")
            continue
        s, e = int(span[0]), int(span[1])
        if s < 0 or e > n or s >= e:
            errors.append(f"{row_ref} ({side_label}): span [{s}, {e}) vượt ngoài độ dài {n}.")
            continue
        for idx in range(s, e):
            if idx in used_indices:
                errors.append(f"{row_ref} ({side_label}): vị trí ký tự {idx} bị chồng lấn giữa các phần tử text_diff.")
                break
            used_indices.add(idx)
        sliced_parts.append(text[s:e])

    joined = "".join(sliced_parts)
    if joined != sub_text:
        errors.append(
            f"{row_ref} ({side_label}): sub_text='{sub_text}' không khớp chuỗi cắt theo pos '{joined}'."
        )


def _validate_placeholder_map_v26(
    book_dir: Path,
    book_name: str,
    ch_labels: Dict[str, List[Dict[str, Any]]],
    pairs: List[AlignedSentencePair],
    errors: List[str],
) -> None:
    """
    Kiểm tra 7 ràng buộc bắt buộc của `<Tên sách>_placeholder_map.json` theo Quy định đồ án v2.6 (Trang 14).
    """
    map_path = book_dir / f"{book_name}_placeholder_map.json"
    if not map_path.exists():
        return
    try:
        data = json.loads(map_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{map_path.name}: JSON không hợp lệ ({exc}).")
        return

    placeholders = data.get("placeholders")
    if not isinstance(placeholders, list):
        errors.append(f"{map_path.name}: thiếu mảng 'placeholders'.")
        return

    pair_by_id = {p.sentence_id: p for p in pairs}
    seen_lbl: set = set()
    seen_aln: set = set()
    n_lbl_entries = 0
    n_aln_entries = 0

    for idx, item in enumerate(placeholders, start=1):
        lbl = item.get("label")
        aln = item.get("align")
        if lbl is None and aln is None:
            errors.append(f"{map_path.name} mục #{idx}: cả label và align đều null.")
            continue

        if lbl is not None:
            n_lbl_entries += 1
            fn = lbl.get("img_id", "")
            bi = int(lbl.get("box_index", -1))
            pos = int(lbl.get("pos", -1))
            key = (fn, bi, pos)
            if key in seen_lbl:
                errors.append(f"{map_path.name} mục #{idx}: trùng vị trí label {key}.")
            seen_lbl.add(key)
            boxes = ch_labels.get(fn, [])
            if bi < 0 or bi >= len(boxes):
                errors.append(f"{map_path.name} mục #{idx}: box_index={bi} vượt biên ảnh {fn}.")
            else:
                txt = unicodedata.normalize("NFC", str(boxes[bi].get("transcription", "")))
                if pos < 0 or pos >= len(txt) or txt[pos] != "\u3013":
                    errors.append(f"{map_path.name} mục #{idx}: ch/Label.txt {key} không phải ký tự 〓.")

        if aln is not None:
            n_aln_entries += 1
            sid = aln.get("sentence_id", "")
            pos = int(aln.get("pos", -1))
            key = (sid, pos)
            if key in seen_aln:
                errors.append(f"{map_path.name} mục #{idx}: trùng vị trí align {key}.")
            seen_aln.add(key)
            p = pair_by_id.get(sid)
            if p is None:
                errors.append(f"{map_path.name} mục #{idx}: không tìm thấy sentence_id '{sid}'.")
            else:
                txt = unicodedata.normalize("NFC", p.ch_txt)
                if pos < 0 or pos >= len(txt) or txt[pos] != "\u3013":
                    errors.append(f"{map_path.name} mục #{idx}: ch_txt {key} không phải ký tự 〓.")
                elif p.text_diff is not None:
                    covered = any(
                        it.get("type") == "error"
                        and any(int(s) <= pos < int(e) for s, e in it.get("nom_pos", []))
                        for it in p.text_diff
                    )
                    if not covered:
                        errors.append(f"{map_path.name} mục #{idx}: vị trí 〓 {key} chưa có phần tử 'error' phủ trong text_diff.")

        uni = item.get("unicode")
        if uni is not None:
            m = re.fullmatch(r"U\+([0-9A-F]{4,6})", str(uni))
            if not m:
                errors.append(f"{map_path.name} mục #{idx}: unicode='{uni}' sai định dạng U+XXXX.")
            else:
                cp = int(m.group(1), 16)
                if cp == 0x3013 or PUA_CHAR_PATTERN.match(chr(cp)) or VARIATION_SELECTOR_PATTERN.match(chr(cp)):
                    errors.append(f"{map_path.name} mục #{idx}: unicode='{uni}' không hợp lệ (U+3013 / PUA / VS).")

        ids_val = item.get("ids")
        if ids_val is not None:
            if "\u3013" in ids_val or PUA_CHAR_PATTERN.search(ids_val):
                errors.append(f"{map_path.name} mục #{idx}: trường ids không được chứa 〓 hoặc PUA.")

    # Kiểm tra đủ số lượng 〓
    total_lbl_ph = sum(
        unicodedata.normalize("NFC", str(b.get("transcription", ""))).count("\u3013")
        for boxes in ch_labels.values()
        for b in boxes
    )
    total_aln_ph = sum(unicodedata.normalize("NFC", p.ch_txt).count("\u3013") for p in pairs)
    if n_lbl_entries != total_lbl_ph:
        errors.append(
            f"{map_path.name}: số mục label ({n_lbl_entries}) != tổng số 〓 trong ch/Label.txt ({total_lbl_ph})."
        )
    if n_aln_entries != total_aln_ph:
        errors.append(
            f"{map_path.name}: số mục align ({n_aln_entries}) != tổng số 〓 trong CSV ch_txt ({total_aln_ph})."
        )


def validate_book_v24(
    book_dir: Path,
    book_name: str,
    require_pdf: bool = False,
) -> Dict[str, Any]:
    """
    Thực hiện kiểm tra tự động toàn diện cho một thư mục `<Tên sách>/` theo Quy định đồ án v2.4.
    Trả về dict chứa `passed`, `errors`, `warnings`, và `evaluation`.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if require_pdf and not (book_dir / f"{book_name}.pdf").exists():
        errors.append(f"Thiếu file PDF gốc: {book_dir / f'{book_name}.pdf'}")

    ch_labels = _validate_ppocr_folder(book_dir / "ch", errors)
    vi_labels = _validate_ppocr_folder(book_dir / "vi", errors)
    image_map = _validate_image_map(book_dir, book_name, errors)

    csv_path = book_dir / f"{book_name}.csv"
    xlsx_path = book_dir / f"{book_name}.xlsx"
    if not csv_path.exists():
        errors.append(f"Thiếu file bắt buộc: {csv_path}")
    if not xlsx_path.exists():
        errors.append(f"Thiếu file bắt buộc: {xlsx_path}")
    if not csv_path.exists() or not xlsx_path.exists():
        return {"passed": False, "errors": errors, "warnings": warnings, "evaluation": {}}

    # Đọc CSV và kiểm tra schema v2.4
    pairs: List[AlignedSentencePair] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        expected_cols = ["img_id", "sentence_id", "ch_txt", "vi_txt", "text_diff"]
        if reader.fieldnames != expected_cols:
            errors.append(f"CSV sai tên cột: {reader.fieldnames} (yêu cầu {expected_cols}).")

        for r_idx, row in enumerate(reader, start=2):
            img_id = (row.get("img_id") or "").strip()
            sent_id = (row.get("sentence_id") or "").strip()
            ch_txt = row.get("ch_txt") or ""
            vi_txt = row.get("vi_txt") or ""
            raw_diff = (row.get("text_diff") or "").strip()
            row_ref = f"CSV dòng {r_idx} ({sent_id})"

            if not ch_txt.strip() or not vi_txt.strip():
                errors.append(f"{row_ref}: hàng không được rỗng một vế (ch_txt hoặc vi_txt trống).")
            if VARIATION_SELECTOR_PATTERN.search(ch_txt):
                errors.append(f"{row_ref}: phát hiện ký tự chọn dạng (Variation Selector) trong ch_txt.")
            if PUA_CHAR_PATTERN.search(ch_txt):
                errors.append(f"{row_ref}: phát hiện ký tự vùng dùng riêng (PUA) trong ch_txt (vi phạm v2.6 Trang 14 & 17).")
            if ch_txt != unicodedata.normalize("NFC", ch_txt) or vi_txt != unicodedata.normalize("NFC", vi_txt):
                errors.append(f"{row_ref}: văn bản chưa chuẩn hóa NFC.")
            if "\n" in ch_txt or "\n" in vi_txt:
                errors.append(f"{row_ref}: không được chứa ký tự xuống dòng trong ô.")

            parsed_diff: Optional[List[Dict[str, Any]]] = None
            if raw_diff == "null":
                parsed_diff = None
            else:
                try:
                    parsed_diff = json.loads(raw_diff)
                    if not isinstance(parsed_diff, list):
                        errors.append(f"{row_ref}: text_diff phải là mảng JSON hoặc null.")
                        parsed_diff = []
                except Exception as exc:
                    errors.append(f"{row_ref}: text_diff không phải JSON hợp lệ ({exc}).")
                    parsed_diff = []

            if parsed_diff is not None:
                used_nom: set = set()
                used_vi: set = set()
                for item in parsed_diff:
                    dtype = item.get("type")
                    if dtype not in ("error", "warn"):
                        errors.append(f"{row_ref}: type='{dtype}' không hợp lệ (chỉ nhận 'error' hoặc 'warn').")
                    if "suggest" in item or "suggest_by" in item:
                        errors.append(f"{row_ref}: file nộp không được còn phần tử có 'suggest'/'suggest_by'.")
                    if dtype == "error" and "reviewed" in item:
                        errors.append(f"{row_ref}: phần tử 'error' không được có trường 'reviewed'.")
                    if dtype == "warn" and "reviewed" in item and item["reviewed"] not in (0, 1):
                        errors.append(f"{row_ref}: trường 'reviewed' chỉ nhận 0 hoặc 1.")

                    nom_pos = item.get("nom_pos", [])
                    vi_pos = item.get("vi_pos", [])
                    if not nom_pos and not vi_pos:
                        errors.append(f"{row_ref}: hai vế nom_pos và vi_pos không được cùng rỗng.")
                    _validate_spans(ch_txt, nom_pos, item.get("nom_sub_text", ""), "ch", row_ref, used_nom, errors)
                    _validate_spans(vi_txt, vi_pos, item.get("vi_sub_text", ""), "vi", row_ref, used_vi, errors)

            pairs.append(
                AlignedSentencePair(
                    img_id=img_id,
                    sentence_id=sent_id,
                    ch_txt=ch_txt,
                    vi_txt=vi_txt,
                    text_diff=parsed_diff,
                )
            )

    # Đối chiếu `.xlsx` khớp 100% văn bản và màu sắc với `text_diff` trong `.csv`
    wb = openpyxl.load_workbook(str(xlsx_path), rich_text=True)
    ws = wb.active
    xlsx_rows = list(ws.iter_rows(min_row=2, values_only=True))
    if len(xlsx_rows) != len(pairs):
        errors.append(f"Số dòng trong .xlsx ({len(xlsx_rows)}) không khớp .csv ({len(pairs)}).")
    else:
        for idx, (p, xrow) in enumerate(zip(pairs, xlsx_rows), start=2):
            x_ch_txt, x_ch_colors = _cell_to_text_and_colors(xrow[2])
            x_vi_txt, x_vi_colors = _cell_to_text_and_colors(xrow[3])
            if x_ch_txt != p.ch_txt:
                errors.append(f"XLSX dòng {idx}: ch_txt không khớp với CSV.")
            if x_vi_txt != p.vi_txt:
                errors.append(f"XLSX dòng {idx}: vi_txt không khớp với CSV.")

            # Xác định trạng thái màu mong đợi từ text_diff
            exp_ch = ["black"] * len(p.ch_txt)
            exp_vi = ["black"] * len(p.vi_txt)
            if p.text_diff:
                for item in p.text_diff:
                    t = "red" if item.get("type") == "error" else "yellow"
                    for s, e in item.get("nom_pos", []):
                        for k in range(s, min(e, len(exp_ch))):
                            exp_ch[k] = t
                    for s, e in item.get("vi_pos", []):
                        for k in range(s, min(e, len(exp_vi))):
                            exp_vi[k] = t

            for side, actual_colors, exp_colors in (
                ("ch_txt", x_ch_colors, exp_ch),
                ("vi_txt", x_vi_colors, exp_vi),
            ):
                if len(actual_colors) != len(exp_colors):
                    continue
                for pos_i, (rgb6, expected_tag) in enumerate(zip(actual_colors, exp_colors)):
                    if expected_tag == "black" and rgb6 not in ALLOWED_BLACK_RGB:
                        errors.append(f"XLSX dòng {idx} {side}[{pos_i}]: màu #{rgb6}, kỳ vọng đen.")
                        break
                    if expected_tag == "red" and rgb6 not in ALLOWED_RED_RGB:
                        errors.append(f"XLSX dòng {idx} {side}[{pos_i}]: màu #{rgb6}, kỳ vọng đỏ.")
                        break
                    if expected_tag == "yellow" and rgb6 not in ALLOWED_YELLOW_RGB:
                        errors.append(f"XLSX dòng {idx} {side}[{pos_i}]: màu #{rgb6}, kỳ vọng vàng.")
                        break

    # Đối chiếu văn bản nối từ Label.txt (theo thứ tự đọc trong image_map) khớp với CSV (v2.4 Trang 14)
    if ch_labels and vi_labels:
        if image_map and image_map.get("pairs"):
            ch_order = [fn for pr in image_map["pairs"] for fn in pr.get("ch", [])]
            vi_order = [fn for pr in image_map["pairs"] for fn in pr.get("vi", [])]
        else:
            ch_order = sorted(ch_labels.keys(), reverse=True)
            vi_order = sorted(vi_labels.keys())

        lbl_ch_concat = "".join(
            b["transcription"] for fn in ch_order if fn in ch_labels for b in ch_labels[fn]
        )
        csv_ch_concat = "".join(p.ch_txt for p in pairs)
        if re.sub(r"\s+", "", lbl_ch_concat) != re.sub(r"\s+", "", csv_ch_concat):
            errors.append("Văn bản nối từ ch/Label.txt không khớp với cột ch_txt trong CSV (v2.4 Trang 14).")

        lbl_vi_concat = "".join(
            b["transcription"] for fn in vi_order if fn in vi_labels for b in vi_labels[fn]
        )
        csv_vi_concat = "".join(p.vi_txt for p in pairs)
        if re.sub(r"[\s\-]+", "", lbl_vi_concat) != re.sub(r"[\s\-]+", "", csv_vi_concat):
            errors.append("Văn bản nối từ vi/Label.txt không khớp với cột vi_txt trong CSV (v2.4 Trang 14).")

    _validate_placeholder_map_v26(book_dir, book_name, ch_labels, pairs, errors)

    evaluation = evaluate_pairs_v24(pairs)
    if not evaluation["passed_95_threshold"]:
        warnings.append(
            f"Độ tương đồng ({evaluation['similarity_percent']}%) chưa đạt ngưỡng 95%."
        )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "evaluation": evaluation,
    }


def verify_book_submission_folder(book_dir: Path, book_name: str) -> List[str]:
    """Hàm tương thích ngược: trả về danh sách lỗi của `validate_book_v24`."""
    res = validate_book_v24(book_dir, book_name, require_pdf=True)
    return res["errors"]
