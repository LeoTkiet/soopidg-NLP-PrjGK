# Hướng Dẫn Sử Dụng Dự Án (USER GUIDE)

Tài liệu này hướng dẫn chi tiết cách cài đặt môi trường, cấu hình token API Kim Hán Nôm và chạy toàn bộ quy trình từ đầu đến cuối trên một máy tính mới.

---

## 1. Cài đặt môi trường và thư viện

### Bước 1.1: Tạo môi trường ảo Python
```bash
python -m venv .venv
# Trên Ubuntu / Linux / macOS:
source .venv/bin/activate
# Trên Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
```

### Bước 1.2: Cài đặt các thư viện cố định phiên bản
```bash
pip install -r requirements.txt
```

---

## 2. Cấu hình xác thực API Kim Hán Nôm

Hệ thống sử dụng API chính thức tại `https://kimhannom.fit.hcmus.edu.vn/`.

### Bước 2.1: Lấy `token` từ trình duyệt
1. Mở trình duyệt và truy cập: `https://kimhannom.fit.hcmus.edu.vn/`
2. Đăng nhập bằng tài khoản được cấp:
   - **Tên đăng nhập**: `24120386@student.hcmus.edu.vn`
   - **Mật khẩu**: `KHN@2026`
3. Nhấn `F12` (Inspect) -> mở tab **Application** (Chrome/Edge) hoặc **Storage** (Firefox) -> chọn mục **Cookies** -> `https://kimhannom.fit.hcmus.edu.vn`.
4. Sao chép giá trị (Value) của khóa `token`.

### Bước 2.2: Cập nhật file `.env`
Mở file `.env` ở thư mục gốc dự án và dán giá trị token vào biến `KIMHANNOM_BEARER_TOKEN`:
```env
KIMHANNOM_BASE_URL=https://kimhannom.fit.hcmus.edu.vn
KIMHANNOM_EMAIL=24120386@student.hcmus.edu.vn
KIMHANNOM_PASSWORD=KHN@2026
KIMHANNOM_BEARER_TOKEN=<DÁN_TOKEN_TỪ_COOKIE_VÀO_ĐÂY>
KIMHANNOM_USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
GROUP_ID=24120386_MSSV2_MSSV3
```

> **Lưu ý quan trọng về API Kim Hán Nôm**:
> - `User-Agent` bắt buộc phải giữ nguyên chuỗi mặc định trên (tuyệt đối không để `python-requests/...`).
> - Giới hạn số lượt gọi trên hệ thống: **25 lượt/phút**, **50 lượt/giờ**, **200 lượt/ngày**, **600 lượt/tuần**. Module `src/step2_kimhannom_api.py` đã tích hợp sẵn bộ kiểm soát tốc độ và ghi log tại `cache/api_usage_log.json`.

---

## 3. Các bước chạy Pipeline

### Bước 3.1: Kiểm tra môi trường, dữ liệu sách và từ điển
```bash
python main.py --step check
```

### Bước 3.2: Khởi tạo cấu trúc thư mục đầu ra chuẩn cho 4 cuốn sách
```bash
python main.py --step init
```
Lệnh này sẽ tạo các thư mục `ch`, `vi`, `intro`, `ref`, `toc`, `blank`, `misc` cho từng cuốn sách trong `output/<Tên sách>/`.

### Bước 3.3: Chạy các bước xử lý chính (sau khi các thành viên hoàn thiện từng module)
1. **Chiết xuất & phân loại ảnh từ PDF**:
   ```bash
   python main.py --step extract
   ```
2. **Chạy OCR chữ Hán Nôm qua API Kim Hán Nôm**:
   ```bash
   python main.py --step ocr-nom
   ```
3. **Chạy OCR chữ Quốc ngữ**:
   ```bash
   python main.py --step ocr-vi
   ```
4. **Làm sạch văn bản và Dóng hàng (Alignment) Nôm - Quốc ngữ**:
   ```bash
   python main.py --step align
   ```
5. **Xuất file `.csv`, `.xlsx` (tô màu đen/đỏ) và đánh giá độ tương đồng ($\ge 95\%$)**:
   ```bash
   python main.py --step evaluate
   ```
6. **Kiểm tra cấu trúc & đóng gói file nộp `<MSSV1_MSSV2_MSSV3>.zip`**:
   ```bash
   python main.py --step package
   ```

