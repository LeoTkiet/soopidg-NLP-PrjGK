"""
Bước 1 - 3: Kiểm tra nguồn dữ liệu, chiết xuất hình ảnh độ phân giải gốc từ PDF,
đặt tên theo đúng quy định và phân loại vào các thư mục (ch, vi, intro, ref, toc, blank, misc).
"""

import io
import json
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    import pymupdf as fitz  # PyMuPDF
except ImportError:
    import fitz  # type: ignore

from PIL import Image


VALID_SUBFOLDERS = ["ch", "vi", "intro", "ref", "toc", "blank", "misc"]

_ROTATE_MAP = {
    90: Image.Transpose.ROTATE_270,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_90,
}


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


def _resolve_page_image_xrefs(doc: Any) -> List[Optional[int]]:
    """
    Xác định xref của ảnh scan gốc được vẽ trên từng trang PDF.
    Xử lý trường hợp file PDF dùng chung từ điển /Resources /XObject cho mọi trang
    (khiến page.get_images() trả về hàng trăm ảnh thay vì 1 ảnh).
    """
    if len(doc) == 0:
        return []
    p0_imgs = doc[0].get_images(full=True)
    if len(p0_imgs) > 1:
        name_map = {im[7]: im[0] for im in p0_imgs}
        xrefs: List[Optional[int]] = []
        for idx in range(len(doc)):
            contents = doc[idx].read_contents().decode("latin1", errors="ignore")
            names = re.findall(r"/(\S+)\s+Do", contents)
            matched_xref = next((name_map[n] for n in names if n in name_map), None)
            if matched_xref is None:
                imgs = doc[idx].get_images(full=True)
                matched_xref = imgs[0][0] if imgs else None
            xrefs.append(matched_xref)
        return xrefs

    xrefs = []
    for idx in range(len(doc)):
        imgs = doc[idx].get_images(full=True)
        xrefs.append(imgs[0][0] if imgs else None)
    return xrefs


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
                sample_w = imgs[0][2]
                sample_h = imgs[0][3]
                sample_ext = "jpeg" if imgs[0][8] == "DCTDecode" else imgs[0][8]
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


def build_page_folder_map(
    page_mapping: Optional[Dict[str, List[List[int]]]],
    total_pages: int,
) -> Dict[int, str]:
    """
    Chuyển cấu hình page_mapping (danh sách các khoảng [start, end] 1-based)
    thành bảng ánh xạ {page_num: subfolder_name}.
    """
    mapping: Dict[int, str] = {}
    if page_mapping:
        for folder_name, ranges in page_mapping.items():
            if folder_name not in VALID_SUBFOLDERS:
                continue
            for r in ranges or []:
                if isinstance(r, (list, tuple)) and len(r) == 2:
                    start_p, end_p = int(r[0]), int(r[1])
                    for p in range(start_p, end_p + 1):
                        mapping[p] = folder_name
    for p in range(1, total_pages + 1):
        mapping.setdefault(p, "misc")
    return mapping


def _save_page_image(doc: Any, page: Any, xref: Optional[int], out_path: Path) -> None:
    """
    Lưu ảnh gốc của 1 trang PDF ra file .jpg giữ nguyên độ phân giải gốc,
    đồng thời tự động xoay đúng chiều nếu trang PDF có thuộc tính rotation (90/180/270).
    """
    rot = page.rotation % 360
    if xref is not None:
        raw_bytes = doc.xref_stream_raw(xref)
        if rot == 0:
            # Luồng JPEG gốc (DCTDecode) ghi trực tiếp để không suy giảm chất lượng
            if raw_bytes[:2] == b"\xff\xd8":
                out_path.write_bytes(raw_bytes)
                return
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            pil_img.save(str(out_path), format="JPEG", quality=95, subsampling=0)
            return
        else:
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
            if rot in _ROTATE_MAP:
                pil_img = pil_img.transpose(_ROTATE_MAP[rot])
            pil_img.save(str(out_path), format="JPEG", quality=95, subsampling=0)
            return

    pix = page.get_pixmap(dpi=300)
    pix.save(str(out_path), jpg_quality=95)


def extract_images_from_pdf(
    pdf_path: Path,
    output_dir: Path,
    page_range: Optional[Tuple[int, int]] = None,
) -> List[Path]:
    """
    Chiết xuất hình ảnh từ file PDF với độ phân giải gốc cao nhất (Quy định Trang 5):
    - Trích xuất ảnh scan gốc nhúng bên trong và lưu dưới dạng .jpg.
    - Đặt tên theo cú pháp: <Tên sách>.<Số thứ tự trang>[_<Số thứ tự hình ảnh>].jpg
    """
    book_name = pdf_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    start_page = page_range[0] if page_range else 1
    end_page = page_range[1] if page_range else total_pages
    page_xrefs = _resolve_page_image_xrefs(doc)

    saved_files: List[Path] = []
    for page_num in range(start_page, end_page + 1):
        page = doc[page_num - 1]
        xref = page_xrefs[page_num - 1]
        img_filename = build_image_filename(book_name, page_num, total_pages)
        out_path = output_dir / img_filename
        _save_page_image(doc, page, xref, out_path)
        saved_files.append(out_path)

    doc.close()
    return saved_files


def extract_and_classify_book(
    pdf_path: Path,
    output_root: Path,
    page_mapping: Optional[Dict[str, List[List[int]]]] = None,
) -> Dict[str, int]:
    """
    Chiết xuất toàn bộ trang ảnh của 1 cuốn sách PDF và phân loại trực tiếp vào
    các thư mục con (ch, vi, intro, ref, toc, blank, misc) theo page_mapping.
    Trả về thống kê số lượng ảnh trong từng thư mục con.
    """
    book_name = pdf_path.stem
    paths = create_book_directory_structure(output_root, book_name)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    page_xrefs = _resolve_page_image_xrefs(doc)
    folder_map = build_page_folder_map(page_mapping, total_pages)

    counts: Dict[str, int] = {sub: 0 for sub in VALID_SUBFOLDERS}
    for page_num in range(1, total_pages + 1):
        page = doc[page_num - 1]
        xref = page_xrefs[page_num - 1]
        target_sub = folder_map[page_num]
        img_filename = build_image_filename(book_name, page_num, total_pages)

        # Xóa ảnh cũ nếu từng nằm ở thư mục con khác
        for sub in VALID_SUBFOLDERS:
            if sub != target_sub:
                old_file = paths[sub] / img_filename
                if old_file.exists():
                    old_file.unlink()

        out_path = paths[target_sub] / img_filename
        _save_page_image(doc, page, xref, out_path)
        counts[target_sub] += 1

    doc.close()
    return counts


def run_extract_all_books(cfg: Dict[str, Any], book_filter: Optional[str] = None) -> None:
    """
    Điều phối chiết xuất & phân loại ảnh cho tất cả các sách trong config.yaml
    (hoặc lọc theo id/tên sách nếu truyền book_filter).
    """
    raw_dir = Path(cfg["paths"]["raw_data_dir"])
    out_root = Path(cfg["paths"]["output_dir"])

    print("=== CHIẾT XUẤT & PHÂN LOẠI ẢNH TỪ PDF (ĐỘ PHÂN GIẢI GỐC) ===")
    total_extracted = 0
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        if book_filter and book_filter not in (book_id, fname, Path(fname).stem):
            continue

        pdf_path = raw_dir / fname
        if not pdf_path.exists():
            print(f"  [LỖI] Không tìm thấy file PDF: {pdf_path}")
            continue

        print(f"\n-> Đang xử lý [{book_id}] {fname} ...")
        counts = extract_and_classify_book(
            pdf_path=pdf_path,
            output_root=out_root,
            page_mapping=b.get("page_mapping"),
        )
        book_total = sum(counts.values())
        total_extracted += book_total
        summary = ", ".join(f"{k}: {v}" for k, v in counts.items() if v > 0)
        print(f"   Hoàn tất {book_total} trang ({summary})")

    print(f"\n=> TỔNG SỐ ẢNH ĐÃ CHIẾT XUẤT & PHÂN LOẠI: {total_extracted} ảnh.")


def _expand_ranges(ranges: Optional[List[List[int]]]) -> List[int]:
    """Mở rộng danh sách khoảng [start, end] (1-based, inclusive) thành danh sách số trang tăng dần."""
    pages: List[int] = []
    for r in ranges or []:
        if isinstance(r, (list, tuple)) and len(r) == 2:
            pages.extend(range(int(r[0]), int(r[1]) + 1))
    return sorted(set(pages))


def generate_book_image_map(
    book_cfg: Dict[str, Any],
    output_root: Path,
) -> Path:
    """
    Tạo file `<Tên sách>_image_map.json` theo đúng Quy định đồ án v2.4 (Trang 9 - 10):
    {
      "pairs": [
        { "ch": ["Book.440.jpg"], "vi": ["Book.019.jpg"] },
        ...
      ]
    }
    - Với loại T1: phần Quốc ngữ (`vi`) đọc tăng dần, phần Hán Nôm (`ch`) đọc giảm dần.
    - Xử lý trường hợp chênh lệch 1 trang bìa/mục lục đầu sách (`book_1`: 5 trang `vi` 13-17 ứng với 6 trang `ch` 446-441).
    """
    fname = book_cfg.get("filename") or book_cfg.get("file_name")
    book_name = Path(fname).stem
    total_pages = int(book_cfg.get("total_pdf_pages", 0))
    pm = book_cfg.get("page_mapping", {})

    vi_pages = _expand_ranges(pm.get("vi"))
    ch_pages_desc = list(reversed(_expand_ranges(pm.get("ch"))))

    pairs: List[Dict[str, Any]] = []
    if len(vi_pages) == len(ch_pages_desc):
        for ch_p, vi_p in zip(ch_pages_desc, vi_pages):
            pairs.append(
                {
                    "ch": [build_image_filename(book_name, ch_p, total_pages)],
                    "vi": [build_image_filename(book_name, vi_p, total_pages)],
                }
            )
    elif len(ch_pages_desc) == len(vi_pages) + 1 and book_cfg.get("id") == "book_1":
        # book_1: Kiểm chứng trực tiếp theo số trang tham chiếu in ở góc phải trên bản Quốc ngữ:
        # - 446 <-> 013 (Bìa: Thánh Mẫu Phương Danh)
        # - 445 <-> 014 (Trang ấn ký in '( 445 )')
        # - 444 <-> [015, 016] (Cả 2 trang mục lục Quốc ngữ đều in '( 444 )')
        # - 443 <-> 017 (Trang mục lục Quốc ngữ in '( 443 )')
        # - 442, 441: Bản scan PDF bị thiếu 2 trang Quốc ngữ in số 16 & 17 (trang PDF 018 bị trắng) -> missing/ch
        # - 440..234 <-> 019..225: đối ứng 1-1 chính xác (vi + ch = 459).
        pairs.extend(
            [
                {
                    "ch": [build_image_filename(book_name, 446, total_pages)],
                    "vi": [build_image_filename(book_name, 13, total_pages)],
                },
                {
                    "ch": [build_image_filename(book_name, 445, total_pages)],
                    "vi": [build_image_filename(book_name, 14, total_pages)],
                },
                {
                    "ch": [build_image_filename(book_name, 444, total_pages)],
                    "vi": [
                        build_image_filename(book_name, 15, total_pages),
                        build_image_filename(book_name, 16, total_pages),
                    ],
                },
                {
                    "ch": [build_image_filename(book_name, 443, total_pages)],
                    "vi": [build_image_filename(book_name, 17, total_pages)],
                },
                {
                    "ch": [build_image_filename(book_name, 442, total_pages)],
                    "vi": [],
                    "note": "Bản scan PDF bị thiếu trang Quốc ngữ in số 16 (ứng với trang Nôm 442)",
                },
                {
                    "ch": [build_image_filename(book_name, 441, total_pages)],
                    "vi": [],
                    "note": "Bản scan PDF bị thiếu trang Quốc ngữ in số 17 (ứng với trang Nôm 441)",
                },
            ]
        )
        # Lưu bản sao trang thiếu Quốc ngữ vào missing/ch/ theo Quy định v2.6 (Trang 8)
        missing_ch_dir = output_root / book_name / "missing" / "ch"
        missing_ch_dir.mkdir(parents=True, exist_ok=True)
        for mp in (442, 441):
            m_fname = build_image_filename(book_name, mp, total_pages)
            src_m = output_root / book_name / "ch" / m_fname
            dst_m = missing_ch_dir / m_fname
            if src_m.exists() and not dst_m.exists():
                shutil.copy2(src_m, dst_m)

        # Các trang nội dung chính 440..234 <-> 019..225 (207 cặp 1-1)
        vi_body = [p for p in vi_pages if p >= 19]
        ch_body = [p for p in ch_pages_desc if p <= 440]
        for ch_p, vi_p in zip(ch_body, vi_body):
            pairs.append(
                {
                    "ch": [build_image_filename(book_name, ch_p, total_pages)],
                    "vi": [build_image_filename(book_name, vi_p, total_pages)],
                }
            )
    else:
        min_len = min(len(ch_pages_desc), len(vi_pages))
        for ch_p, vi_p in zip(ch_pages_desc[:min_len], vi_pages[:min_len]):
            pairs.append(
                {
                    "ch": [build_image_filename(book_name, ch_p, total_pages)],
                    "vi": [build_image_filename(book_name, vi_p, total_pages)],
                }
            )

    book_dir = output_root / book_name
    book_dir.mkdir(parents=True, exist_ok=True)
    map_path = book_dir / f"{book_name}_image_map.json"
    map_path.write_text(
        json.dumps({"pairs": pairs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return map_path


def build_updated_pdf_if_needed(
    book_cfg: Dict[str, Any],
    raw_dir: Path,
    output_root: Path,
) -> Optional[Path]:
    """
    Sao chép `<Tên sách>.pdf` vào `output/<Tên sách>/` và tạo `<Tên sách>_updated.pdf`
    nếu sách có xoay trang (ví dụ `book_1` có 29 trang bị xoay 90/180/270 độ)
    theo Quy định đồ án v2.4 (Trang 4, 8).
    """
    fname = book_cfg.get("filename") or book_cfg.get("file_name")
    book_name = Path(fname).stem
    src_pdf = raw_dir / fname
    book_dir = output_root / book_name
    book_dir.mkdir(parents=True, exist_ok=True)

    dst_pdf = book_dir / fname
    if src_pdf.exists() and not dst_pdf.exists():
        shutil.copy2(src_pdf, dst_pdf)

    qc = book_cfg.get("quality_check", {})
    rotated = qc.get("rotated_pdf_pages") or []
    if not rotated:
        return None

    # Ghép lại PDF từ toàn bộ các ảnh đã xoay chuẩn chiều trong thư mục con theo đúng thứ tự trang 1..N
    total_pages = int(book_cfg.get("total_pdf_pages", 0))
    folder_map = build_page_folder_map(book_cfg.get("page_mapping"), total_pages)
    updated_pdf_path = book_dir / f"{book_name}_updated.pdf"

    new_doc = fitz.open()
    for page_num in range(1, total_pages + 1):
        sub = folder_map[page_num]
        img_name = build_image_filename(book_name, page_num, total_pages)
        img_path = book_dir / sub / img_name
        if not img_path.exists():
            continue
        with Image.open(img_path) as im:
            w, h = im.size
        page = new_doc.new_page(width=w, height=h)
        page.insert_image(fitz.Rect(0, 0, w, h), filename=str(img_path))

    new_doc.save(str(updated_pdf_path), deflate=True)
    new_doc.close()
    return updated_pdf_path


def run_generate_image_maps(cfg: Dict[str, Any], book_filter: Optional[str] = None) -> None:
    """Sinh file `<Tên sách>_image_map.json` chuẩn v2.4 cho tất cả các sách trong config.yaml."""
    out_root = Path(cfg["paths"]["output_dir"])
    print("=== TẠO FILE ÁNH XẠ HÌNH ẢNH (<Tên sách>_image_map.json - v2.4) ===")
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        if book_filter and book_filter not in (book_id, fname, Path(fname).stem):
            continue
        map_path = generate_book_image_map(b, out_root)
        data = json.loads(map_path.read_text(encoding="utf-8"))
        print(f"  + [{book_id}] Đã xuất {map_path.name} ({len(data['pairs'])} cặp trang ch <-> vi)")
