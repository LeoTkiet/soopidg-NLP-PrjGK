# Báo Cáo Tiến Độ Dự Án & Kế Hoạch Tiếp Theo
**Cập nhật lần cuối**: 19/11/2026  
**Mã nhóm**: `24120356_24120386_24120399`  
**Báo cáo gửi giảng viên đợt 19/11**: Xem chi tiết tại [`docs/REPORT_19_11_2026.md`](REPORT_19_11_2026.md)

---

## 1. Tổng Hợp Các Hạng Mục Đã Hoàn Thành (Giai Đoạn 1 & Khởi Động Giai Đoạn 2)

### 1.1. Cấu hình môi trường & Xác thực tự động (`.env`, `config.yaml`, `src/config.py`)
- **Đồng bộ cấu hình**:
  - Sửa đường dẫn bộ từ điển `dictionary_entries_dir` trỏ đúng vào `Data/dictionaries-04-11-2026/entries` (kiểm tra `OK` toàn bộ 7 file `.jsonl` trọng tâm).
  - Đồng bộ mã nhóm `GROUP_ID=24120356_24120386_24120399` trên cả `.env` và `config.yaml`.
- **Khắc phục lỗi Token & Tự động làm mới JWT**:
  - Phát hiện token copy thủ công từ trình duyệt bị cắt ở 500 ký tự (thiếu phần chữ ký `.signature`, gây lỗi `InvalidChunkLength` khi gọi API) và có thời hạn chỉ 60 phút.
  - Bổ sung cơ chế tự động đăng nhập lại (`ensure_valid_token`) qua endpoint `POST /account/login` trong `src/step2_kimhannom_api.py`, tự động lấy chuỗi JWT đầy đủ (964 ký tự) và cập nhật vào `.env` khi token sắp hết hạn.

### 1.2. Khảo sát chi tiết 1.431 trang PDF & Lập bảng phân trang (`config.yaml`)
Đã hoàn thành khảo sát chất lượng ảnh, phát hiện trang xoay/trang quét đúp và lập bảng ánh xạ trang (`page_mapping`) chính xác tuyệt đối cho cả 4 tập sách:

| Mã sách | Tên tác phẩm | Tổng trang PDF | `vi/` | `ch/` | `intro/` | `toc/` | `blank/` | `misc/` | Công thức đối ứng & Ghi chú chất lượng |
| :--- | :--- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :--- |
| **`book_1`** | `T1_Thánh Mẫu Phương Danh (Tập 1).pdf` | **455** | 212 | 213 | 7 | 8 | 9 | 6 | - Phát hiện **29 trang** phần Nôm có cờ xoay PDF (`90°/180°/270°`): `[233, 245, 259, 263, 264, 270, 273, 290, 294, 313, 315, 317, 321, 330, 335, 343, 345, 347, 348, 349, 354, 362, 379, 389, 409, 419, 425, 429, 434]`.<br>- Đối ứng 1-1 từ trang 19 đến 225: $\text{PDF}_{vi} + \text{PDF}_{ch} = 459$. |
| **`book_2`** | `T1_Thánh Mẫu Phương Danh (Tập 2).pdf` | **311** | 145 | 145 | 3 | 6 | 8 | 4 | - Không có trang xoay hay quét đúp. Trang 153 ghi chú `(BỊ RÁCH TỪ ĐÂY)` được đưa vào `misc/`.<br>- Đối ứng 1-1 toàn bộ 145 trang: $\text{PDF}_{vi} + \text{PDF}_{ch} = 311$ ($\text{Sách}_{vi} + \text{Sách}_{ch} = 308$). |
| **`book_3`** | `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 1).pdf` | **388** | 163 | 163 | 4 | 5 | 8 | 45 | - Phát hiện **42 trang quét đúp** (26 trang `vi`, 14 trang `ch`, 2 trang `toc/blank` cuối sách): `[77..78, 83..84, 107..108, 117..118, 121..122, 125..126, 129..130, 145..146, 161..162, 165..166, 169..172, 181..182, 279..280, 287..288, 309..314, 345..346, 359..360, 387..388]`.<br>- Sau khi lọc sang `misc/`, còn đúng **163 trang `vi` $\leftrightarrow$ 163 trang `ch`** ($\text{Sách}_{vi} + \text{Sách}_{ch} = 349$). |
| **`book_4`** | `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 2).pdf` | **277** | 128 | 128 | 2 | 4 | 9 | 6 | - Phát hiện **4 trang quét đúp** `[5, 6, 95, 96]` đã lọc sang `misc/blank`.<br>- Còn đúng **128 trang `vi` $\leftrightarrow$ 128 trang `ch`** ($\text{Sách}_{vi} + \text{Sách}_{ch} = 274$). |
| **Tổng** | **4 Tập sách (`T1`)** | **1.431** | **648** | **649** | **16** | **23** | **34** | **61** | **Tổng số trang cần OCR: 648 trang `vi/` + 649 trang `ch/`** |

### 1.3. Chiết xuất & Phân loại toàn bộ 1.431 ảnh độ phân giải gốc (`src/step1_pdf_extractor.py`)
- Xử lý triệt để hiện tượng chia sẻ từ điển `/Resources /XObject` trong PDF ở các tập 2, 3, 4 (trích xuất đúng luồng JPEG gốc `800x1135` của từng trang thay vì render lại).
- Tự động xoay chuẩn chiều đứng cho 29 trang bị xoay trong `book_1`.
- Đã chạy lệnh `python main.py --step extract` tạo đầy đủ **1.431 file `.jpg`** chuẩn cú pháp `<Tên sách>.<STT>.jpg` trong `output/<Tên sách>/<thư_mục_con>/`.

### 1.4. Hoàn thiện Pipeline OCR Hán Nôm & Kiểm thử API (`src/step2_kimhannom_api.py`)
- Tối ưu quy trình gọi API: chỉ gọi `image-upload` + `image-ocr` (bỏ qua `structure-classification`), giảm số request từ 3 xuống **2 request/trang** (tiết kiệm $33\%$ quota).
- Tự động bóc tách đa giác 4 đỉnh từ cấu trúc `[[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ["text", score]]`, lọc bỏ tiêu đề sách ngoài lề trái (`圣母芳名`) và số trang, đồng thời gom cụm cột dọc từ phải sang trái (`src/step4_ppocr_formatter.py`).
- Đã chạy kiểm thử thành công trên `book_1` (`234.jpg`, `235.jpg`, `439.jpg`, `440.jpg`), lưu cache tại `cache/ocr_nom/` và xuất chuẩn xác `output/T1_Thánh Mẫu Phương Danh (Tập 1)/ch/Label.txt` & `fileState.txt`.

### 1.5. Hoàn thành Gói Dữ Liệu Mẫu 2 Cặp Trang Nộp Kiểm Tra Tiến Độ Chủ Nhật 08/11/2026 (`scripts/build_sample_submission.py`)
- Đã xây dựng trọn bộ gói mẫu theo **Phương án A (2 trang đầu phần *Tựa* của `book_1`)**:
  - **Cặp 1**: Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg` $\leftrightarrow$ Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg`
  - **Cặp 2**: Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg` $\leftrightarrow$ Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg`
- Đã tích hợp bảng chuẩn hóa ký tự PUA (`PUA_NORMALIZATION_MAP` trong `src/step6_text_cleaner_aligner.py`), hỗ trợ đọc quan hệ chữ dị thể `relations` từ `cjkvi_variants.jsonl` (`src/step5_dictionary_loader.py`), và tách âm tiết tên phiên âm có gạch nối `-` (`src/step7_exporter_evaluator.py`).
- **Kết quả đánh giá gói mẫu (`submission/24120356_24120386_24120399_sample.zip`)**:
  - Tổng số câu dóng hàng: **8 câu** (`.440.1` $\to$ `.440.6` và `.439.1` $\to$ `.439.2`, đã ghép câu vắt qua trang `.440.6` đúng quy định Trang 8).
  - Tổng số chữ / âm tiết: **248 chữ Nôm $\leftrightarrow$ 248 âm tiết Quốc ngữ** (khớp 1-1 tuyệt đối 100%).
  - Số chữ màu đen (`#000000`): **241 / 248 chữ**; Số chữ màu đỏ (`#FF0000`): **7 chữ** (đều là âm tiết phiên âm tên riêng nước ngoài: *Li-gô-ri-ô*, *Ma-ri-a*, *Pha-lăng-côn*, *Âu-gu-tinh*).
  - **Độ tương đồng đạt `97.18%` ($\ge 95\%$ — ĐẠT CHUẨN NỘP BÀI)**.

### 1.6. Khắc phục Góp ý Giảng viên & Nâng cấp Toàn diện Pipeline lên Chuẩn v2.4 (19/11/2026)
- **Khắc phục góp ý mở rộng Bounding Box chữ Nôm** (`src/step4_ppocr_formatter.py`, `src/step2_kimhannom_api.py`, `config.yaml`):
  - Cài đặt thuật toán `expand_sinonom_boxes` mở rộng tự động `pad_x=+6px` mỗi bên trái/phải và `pad_y=+8px` đầu/cuối cột kèm bảo vệ chống chồng lấn giữa các cột dọc liền kề (`min_col_gap=2px`).
  - Xuất ảnh đối chiếu trực quan trước/sau (`submission/preview/preview_ch_440_before_after.jpg` & `preview_ch_439_before_after.jpg`) xác nhận 100% nét chữ Nôm được bao trọn, không cắt nét.
- **Nâng cấp đồng bộ toàn bộ mã nguồn theo Quy định đồ án v2.4 (16/11/2026)**:
  - `src/step1_pdf_extractor.py`: Bổ sung `generate_book_image_map` (đã xuất `<Tên sách>_image_map.json` cho cả 4 tập = **648 cặp trang**) và `build_updated_pdf_if_needed`.
  - `src/step3_vietnamese_ocr.py`: Cài đặt bộ tách dòng mực đậm (`Foreground Ink Projection` loại bỏ vết in xuyên trang) kết hợp VLM OCR (`gemini-2.5-flash` / OpenAI-compatible) và cache JSON theo trang.
  - `src/step5_dictionary_loader.py`: Bổ sung cache nhị phân `cache/dict_index.pkl` giúp giảm thời gian nạp 6 nguồn từ điển từ ~15s xuống `< 0.2s`.
  - `src/step6_text_cleaner_aligner.py` & `src/step7_exporter_evaluator.py`: Cài đặt thuật toán dóng hàng **Levenshtein có trọng số từ điển**, xóa Variation Selectors (`U+FE00..FE0F`, `U+E0100..E01EF`), xuất 5 cột v2.4 (`img_id, sentence_id, ch_txt, vi_txt, text_diff`) và tô màu `.xlsx` khớp 100% `text_diff` bằng mã màu chuẩn Excel.
  - `src/step8_packager.py`: Cài đặt bộ kiểm tra tự động bắt buộc `validate_book_v24` (`python main.py --step validate`) — đã chạy kiểm chứng gói mẫu v2.4 đạt **`PASS (0 lỗi)`**, độ tương đồng **`97.18%`**.

---

## 2. Kế Hoạch Các Công Việc Tiếp Theo (Next Actions)

### 👤 Việc tiếp theo của Thành Viên 1 (Phụ trách `step1`, `step2` & dữ liệu `book_1`, `book_2`)
1. **Chạy cuốn chiếu OCR Hán Nôm (`--step ocr-nom`) theo quota**:
   - Tổng số trang `ch/` cần OCR của cả 4 tập là **649 trang** (tương ứng **1.298 request** nếu gọi 100% qua API Kim Hán Nôm).
   - Với giới hạn **50 request/giờ (25 trang/giờ)**, **200 request/ngày (100 trang/ngày)**, **600 request/tuần (300 trang/tuần)**:
     ```powershell
     # Chạy tự động theo từng ca (tự dừng khi chạm 50 request/giờ và lưu cache):
     python main.py --step ocr-nom --book book_1
     python main.py --step ocr-nom --book book_2
     ```
   - Kết hợp tài khoản của các thành viên trong nhóm hoặc mô hình OCR chữ Hán/Nôm phụ trợ (PP-OCRv5 / Qwen2.5-VL) cho `book_3` và `book_4` để hoàn thành toàn bộ 649 trang `ch/` trong vòng 2–3 ngày.
2. **Tạo file `<Tên sách>.pdf` và `<Tên sách>_updated.pdf` trong `output/<Tên sách>/`**:
   - Sao chép file PDF gốc vào `output/<Tên sách>/<Tên sách>.pdf` theo đúng yêu cầu đóng gói.
   - Đối với sách có xoay trang (`book_1`) hoặc loại bỏ trang quét đúp (`book_3`, `book_4`), xuất thêm `<Tên sách>_updated.pdf` và ghi chú vào báo cáo.
3. **Chuẩn hóa ký tự PUA (Private Use Area) từ kết quả Kim Hán Nôm**:
   - Một số chữ Nôm trả về từ API Kim Hán Nôm nằm ở vùng mã PUA (`U+F0000..U+FFFFF`, ví dụ `󰜏`, `󰅒`, `󰜋`, `󰑼`). Cần tích hợp bước chuẩn hóa Unicode (qua API `/api/web/clc-sinonom/unicode-normalize` hoặc bảng ánh xạ PUA $\to$ Unicode chuẩn trong từ điển) trước khi đưa vào bước dóng hàng.

### 👤 Việc tiếp theo của Thành Viên 2 (Phụ trách `step3`, `step4` & dữ liệu `book_3`, `book_4`)
1. **Chạy OCR Quốc ngữ hàng loạt (`src/step3_vietnamese_ocr.py`)**:
   - Toàn bộ **648 ảnh Quốc ngữ** trong `output/<Tên sách>/vi/` của cả 4 tập đã sẵn sàng.
   - Hoàn thiện `python main.py --step ocr-vi` để nhận dạng văn bản Tiếng Việt, tự động cắt bỏ dòng số trang đầu trang (ví dụ `- 225 - (234)`) và dòng tiêu đề chân trang (`Thánh Mẫu Phương Danh`), đồng thời xóa các chỉ mục chú thích `(1)`, `[1]`, `(*)`.
2. **Kiểm định trực quan trên `PPOCRLabel` (`src/step4_ppocr_formatter.py`)**:
   - Mở `output/<Tên sách>/ch/` và `output/<Tên sách>/vi/` bằng phần mềm `PPOCRLabel`.
   - Kiểm tra các trường hợp cột chữ Nôm có khoảng trắng tách đoạn (cần tách thành 2 box riêng) hoặc chữ Nôm ghép 2 ký tự ngang, và chụp màn hình phục vụ Phụ lục Báo cáo.

### 👤 Việc tiếp theo của Thành Viên 3 (Phụ trách `step5`, `step6`, `step7`, `step8`)
1. **Xây dựng cache chỉ mục từ điển (`src/step5_dictionary_loader.py`)**:
   - Nạp 7 nguồn từ điển JSONL trong `Data/dictionaries-04-11-2026/entries/` và lưu cache nhị phân vào `cache/dict_index.pkl` để tăng tốc tra cứu âm đọc.
2. **Dóng hàng câu theo cặp trang đối ứng (`src/step6_text_cleaner_aligner.py`)**:
   - Tận dụng công thức đối ứng trang 1-1 đã xác định trong `config.yaml` (ví dụ `book_1`: $\text{PDF}_{vi} + \text{PDF}_{ch} = 459$; `book_2`: $\text{PDF}_{vi} + \text{PDF}_{ch} = 311$) để dóng hàng chính xác từng cặp trang trước khi tách câu, tránh trôi lệch (drift) qua nhiều trang.
3. **Xuất `.csv`, `.xlsx` tô màu Đen/Đỏ & Hậu kiểm $\ge 95\%$ (`src/step7_exporter_evaluator.py`)**:
   - Chạy thử nghiệm dóng hàng + chấm điểm tương đồng ngay trên các trang đã OCR xong của `book_1` để đo tỷ lệ khớp từ điển ban đầu và lọc danh sách từ tô đỏ cần sửa.

