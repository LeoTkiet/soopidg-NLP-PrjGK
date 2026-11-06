# Kế Hoạch Chi Tiết & Phân Công Thực Hiện Đồ Án (Nhóm 3 Người)

Tài liệu này tổng hợp đầy đủ các quy định từ `Quy định đồ án_v1.1.pdf`, `Hướng dẫn sử dụng API Kim Hán Nôm.pdf`, cấu trúc từ điển `dictionaries-04-11-2026` và bộ dữ liệu thực tế trong `D:\PrjGK\Data` để phân công cụ thể cho nhóm 3 thành viên.

---

## 1. Phân Tích Dữ Liệu Được Giao & Các Quy Định Cốt Lõi

### 1.1. Khảo sát dữ liệu trong `D:\PrjGK\Data`
Nhóm có **4 file PDF** đều mang mã phân loại **`T1`**:
1. `T1_Thánh Mẫu Phương Danh (Tập 1).pdf` (~184.9 MB)
2. `T1_Thánh Mẫu Phương Danh (Tập 2).pdf` (~137.0 MB)
3. `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 1).pdf` (~177.1 MB)
4. `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 2).pdf` (~96.4 MB)

**Đặc điểm mã `T1` (Phụ lục Trang 15)**:
- Phần **Quốc ngữ** nằm ở nửa đầu file PDF (đọc từ trái sang phải).
- Phần **Hán Nôm** nằm ở nửa cuối file PDF (đọc từ phải sang trái; ví dụ trang 1 Quốc ngữ tương ứng bản dịch của trang cuối Hán Nôm, hoặc 1 trang Quốc ngữ ứng với 2 trang Hán Nôm).
- **Lưu ý sống còn (Trang 2)**: Trước khi chạy OCR hàng loạt, phải xác nhận phạm vi trang Nôm và trang Quốc ngữ khớp nội dung với nhau, kiểm tra chất lượng trang scan (nếu rách/mờ $>20\%$ tổng số trang Nôm phải báo ngay cho người giao tài liệu). Luôn dóng hàng cả trang bìa hoặc mục lục nếu có bản dịch Quốc ngữ tương ứng.

### 1.2. Các quy tắc kỹ thuật bắt buộc phải tuân thủ
1. **Quy tắc đặt tên file ảnh (Trang 5)**:
   - Định dạng bắt buộc: `.jpg` (JPEG), giữ **độ phân giải gốc cao nhất** của PDF.
   - Cú pháp: `<Tên sách>.<Số thứ tự trang>[_<Số thứ tự hình ảnh>].jpg`.
   - `<Tên sách>` phải giữ y nguyên tên file PDF gốc (ví dụ: `T1_Thánh Mẫu Phương Danh (Tập 1).001.jpg`).
   - `<Số thứ tự trang>`: tối thiểu 3 chữ số tính từ `001` (trang đầu của PDF). Nếu $>999$ trang thì viết thẳng `1000`, `1234`.
   - Nếu có xoay trang, chỉnh sáng, làm nét ảnh... bắt buộc phải ghép lại thành `<Tên sách>_updated.pdf` (không trùng lặp ảnh) và báo cáo.
2. **Quy tắc API Kim Hán Nôm (Tài liệu API Trang 1 - 10)**:
   - Header bắt buộc cho mọi request:
     - `User-Agent`: `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0` (Không được bắt đầu bằng `python-requests`).
     - `Authorization`: `Bearer <token>` (lấy khóa `token` trong Cookies sau khi đăng nhập `24120386@student.hcmus.edu.vn` / `KHN@2026`).
   - **Giới hạn lượt gọi (Rate Limit) cực kỳ khắt khe**:
     - Tối đa **25 lượt/phút**, **50 lượt/giờ**, **200 lượt/ngày**, **600 lượt/tuần**.
     - **Chiến lược quan trọng**: Mỗi ảnh nếu gọi đủ `image-upload` + `structure-classification` + `image-ocr` sẽ tốn **3 request**! Nhưng vì ta đã biết trước loại sách là chữ Nôm đọc dọc (`ocr_id=1`, `lang_type=2`, `reading_direction=1`, `epitaph=0`), ta **BỎ QUA** API `structure-classification` để tiết kiệm $33\%$ quota (chỉ tốn 2 request/ảnh: `image-upload` + `image-ocr`), và **lưu cache JSON ngay lập tức** sau mỗi lần gọi! Ngoài ra có thể kết hợp chạy PP-OCRv5 / PaddleOCR local rồi dùng Kim Hán Nôm cho các trang/vùng khó.
3. **Quy tắc file OCR theo chuẩn PPOCRLabel (Trang 6 - 7)**:
   - Trong `ch/` và `vi/` phải có `Label.txt` và `fileState.txt`.
   - Cú pháp `Label.txt`: `<folderName>/<imageName>\t[{"transcription":"...","points":[[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}]\n`.
   - Mỗi box **đúng 4 điểm**, ôm sát chữ, loại bỏ số trang, tiêu đề đầu/chân trang, bảng biểu, tranh ảnh.
   - **Trang Nôm (`ch/`)**: Đánh theo từng cột dọc (thứ tự từ phải sang trái, từ trên xuống dưới). Nếu trong cột có khoảng trắng tách chữ thì tách thành 2 box riêng; nếu chữ Nôm ghép từ 2 ký tự ngang thì đánh 2 box riêng.
   - **Trang Quốc ngữ (`vi/`)**: Đánh theo hàng ngang hoặc đoạn (thứ tự từ trái sang phải, từ trên xuống dưới).
   - Nếu ảnh độ phân giải cao gây lag trên PPOCRLabel, rescale về `1K` để gán nhãn rồi dùng hàm `scale_bboxes` trong `src/step4_ppocr_formatter.py` để upscale tọa độ về độ phân giải gốc.
4. **Quy tắc Dóng hàng & Đánh giá $\ge 95\%$ (Trang 8 - 10)**:
   - File `<Tên sách>.csv` và `<Tên sách>.xlsx` gồm 4 cột: `img_id`, `sentence_id`, `SinoNom_Char`, `ChuQN_txt`.
   - `img_id`: Tên hình ảnh trang Nôm không chứa tên thư mục (vd: `T1_Thánh Mẫu Phương Danh (Tập 1).150.jpg`).
   - `sentence_id`: `<img_id bỏ đuôi .jpg>.<số thứ tự câu tính từ 1>` (vd: `T1_Thánh Mẫu Phương Danh (Tập 1).150.1`).
   - Trong `<Tên sách>.xlsx`: Tô **màu đen** cho cặp chữ Nôm và chữ Quốc ngữ giống nhau về nghĩa/âm trong từ điển; tô **màu đỏ** nếu khác nhau hoặc chữ Nôm không có trong từ điển.
   - Công thức tính điểm:
     $$\text{Độ tương đồng (\%)} = \left(1 - \frac{\text{Tổng số chữ đỏ}}{\text{Tổng số chữ}}\right) \times 100 \ge 95\%$$

---

## 2. Phân Công Nhiệm Vụ Chi Tiết Cho 3 Thành Viên

### 👤 Thành Viên 1 (Trưởng nhóm Kỹ thuật - Phụ trách Tiền xử lý PDF/Ảnh & OCR Hán Nôm)
- **Phạm vi phụ trách code**: `src/step1_pdf_extractor.py`, `src/step2_kimhannom_api.py`.
- **Phạm vi dữ liệu phụ trách kiểm duyệt chính**: 2 tập sách `T1_Thánh Mẫu Phương Danh (Tập 1 & Tập 2)`.
- **Công việc cụ thể**:
  1. Mở 4 file PDF kiểm tra phạm vi trang Quốc ngữ (nửa đầu) và trang Hán Nôm (nửa cuối), lập bảng ánh xạ trang Quốc ngữ $\leftrightarrow$ trang Hán Nôm cho cả 4 tập.
  2. Hoàn thiện `src/step1_pdf_extractor.py`: chiết xuất ảnh `.jpg` giữ nguyên độ phân giải gốc từ PDF, xoay các trang bị ngược, phân loại ảnh vào đúng thư mục `ch/`, `vi/`, `toc/`, `intro/`, `blank/`, `misc/`. Nếu có xoay/chỉnh ảnh thì xuất `<Tên sách>_updated.pdf`.
  3. Lấy Bearer Token từ web Kim Hán Nôm, điều phối chạy `src/step2_kimhannom_api.py` (kết hợp cache để không vượt quota 25/phút, 50/giờ, 200/ngày, 600/tuần) hoặc kết hợp mô hình OCR chữ Hán/Nôm phụ trợ để sinh dữ liệu thô cho thư mục `ch/`.

### 👤 Thành Viên 2 (Phụ trách OCR Quốc ngữ, Chuẩn hóa PPOCRLabel & Hậu kiểm BBox)
- **Phạm vi phụ trách code**: `src/step3_vietnamese_ocr.py`, `src/step4_ppocr_formatter.py`.
- **Phạm vi dữ liệu phụ trách kiểm duyệt chính**: 2 tập sách `T1_Đức Chúa Giêsu Ngự Trong Phép Mình Thánh (Tập 1 & Tập 2)`.
- **Công việc cụ thể**:
  1. Hoàn thiện `src/step3_vietnamese_ocr.py` sử dụng PaddleOCR / VietOCR / VLM để chạy OCR toàn bộ các trang Quốc ngữ trong thư mục `vi/` của cả 4 tập sách.
  2. Viết bộ lọc tự động loại bỏ các bounding box thuộc về số trang, tiêu đề trang (header/footer), chỉ mục chú thích `[1]`, `(1)`.
  3. Hoàn thiện `src/step4_ppocr_formatter.py`: sắp xếp lại thứ tự bounding box chuẩn (Nôm: phải sang trái, trên xuống dưới; Quốc ngữ: trái sang phải, trên xuống dưới), đảm bảo mỗi box đúng 4 điểm, xuất `Label.txt` và `fileState.txt`.
  4. Mở công cụ **PPOCRLabel** kiểm tra trực quan và chụp ảnh màn hình mẫu (một trang Hán Nôm và một trang Quốc ngữ) để đưa vào Phụ lục Báo cáo theo quy định (Trang 10).

### 👤 Thành Viên 3 (Phụ trách Từ điển JSONL, Làm sạch, Dóng hàng & Đánh giá $\ge 95\%$)
- **Phạm vi phụ trách code**: `src/step5_dictionary_loader.py`, `src/step6_text_cleaner_aligner.py`, `src/step7_exporter_evaluator.py`, `src/step8_packager.py`.
- **Phạm vi dữ liệu phụ trách**: Xử lý từ điển, dóng hàng và kiểm định chất lượng đầu ra `.csv` / `.xlsx` cho cả 4 tập sách.
- **Công việc cụ thể**:
  1. Tối ưu hóa `src/step5_dictionary_loader.py`: nạp các từ điển trong `D:\PrjGK\dictionaries-04-11-2026\entries\` (`btcn.jsonl`, `dv.jsonl`, `hannom_rcv.jsonl`, `hvdic.jsonl`, `dnqatv_wikisource.jsonl`, `unihan.jsonl`, `cjkvi_variants.jsonl`) và lưu thành file cache nhị phân (`pickle` hoặc `sqlite`) để tra cứu âm đọc trong $<1$ giây.
  2. Hoàn thiện `src/step6_text_cleaner_aligner.py`:
     - Nối các câu bị ngắt khi chuyển trang.
     - Tách câu và chạy thuật toán dóng hàng (Dynamic Programming dựa trên độ khớp âm tiết Hán Nôm - Quốc ngữ từ bộ từ điển, vì đây là sách dịch âm Công giáo nên tỉ lệ khớp âm tiết 1-1 cực kỳ cao).
  3. Chạy `src/step7_exporter_evaluator.py` để xuất `<Tên sách>.csv` và `<Tên sách>.xlsx` có tô màu đen/đỏ cho từng chữ.
  4. Lọc ra danh sách các câu/chữ bị tô **màu đỏ** để cả 3 thành viên cùng rà soát sửa lỗi nhận dạng OCR (Spellcheck) cho đến khi **Độ tương đồng của từng cuốn đạt $\ge 95\%$**.
  5. Chạy `src/step8_packager.py` kiểm tra toàn bộ cấu trúc file nộp và viết báo cáo `<MSSV1_MSSV2_MSSV3>_report.pdf`.

---

## 3. Lộ Trình Thực Hiện Theo Giai Đoạn (4 Giai Đoạn)

| Giai đoạn | Mục tiêu trọng tâm | Đầu ra nghiệm thu (Deliverables) |
| :--- | :--- | :--- |
| **Giai đoạn 1: Khảo sát & Chiết xuất ảnh** | Kiểm tra chất lượng 4 file PDF, xác định cặp trang Nôm - Quốc ngữ tương ứng, chiết xuất ảnh `.jpg` độ phân giải gốc vào `ch/`, `vi/`, `toc/`, `blank/`, `misc/`. | Thư mục ảnh chuẩn tên `<Tên sách>.<STT>.jpg` và bảng ánh xạ trang của 4 tập sách. |
| **Giai đoạn 2: Chạy OCR Nôm & Quốc ngữ** | Chạy OCR chữ Quốc ngữ (local) và chữ Hán Nôm (qua API Kim Hán Nôm có điều tiết quota + mô hình hỗ trợ). Chuẩn hóa `Label.txt` & `fileState.txt`. | Các file `Label.txt`, `fileState.txt` mở được trên `PPOCRLabel`, đúng thứ tự đọc. |
| **Giai đoạn 3: Làm sạch, Từ điển & Dóng hàng** | Ghép câu chuyển trang, tách câu, dóng hàng bằng chỉ mục từ điển Hán Nôm, xuất `.csv` & `.xlsx` tô màu đen/đỏ. | File `<Tên sách>.csv` và `<Tên sách>.xlsx` bản nháp đầu tiên kèm điểm độ tương đồng. |
| **Giai đoạn 4: Tinh chỉnh $\ge 95\%$ & Đóng gói** | Sửa lỗi các chữ màu đỏ (do OCR nhận nhầm chữ Nôm hoặc Quốc ngữ) để kéo độ tương đồng vượt mốc $95\%$. Hoàn thiện báo cáo & nén ZIP. | Độ tương đồng $\ge 95\%$, `<MSSV>_report.pdf`, `source.zip`, gói nộp hoàn chỉnh. |

