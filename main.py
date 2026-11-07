"""
CLI điều phối toàn bộ Pipeline Xây dựng Dữ liệu Song song Hán Nôm - Quốc ngữ.
Chạy lệnh:
    python main.py --step check
    python main.py --step extract
    python main.py --step ocr-nom --book book_1 --max-pages 5
"""

import argparse
from pathlib import Path

from src.config import load_config
from src.step1_pdf_extractor import (
    create_book_directory_structure,
    inspect_pdf_books,
    run_extract_all_books,
)
from src.step2_kimhannom_api import run_ocr_nom_pipeline


def run_environment_check(cfg: dict) -> None:
    """Kiểm tra cấu hình, đường dẫn dữ liệu gốc và từ điển."""
    print("=== KIỂM TRA CẤU HÌNH DỰ ÁN HÁN NÔM - QUỐC NGỮ ===")
    print(f"- Mã nhóm (Group ID): {cfg['project']['group_id']}")
    print(f"- Ngưỡng độ tương đồng yêu cầu: >= {cfg['project']['min_similarity_threshold']}%")
    print(f"- Kim Hán Nôm Base URL: {cfg['auth']['base_url']}")
    print(f"- Tài khoản đăng nhập: {cfg['auth']['email']}")

    raw_dir = Path(cfg["paths"]["raw_data_dir"])
    dict_dir = Path(cfg["paths"]["dictionary_entries_dir"])

    print(f"\n[1] Khảo sát 4 tập sách gốc ({raw_dir}):")
    pdf_stats = {item["filename"]: item for item in inspect_pdf_books(raw_dir)}
    total_pages = 0
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        b_path = raw_dir / fname
        status = "OK" if b_path.exists() else "KHÔNG TÌM THẤY"
        stat = pdf_stats.get(fname, {})
        pages = int(stat.get("num_pages", 0))
        total_pages += pages
        res = f"{stat.get('sample_img_width')}x{stat.get('sample_img_height')} ({stat.get('sample_img_ext')})"
        member = b.get("assigned_member", "N/A")
        pm = b.get("page_mapping", {})
        vi_cnt = sum(r[1] - r[0] + 1 for r in pm.get("vi", []))
        ch_cnt = sum(r[1] - r[0] + 1 for r in pm.get("ch", []))
        print(
            f"  + [{status}] {fname}\n"
            f"      Số trang: {pages} trang (vi: {vi_cnt}, ch: {ch_cnt}) | "
            f"Độ phân giải ảnh gốc: {res} | Phụ trách: {member}"
        )
    print(f"  => TỔNG SỐ TRANG PDF CỦA CẢ 4 TẬP: {total_pages} trang")

    print(f"\n[2] Kiểm tra thư mục từ điển ({dict_dir}):")
    for src in cfg["dictionaries"]["primary_sources"] + cfg["dictionaries"]["variant_sources"]:
        s_path = dict_dir / src
        status = "OK" if s_path.exists() else "KHÔNG TÌM THẤY"
        print(f"  + [{status}] {src}")


def run_init_folders(cfg: dict) -> None:
    """Khởi tạo cấu trúc thư mục đầu ra chuẩn cho tất cả các sách được giao."""
    out_root = Path(cfg["paths"]["output_dir"])
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_name = Path(fname).stem
        paths = create_book_directory_structure(out_root, book_name)
        print(f"Đã khởi tạo cấu trúc thư mục chuẩn cho: {paths['book_dir']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline Xây dựng Dữ liệu Song song Hán Nôm và Quốc ngữ"
    )
    parser.add_argument(
        "--step",
        choices=["check", "init", "extract", "ocr-nom", "ocr-vi", "align", "evaluate", "package"],
        default="check",
        help="Bước cần chạy trong pipeline",
    )
    parser.add_argument(
        "--book",
        type=str,
        default=None,
        help="Lọc theo mã sách (vd: book_1, book_2) hoặc tên file PDF",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Số trang tối đa gọi API mới trong 1 lần chạy (dùng cho --step ocr-nom)",
    )
    args = parser.parse_args()
    cfg = load_config()

    if args.step == "check":
        run_environment_check(cfg)
    elif args.step == "init":
        run_init_folders(cfg)
    elif args.step == "extract":
        run_extract_all_books(cfg, book_filter=args.book)
    elif args.step == "ocr-nom":
        run_ocr_nom_pipeline(cfg, book_filter=args.book, max_pages=args.max_pages)
    else:
        print(
            f"Bước '{args.step}' thuộc phạm vi của Thành viên 2 & 3. "
            "Xem chi tiết tại docs/ProjectDescription.md và docs/PLAN_3_MEMBERS.md."
        )


if __name__ == "__main__":
    main()
