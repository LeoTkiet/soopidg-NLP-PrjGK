"""
Bước 8: Kiểm tra cấu trúc dữ liệu trước khi nộp và đóng gói file ZIP theo đúng Quy định (Trang 4 - 5).
Cấu trúc yêu cầu:
<MSSV1_MSSV2_MSSV3>.zip/
|-- <Tên sách>/
|   |-- ch/ (Label.txt, fileState.txt, *.jpg, [Label_char.txt, fileState_char.txt])
|   |-- vi/ (Label.txt, fileState.txt, *.jpg)
|   |-- intro/ (nếu có)
|   |-- ref/ (nếu có)
|   |-- toc/ (nếu có)
|   |-- blank/ (nếu có)
|   |-- misc/ (nếu có)
|   |-- <Tên sách>.pdf
|   |-- <Tên sách>_updated.pdf (nếu có)
|   |-- <Tên sách>.xlsx
|   `-- <Tên sách>.csv
|-- <MSSV1_MSSV2_MSSV3>_report.pdf
|-- source.zip
`-- extras.zip (nếu có)
"""

from pathlib import Path
from typing import List


def verify_book_submission_folder(book_dir: Path, book_name: str) -> List[str]:
    """
    Kiểm tra tính hợp lệ của thư mục <Tên sách>/ trước khi nén nộp bài.
    Trả về danh sách các cảnh báo/lỗi nếu thiếu file bắt buộc.
    """
    errors: List[str] = []

    required_files = [
        book_dir / f"{book_name}.pdf",
        book_dir / f"{book_name}.xlsx",
        book_dir / f"{book_name}.csv",
        book_dir / "ch" / "Label.txt",
        book_dir / "ch" / "fileState.txt",
        book_dir / "vi" / "Label.txt",
        book_dir / "vi" / "fileState.txt",
    ]
    for req in required_files:
        if not req.exists():
            errors.append(f"Thiếu file bắt buộc: {req}")

    return errors

