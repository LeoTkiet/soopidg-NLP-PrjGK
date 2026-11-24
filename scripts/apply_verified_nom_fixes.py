"""
Công cụ hậu kiểm & sửa lỗi nhận dạng OCR Hán Nôm có kiểm chứng mộc bản (đồng bộ 100%
giữa `ch/Label.txt`, `.csv`, `text_diff`, `.xlsx` và `_placeholder_map.json` theo Quy định v2.6).

Nguyên tắc an toàn:
- CHỈ thay thế tại đúng vị trí ký tự Nôm được dóng hàng (`text_diff` loại `"error"`) khớp với
  đúng cặp `(chữ_OCR_nhầm, âm_Quốc_ngữ)` đã kiểm chứng trực tiếp trên ảnh mộc bản gốc.
- KHÔNG thay thế mù quáng toàn văn (VD: `無` đọc "vô" giữ nguyên `無`, chỉ sửa `無` đọc "chưng" -> `烝`).
- Sau khi cập nhật đồng bộ `ch/Label.txt`, tự động chạy lại `--step align` và `--step validate`.
"""

import argparse
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.step4_ppocr_formatter import write_ppocr_files
from src.step7_exporter_evaluator import (
    load_aligned_csv,
    load_ppocr_label_file,
    run_align_pipeline,
)
from src.step8_packager import validate_book_v24

# Các cặp lỗi nhận dạng hệ thống của API Kim Hán Nôm đã được kiểm chứng trực tiếp trên ảnh mộc bản
# Định dạng: (chữ_OCR_sai, âm_Quốc_ngữ_thường) -> chữ_Nôm_đúng_theo_mộc_bản_và_từ_điển
VERIFIED_WOODBLOCK_FIXES: Dict[Tuple[str, str], str] = {
    ("𠯇", "và"): "吧",      # mộc bản: 吧 (x381 trên book_1)
    ("啼", "và"): "吧",      # mộc bản: 吧 (x11)
    ("哭", "ra"): "𠚢",      # mộc bản: 𠚢 (x176)
    ("喫", "ra"): "𠚢",      # mộc bản: 𠚢 (x63)
    ("哭", "là"): "𱺵",      # mộc bản: 𱺵 (x31)
    ("塊", "hồn"): "魂",     # mộc bản: 魂 (x101)
    ("無", "chưng"): "烝",   # mộc bản: 烝 (x60)
    ("築", "chưng"): "烝",   # mộc bản: 烝 (x10)
    ("肄", "sốt"): "𤈠",     # mộc bản: 𤈠 (⿰火聿, x56)
    ("宗", "xuống"): "𡬈",   # mộc bản: 𡬈 (x50)
    ("徒", "chạy"): "𧼋",    # mộc bản: 𧼋 (x23)
    ("郎", "tức"): "即",     # mộc bản: 即 (x13)
    ("鍮", "trọn"): "論",    # mộc bản: 論 (x13)
    ("利", "sáng"): "𤏬",    # mộc bản: 𤏬 (x11)
    ("刈", "sáng"): "𤏬",    # mộc bản: 𤏬 (x11)
    ("泟", "sạch"): "浄",    # mộc bản: 浄 (x11)
    ("枚", "câu"): "枸",     # mộc bản: 枸 (x10)
}


def apply_verified_fixes_to_book(cfg: dict, book_id_filter: str) -> None:
    out_root = Path(cfg["paths"]["output_dir"])
    target_book = None
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        if book_id_filter in (b.get("id"), fname, Path(fname).stem):
            target_book = b
            break
    if not target_book:
        raise ValueError(f"Không tìm thấy sách '{book_id_filter}' trong config.yaml")

    book_name = Path(target_book["filename"]).stem
    book_dir = out_root / book_name
    ch_dir = book_dir / "ch"
    csv_path = book_dir / f"{book_name}.csv"
    map_path = book_dir / f"{book_name}_image_map.json"

    ch_labels = load_ppocr_label_file(ch_dir / "Label.txt")
    pairs = load_aligned_csv(csv_path)
    image_map = json.loads(map_path.read_text(encoding="utf-8"))

    # 1. Xây dựng chuỗi ký tự không khoảng trắng từ CSV kèm danh sách các vị trí cần sửa
    csv_nonws_chars: List[str] = []
    fix_at_global_idx: Dict[int, Tuple[str, str, str]] = {}  # g_idx -> (old_ch, new_ch, vi_syl)

    for p in pairs:
        ch_nfc = unicodedata.normalize("NFC", p.ch_txt)
        # Ánh xạ vị trí char trong câu -> chỉ số toàn cục không tính khoảng trắng
        local_to_global: Dict[int, int] = {}
        for idx, ch in enumerate(ch_nfc):
            if not ch.isspace():
                local_to_global[idx] = len(csv_nonws_chars)
                csv_nonws_chars.append(ch)

        if not p.text_diff:
            continue
        for item in p.text_diff:
            if item.get("type") != "error":
                continue
            nom_sub = unicodedata.normalize("NFC", item.get("nom_sub_text", ""))
            vi_sub = unicodedata.normalize("NFC", item.get("vi_sub_text", "")).strip().lower()
            nom_pos = item.get("nom_pos") or []
            if len(nom_sub) != 1 or not vi_sub or len(nom_pos) != 1:
                continue
            s, e = int(nom_pos[0][0]), int(nom_pos[0][1])
            if e - s != 1:
                continue
            replacement = VERIFIED_WOODBLOCK_FIXES.get((nom_sub, vi_sub))
            if replacement and s in local_to_global:
                g_idx = local_to_global[s]
                fix_at_global_idx[g_idx] = (nom_sub, replacement, vi_sub)

    # 2. Ánh xạ 1-1 ngược lại các vị trí ký tự không khoảng trắng trong ch/Label.txt (đúng thứ tự đọc)
    ch_order = [
        fn for pr in image_map.get("pairs", []) if pr.get("ch") and pr.get("vi") for fn in pr.get("ch", [])
    ]
    lbl_nonws_locs: List[Tuple[str, int, int, str]] = []  # (fn, box_idx, char_pos, ch)
    for fn in ch_order:
        for b_idx, box in enumerate(ch_labels.get(fn, [])):
            txt = unicodedata.normalize("NFC", str(box.get("transcription", "")))
            for pos, ch in enumerate(txt):
                if not ch.isspace():
                    lbl_nonws_locs.append((fn, b_idx, pos, ch))

    if len(lbl_nonws_locs) != len(csv_nonws_chars):
        raise RuntimeError(
            f"Lệch độ dài ch/Label.txt ({len(lbl_nonws_locs)}) vs CSV ({len(csv_nonws_chars)})! "
            "Hãy chạy --step align trước khi chạy script này."
        )

    # 3. Áp dụng sửa đổi lên ch_labels tại đúng vị trí kiểm chứng khớp ký tự
    edits_by_box: Dict[Tuple[str, int], Dict[int, str]] = {}
    applied_stats = Counter()
    for g_idx, (old_ch, new_ch, vi_syl) in fix_at_global_idx.items():
        fn, b_idx, pos, actual_ch = lbl_nonws_locs[g_idx]
        if actual_ch != old_ch:
            continue
        edits_by_box.setdefault((fn, b_idx), {})[pos] = new_ch
        applied_stats[(old_ch, new_ch, vi_syl)] += 1

    for (fn, b_idx), pos_map in edits_by_box.items():
        orig = unicodedata.normalize("NFC", str(ch_labels[fn][b_idx]["transcription"]))
        chars = list(orig)
        for pos, new_ch in pos_map.items():
            chars[pos] = new_ch
        ch_labels[fn][b_idx]["transcription"] = "".join(chars)

    write_ppocr_files(ch_dir, ch_labels, is_char_level=False)
    total_fixed = sum(applied_stats.values())
    print(f"=== ĐÃ SỬA ĐỒNG BỘ {total_fixed} LỖI OCR HÁN NÔM TRÊN ch/Label.txt ({book_id_filter}) ===")
    for (o, n, v), cnt in applied_stats.most_common():
        print(f"  - {o} -> {n} (đọc '{v}'): {cnt} vị trí")

    # 4. Chạy lại align (tự xuất .csv, .xlsx, _placeholder_map.json, _red_report.csv) và validate v2.6
    print()
    run_align_pipeline(cfg, book_filter=book_id_filter)
    print("\n=== KIỂM TRA TỰ ĐỘNG CHUẨN v2.6 SAU KHI SỬA ===")
    val = validate_book_v24(book_dir, book_name, require_pdf=False)
    status = "PASS (0 lỗi)" if val["passed"] else f"FAIL ({len(val['errors'])} lỗi)"
    print(
        f"  + [{book_id_filter}] {book_name}: {status} | "
        f"Độ tương đồng: {val['evaluation'].get('similarity_percent', 0.0)}%"
    )
    for err in val["errors"][:10]:
        print(f"      - [LỖI] {err}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sửa đồng bộ lỗi OCR Hán Nôm đã kiểm chứng mộc bản")
    parser.add_argument("--book", required=True, help="Mã sách (vd: book_1)")
    args = parser.parse_args()
    cfg = load_config()
    apply_verified_fixes_to_book(cfg, args.book)


if __name__ == "__main__":
    main()
