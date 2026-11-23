# Bảng Phân Công Công Việc Giai Đoạn Nước Rút (TV2 & TV3)

- **Mã nhóm**: `24120356_24120386_24120399`
- **Ngày giao việc**: `23/11/2026`
- **Hạn nộp cuối kỳ**: Cuối ngày **`29/11/2026`** (Hạn hệ thống: `30/11/2026`)
- **Trạng thái hạ tầng hiện tại (TV1 đã hoàn tất & merge vào `main`)**:
  - Toàn bộ mã nguồn Pipeline 8 bước chuẩn **Quy định đồ án v2.4** (`step1` $\to$ `step8` + `main.py` đã nối đầy đủ `--step align`, `--step evaluate`, `--step validate`, `--step package`).
  - Bảng ánh xạ trang cho **1.431 trang** của 4 tập sách trong `config.yaml` (đã chuyển đường dẫn tương đối để chạy được trên mọi máy).
  - Gói mẫu 2 cặp trang `book_1` đã kiểm chứng đạt **`97.18%`** (`PASS 0 lỗi`).

---

## 1. Thiết Lập Môi Trường Trên Máy Cá Nhân (TV2 & TV3 làm 1 lần — ~10 phút)

### Bước 1: Kéo code mới nhất từ nhánh `main`
```powershell
git pull origin main
```
*(Nếu mới clone lần đầu: `git clone https://github.com/LeoTkiet/soopidg-NLP-PrjGK.git` rồi mở thư mục dự án).*

### Bước 2: Đặt dữ liệu gốc `Data/` vào thư mục dự án
- Tải thư mục `Data/` từ Google Drive chung của nhóm (gồm 4 file `.pdf` và thư mục `dictionaries-04-11-2026/`) đặt đúng vào đường dẫn `<thư_mục_repo>/Data/`.

### Bước 3: Cài đặt thư viện Python
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Bước 4: Tạo file `.env` cá nhân
Copy `.env.example` thành `.env` rồi điền đúng thông tin của **chính bạn**:
```env
KIMHANNOM_BASE_URL=https://kimhannom.fit.hcmus.edu.vn
KIMHANNOM_EMAIL=<MSSV_CUA_BAN>@student.hcmus.edu.vn
KIMHANNOM_PASSWORD=KHN@2026
KIMHANNOM_BEARER_TOKEN=
KIMHANNOM_USER_AGENT="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"

GEMINI_API_KEY=<API_KEY_GEMINI_CUA_BAN>
GROUP_ID=24120356_24120386_24120399
```
> **Lưu ý cực kỳ quan trọng:**
> 1. **Mỗi thành viên PHẢI dùng tài khoản Kim Hán Nôm riêng của mình** (không dùng chung tài khoản TV1) để tận dụng tối đa quota `3 × 200 = 600 req/ngày` (`300 trang Nôm/ngày`). `KIMHANNOM_BEARER_TOKEN` có thể để trống, code sẽ tự động đăng nhập bằng Email & Password.
> 2. **`GEMINI_API_KEY`** lấy miễn phí tại `https://aistudio.google.com/apikey` để chạy OCR Quốc ngữ (`--step ocr-vi`). Nếu để trống, lệnh `ocr-vi` sẽ chỉ vẽ khung dòng trống (`layout_only`).

### Bước 5: Kiểm tra môi trường & Chiết xuất ảnh (chạy 1 lần, ~30 giây)
```powershell
python main.py --step check
python main.py --step extract
python main.py --step image-map
```

---

## 2. Phân Bổ Khối Lượng Toàn Nhóm (Cân Tải & An Toàn Quota 600 req/tuần)

Tổng khối lượng cần OCR còn lại: **645 trang Nôm (`ch/`)** + **648 trang Quốc ngữ (`vi/`)**.  
Giới hạn API Kim Hán Nôm **mỗi tài khoản**: tối đa **25 trang/giờ** (50 req/giờ), **100 trang/ngày** (200 req/ngày), **300 trang/tuần** (600 req/tuần).

| Thành viên | Sách phụ trách OCR (`ch/` & `vi/`) | Tổng quota Nôm | Nhiệm vụ chuyên môn kèm theo |
| :--- | :--- | :---: | :--- |
| **TV1 (`24120386`)** | Trọn gói **`book_1`** (`209 ch` còn lại + `212 vi`) | **~418 req** *(3 ngày)* | - Hậu kiểm `book_1` trên PPOCRLabel & sửa chữ đỏ.<br>- Chạy `--step package` (tạo `_updated.pdf` cho 29 trang xoay của `book_1`).<br>- Tổng hợp báo cáo cuối `<MSSV>_report.pdf`, đóng gói ZIP & nộp bài. |
| **TV2** | - Trọn gói **`book_3`** (`163 ch` + `163 vi`)<br>- **Nửa đầu `book_4` phần `ch/`**: trang `144`–`207` (`64 trang`)<br>- Toàn bộ **`book_4` phần `vi/`** (`128 trang`) | **~454 req** *(3 ngày)* | - Hậu kiểm trực quan trên **PPOCRLabel** cho `book_3` và `book_4`.<br>- Chụp 2 ảnh màn hình PPOCRLabel mẫu (1 trang Nôm + 1 trang Quốc ngữ) gửi TV1 đưa vào Phụ lục Báo cáo.<br>- Sửa danh sách chữ đỏ của `book_3` & `book_4` đạt $\ge 95\%$. |
| **TV3** | - Trọn gói **`book_2`** (`145 ch` + `145 vi`)<br>- **Nửa sau `book_4` phần `ch/`**: trang `208`–`271` (`64 trang`) | **~418 req** *(3 ngày)* | - Gom dữ liệu cache/`Label.txt` của cả 3 người, ghép đủ 128 trang `ch/` của `book_4`.<br>- Chạy `--step align` tạo `.csv`/`.xlsx` v2.4 & báo cáo chữ đỏ (`_red_report.csv`) cho cả 4 tập.<br>- Sửa chữ đỏ `book_2`, chạy `--step evaluate` & `--step validate` đảm bảo **0 lỗi & $\ge 95\%$** cho cả 4 tập. |

---

## 3. Hướng Dẫn Lệnh Chạy Cụ Thể Cho Từng Thành Viên

### 👤 Chi tiết công việc của Thành Viên 2 (TV2)

#### A. Chạy OCR Hán Nôm (`ch/`) — 227 trang (chạy trong 3 ngày: 24/11 – 26/11)
Mỗi ngày chạy **4 ca**, mỗi ca cách nhau ít nhất **1 tiếng**, mỗi ca **25 trang** (code tự lưu cache vào `cache/ocr_nom/` sau từng trang, chạy lại sẽ tự bỏ qua trang đã xong):

```powershell
# Ngày 1 & Ngày 2: Chạy hết book_3 (163 trang -> khoảng 7 ca x 25 trang)
python main.py --step ocr-nom --book book_3 --max-pages 25

# Ngày 2 (ca cuối) & Ngày 3: Chạy nửa đầu book_4 (trang 144 -> 207: 64 trang -> 3 ca)
python main.py --step ocr-nom --book book_4 --start-page 144 --end-page 207 --max-pages 25
```

#### B. Chạy OCR Quốc ngữ (`vi/`) — 291 trang (chạy song song trong 24/11 – 25/11)
```powershell
python main.py --step ocr-vi --book book_3
python main.py --step ocr-vi --book book_4
```
*(Nếu gặp giới hạn RPM của Gemini Free Tier, có thể thêm `--max-pages 30` để chạy từng đợt — code tự đọc cache, không chạy lại trang đã xong).*

#### C. Hậu kiểm trực quan trên PPOCRLabel & Chụp Phụ lục (26/11 – 27/11)
1. Mở lần lượt thư mục `output/T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 1)/ch` và `vi` (và tương tự với Tập 2 sau khi ghép đủ cache từ TV3) trên **PPOCRLabel**.
2. Kiểm tra:
   - Không còn số trang đầu trang, không còn tiêu đề gáy sách / chân trang.
   - Các cột chữ Nôm có khoảng trắng tách đoạn rõ ràng cần tách thành 2 box; mọi box có đúng 4 điểm và không bị cắt nét chữ.
   - Giữ đúng thứ tự đọc (Nôm: phải $\to$ trái, trên $\to$ dưới; Quốc ngữ: trên $\to$ dưới, trái $\to$ phải).
3. Chụp **2 ảnh màn hình rõ nét** (1 trang Nôm, 1 trang Quốc ngữ đang mở trên PPOCRLabel) gửi vào Drive mục `report_assets/`.

#### D. Sửa lỗi chữ đỏ cho `book_3` & `book_4` (28/11)
- Nhận file `cache/reports/<Tên sách>_red_report.csv` từ TV3.
- Đối chiếu từng chữ đỏ với ảnh gốc trong `ch/` và `vi/`, sửa đồng bộ cả `Label.txt` lẫn `.csv`, sau đó chạy kiểm tra:
  ```powershell
  python main.py --step evaluate --book book_3
  python main.py --step validate --book book_3
  python main.py --step evaluate --book book_4
  python main.py --step validate --book book_4
  ```
- Đảm bảo cả 2 tập đạt **Độ tương đồng $\ge 95\%$** và **`PASS (0 lỗi)`**.

---

### 👤 Chi tiết công việc của Thành Viên 3 (TV3)

#### A. Chạy OCR Hán Nôm (`ch/`) — 209 trang (chạy trong 3 ngày: 24/11 – 26/11)
Mỗi ngày chạy **4 ca**, mỗi ca cách nhau ít nhất **1 tiếng**, mỗi ca **25 trang**:

```powershell
# Ngày 1 & Ngày 2: Chạy hết book_2 (145 trang -> 6 ca x 25 trang)
python main.py --step ocr-nom --book book_2 --max-pages 25

# Ngày 2 (ca cuối) & Ngày 3: Chạy nửa sau book_4 (trang 208 -> 271: 64 trang -> 3 ca)
python main.py --step ocr-nom --book book_4 --start-page 208 --end-page 271 --max-pages 25
```

#### B. Chạy OCR Quốc ngữ (`vi/`) — 145 trang (chạy song song trong 24/11 – 25/11)
```powershell
python main.py --step ocr-vi --book book_2
```

#### C. Tổng hợp dữ liệu, Chạy Dóng hàng & Xuất Báo cáo Chữ đỏ (tối 26/11 – 27/11)
1. Tải toàn bộ `cache/ocr_nom/`, `cache/ocr_vi/` và `Label.txt`/`fileState.txt` của TV1 và TV2 từ Drive nhóm gộp vào đúng thư mục `cache/` và `output/` trên máy.
2. Riêng `book_4` (vì phần `ch/` chạy làm 2 nửa giữa TV2 và TV3), sau khi gộp đủ 128 file JSON vào `cache/ocr_nom/T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 2)/`, chạy lệnh sau để xuất lại `ch/Label.txt` đủ 128 trang (không gọi thêm API):
   ```powershell
   python main.py --step ocr-nom --book book_4 --max-pages 0
   ```
3. Chạy dóng hàng tự động & xuất `.csv`, `.xlsx` chuẩn v2.4 kèm báo cáo chữ đỏ cho cả 4 tập:
   ```powershell
   python main.py --step align
   ```
4. Lệnh trên sẽ tự sinh:
   - `output/<Tên sách>/<Tên sách>.csv` (5 cột chuẩn v2.4: `img_id, sentence_id, ch_txt, vi_txt, text_diff`)
   - `output/<Tên sách>/<Tên sách>.xlsx` (tô màu Đen/Đỏ/Vàng khớp 100% `text_diff`)
   - `cache/reports/<Tên sách>_red_report.csv` (danh sách tất cả chữ màu đỏ cần rà soát)
5. Gửi file `_red_report.csv` + `.csv` + `.xlsx` bản nháp của `book_1` cho TV1, của `book_3` & `book_4` cho TV2, và TV3 tự sửa `book_2`.

#### D. Sửa lỗi chữ đỏ `book_2` & Kiểm định tổng thể v2.4 (28/11)
- Sau khi cả 3 thành viên hoàn tất sửa chữ đỏ (cập nhật cả `Label.txt` và `.csv`), chạy lại cho toàn bộ 4 tập:
  ```powershell
  python main.py --step evaluate
  python main.py --step validate
  ```
- Mục tiêu nghiệm thu bắt buộc: **Cả 4 tập đều đạt `PASS (0 lỗi)` và Độ tương đồng $\ge 95\%$**.
- Chụp 2 ảnh màn hình mở file `.xlsx` (không lỗi font, thấy rõ chữ tô màu) và `.csv` (không lệch cột) gửi cho TV1 đưa vào Phụ lục Báo cáo.

---

## 4. Quy Ước Đồng Bộ Dữ Liệu (BẮT BUỘC TUÂN THỦ)

1. **KHÔNG push ảnh `.jpg`, `output/` hoặc `cache/` lên Git** (`.gitignore` đã chặn để tránh nặng repo).
2. **Cuối mỗi ngày (trước 22:00)**, nén và tải lên thư mục Google Drive chung theo cấu trúc:
   - `cache/ocr_nom/<Tên sách>/` (các file `.json` mới sinh ra)
   - `cache/ocr_vi/<Tên sách>/` (các file `.json` mới sinh ra)
   - `output/<Tên sách>/ch/{Label.txt, fileState.txt}` và `output/<Tên sách>/vi/{Label.txt, fileState.txt}`
3. **Quy tắc sửa lỗi chuẩn v2.4 (tránh fail `validate`):**
   - **Đồng bộ 3 nơi**: Hễ sửa chữ trong `.csv` thì PHẢI sửa tương ứng trong `ch/Label.txt` hoặc `vi/Label.txt`, rồi chạy `python main.py --step evaluate --book <id>` để tự cập nhật lại `text_diff` và `.xlsx` (tuyệt đối không sửa tay màu trực tiếp trên Excel rồi bỏ qua `text_diff`).
   - **Giữ nguyên từ cổ bản in gốc** (không tự ý sửa chính tả cổ sang tiếng Việt hiện đại).
   - **Chữ Nôm bị nhận sai do PUA**: Nếu gặp ký tự ô vuông/PUA mới chưa có trong `PUA_NORMALIZATION_MAP` (`src/step6_text_cleaner_aligner.py`), báo ngay vào nhóm để TV1 bổ sung chung cho cả 4 tập.

---

## 5. Mốc Thời Gian Chốt (Deadline 24/11 $\to$ 29/11/2026)

| Ngày | Mục tiêu bắt buộc hoàn thành | Người kiểm chốt |
| :--- | :--- | :--- |
| **Tối 23/11** | Cài môi trường, điền `.env` (tài khoản Kim Hán Nôm riêng + `GEMINI_API_KEY`), chạy xong `--step check`, `--step extract`, `--step image-map`. | TV1, TV2, TV3 |
| **24/11** | Mỗi người xong ít nhất **100 trang `ch/`** + bắt đầu chạy `ocr-vi`. Up cache lên Drive lúc 22:00. | Cả nhóm |
| **25/11** | Mỗi người xong thêm **100 trang `ch/`** (lũy kế 200 trang/người) + hoàn tất **100% `ocr-vi`** cho tập phụ trách. | Cả nhóm |
| **26/11** | Hoàn tất **100% OCR `ch/`** cho cả 4 tập (xong các trang lẻ còn lại); TV3 gộp cache `book_4`, chạy `--step align` và phát danh sách chữ đỏ (`_red_report.csv`). | TV3 chốt bản nháp |
| **27/11** | Hậu kiểm `PPOCRLabel` + bắt đầu sửa chữ đỏ theo tập phụ trách. TV2 gửi 2 ảnh chụp PPOCRLabel. | TV1, TV2, TV3 |
| **28/11** | Hoàn tất sửa chữ đỏ kéo cả 4 tập lên **$\ge 95\%$**; chạy `--step validate` đạt **`PASS (0 lỗi)`** toàn bộ 4 tập. TV3 gửi 2 ảnh chụp Excel/CSV. | TV3 kiểm định, TV1 duyệt |
| **29/11** | TV1 chạy `--step package` (tạo `_updated.pdf` & copy PDF gốc), hoàn thiện `<24120356_24120386_24120399>_report.pdf`, nén `source.zip` & gói nộp cuối, kiểm tra giải nén và nộp bài trước hạn `30/11`. | TV1 |
