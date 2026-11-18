"""
Bước 4 (Phần Quốc ngữ): Pipeline phát hiện dòng và nhận dạng OCR cho các trang chữ Quốc ngữ (`vi/`).
Tuân thủ Quy định đồ án v2.4 (Trang 4, 11, 12, 13):
- Phát hiện bounding box từng dòng ngang bằng thuật toán lọc mực in mặt trước (Foreground Ink Projection)
  giúp loại bỏ hoàn toàn vết in xuyên trang (paper bleed-through) từ mặt sau.
- Tự động loại bỏ số trang đầu trang (VD: `- 19 - ( 440 )`) và tiêu đề chân trang (`Thánh Mẫu Phương Danh`).
- Hỗ trợ nhận dạng chữ Quốc ngữ qua VLM (Gemini / OpenAI-compatible Vision API) kèm lưu cache JSON từng trang
  (`cache/ocr_vi/<Tên sách>/<img_stem>.json`), hoặc chế độ xuất khung dòng chuẩn PPOCRLabel.
"""

import base64
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from src.step4_ppocr_formatter import sort_boxes_quoc_ngu, write_ppocr_files


def detect_quoc_ngu_line_boxes(
    image_path: Path,
    dark_threshold: int = 125,
    y_min_ratio: float = 0.12,
    y_max_ratio: float = 0.81,
    x_min_ratio: float = 0.085,
    x_max_ratio: float = 0.915,
    pad_x: int = 4,
    pad_y: int = 4,
) -> List[List[List[int]]]:
    """
    Phát hiện tọa độ 4 đỉnh của từng dòng chữ Quốc ngữ trên trang scan:
    - Ngưỡng mực đậm `dark_threshold=125` tách sạch chữ in mặt trước khỏi bóng chữ xuyên trang mặt sau.
    - Vùng nội dung chính giới hạn theo tỷ lệ chiều cao `[y_min_ratio, y_max_ratio]` giúp loại bỏ
      số trang đầu trang (y < 12%) và dòng tên sách chân trang (y > 81%).
    """
    im = Image.open(image_path).convert("L")
    w, h = im.size
    arr = np.asarray(im, dtype=np.uint8)

    y_min = int(round(h * y_min_ratio))
    y_max = int(round(h * y_max_ratio))
    x_min = int(round(w * x_min_ratio))
    x_max = int(round(w * x_max_ratio))

    mask = arr < dark_threshold
    mask[:y_min, :] = False
    mask[y_max:, :] = False
    mask[:, :x_min] = False
    mask[:, x_max:] = False

    row_counts = mask.sum(axis=1)
    raw_spans: List[List[int]] = []
    in_line = False
    start_y = 0
    for y in range(y_min, y_max):
        if row_counts[y] >= 5 and not in_line:
            in_line = True
            start_y = y
        elif row_counts[y] < 5 and in_line:
            in_line = False
            if y - start_y >= 8:
                raw_spans.append([start_y, y])
    if in_line and (y_max - start_y) >= 8:
        raw_spans.append([start_y, y_max])

    # Gom các dấu thanh rời sát dòng (khoảng hở < 8px) nhưng không gộp hai dòng liền nhau (chiều cao tối đa < 48px)
    merged: List[List[int]] = []
    for sp in raw_spans:
        if merged and (sp[0] - merged[-1][1] < 8) and (sp[1] - merged[-1][0] < 48):
            merged[-1][1] = sp[1]
        else:
            merged.append(sp)

    polygons: List[List[List[int]]] = []
    for sy, ey in merged:
        band = mask[sy : ey + 1, :]
        col_idx = np.where(band.sum(axis=0) >= 2)[0]
        if len(col_idx) == 0:
            continue
        bx1 = int(max(0, int(col_idx[0]) - pad_x))
        bx2 = int(min(w - 1, int(col_idx[-1]) + pad_x))
        by1 = int(max(0, sy - pad_y))
        by2 = int(min(h - 1, ey + pad_y))
        polygons.append([[bx1, by1], [bx2, by1], [bx2, by2], [bx1, by2]])

    return polygons


def clean_quoc_ngu_line_ocr(text: str) -> str:
    """
    Làm sạch 1 dòng văn bản Quốc ngữ theo Quy định v2.4 (Trang 13):
    - Xóa chỉ mục chú thích [1], (1) nếu lẫn vào dòng.
    - Chuẩn hóa khoảng trắng thừa, giữ nguyên từ cổ và dấu gạch ngang của bản gốc.
    """
    text = re.sub(r"\[\d+\]|\(\d+\)", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


class VietnameseOCREngine:
    """
    Bộ phát hiện dòng và nhận dạng chữ Quốc ngữ (hỗ trợ Gemini Vision / OpenAI-compatible VLM
    hoặc xuất bounding box khung dòng để hậu kiểm trên PPOCRLabel).
    """

    def __init__(
        self,
        backend: str = "auto",
        model_name: Optional[str] = None,
    ) -> None:
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None

        if backend == "auto":
            if self.gemini_api_key:
                self.backend = "gemini"
            elif self.openai_api_key:
                self.backend = "openai"
            else:
                self.backend = "layout_only"
        else:
            self.backend = backend

        self.model_name = model_name or (
            "gemini-2.5-flash" if self.backend == "gemini" else "gpt-4o-mini"
        )

    def _recognize_lines_with_gemini(
        self, image_path: Path, n_lines: int
    ) -> List[str]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.gemini_api_key)
        prompt = (
            "Hãy OCR chính xác từng dòng văn bản chữ Quốc ngữ trong trang sách scan này "
            "(KHÔNG đọc số trang ở đầu trang như '- 19 - ( 440 )', KHÔNG đọc dòng tên sách ở chân trang, "
            "KHÔNG sửa từ cổ hay cách viết cũ, giữ nguyên dấu câu và dấu gạch ngang tên riêng). "
            f"Trang này có khoảng {n_lines} dòng nội dung chính. "
            "Trả về CHỈ một mảng JSON các chuỗi (mỗi phần tử là đúng 1 dòng theo thứ tự từ trên xuống dưới), "
            "không giải thích thêm."
        )
        img_bytes = image_path.read_bytes()
        resp = client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                prompt,
            ],
        )
        raw = (resp.text or "").strip()
        m = re.search(r"\[.*\]", raw, flags=re.S)
        if not m:
            return []
        parsed = json.loads(m.group(0))
        return [clean_quoc_ngu_line_ocr(str(x)) for x in parsed if str(x).strip()]

    def _recognize_lines_with_openai(
        self, image_path: Path, n_lines: int
    ) -> List[str]:
        from openai import OpenAI

        client = OpenAI(api_key=self.openai_api_key, base_url=self.openai_base_url)
        b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
        prompt = (
            "Hãy OCR chính xác từng dòng chữ Quốc ngữ trong phần nội dung chính của trang sách này "
            "(bỏ qua số trang đầu trang và tiêu đề chân trang; giữ nguyên từ cổ và chính tả bản gốc). "
            f"Trang có khoảng {n_lines} dòng. Trả về đúng 1 mảng JSON các chuỗi theo thứ tự từ trên xuống dưới."
        )
        resp = client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            temperature=0.0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\[.*\]", raw, flags=re.S)
        if not m:
            return []
        parsed = json.loads(m.group(0))
        return [clean_quoc_ngu_line_ocr(str(x)) for x in parsed if str(x).strip()]

    def recognize_page(self, image_path: Path) -> List[Dict[str, Any]]:
        """
        Phát hiện khung từng dòng ngang trên ảnh Quốc ngữ và nhận dạng văn bản.
        Trả về danh sách box chuẩn PPOCRLabel sắp xếp từ trên xuống dưới.
        """
        polygons = detect_quoc_ngu_line_boxes(image_path)
        if not polygons:
            return []

        texts: List[str] = []
        if self.backend == "gemini":
            texts = self._recognize_lines_with_gemini(image_path, len(polygons))
        elif self.backend == "openai":
            texts = self._recognize_lines_with_openai(image_path, len(polygons))

        boxes: List[Dict[str, Any]] = []
        for idx, pts in enumerate(polygons):
            txt = texts[idx] if idx < len(texts) else ""
            boxes.append({"transcription": txt, "points": pts})
        return sort_boxes_quoc_ngu(boxes)


def run_ocr_vi_pipeline(
    cfg: Dict[str, Any],
    book_filter: Optional[str] = None,
    max_pages: Optional[int] = None,
    backend: str = "auto",
) -> None:
    """
    Điều phối chạy phát hiện dòng & OCR chữ Quốc ngữ cho thư mục `vi/` của các sách,
    lưu cache từng trang tại `cache/ocr_vi/<Tên sách>/` và xuất `vi/Label.txt` + `vi/fileState.txt`.
    """
    out_root = Path(cfg["paths"]["output_dir"])
    cache_root = Path(cfg["paths"]["cache_dir"])
    engine = VietnameseOCREngine(backend=backend)
    print(f"=== CHẠY OCR CHỮ QUỐC NGỮ (Backend: {engine.backend}) ===")

    processed_new = 0
    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        book_name = Path(fname).stem
        if book_filter and book_filter not in (book_id, fname, book_name):
            continue

        vi_dir = out_root / book_name / "vi"
        book_cache_dir = cache_root / "ocr_vi" / book_name
        book_cache_dir.mkdir(parents=True, exist_ok=True)
        vi_images = sorted(vi_dir.glob("*.jpg"))
        if not vi_images:
            print(f"  [{book_id}] Chưa có ảnh trong {vi_dir}.")
            continue

        annotations: Dict[str, List[Dict[str, Any]]] = {}
        for img_path in vi_images:
            cache_file = book_cache_dir / f"{img_path.stem}.json"
            if cache_file.exists():
                rec = json.loads(cache_file.read_text(encoding="utf-8"))
                annotations[img_path.name] = rec.get("boxes", [])
                continue

            if max_pages is not None and processed_new >= max_pages:
                continue

            boxes = engine.recognize_page(img_path)
            rec = {
                "image_name": img_path.name,
                "backend": engine.backend,
                "boxes": boxes,
            }
            cache_file.write_text(
                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            annotations[img_path.name] = boxes
            processed_new += 1

        if annotations:
            write_ppocr_files(vi_dir, annotations, is_char_level=False)
            print(
                f"  + [{book_id}] Đã xuất vi/Label.txt & vi/fileState.txt "
                f"({len(annotations)}/{len(vi_images)} trang)."
            )
