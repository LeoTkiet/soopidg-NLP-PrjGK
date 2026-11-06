# Dự Án Xây Dựng Dữ Liệu Song Song Hán Nôm và Quốc Ngữ

## 1. Giới thiệu dự án
Dự án xây dựng pipeline tự động & bán tự động phục vụ trích xuất hình ảnh từ sách PDF, nhận dạng ký tự quang học (OCR) chữ Hán Nôm (qua hệ thống API Kim Hán Nôm) và chữ Quốc ngữ, chuẩn hóa định dạng PPOCRLabel (`Label.txt`, `fileState.txt`), đối chiếu từ điển Hán Nôm - Quốc ngữ (Schema v1), và dóng hàng câu song ngữ xuất ra `.csv` & `.xlsx` đạt độ tương đồng $\ge 95\%$.

### Danh sách tác phẩm thực hiện (Phân loại `T1`)
1. `T1_Thánh Mẫu Phương Danh (Tập 1).pdf`
2. `T1_Thánh Mẫu Phương Danh (Tập 2).pdf`
3. `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 1).pdf`
4. `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 2).pdf`

> **Đặc điểm phân loại `T1`**: Quốc ngữ nằm ở phần đầu, Hán Nôm nằm ở phần cuối. Thứ tự đọc trang Quốc ngữ từ trái sang phải, thứ tự đọc trang Hán Nôm từ phải sang trái.

---

## 2. Thông tin thành viên nhóm (3 thành viên)
| STT | Họ và tên | MSSV | Email sinh viên | Vai trò chính |
| :--- | :--- | :--- | :--- | :--- |
| 1 | Thành viên 1 | `24120386` | `24120386@student.hcmus.edu.vn` | Tiền xử lý PDF/Ảnh, Kim Hán Nôm API & OCR Nôm |
| 2 | Thành viên 2 | `MSSV2` | `MSSV2@student.hcmus.edu.vn` | OCR Quốc ngữ, Chuẩn hóa PPOCRLabel & Kiểm tra BBox |
| 3 | Thành viên 3 | `MSSV3` | `MSSV3@student.hcmus.edu.vn` | Từ điển JSONL, Làm sạch, Dóng hàng (Align) & Đánh giá $\ge 95\%$ |

---

## 3. Môi trường thực thi (System Environment)
Theo quy định tại mục **Quy định chung về mã nguồn**, dự án được thiết kế và kiểm thử trên môi trường:
- **Hệ điều hành (OS)**: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS (Tương thích đầy đủ trên Windows 10/11).
- **Phiên bản Python**: Python `3.10.x` hoặc `3.11.x`.
- **RAM khuyến nghị**: $\ge 16\text{ GB}$ (để nạp nhanh bộ chỉ mục từ điển Hán Nôm JSONL ~969.000 mục từ).
- **Cấu hình đồ họa (GPU)**: NVIDIA GPU $\ge 8\text{ GB}$ VRAM (tùy chọn nếu chạy thêm mô hình OCR local cho Quốc ngữ) hoặc CPU khi sử dụng API Kim Hán Nôm.
- **Quản lý thư viện**: Tất cả thư viện trong `requirements.txt` đã được cố định phiên bản (`pinned versions`).

---

## 4. Cấu trúc mã nguồn và tài liệu (`docs/`)
```text
D:\PrjGK\
├── config.yaml                      # Cấu hình sách, đường dẫn, tham số API & từ điển
├── requirements.txt                 # Danh sách thư viện đã cố định phiên bản (pinned)
├── .env.example                     # Mẫu cấu hình tài khoản & Bearer Token Kim Hán Nôm
├── main.py                          # CLI điều phối các bước trong pipeline
├── README.md                        # Mô tả dự án và môi trường chạy (file bắt buộc ở root)
├── USER_GUIDE.md                    # Hướng dẫn chạy dự án từ đầu đến cuối (file bắt buộc ở root)
├── docs/                            # Thư mục quản lý tập trung toàn bộ tài liệu dự án
│   ├── ProjectDescription.md        # Mô tả chi tiết dự án làm gì, cần làm gì & kiến trúc Pipeline
│   ├── PLAN_3_MEMBERS.md            # Kế hoạch chi tiết & phân công cho nhóm 3 người
│   ├── USER_GUIDE.md                # Bản sao hướng dẫn sử dụng trong docs/
│   ├── Quy định đồ án_v1.1.pdf      # Tài liệu quy định đồ án chính thức
│   ├── Hướng dẫn sử dụng API Kim Hán Nôm.pdf
│   ├── Mô tả dữ liệu từ điển Hán Nôm và Quốc ngữ.pdf
│   └── ThongBaoDoAn.pdf             # Thông báo tỷ lệ điểm & hạn nộp (30/11/2026)
└── src/
    ├── __init__.py
    ├── config.py                    # Đọc cấu hình từ config.yaml và .env
    ├── step1_pdf_extractor.py       # Chiết xuất ảnh độ phân giải gốc & chia thư mục ch/vi/...
    ├── step2_kimhannom_api.py       # Client gọi 4 API Kim Hán Nôm + kiểm soát Rate Limit
    ├── step3_vietnamese_ocr.py      # Engine OCR cho các trang chữ Quốc ngữ
    ├── step4_ppocr_formatter.py     # Xuất/kiểm tra Label.txt, fileState.txt & scale BBox
    ├── step5_dictionary_loader.py   # Đọc & lập chỉ mục bộ từ điển JSONL (Schema v1)
    ├── step6_text_cleaner_aligner.py# Làm sạch văn bản, tách câu & dóng hàng Nôm - Quốc ngữ
    ├── step7_exporter_evaluator.py  # Xuất .csv, .xlsx (tô màu đen/đỏ) & tính độ tương đồng
    └── step8_packager.py            # Kiểm tra cấu trúc nộp bài & đóng gói ZIP
```

