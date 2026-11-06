"""
Bước 1 - 3: Kiểm tra nguồn dữ liệu, chiết xuất hình ảnh độ phân giải gốc từ PDF,
đặt tên theo đúng quy định và phân loại vào các thư mục (ch, vi, intro, ref, toc, blank, misc).
"""

from pathlib import Path
from typing import Dict, List, Optional
try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz  # type: ignore


VALID_SUBFOLDERS = ["ch", "vi", "intro", "ref", "toc", "blank", "misc"]


def format_page_number(page_idx_1based: int, total_pages: int) -> str:
    """
    Quy định chung về file hình ảnh (Trang 5 - Quy định đồ án v1.1):
    - Gồm ít nhất 3 số, đánh từ số 1 (ví dụ: 001, 011, 111).
    - Nếu số trang của sách lớn hơn 999 thì không thêm chữ số 0 ở đầu (ví dụ: 1234).
    """
    if total_pages > 999 and page_idx_1based > 999:
        return str(page_idx_1based)
    return f"{page_idx_1based:03d}"


def build_image_filename(
    book_name: str,
    page_idx_1based: int,
    total_pages: int,
    sub_image_idx: Optional[int] = None,
) -> str:
    """
    Tạo tên file hình ảnh theo cú pháp:
    <Tên sách>.<Số thứ tự trang>[_<Số thứ tự hình ảnh>].jpg
    Lưu ý: <Tên sách> phải giữ nguyên tên gốc của file PDF (bỏ đuôi .pdf).
    """
    page_str = format_page_number(page_idx_1based, total_pages)
    if sub_image_idx is not None:
        return f"{book_name}.{page_str}_{sub_image_idx}.jpg"
    return f"{book_name}.{page_str}.jpg"


def create_book_directory_structure(output_root: Path, book_name: str) -> Dict[str, Path]:
    """
    Khởi tạo cây thư mục chuẩn cho một cuốn sách theo Quy định chung về dữ liệu nộp (Trang 4).
    """
    book_dir = output_root / book_name
    paths = {"book_dir": book_dir}
    for sub in VALID_SUBFOLDERS:
        sub_path = book_dir / sub
        sub_path.mkdir(parents=True, exist_ok=True)
        paths[sub] = sub_path
    return paths


def inspect_pdf_books(raw_data_dir: Path) -> List[Dict[str, object]]:
    """
    Khảo sát chi tiết các file PDF trong thư mục Data/:
    Số trang, kích thước trang, độ phân giải ảnh scan gốc nhúng bên trong (embedded image).
    """
    results: List[Dict[str, object]] = []
    for pdf_path in sorted(raw_data_dir.glob("*.pdf")):
        doc = fitz.open(pdf_path)
        num_pages = len(doc)
        sample_w, sample_h, sample_ext = 0, 0, "none"
        if num_pages > 0:
            imgs = doc[0].get_images(full=True)
            if imgs:
                info = doc.extract_image(imgs[0][0])
                sample_w = info.get("width", 0)
                sample_h = info.get("height", 0)
                sample_ext = info.get("ext", "")
        results.append(
            {
                "filename": pdf_path.name,
                "book_name": pdf_path.stem,
                "num_pages": num_pages,
                "sample_img_width": sample_w,
                "sample_img_height": sample_h,
                "sample_img_ext": sample_ext,
            }
        )
        doc.close()
    return results


def extract_images_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    page_range: Optional[tuple] = None,
) -> List[Path]:
    """
    Chiết xuất hình ảnh từ file PDF với độ phân giải gốc cao nhất (Quy định Trang 5):
    - Nếu trang PDF chứa 1 ảnh scan gốc nhúng (embedded image), trích xuất và lưu dưới dạng .jpg
      với đúng độ phân giải gốc (ví dụ 3144 x 2096) và chất lượng JPEG cao nhất (quality=95).
    - Nếu trang không chứa ảnh nhúng đơn lẻ thì render trang với DPI cao.
    - Đặt tên theo cú pháp: <Tên sách>.<Số thứ tự trang>[_<Số thứ tự hình ảnh>].jpg
    """
    from PIL import Image
    import io

    book_name = pdf_path.stem  # Giữ nguyên tên sách gốc
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    start_page = page_range[0] if page_range else 1
    end_page = page_range[1] if page_range else total_pages

    saved_files: List[Path] = []
    for page_num in range(start_page, end_page + 1):
        page = doc[page_num - 1]
        img_filename = build_image_filename(book_name, page_num, total_pages)
        out_path = output_dir / img_filename

        imgs = page.get_images(full=True)
        if len(imgs) == 1:
            xref = imgs[0][0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            ext = base_image.get("ext", "").lower()
            if ext in ("jpg", "jpeg"):
                out_path.write_bytes(image_bytes)
            else:
                pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                pil_img.save(str(out_path), format="JPEG", quality=95)
        else:
            pix = page.get_pixmap(dpi=300)
            pix.save(str(out_path), jpg_quality=95)

        saved_files.append(out_path)

    doc.close()
    return saved_files
