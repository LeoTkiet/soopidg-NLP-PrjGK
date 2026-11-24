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
import time
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


def _collect_gemini_api_keys() -> List[str]:
    """
    Thu thập danh sách Gemini API key từ biến môi trường theo thứ tự ưu tiên:
    - `GEMINI_API_KEYS` (phân tách bằng dấu phẩy `,` hoặc dấu chấm phẩy `;` hoặc xuống dòng)
    - `GEMINI_API_KEY`, `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, ...
    Tự loại bỏ trùng lặp và khoảng trắng thừa.
    """
    raw_keys: List[str] = []

    for env_name in ("GEMINI_API_KEYS", "GEMINI_API_KEY"):
        pool_str = os.getenv(env_name, "")
        if pool_str.strip():
            for part in re.split(r"[,;\r\n]+", pool_str):
                k = part.strip().strip('"').strip("'")
                if k:
                    raw_keys.append(k)

    # Tự động quét thêm GEMINI_API_KEY_1, GEMINI_API_KEY_2, ... theo thứ tự số
    numbered: List[tuple] = []
    for env_k, env_v in os.environ.items():
        m = re.fullmatch(r"GEMINI_API_KEY_(\d+)", env_k)
        if m and env_v.strip():
            numbered.append((int(m.group(1)), env_v.strip().strip('"').strip("'")))
    for _, val in sorted(numbered, key=lambda x: x[0]):
        raw_keys.append(val)

    deduped: List[str] = []
    seen: set = set()
    for k in raw_keys:
        if k not in seen:
            seen.add(k)
            deduped.append(k)
    return deduped


class GeminiKeyPool:
    """
    Bộ quản lý xoay vòng API Key Pool (Round-Robin + Cooldown theo từng cặp (key, model)):
    - Phân tải đều (round-robin) giữa tất cả các API key hợp lệ được cấu hình.
    - Theo dõi giãn cách (min_delay_seconds) RIÊNG cho từng key để tối đa hóa thông lượng.
    - Khi 1 key dính 429 RPM hoặc 503 tạm thời -> đưa key đó vào cooldown và xoay NGAY sang key khác.
    - Khi 1 key hết quota ngày (PerDay) cho 1 model -> đánh dấu cạn riêng cặp (key, model) và xoay tiếp.
    - Khi 1 key lỗi xác thực (401/403) -> vô hiệu hóa key đó; khi 1 model 404 -> bỏ model đó trên toàn pool.
    """

    def __init__(
        self,
        api_keys: List[str],
        models: List[str],
        min_delay_per_key: float = 4.0,
    ) -> None:
        self.models = list(models)
        self.min_delay_per_key = max(0.0, float(min_delay_per_key))
        self.disabled_models: set = set()
        self._rr_cursor = 0
        self._slots: List[Dict[str, Any]] = []
        for idx, key in enumerate(api_keys, start=1):
            self._slots.append(
                {
                    "label": f"key#{idx}/{len(api_keys)}",
                    "api_key": key,
                    "client": None,
                    "disabled": False,
                    "last_used": 0.0,
                    "cooldown_until": {},   # model_id -> timestamp
                    "fail_streak": {},      # model_id -> int
                    "daily_exhausted": set(),  # set of model_id
                }
            )

    @property
    def size(self) -> int:
        return len(self._slots)

    def _get_client(self, slot: Dict[str, Any]) -> Any:
        if slot["client"] is None:
            from google import genai
            slot["client"] = genai.Client(api_key=slot["api_key"])
        return slot["client"]

    def _select_next_pair(self) -> Optional[tuple]:
        """
        Chọn cặp `(slot, model_id, wait_seconds)` tốt nhất theo thuật toán Round-Robin:
        - Ưu tiên cặp sẵn sàng chạy ngay (wait == 0) ở model ưu tiên cao nhất.
        - Nếu mọi cặp khả dụng đều đang trong cooldown/delay, chọn cặp có thời gian chờ ngắn nhất.
        - Trả về None nếu toàn bộ (key, model) trong pool đã bị vô hiệu hóa / hết quota ngày.
        """
        now = time.time()
        n = len(self._slots)
        active_models = [m for m in self.models if m not in self.disabled_models]
        if not active_models or n == 0:
            return None

        best_choice: Optional[tuple] = None  # (wait_sec, model_rank, offset, slot_idx, model_id)
        for m_rank, model_id in enumerate(active_models):
            for offset in range(n):
                s_idx = (self._rr_cursor + offset) % n
                slot = self._slots[s_idx]
                if slot["disabled"] or model_id in slot["daily_exhausted"]:
                    continue

                ready_at = max(
                    slot["last_used"] + self.min_delay_per_key if slot["last_used"] > 0 else 0.0,
                    slot["cooldown_until"].get(model_id, 0.0),
                )
                wait_s = max(0.0, ready_at - now)
                if wait_s == 0.0:
                    # Sẵn sàng ngay lập tức -> chọn luôn và đẩy con trỏ round-robin
                    self._rr_cursor = (s_idx + 1) % n
                    return (slot, model_id, 0.0)

                cand = (wait_s, m_rank, offset, s_idx, model_id)
                if best_choice is None or cand < best_choice:
                    best_choice = cand

        if best_choice is None:
            return None
        wait_s, _, _, s_idx, model_id = best_choice
        self._rr_cursor = (s_idx + 1) % n
        return (self._slots[s_idx], model_id, wait_s)

    def mark_success(self, slot: Dict[str, Any], model_id: str) -> None:
        slot["last_used"] = time.time()
        slot["fail_streak"][model_id] = 0
        slot["cooldown_until"].pop(model_id, None)

    def mark_invalid_key(self, slot: Dict[str, Any]) -> None:
        slot["disabled"] = True

    def mark_model_unavailable(self, model_id: str) -> None:
        self.disabled_models.add(model_id)

    def mark_daily_exhausted(self, slot: Dict[str, Any], model_id: str) -> None:
        slot["last_used"] = time.time()
        slot["daily_exhausted"].add(model_id)

    def mark_temp_cooldown(
        self, slot: Dict[str, Any], model_id: str, suggested_wait: Optional[float] = None
    ) -> float:
        now = time.time()
        slot["last_used"] = now
        streak = slot["fail_streak"].get(model_id, 0) + 1
        slot["fail_streak"][model_id] = streak
        if suggested_wait is not None and suggested_wait <= 90.0:
            cd = suggested_wait + 2.0
        else:
            cd = min(60.0, 8.0 * (2 ** (streak - 1)))
        slot["cooldown_until"][model_id] = now + cd
        return cd


class VietnameseOCREngine:
    """
    Bộ phát hiện dòng và nhận dạng chữ Quốc ngữ (hỗ trợ Gemini Vision với API Key Pool Rotation
    + fallback model khi gặp 503/429, OpenAI-compatible VLM, hoặc layout_only cho PPOCRLabel).
    """

    DEFAULT_GEMINI_FALLBACKS = [
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
    ]

    def __init__(
        self,
        backend: str = "auto",
        model_name: Optional[str] = None,
        min_delay_seconds: Optional[float] = None,
    ) -> None:
        self.gemini_api_keys = _collect_gemini_api_keys()
        self.gemini_api_key = self.gemini_api_keys[0] if self.gemini_api_keys else ""
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None
        self.min_delay_seconds = (
            min_delay_seconds
            if min_delay_seconds is not None
            else float(os.getenv("OCR_VI_DELAY_SECONDS", "4.0"))
        )

        if backend == "auto":
            if self.gemini_api_keys:
                self.backend = "gemini"
            elif self.openai_api_key:
                self.backend = "openai"
            else:
                self.backend = "layout_only"
        else:
            self.backend = backend

        env_model = os.getenv("GEMINI_MODEL", "").strip()
        self.model_name = model_name or env_model or (
            "gemini-2.5-flash" if self.backend == "gemini" else "gpt-4o-mini"
        )
        chain = [self.model_name] + [
            m for m in self.DEFAULT_GEMINI_FALLBACKS if m != self.model_name
        ]
        self.gemini_models = chain
        self.key_pool = (
            GeminiKeyPool(
                api_keys=self.gemini_api_keys,
                models=self.gemini_models,
                min_delay_per_key=self.min_delay_seconds,
            )
            if self.gemini_api_keys
            else None
        )
        self.active_model_used = self.model_name
        self.active_key_label = "key#1/1"

    @staticmethod
    def _is_auth_error(exc: Exception) -> bool:
        msg = str(exc).upper()
        return any(
            kw in msg
            for kw in (
                "401",
                "403",
                "API_KEY_INVALID",
                "API KEY NOT VALID",
                "ACCESS_TOKEN_TYPE_UNSUPPORTED",
                "PERMISSION_DENIED",
                "UNAUTHENTICATED",
            )
        )

    @staticmethod
    def _is_model_unavailable_error(exc: Exception) -> bool:
        msg = str(exc).upper()
        return any(
            kw in msg
            for kw in ("404", "NOT_FOUND", "NO LONGER AVAILABLE", "DEPRECATED", "NOT SUPPORTED")
        )

    @staticmethod
    def _is_daily_quota_error(exc: Exception) -> bool:
        msg = str(exc)
        return "PerDay" in msg or "per_day" in msg.lower() or "GenerateRequestsPerDay" in msg

    @staticmethod
    def _extract_retry_delay_seconds(exc: Exception) -> Optional[float]:
        msg = str(exc)
        m = re.search(r"retry(?:\s+in|\s*Delay['\":\s]+)\s*(\d+(?:\.\d+)?)\s*s", msg, flags=re.I)
        if m:
            return float(m.group(1))
        return None

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        msg = str(exc).upper()
        return any(
            kw in msg
            for kw in (
                "503",
                "UNAVAILABLE",
                "429",
                "RESOURCE_EXHAUSTED",
                "OVERLOADED",
                "RATE",
                "TIMEOUT",
                "DEADLINE",
                "500",
                "INTERNAL",
            )
        )

    def _call_gemini_json(self, contents: List[Any]) -> Any:
        """
        Gọi Gemini Vision với JSON output thông qua `GeminiKeyPool` (Round-Robin Rotation):
        - Xoay vòng qua tất cả các key khả dụng trong pool.
        - Khi 1 key dính 429/503 -> đưa riêng key đó vào cooldown và chuyển NGAY sang key tiếp theo.
        - Khi hết lượt ngày (PerDay) trên 1 (key, model) -> đánh dấu cạn và xoay tiếp.
        """
        from google.genai import types

        if self.key_pool is None or self.key_pool.size == 0:
            raise RuntimeError("Chưa cấu hình GEMINI_API_KEY hoặc GEMINI_API_KEYS trong .env!")

        max_attempts = max(12, self.key_pool.size * len(self.gemini_models) * 2)
        last_exc: Optional[Exception] = None

        for _ in range(max_attempts):
            picked = self.key_pool._select_next_pair()
            if picked is None:
                break
            slot, model_id, wait_s = picked
            if wait_s > 0:
                print(
                    f"    [Pool Wait] Tất cả key đang cooldown, đợi {wait_s:.0f}s "
                    f"rồi chạy {slot['label']} ({model_id})...",
                    flush=True,
                )
                time.sleep(wait_s)

            try:
                client = self.key_pool._get_client(slot)
                resp = client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                    ),
                )
                self.key_pool.mark_success(slot, model_id)
                self.active_model_used = model_id
                self.active_key_label = slot["label"]
                raw = (resp.text or "").strip()
                try:
                    return json.loads(raw)
                except Exception:
                    m = re.search(r"(\{.*\}|\[.*\])", raw, flags=re.S)
                    if m:
                        return json.loads(m.group(1))
                    return None
            except Exception as exc:
                last_exc = exc
                if self._is_model_unavailable_error(exc):
                    self.key_pool.mark_model_unavailable(model_id)
                    print(
                        f"    [Bỏ qua model] {model_id} không khả dụng (404), chuyển model khác...",
                        flush=True,
                    )
                    continue
                if self._is_auth_error(exc):
                    self.key_pool.mark_invalid_key(slot)
                    print(
                        f"    [Key lỗi] {slot['label']} không hợp lệ (401/403), loại khỏi pool...",
                        flush=True,
                    )
                    continue
                if not self._is_retryable_error(exc):
                    raise
                if self._is_daily_quota_error(exc):
                    self.key_pool.mark_daily_exhausted(slot, model_id)
                    print(
                        f"    [Xoay Pool] {slot['label']} hết quota ngày cho {model_id} -> xoay sang key/model khác...",
                        flush=True,
                    )
                    continue
                suggested_wait = self._extract_retry_delay_seconds(exc)
                cd = self.key_pool.mark_temp_cooldown(slot, model_id, suggested_wait)
                print(
                    f"    [Xoay Pool] {slot['label']} ({model_id}) tạm nghẽn ({str(exc)[:75]}...) "
                    f"-> cooldown {cd:.0f}s, xoay ngay sang key khác...",
                    flush=True,
                )

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Toàn bộ API key và model Gemini trong pool đều đã cạn quota hoặc không khả dụng.")

    def _recognize_lines_with_gemini(
        self, image_path: Path, n_lines: int
    ) -> List[str]:
        from google.genai import types

        prompt = (
            "Hãy OCR chính xác từng dòng văn bản chữ Quốc ngữ trong trang sách scan này "
            "(KHÔNG đọc số trang ở đầu trang như '- 19 - ( 440 )', KHÔNG đọc dòng tên sách ở chân trang, "
            "KHÔNG sửa từ cổ hay cách viết cũ, giữ nguyên dấu câu và dấu gạch ngang tên riêng). "
            f"Trang này có khoảng {n_lines} dòng nội dung chính. "
            "Trả về CHỈ một mảng JSON các chuỗi (mỗi phần tử là đúng 1 dòng theo thứ tự từ trên xuống dưới)."
        )
        parsed = self._call_gemini_json(
            [
                types.Part.from_bytes(data=image_path.read_bytes(), mime_type="image/jpeg"),
                prompt,
            ]
        )
        if not isinstance(parsed, list):
            return []
        return [clean_quoc_ngu_line_ocr(str(x)) for x in parsed if str(x).strip()]

    def recognize_pages_batch_gemini(
        self, page_items: List[tuple]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Gom nhiều trang Quốc ngữ (mặc định 5 trang) vào CÙNG 1 request Gemini để tiết kiệm 5x quota RPD/RPM.
        `page_items`: danh sách `(image_path, polygons)`.
        """
        from google.genai import types

        n_pages = len(page_items)
        contents: List[Any] = [
            (
                f"Bạn nhận được {n_pages} trang sách chữ Quốc ngữ liên tiếp (đánh số từ \"1\" đến \"{n_pages}\"). "
                "Hãy OCR chính xác từng dòng văn bản nội dung chính của MỖI trang:\n"
                "- KHÔNG đọc số trang ở đầu trang (VD: '- 19 - ( 440 )').\n"
                "- KHÔNG đọc dòng tiêu đề tên sách ở chân trang.\n"
                "- KHÔNG sửa từ cổ hay chính tả bản in gốc; giữ nguyên dấu câu và dấu gạch ngang tên riêng.\n"
                f"Trả về CHỈ một JSON object có đúng các khóa \"1\"..\"{n_pages}\", mỗi khóa ứng với một mảng JSON "
                "các chuỗi dòng chữ của trang đó theo thứ tự từ trên xuống dưới."
            )
        ]
        for idx, (img_path, polygons) in enumerate(page_items, start=1):
            contents.append(f"=== TRANG {idx} (khoảng {len(polygons)} dòng nội dung chính) ===")
            contents.append(
                types.Part.from_bytes(data=img_path.read_bytes(), mime_type="image/jpeg")
            )

        parsed = self._call_gemini_json(contents)
        results: Dict[str, List[Dict[str, Any]]] = {}
        if not isinstance(parsed, dict):
            return results

        for idx, (img_path, polygons) in enumerate(page_items, start=1):
            raw_lines = parsed.get(str(idx))
            if not isinstance(raw_lines, list):
                continue
            texts = [clean_quoc_ngu_line_ocr(str(x)) for x in raw_lines if str(x).strip()]
            boxes: List[Dict[str, Any]] = []
            for p_idx, pts in enumerate(polygons):
                txt = texts[p_idx] if p_idx < len(texts) else ""
                if not txt.strip():
                    continue
                boxes.append({"transcription": txt, "points": pts})
            results[img_path.name] = sort_boxes_quoc_ngu(boxes)
        return results

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
            if self.backend != "layout_only" and not txt.strip():
                continue
            boxes.append({"transcription": txt, "points": pts})
        return sort_boxes_quoc_ngu(boxes)


def _extract_page_num_from_filename(image_path: Path) -> Optional[int]:
    """Trích xuất số trang PDF (int) từ tên file ảnh `<Tên sách>.<STT>[_<sub_idx>].jpg`."""
    try:
        tail = image_path.stem.rsplit(".", 1)[-1].split("_")[0]
        return int(tail)
    except Exception:
        return None


def run_ocr_vi_pipeline(
    cfg: Dict[str, Any],
    book_filter: Optional[str] = None,
    max_pages: Optional[int] = None,
    backend: str = "auto",
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    batch_size: Optional[int] = None,
) -> None:
    """
    Điều phối chạy phát hiện dòng & OCR chữ Quốc ngữ cho thư mục `vi/` của các sách,
    lưu cache từng trang tại `cache/ocr_vi/<Tên sách>/` và xuất `vi/Label.txt` + `vi/fileState.txt`.
    Khi dùng Gemini, tự động gom `batch_size` trang (mặc định 5 trang) vào 1 request để tiết kiệm 5x quota.
    """
    out_root = Path(cfg["paths"]["output_dir"])
    cache_root = Path(cfg["paths"]["cache_dir"])
    engine = VietnameseOCREngine(backend=backend)
    eff_batch = (
        batch_size
        if batch_size is not None
        else max(1, int(os.getenv("OCR_VI_BATCH_SIZE", "5")))
    )
    pool_info = (
        f" | Pool: {engine.key_pool.size} API key"
        if engine.backend == "gemini" and engine.key_pool is not None
        else ""
    )
    print(
        f"=== CHẠY OCR CHỮ QUỐC NGỮ (Backend: {engine.backend}{pool_info}"
        f"{f' | Gom {eff_batch} trang/request' if engine.backend == 'gemini' and eff_batch > 1 else ''}) ==="
    )
    if start_page is not None or end_page is not None:
        print(f"- Phạm vi lọc trang: {start_page or 'đầu'} -> {end_page or 'cuối'}")
    if engine.backend == "layout_only":
        print(
            "[CẢNH BÁO] Chưa cấu hình GEMINI_API_KEY hoặc OPENAI_API_KEY trong .env!\n"
            "  -> Đang chạy chế độ 'layout_only' (CHỈ vẽ khung dòng, văn bản để trống).\n"
            "  -> Hãy điền GEMINI_API_KEY vào .env để nhận dạng đầy đủ chữ Quốc ngữ."
        )

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
        pending_images: List[Path] = []
        for img_path in vi_images:
            cache_file = book_cache_dir / f"{img_path.stem}.json"
            if cache_file.exists():
                rec = json.loads(cache_file.read_text(encoding="utf-8"))
                cached_boxes = rec.get("boxes", [])
                if rec.get("backend") != "layout_only":
                    cached_boxes = [b for b in cached_boxes if str(b.get("transcription", "")).strip()]
                annotations[img_path.name] = cached_boxes
                continue
            pnum = _extract_page_num_from_filename(img_path)
            if pnum is not None:
                if start_page is not None and pnum < start_page:
                    continue
                if end_page is not None and pnum > end_page:
                    continue
            pending_images.append(img_path)

        if max_pages is not None:
            remaining_budget = max(0, max_pages - processed_new)
            pending_images = pending_images[:remaining_budget]

        print(
            f"-> [{book_id}] {book_name}: Đã có cache {len(annotations)}/{len(vi_images)} trang | "
            f"Cần chạy mới: {len(pending_images)} trang."
        )

        stop_book = False
        try:
            if engine.backend == "gemini" and eff_batch > 1:
                for start_idx in range(0, len(pending_images), eff_batch):
                    if stop_book:
                        break
                    chunk = pending_images[start_idx : start_idx + eff_batch]
                    page_items = []
                    for img_p in chunk:
                        polys = detect_quoc_ngu_line_boxes(img_p)
                        if not polys:
                            rec = {
                                "image_name": img_p.name,
                                "backend": engine.backend,
                                "model": engine.active_model_used,
                                "boxes": [],
                            }
                            (book_cache_dir / f"{img_p.stem}.json").write_text(
                                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                            annotations[img_p.name] = []
                            processed_new += 1
                        else:
                            page_items.append((img_p, polys))

                    if not page_items:
                        continue

                    names_preview = ", ".join(p.name.rsplit(".", 2)[-2] for p, _ in page_items)
                    print(
                        f"  + Đang OCR batch {len(page_items)} trang [{names_preview}] ...",
                        flush=True,
                    )
                    try:
                        batch_res = engine.recognize_pages_batch_gemini(page_items)
                        for img_p, _ in page_items:
                            boxes = batch_res.get(img_p.name)
                            if boxes is None:
                                # Fallback chạy đơn lẻ nếu 1 trang bị thiếu khóa JSON
                                boxes = engine.recognize_page(img_p)
                            rec = {
                                "image_name": img_p.name,
                                "backend": engine.backend,
                                "model": engine.active_model_used,
                                "boxes": boxes,
                            }
                            (book_cache_dir / f"{img_p.stem}.json").write_text(
                                json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                            )
                            annotations[img_p.name] = boxes
                            processed_new += 1
                        print(
                            f"    => OK batch {len(page_items)} trang "
                            f"({engine.active_key_label} | model={engine.active_model_used} | "
                            f"tổng đã xong: {len(annotations)}/{len(vi_images)}).",
                            flush=True,
                        )
                    except Exception as exc:
                        print(f"  [LỖI OCR-VI] Dừng ở batch [{names_preview}]: {exc}")
                        stop_book = True
            else:
                for img_path in pending_images:
                    if stop_book:
                        break
                    try:
                        print(
                            f"  + Đang OCR Quốc ngữ ({engine.backend}): {img_path.name} ...",
                            flush=True,
                        )
                        boxes = engine.recognize_page(img_path)
                        rec = {
                            "image_name": img_path.name,
                            "backend": engine.backend,
                            "model": getattr(engine, "active_model_used", engine.model_name),
                            "boxes": boxes,
                        }
                        (book_cache_dir / f"{img_path.stem}.json").write_text(
                            json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8"
                        )
                        annotations[img_path.name] = boxes
                        processed_new += 1
                        print(
                            f"    => OK ({len(boxes)} dòng | model={rec['model']}). Đã lưu cache.",
                            flush=True,
                        )
                    except Exception as exc:
                        print(f"  [LỖI OCR-VI] Dừng ở ảnh {img_path.name}: {exc}")
                        stop_book = True
        finally:
            if annotations:
                write_ppocr_files(vi_dir, annotations, is_char_level=False)
                print(
                    f"  + [{book_id}] Đã xuất vi/Label.txt & vi/fileState.txt "
                    f"({len(annotations)}/{len(vi_images)} trang)."
                )
