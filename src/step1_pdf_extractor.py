"""
Bước 1: Khảo sát PDF, chiết xuất ảnh JPEG độ phân giải gốc,
xoay trang (nếu cần), phân loại thư mục và ghép <Tên sách>_updated.pdf.

Tuân theo Quy định đồ án v1.1 / v2.1:
- Tên file: <Tên sách>.<STT trang 3 chữ số>[_<STT ảnh>].jpg
- <Tên sách> giữ nguyên stem của file PDF được giao
- Ảnh có thể nằm ở nhiều thư mục (copy, không move)
- PDF mới không được trùng ảnh
"""

from __future__ import annotations

import io
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image
from tqdm import tqdm

try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz  # type: ignore


VALID_SUBFOLDERS = [
    "ch",
    "vi",
    "intro",
    "ref",
    "toc",
    "blank",
    "misc",
    "missing/ch",
    "missing/vi",
]

JPEG_QUALITY = 95
COVER_TOLERANCE_PT = 1.0
PAGE_TOKEN_RE = re.compile(r"^(\d+)(?:_(\d+))?$")


def find_pdf(raw_data_dir: Path, filename: str) -> Path:
    """Tìm file PDF theo tên, bỏ qua khác biệt NFC/NFD của chữ có dấu."""
    if not raw_data_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục dữ liệu: {raw_data_dir}")

    can_tim = unicodedata.normalize("NFC", filename)
    for pdf in raw_data_dir.glob("*.pdf"):
        if unicodedata.normalize("NFC", pdf.name) == can_tim:
            return pdf
    raise FileNotFoundError(f"Không thấy file PDF: {filename}")


def expand_ranges(ranges: Sequence[Sequence[int]]) -> List[int]:
    """[[3, 5], [9, 9]] -> [3, 4, 5, 9]"""
    pages: List[int] = []
    for item in ranges:
        if len(item) != 2:
            raise ValueError(f"Khoảng trang không hợp lệ: {item}")
        start, end = int(item[0]), int(item[1])
        if start < 1 or end < start:
            raise ValueError(f"Khoảng trang không hợp lệ: {item}")
        pages.extend(range(start, end + 1))
    return pages


def format_page_number(page_idx_1based: int) -> str:
    """Ít nhất 3 chữ số: 1 -> 001, 111 -> 111, 1234 -> 1234."""
    return f"{page_idx_1based:03d}"


def build_image_filename(
    book_name: str,
    page_idx_1based: int,
    sub_image_idx: Optional[int] = None,
) -> str:
    """
    Cú pháp: <Tên sách>.<Số thứ tự trang>[_<Số thứ tự hình ảnh>].jpg
    Chỉ thêm _<STT ảnh> khi một trang PDF có nhiều hơn một ảnh chụp.
    """
    page_str = format_page_number(page_idx_1based)
    if sub_image_idx is not None:
        return f"{book_name}.{page_str}_{sub_image_idx}.jpg"
    return f"{book_name}.{page_str}.jpg"


def parse_image_sort_key(path: Path, book_name: str) -> Tuple[int, int]:
    """Trả về (số trang, số ảnh phụ) để sắp xếp khi ghép PDF."""
    stem = path.stem
    prefix = f"{book_name}."
    token = stem[len(prefix):] if stem.startswith(prefix) else stem.rsplit(".", 1)[-1]
    match = PAGE_TOKEN_RE.match(token)
    if not match:
        return (10**9, 0)
    page_num = int(match.group(1))
    sub_idx = int(match.group(2)) if match.group(2) else 0
    return (page_num, sub_idx)


def create_book_directory_structure(output_root: Path, book_name: str) -> Dict[str, Path]:
    """Tạo cây thư mục chuẩn cho một cuốn sách (kể cả missing/ theo v2.1)."""
    book_dir = output_root / book_name
    paths: Dict[str, Path] = {"book_dir": book_dir}
    for sub in VALID_SUBFOLDERS:
        sub_path = book_dir / sub
        sub_path.mkdir(parents=True, exist_ok=True)
        paths[sub] = sub_path
    return paths


def get_image_info(doc, page_index: int) -> Tuple[int, int, str]:
    """
    Trả về (rộng, cao, đuôi file) của ảnh nhúng đầu tiên trong trang.
    Nếu trang không có ảnh nhúng thì trả về (0, 0, "none").
    """
    page = doc.load_page(page_index)
    imgs = page.get_images(full=True)
    if not imgs:
        return 0, 0, "none"

    xref = imgs[0][0]
    info = doc.extract_image(xref)
    return (
        info.get("width", 0),
        info.get("height", 0),
        info.get("ext", "none"),
    )


def inspect_pdf_books(raw_data_dir: Path) -> List[Dict[str, object]]:
    """
    Khảo sát các file PDF:
    - Tên file và tên sách.
    - Tổng số trang.
    - Thông tin ảnh nhúng ở trang đầu và trang giữa.
    """
    if not raw_data_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục dữ liệu PDF: {raw_data_dir}")

    pdf_files = sorted(
        raw_data_dir.glob("*.pdf"),
        key=lambda p: unicodedata.normalize("NFC", p.name),
    )
    if not pdf_files:
        print(f"Không tìm thấy file PDF nào trong: {raw_data_dir}")
        return []

    results: List[Dict[str, object]] = []
    for pdf_path in pdf_files:
        with fitz.open(pdf_path) as doc:
            num_pages = len(doc)
            if num_pages > 0:
                first = get_image_info(doc, 0)
                middle = get_image_info(doc, num_pages // 2)
            else:
                first = (0, 0, "none")
                middle = (0, 0, "none")

            results.append({
                "filename": unicodedata.normalize("NFC", pdf_path.name),
                "book_name": unicodedata.normalize("NFC", pdf_path.stem),
                "num_pages": num_pages,
                "first_page_image": first,
                "middle_page_image": middle,
                "sample_img_width": first[0],
                "sample_img_height": first[1],
                "sample_img_ext": first[2],
                "path": pdf_path,
            })
    return results


def _image_covers_page(image_rect, page_rect) -> bool:
    return (
        abs(image_rect.x0 - page_rect.x0) <= COVER_TOLERANCE_PT
        and abs(image_rect.y0 - page_rect.y0) <= COVER_TOLERANCE_PT
        and abs(image_rect.x1 - page_rect.x1) <= COVER_TOLERANCE_PT
        and abs(image_rect.y1 - page_rect.y1) <= COVER_TOLERANCE_PT
    )


def _target_render_dpi(doc, page, imgs) -> int:
    """Chọn DPI render sao cho không nhỏ hơn độ phân giải ảnh nhúng gốc."""
    page_w = page.rect.width
    if page_w <= 0:
        return 300

    max_width = 0
    for img in imgs:
        try:
            info = doc.extract_image(img[0])
            max_width = max(max_width, int(info.get("width", 0)))
        except Exception:
            continue

    if max_width <= 0:
        return 300
    return max(300, int(round(max_width * 72.0 / page_w)))


def _save_jpeg_bytes(image_bytes: bytes, ext: str, out_path: Path) -> None:
    if ext in ("jpg", "jpeg"):
        out_path.write_bytes(image_bytes)
        return
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.convert("RGB").save(out_path, format="JPEG", quality=100, subsampling=0)


def extract_images_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    page_range: Optional[tuple] = None,
    skip_existing: bool = True,
) -> List[Path]:
    """
    Tách ảnh từ PDF:
    - Ảnh nhúng duy nhất, bao phủ toàn trang, không xoay, không có nội dung bổ sung:
      trích xuất luồng JPEG/ảnh gốc.
    - Các trường hợp còn lại: render trang với DPI không thấp hơn ảnh gốc (tối thiểu 300).

    page_range: (trang_bắt_đầu, trang_kết_thúc), tính từ 1.
    skip_existing: True thì không tách lại trang đã có file .jpg.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy PDF: {pdf_path}")

    book_name = pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_files: List[Path] = []
    extracted_pages: List[int] = []
    rendered_pages: List[int] = []
    skipped_pages: List[int] = []

    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)
        if page_range is None:
            start_page, end_page = 1, total_pages
        else:
            if len(page_range) != 2:
                raise ValueError("page_range phải có dạng (trang_bắt_đầu, trang_kết_thúc)")
            start_page, end_page = int(page_range[0]), int(page_range[1])
            if not (1 <= start_page <= end_page <= total_pages):
                raise ValueError(
                    f"Phạm vi trang không hợp lệ: {page_range}. PDF có {total_pages} trang."
                )

        wanted_pages = list(range(start_page, end_page + 1))
        if skip_existing:
            pages_to_extract = [
                page_num
                for page_num in wanted_pages
                if not (output_dir / build_image_filename(book_name, page_num)).exists()
            ]
        else:
            pages_to_extract = wanted_pages

        skipped_pages = [p for p in wanted_pages if p not in pages_to_extract]
        saved_files.extend(
            output_dir / build_image_filename(book_name, page_num)
            for page_num in skipped_pages
        )

        if not pages_to_extract:
            print(
                f"Bỏ qua chiết xuất: đã có đủ {len(skipped_pages)} ảnh trong {output_dir}."
            )
            return saved_files

        if skipped_pages:
            print(
                f"Tái sử dụng {len(skipped_pages)} ảnh có sẵn, "
                f"tách thêm {len(pages_to_extract)} trang còn thiếu."
            )

        for page_num in tqdm(pages_to_extract, desc=f"Chiết xuất {book_name}", unit="trang"):
            page = doc.load_page(page_num - 1)
            out_path = output_dir / build_image_filename(book_name, page_num)
            imgs = page.get_images(full=True)
            can_extract_original = False
            xref = None

            if len(imgs) == 1 and page.rotation == 0:
                xref = imgs[0][0]
                image_rects = page.get_image_rects(xref)
                if len(image_rects) == 1:
                    covers_page = _image_covers_page(image_rects[0], page.rect)
                    has_extra_content = bool(page.get_drawings()) or bool(
                        page.get_text("text").strip()
                    )
                    can_extract_original = covers_page and not has_extra_content

            if can_extract_original and xref is not None:
                base_image = doc.extract_image(xref)
                _save_jpeg_bytes(
                    base_image["image"],
                    str(base_image.get("ext", "")).lower(),
                    out_path,
                )
                extracted_pages.append(page_num)
            else:
                dpi = _target_render_dpi(doc, page, imgs)
                pix = page.get_pixmap(dpi=dpi, alpha=False)
                pix.save(str(out_path), jpg_quality=JPEG_QUALITY)
                rendered_pages.append(page_num)

            saved_files.append(out_path)

    print(
        f"Đã chiết xuất {len(extracted_pages) + len(rendered_pages)} ảnh mới "
        f"(gốc: {len(extracted_pages)}, render: {len(rendered_pages)}, "
        f"tái sử dụng: {len(skipped_pages)})."
    )
    if rendered_pages:
        preview = rendered_pages[:20]
        suffix = "..." if len(rendered_pages) > 20 else ""
        print("Các trang đã render (cần rà độ phân giải):", preview, suffix)

    return saved_files


def rotate_images(
    images_dir: Path,
    book_name: str,
    rotation: Dict[int, int],
    output_dir: Optional[Path] = None,
) -> List[Path]:
    """
    Xoay ảnh theo góc Pillow (ngược chiều kim đồng hồ): 90, 180, 270.

    Nếu output_dir là None thì ghi đè ngay trong images_dir.
    """
    if not images_dir.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục ảnh: {images_dir}")

    dest_dir = output_dir or images_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    saved_files: List[Path] = []

    for page_num, angle in sorted(rotation.items()):
        page_num = int(page_num)
        angle = int(angle)
        if angle not in (90, 180, 270):
            raise ValueError(f"Góc xoay không hợp lệ ở trang {page_num}: {angle}")

        image_name = build_image_filename(book_name, page_num)
        image_path = images_dir / image_name
        if not image_path.exists():
            print(f"Không tìm thấy ảnh trang {page_num}: {image_name}")
            continue

        output_path = dest_dir / image_name
        with Image.open(image_path) as image:
            rotated = image.rotate(angle, expand=True)
            rotated.convert("RGB").save(
                output_path,
                format="JPEG",
                quality=JPEG_QUALITY,
                subsampling=0,
            )
        saved_files.append(output_path)

    print(f"Đã xoay {len(saved_files)}/{len(rotation)} ảnh.")
    return saved_files


def _search_dirs(images_dir: Path | Sequence[Path]) -> List[Path]:
    if isinstance(images_dir, (list, tuple)):
        return [Path(d) for d in images_dir]
    return [Path(images_dir)]


def _find_page_images(
    book_name: str,
    page_num: int,
    search_dirs: Sequence[Path],
) -> List[Path]:
    """Ưu tiên thư mục đứng trước (ảnh đã xoay trước, ảnh gốc sau)."""
    base_name = build_image_filename(book_name, page_num)
    for directory in search_dirs:
        source = directory / base_name
        sub_images = sorted(directory.glob(f"{Path(base_name).stem}_*.jpg"))
        image_files = ([source] if source.exists() else []) + sub_images
        if image_files:
            return image_files
    return []


def classify_images(
    images_dir: Path | Sequence[Path],
    paths: Dict[str, Path],
    book_name: str,
    classification: Dict[str, list],
) -> List[int]:
    """
    Sao chép ảnh vào thư mục theo danh sách phân loại (một ảnh có thể thuộc nhiều thư mục).

    Hỗ trợ danh sách trang [1, 2, 3] hoặc khoảng [[1, 3], [5, 7]].
    Trả về danh sách số trang đã phân loại.
    """
    search_dirs = _search_dirs(images_dir)
    classified_pages: set[int] = set()

    for folder, page_numbers in classification.items():
        if folder not in VALID_SUBFOLDERS:
            print(f"Danh mục không hợp lệ: {folder}")
            continue
        if folder not in paths:
            print(f"Chưa khởi tạo đường dẫn thư mục: {folder}")
            continue
        if not page_numbers:
            continue

        if isinstance(page_numbers[0], (list, tuple)):
            page_numbers = expand_ranges(page_numbers)

        destination_dir = paths[folder]
        destination_dir.mkdir(parents=True, exist_ok=True)

        for page_num in sorted(set(int(p) for p in page_numbers)):
            if page_num < 1:
                print(f"Số trang không hợp lệ: {page_num}")
                continue

            image_files = _find_page_images(book_name, page_num, search_dirs)
            base_name = build_image_filename(book_name, page_num)

            if not image_files:
                print(f"Thiếu ảnh trang {page_num}: {base_name}")
                continue

            classified_pages.add(page_num)
            for image_path in image_files:
                shutil.copy2(image_path, destination_dir / image_path.name)

    return sorted(classified_pages)


def copy_source_pdf(pdf_path: Path, book_dir: Path) -> Path:
    """Sao chép PDF gốc vào thư mục sách, giữ nguyên tên file được giao."""
    book_dir.mkdir(parents=True, exist_ok=True)
    dest = book_dir / pdf_path.name
    if dest.resolve() != pdf_path.resolve():
        shutil.copy2(pdf_path, dest)
    return dest


def merge_images_to_updated_pdf(
    images_dir: Path | Sequence[Path],
    book_name: str,
    output_pdf: Path,
) -> Path:
    """
    Ghép ảnh thành <Tên sách>_updated.pdf, mỗi ảnh một lần,
    theo thứ tự số trang rồi số ảnh phụ. Thư mục đứng trước được ưu tiên.
    """
    by_name: Dict[str, Path] = {}
    for directory in _search_dirs(images_dir):
        if not directory.exists():
            continue
        for image_path in directory.glob(f"{book_name}.*.jpg"):
            by_name.setdefault(image_path.name, image_path)

    image_files = sorted(
        by_name.values(),
        key=lambda p: parse_image_sort_key(p, book_name),
    )
    if not image_files:
        raise FileNotFoundError(f"Không có ảnh để ghép PDF: {images_dir}")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    try:
        for image_path in tqdm(image_files, desc="Ghép updated.pdf", unit="ảnh"):
            img_doc = fitz.open(image_path)
            try:
                rect = img_doc[0].rect
                page = doc.new_page(width=rect.width, height=rect.height)
                page.insert_image(page.rect, filename=str(image_path))
            finally:
                img_doc.close()
        doc.save(output_pdf, deflate=True)
    finally:
        doc.close()

    print(f"Đã ghi {output_pdf.name} ({len(image_files)} trang, không trùng ảnh).")
    return output_pdf


def _collect_extracted_pages(images_dir: Path, book_name: str) -> List[int]:
    pages: set[int] = set()
    for path in images_dir.glob(f"{book_name}.*.jpg"):
        page_num, _ = parse_image_sort_key(path, book_name)
        if page_num < 10**9:
            pages.add(page_num)
    return sorted(pages)


def _normalize_rotation(raw: Optional[Dict[Any, Any]]) -> Dict[int, int]:
    if not raw:
        return {}
    return {int(page): int(angle) for page, angle in raw.items()}


def _normalize_page_range(raw: Any) -> Optional[tuple]:
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return (int(raw[0]), int(raw[1]))
    raise ValueError(f"page_range không hợp lệ: {raw}")


def process_book(
    raw_data_dir: Path,
    output_root: Path,
    book_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Pipeline bước 1 cho một cuốn sách:
    khảo sát -> chiết xuất -> xoay -> phân loại -> (nếu có xoay) ghép updated.pdf.
    """
    pdf_path = find_pdf(raw_data_dir, book_cfg["filename"])
    book_name = pdf_path.stem
    paths = create_book_directory_structure(output_root, book_name)
    book_dir = paths["book_dir"]

    copy_source_pdf(pdf_path, book_dir)

    raw_dir = book_dir / "images_raw"
    processed_dir = book_dir / "images_processed"
    extract_images_from_pdf(pdf_path, raw_dir, _normalize_page_range(book_cfg.get("page_range")))

    if processed_dir.exists():
        shutil.rmtree(processed_dir)
    shutil.copytree(raw_dir, processed_dir)

    rotation = _normalize_rotation(book_cfg.get("rotate"))
    updated_pdf: Optional[Path] = None
    if rotation:
        rotate_images(processed_dir, book_name, rotation)
        updated_pdf = merge_images_to_updated_pdf(
            processed_dir,
            book_name,
            book_dir / f"{book_name}_updated.pdf",
        )

    classification = book_cfg.get("classify") or {}
    classified_pages: List[int] = []
    unclassified_pages: List[int] = []
    if classification:
        classified_pages = classify_images(processed_dir, paths, book_name, classification)
        all_pages = set(_collect_extracted_pages(processed_dir, book_name))
        unclassified_pages = sorted(all_pages - set(classified_pages))
        if unclassified_pages:
            preview = unclassified_pages[:30]
            suffix = "..." if len(unclassified_pages) > 30 else ""
            print(
                f"Cảnh báo: {len(unclassified_pages)} trang chưa được phân loại:",
                preview,
                suffix,
            )
    else:
        print("Chưa có mục classify trong config.yaml — chỉ chiết xuất ảnh, chưa chia thư mục.")

    print(f"Hoàn tất bước 1 cho: {book_name}")
    return {
        "book_name": book_name,
        "pdf_path": pdf_path,
        "book_dir": book_dir,
        "extracted": len(_collect_extracted_pages(processed_dir, book_name)),
        "rotated": len(rotation),
        "classified": len(classified_pages),
        "unclassified": unclassified_pages,
        "updated_pdf": updated_pdf,
    }


def process_all_books(cfg: Dict[str, Any], book_ids: Optional[Iterable[str]] = None) -> None:
    """Chạy bước 1 cho toàn bộ sách trong config, hoặc theo danh sách id."""
    raw_data_dir = Path(cfg["paths"]["raw_data_dir"])
    output_root = Path(cfg["paths"]["output_dir"])
    wanted = set(book_ids) if book_ids else None

    for book_cfg in cfg.get("books", []):
        if wanted is not None and book_cfg.get("id") not in wanted:
            continue
        print(f"\n=== {book_cfg.get('id')}: {book_cfg.get('filename')} ===")
        process_book(raw_data_dir, output_root, book_cfg)
