"""
Bước 4 (Phần Nôm): Client gọi Bộ API Kim Hán Nôm (https://kimhannom.fit.hcmus.edu.vn)
Tuân thủ nghiêm ngặt tài liệu "Hướng dẫn sử dụng API Kim Hán Nôm" (Phiên bản 2026-10-10):
1. POST /api/web/clc-sinonom/image-upload
2. POST /api/web/clc-sinonom/structure-classification
3. POST /api/web/clc-sinonom/image-ocr
4. POST /api/web/clc-sinonom/image-rec

Giới hạn số lượt gọi (Rate Limits):
- Phút: 25 lượt
- Giờ: 50 lượt
- Ngày: 200 lượt
- Tuần: 600 lượt
"""

import base64
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from PIL import Image

from src.config import DEFAULT_USER_AGENT, PROJECT_ROOT
from src.step4_ppocr_formatter import (
    expand_sinonom_boxes,
    sort_boxes_sinonom_vertical,
    write_ppocr_files,
)
from src.step6_text_cleaner_aligner import normalize_pua_chars


class RateLimitExceededError(RuntimeError):
    """Ngoại lệ khi chạm ngưỡng giới hạn API theo giờ/ngày/tuần."""


class KimHanNomAPIClient:
    """Client giao tiếp với hệ thống Kim Hán Nôm kèm bộ đếm Rate Limit và lưu Cache."""

    def __init__(
        self,
        bearer_token: str,
        base_url: str = "https://kimhannom.fit.hcmus.edu.vn",
        user_agent: str = DEFAULT_USER_AGENT,
        min_delay_seconds: float = 3.0,
        usage_log_path: Optional[Path] = None,
        email: str = "",
        password: str = "",
        enforce_local_quota: bool = True,
    ) -> None:
        if user_agent.lower().startswith("python-requests"):
            raise ValueError(
                "User-Agent KHÔNG được bắt đầu bằng 'python-requests' theo quy định API!"
            )
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token.strip()
        self.user_agent = user_agent
        self.min_delay_seconds = min_delay_seconds
        self.usage_log_path = usage_log_path or Path("cache/api_usage_log.json")
        self.usage_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.email = email
        self.password = password
        self.enforce_local_quota = enforce_local_quota
        self._last_request_ts = 0.0

    def _is_token_valid(self) -> bool:
        """Kiểm tra JWT token có đủ 3 phần (header.payload.signature) và chưa hết hạn."""
        parts = self.bearer_token.split(".")
        if len(parts) != 3 or len(parts[2]) < 50:
            return False
        try:
            padded = parts[1] + "=" * (-len(parts[1]) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            exp = int(payload.get("exp", 0))
            return exp - time.time() > 120
        except Exception:
            return False

    def ensure_valid_token(self) -> None:
        """Tự động đăng nhập lại qua /account/login nếu token hết hạn hoặc bị cắt cụt."""
        if self._is_token_valid():
            return
        if not self.email or not self.password:
            return
        s = requests.Session()
        s.headers.update({"User-Agent": self.user_agent})
        resp = s.post(
            f"{self.base_url}/account/login",
            data={"UserName": self.email, "Password": self.password},
            allow_redirects=False,
            timeout=20,
        )
        new_token = s.cookies.get("token")
        if new_token:
            self.bearer_token = new_token.strip()
            env_path = PROJECT_ROOT / ".env"
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
                updated = [
                    f"KIMHANNOM_BEARER_TOKEN={self.bearer_token}"
                    if line.startswith("KIMHANNOM_BEARER_TOKEN=")
                    else line
                    for line in lines
                ]
                env_path.write_text("\n".join(updated) + "\n", encoding="utf-8")
            print("  [Auth] Đã tự động làm mới Bearer Token từ hệ thống Kim Hán Nôm.")

    def _get_headers(self, is_json: bool = True) -> Dict[str, str]:
        """Tạo header bắt buộc gồm User-Agent và Authorization: Bearer <token>."""
        self.ensure_valid_token()
        headers = {
            "User-Agent": self.user_agent,
            "Authorization": f"Bearer {self.bearer_token}",
        }
        if is_json:
            headers["Content-Type"] = "application/json"
        return headers

    def get_quota_status(self) -> Dict[str, int]:
        """Trả về số lượt gọi đã dùng trong phút/giờ/ngày/tuần hiện tại."""
        history: List[float] = []
        if self.usage_log_path.exists():
            try:
                history = json.loads(self.usage_log_path.read_text(encoding="utf-8"))
            except Exception:
                history = []
        now = time.time()
        return {
            "used_min": sum(1 for t in history if now - t <= 60),
            "used_hour": sum(1 for t in history if now - t <= 3600),
            "used_day": sum(1 for t in history if now - t <= 86400),
            "used_week": sum(1 for t in history if now - t <= 7 * 86400),
        }

    def _respect_rate_limit(self) -> None:
        """
        Đảm bảo độ trễ tối thiểu giữa các request và kiểm tra giới hạn:
        25/phút, 50/giờ, 200/ngày, 600/tuần.
        Nếu chạm ngưỡng 25/phút thì tự động đợi cho tới khi cửa sổ 60s trôi qua.
        """
        now = time.time()
        elapsed = now - self._last_request_ts
        if elapsed < self.min_delay_seconds:
            time.sleep(self.min_delay_seconds - elapsed)

        history: List[float] = []
        if self.usage_log_path.exists():
            try:
                history = json.loads(self.usage_log_path.read_text(encoding="utf-8"))
            except Exception:
                history = []

        now = time.time()
        last_min = [t for t in history if now - t <= 60]
        if len(last_min) >= 25:
            wait_sec = max(1.0, 60.5 - (now - min(last_min)))
            print(f"  [RateLimit] Đã gọi 25 lượt/phút, tạm nghỉ {wait_sec:.1f}s...")
            time.sleep(wait_sec)
            now = time.time()

        last_hour = [t for t in history if now - t <= 3600]
        last_day = [t for t in history if now - t <= 86400]
        last_week = [t for t in history if now - t <= 7 * 86400]

        if self.enforce_local_quota:
            if len(last_hour) >= 50:
                raise RateLimitExceededError("Chạm giới hạn API Kim Hán Nôm: 50 lượt/giờ!")
            if len(last_day) >= 200:
                raise RateLimitExceededError("Chạm giới hạn API Kim Hán Nôm: 200 lượt/ngày!")
            if len(last_week) >= 600:
                raise RateLimitExceededError("Chạm giới hạn API Kim Hán Nôm: 600 lượt/tuần!")

        last_week.append(now)
        self.usage_log_path.write_text(json.dumps(last_week), encoding="utf-8")
        self._last_request_ts = now

    @staticmethod
    def _parse_envelope(response: requests.Response) -> Dict[str, Any]:
        """Kiểm tra ResponseEnvelope chuẩn: {is_success, code, message, data}."""
        response.raise_for_status()
        payload = response.json()
        if not payload.get("is_success") or payload.get("code") != "000000":
            raise RuntimeError(
                f"Kim Hán Nôm API trả về lỗi (code={payload.get('code')}): {payload.get('message')}"
            )
        return payload.get("data", {})

    def upload_image(self, image_path: Path) -> str:
        """
        1. Tải ảnh lên: POST /api/web/clc-sinonom/image-upload
        Trả về file_name tạm trên máy chủ (ví dụ: 'tempd561fba0e59e48dbaaeac2189a9deef8.jpg').
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-upload"
        with open(image_path, "rb") as img_file:
            files = {"image_file": (image_path.name, img_file, "image/jpeg")}
            resp = requests.post(
                url,
                headers=self._get_headers(is_json=False),
                files=files,
                timeout=60,
            )
        data = self._parse_envelope(resp)
        return data["file_name"]

    def classify_structure(self, server_file_name: str) -> Dict[str, Any]:
        """
        2. Phân loại cấu trúc ảnh: POST /api/web/clc-sinonom/structure-classification
        Trả về: {ocr_id, lang_type, reading_direction, is_sino_nom}
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/structure-classification"
        body = {"file_name": server_file_name}
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=60
        )
        return self._parse_envelope(resp)

    def ocr_image(
        self,
        server_file_name: str,
        ocr_id: int = 1,
        lang_type: int = 2,
        reading_direction: int = 1,
        epitaph: int = 0,
        tag: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        3. OCR ảnh chữ Hán Nôm: POST /api/web/clc-sinonom/image-ocr
        Tham số:
        - ocr_id: 1 (Thông thường, chiều dọc), 2 (Hành chính), 3 (Ngoại cảnh), 4 (Thông thường, chiều ngang)
        - lang_type: 0 (Chưa biết), 1 (Chữ Hán), 2 (Chữ Nôm)
        - reading_direction: 1 (Dọc - mặc định), 2 (Ngang)
        - epitaph: 0 (Văn bản thông thường), 1 (Văn bia)
        - tag: null hoặc model_id chuyên biệt
        Trả về: {result_file_name, result_ocr_text, result_bbox}
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-ocr"
        body = {
            "ocr_id": ocr_id,
            "lang_type": lang_type,
            "reading_direction": reading_direction,
            "epitaph": epitaph,
            "tag": tag,
            "file_name": server_file_name,
        }
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=120
        )
        return self._parse_envelope(resp)

    def recognize_cropped_image(
        self,
        server_file_name: str,
        ocr_id: int = 1,
        lang_type: int = 2,
        reading_direction: int = 1,
    ) -> Dict[str, Any]:
        """
        4. Nhận dạng ảnh đã cắt từ bounding box: POST /api/web/clc-sinonom/image-rec
        Dùng khi image-ocr trả về bounding box không hợp lệ.
        """
        self._respect_rate_limit()
        url = f"{self.base_url}/api/web/clc-sinonom/image-rec"
        body = {
            "ocr_id": ocr_id,
            "lang_type": lang_type,
            "reading_direction": reading_direction,
            "file_name": server_file_name,
        }
        resp = requests.post(
            url, headers=self._get_headers(is_json=True), json=body, timeout=60
        )
        return self._parse_envelope(resp)


def _normalize_single_polygon(raw_box: Any) -> Optional[List[List[int]]]:
    """Chuẩn hóa tọa độ 1 bounding box từ API về đúng 4 đỉnh [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]."""
    if isinstance(raw_box, dict):
        raw_box = raw_box.get("points") or raw_box.get("bbox") or raw_box.get("box")
    if not isinstance(raw_box, (list, tuple)):
        return None

    # Định dạng trả về thực tế của Kim Hán Nôm API (PaddleOCR):
    # [ [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], ["text", confidence] ]
    if (
        len(raw_box) == 2
        and isinstance(raw_box[0], (list, tuple))
        and len(raw_box[0]) == 4
    ):
        raw_box = raw_box[0]

    # Trường hợp [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    if len(raw_box) == 4 and all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in raw_box):
        return [[int(round(float(pt[0]))), int(round(float(pt[1])))] for pt in raw_box]

    # Trường hợp [x1, y1, x2, y2] (xmin, ymin, xmax, ymax)
    if len(raw_box) == 4 and all(isinstance(v, (int, float)) for v in raw_box):
        x1, y1, x2, y2 = [int(round(float(v))) for v in raw_box]
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    # Trường hợp [x1, y1, x2, y2, x3, y3, x4, y4]
    if len(raw_box) == 8 and all(isinstance(v, (int, float)) for v in raw_box):
        vals = [int(round(float(v))) for v in raw_box]
        return [
            [vals[0], vals[1]],
            [vals[2], vals[3]],
            [vals[4], vals[5]],
            [vals[6], vals[7]],
        ]

    return None


def _is_margin_header_or_pagenum(
    pts: List[List[int]],
    text: str,
    img_width: int,
    img_height: int,
) -> bool:
    """
    Kiểm tra xem bounding box có phải là số trang hoặc tiêu đề lề trang (running header/folio)
    nằm ngoài khung nội dung chính hay không (Quy định Trang 6: Không đánh khung cho số trang,
    tiêu đề đầu trang, chân trang).
    """
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Số trang ở mép trên hoặc mép dưới
    if max_y < img_height * 0.085 or min_y > img_height * 0.92:
        return True

    # Tiêu đề sách / số tờ khắc in ở ngoài lề trái (x_max <= 17% chiều rộng trang)
    if max_x <= img_width * 0.17 and len(text) <= 10:
        return True

    # Gáy sách in tiêu đề tên sách ('圣母芳名' / '聖母芳名') hoặc số tờ chữ Hán ở vùng lề trái mở rộng (<= 23%)
    if max_x <= img_width * 0.23 and len(text) <= 6:
        if "圣母芳名" in text or "聖母芳名" in text:
            return True
        if min_y >= img_height * 0.60 and re.fullmatch(r"[一二三四五六七八九十百零廿卅\d]+", text):
            return True

    # Họa tiết hoa thị khung bìa bị OCR nhầm thành '米'/'来' đơn lẻ ở 4 góc/viền
    if text in ("米", "来") and (max_x <= img_width * 0.28 or min_x >= img_width * 0.72 or max_y <= img_height * 0.28 or min_y >= img_height * 0.75):
        return True

    # Hoặc ở sát mép phải ngoài khung
    if min_x >= img_width * 0.88 and len(text) <= 10:
        return True

    return False


def convert_api_result_to_ppocr_boxes(
    api_data: Dict[str, Any],
    img_width: int = 800,
    img_height: int = 1135,
    pad_x: int = 6,
    pad_y: int = 8,
    min_col_gap: int = 2,
) -> List[Dict[str, Any]]:
    """
    Chuyển kết quả trả về của API image-ocr ({result_ocr_text, result_bbox, details})
    sang danh sách bounding box chuẩn PPOCRLabel, lọc bỏ tiêu đề lề/số trang,
    mở rộng khung an toàn (tránh cắt nét chữ Nôm) và sắp xếp theo cột dọc từ phải sang trái.
    """
    raw_texts = api_data.get("result_ocr_text") or []
    raw_bboxes = api_data.get("result_bbox") or []
    details_list = []
    if isinstance(api_data.get("details"), dict):
        details_list = api_data["details"].get("details") or []

    boxes: List[Dict[str, Any]] = []
    if details_list:
        for item in details_list:
            pts = _normalize_single_polygon(item)
            if pts is None:
                continue
            clean_txt = normalize_pua_chars(str(item.get("transcription") or "").strip())
            if not clean_txt or _is_margin_header_or_pagenum(pts, clean_txt, img_width, img_height):
                continue
            box_obj: Dict[str, Any] = {"transcription": clean_txt, "points": pts}
            if "difficult" in item:
                box_obj["difficult"] = bool(item["difficult"])
            boxes.append(box_obj)
    elif raw_bboxes:
        for idx, b in enumerate(raw_bboxes):
            pts = _normalize_single_polygon(b)
            if pts is None:
                continue
            clean_txt = ""
            if (
                isinstance(b, (list, tuple))
                and len(b) == 2
                and isinstance(b[1], (list, tuple))
                and len(b[1]) >= 1
            ):
                clean_txt = str(b[1][0]).strip()
            elif isinstance(b, dict):
                clean_txt = str(b.get("transcription") or b.get("text") or "").strip()
            elif idx < len(raw_texts):
                clean_txt = str(raw_texts[idx]).strip()

            clean_txt = normalize_pua_chars(clean_txt)
            if not clean_txt:
                continue
            if _is_margin_header_or_pagenum(pts, clean_txt, img_width, img_height):
                continue
            boxes.append({"transcription": clean_txt, "points": pts})

    # Nếu API chỉ trả về result_ocr_text mà result_bbox rỗng ([]),
    # khởi tạo các cột dọc tạm từ phải sang trái để mở và tinh chỉnh trên PPOCRLabel
    if not boxes and raw_texts:
        non_empty = [normalize_pua_chars(str(t).strip()) for t in raw_texts if str(t).strip()]
        n_cols = len(non_empty)
        margin_x = int(img_width * 0.12)
        margin_top = int(img_height * 0.10)
        margin_bot = int(img_height * 0.90)
        usable_w = max(100, img_width - 2 * margin_x)
        col_step = usable_w / max(1, n_cols)
        col_w = max(16, int(col_step * 0.75))

        for idx, clean_txt in enumerate(non_empty):
            x_right = int(round(img_width - margin_x - idx * col_step))
            x_left = max(0, x_right - col_w)
            pts = [
                [x_left, margin_top],
                [x_right, margin_top],
                [x_right, margin_bot],
                [x_left, margin_bot],
            ]
            boxes.append({"transcription": clean_txt, "points": pts})

    sorted_boxes = sort_boxes_sinonom_vertical(boxes)
    if pad_x > 0 or pad_y > 0:
        return expand_sinonom_boxes(
            sorted_boxes,
            img_width=img_width,
            img_height=img_height,
            pad_x=pad_x,
            pad_y=pad_y,
            min_col_gap=min_col_gap,
        )
    return sorted_boxes


def ocr_single_nom_image_with_cache(
    client: KimHanNomAPIClient,
    image_path: Path,
    book_cache_dir: Path,
    ocr_params: Dict[str, Any],
    bbox_padding: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Chạy OCR cho 1 ảnh chữ Hán Nôm qua API Kim Hán Nôm (bỏ qua bước structure-classification
    để tiết kiệm 1/3 quota) và lưu cache JSON ngay lập tức.
    Nếu file cache đã tồn tại thì đọc trực tiếp từ cache (không tốn request).
    """
    book_cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = book_cache_dir / f"{image_path.stem}.json"

    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if "result_ocr_text" in cached or "boxes" in cached:
                return cached
        except Exception:
            pass

    server_fname = client.upload_image(image_path)
    api_data = client.ocr_image(
        server_file_name=server_fname,
        ocr_id=int(ocr_params.get("ocr_id", 1)),
        lang_type=int(ocr_params.get("lang_type", 2)),
        reading_direction=int(ocr_params.get("reading_direction", 1)),
        epitaph=int(ocr_params.get("epitaph", 0)),
        tag=ocr_params.get("tag"),
    )

    with Image.open(image_path) as im:
        w, h = im.size
    pad_cfg = bbox_padding or {}
    boxes = convert_api_result_to_ppocr_boxes(
        api_data,
        img_width=w,
        img_height=h,
        pad_x=int(pad_cfg.get("sinonom_pad_x", 6)),
        pad_y=int(pad_cfg.get("sinonom_pad_y", 8)),
        min_col_gap=int(pad_cfg.get("min_col_gap", 2)),
    )

    record = {
        "image_name": image_path.name,
        "width": w,
        "height": h,
        "server_file_name": server_fname,
        "result_file_name": api_data.get("result_file_name"),
        "result_ocr_text": api_data.get("result_ocr_text", []),
        "result_bbox": api_data.get("result_bbox", []),
        "boxes": boxes,
    }
    cache_file.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def export_cached_nom_to_ppocr(
    ch_dir: Path,
    book_cache_dir: Path,
    bbox_padding: Optional[Dict[str, int]] = None,
) -> int:
    """
    Tổng hợp toàn bộ kết quả JSON đã có trong cache của 1 cuốn sách
    để xuất ra ch/Label.txt và ch/fileState.txt theo chuẩn PPOCRLabel.
    Trả về số trang đã xuất nhãn.
    """
    pad_cfg = bbox_padding or {}
    pad_x = int(pad_cfg.get("sinonom_pad_x", 6))
    pad_y = int(pad_cfg.get("sinonom_pad_y", 8))
    min_col_gap = int(pad_cfg.get("min_col_gap", 2))

    annotations: Dict[str, List[Dict[str, Any]]] = {}
    for img_path in sorted(ch_dir.glob("*.jpg")):
        cache_file = book_cache_dir / f"{img_path.stem}.json"
        if not cache_file.exists():
            continue
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            w = int(data.get("width", 800))
            h = int(data.get("height", 1135))
            if data.get("result_bbox") or data.get("result_ocr_text") or data.get("details"):
                boxes = convert_api_result_to_ppocr_boxes(
                    data,
                    img_width=w,
                    img_height=h,
                    pad_x=pad_x,
                    pad_y=pad_y,
                    min_col_gap=min_col_gap,
                )
                data["boxes"] = boxes
                cache_file.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            else:
                boxes = data.get("boxes", [])
            annotations[img_path.name] = boxes
        except Exception:
            continue

    if annotations:
        write_ppocr_files(ch_dir, annotations, is_char_level=False)
    return len(annotations)


def _extract_page_num_from_filename(image_path: Path) -> Optional[int]:
    """Trích xuất số trang PDF (int) từ tên file ảnh `<Tên sách>.<STT>[_<sub_idx>].jpg`."""
    try:
        tail = image_path.stem.rsplit(".", 1)[-1].split("_")[0]
        return int(tail)
    except Exception:
        return None


def run_ocr_nom_pipeline(
    cfg: Dict[str, Any],
    book_filter: Optional[str] = None,
    max_pages: Optional[int] = None,
    start_page: Optional[int] = None,
    end_page: Optional[int] = None,
    ignore_local_quota: bool = False,
) -> None:
    """
    Điều phối chạy OCR chữ Hán Nôm qua API Kim Hán Nôm cho các sách trong config.yaml.
    Tự động đọc cache, kiểm soát quota (25/phút, 50/giờ, 200/ngày, 600/tuần),
    hỗ trợ lọc khoảng trang (`start_page`..`end_page`) để chia đều giữa các thành viên,
    và xuất file ch/Label.txt + ch/fileState.txt sau mỗi đợt chạy.
    """
    out_root = Path(cfg["paths"]["output_dir"])
    cache_root = Path(cfg["paths"]["cache_dir"])
    api_cfg = cfg.get("kimhannom_api", {})
    rate_cfg = api_cfg.get("rate_limits", {})
    default_params = api_cfg.get("default_params", {})
    bbox_padding = api_cfg.get("bbox_padding", {})

    token = cfg.get("auth", {}).get("bearer_token", "").strip()
    email = cfg.get("auth", {}).get("email", "").strip()
    password = cfg.get("auth", {}).get("password", "").strip()
    has_token = bool(token) and not token.startswith("<") and token != "PASTE_YOUR_COOKIE_TOKEN_HERE"
    has_login = bool(email) and not email.startswith("<") and bool(password)

    if not has_token and not has_login:
        print(
            "[CẢNH BÁO] Chưa cấu hình KIMHANNOM_BEARER_TOKEN hoặc KIMHANNOM_EMAIL/PASSWORD hợp lệ trong .env! "
            "Sẽ chỉ tổng hợp từ dữ liệu cache sẵn có."
        )

    client = KimHanNomAPIClient(
        bearer_token=token if has_token else "",
        base_url=cfg["auth"]["base_url"],
        user_agent=cfg["auth"]["user_agent"],
        min_delay_seconds=float(rate_cfg.get("min_delay_seconds", 3.0)),
        usage_log_path=cache_root / "api_usage_log.json",
        email=email,
        password=password,
        enforce_local_quota=not ignore_local_quota,
    )

    quota = client.get_quota_status()
    print("=== CHẠY OCR HÁN NÔM QUA API KIM HÁN NÔM ===")
    if ignore_local_quota:
        print(
            "- [Chế độ] Đã tắt giới hạn chặn cục bộ (--ignore-local-quota); "
            "vẫn giữ delay 3s/request và dừng ngay nếu máy chủ trả lỗi."
        )
    if start_page is not None or end_page is not None:
        print(f"- Phạm vi lọc trang: {start_page or 'đầu'} -> {end_page or 'cuối'}")
    print(
        f"- Quota đã dùng: {quota['used_min']}/25 (phút) | "
        f"{quota['used_hour']}/50 (giờ) | "
        f"{quota['used_day']}/200 (ngày) | "
        f"{quota['used_week']}/600 (tuần)"
    )

    new_api_pages = 0
    stop_api_calls = not (has_token or has_login)

    for b in cfg.get("books", []):
        fname = b.get("filename") or b.get("file_name")
        book_id = b.get("id", "")
        book_name = Path(fname).stem
        if book_filter and book_filter not in (book_id, fname, book_name):
            continue

        ch_dir = out_root / book_name / "ch"
        book_cache_dir = cache_root / "ocr_nom" / book_name
        ch_images = sorted(ch_dir.glob("*.jpg"))
        if not ch_images:
            print(f"\n[{book_id}] {book_name}: Chưa có ảnh trong {ch_dir}. Hãy chạy --step extract trước!")
            continue

        target_images = []
        for img in ch_images:
            pnum = _extract_page_num_from_filename(img)
            if pnum is not None:
                if start_page is not None and pnum < start_page:
                    continue
                if end_page is not None and pnum > end_page:
                    continue
            target_images.append(img)

        cached_count = sum(
            1 for img in target_images if (book_cache_dir / f"{img.stem}.json").exists()
        )
        print(
            f"\n-> [{book_id}] {book_name}: Phạm vi {len(target_images)}/{len(ch_images)} trang ch/ "
            f"(Đã có cache: {cached_count}/{len(target_images)})"
        )

        for img_path in target_images:
            cache_file = book_cache_dir / f"{img_path.stem}.json"
            if cache_file.exists():
                continue
            if stop_api_calls:
                break
            if max_pages is not None and new_api_pages >= max_pages:
                print(f"  [Info] Đã đạt giới hạn --max-pages={max_pages} trang mới trong phiên này.")
                stop_api_calls = True
                break

            try:
                print(f"  + Đang gọi API Kim Hán Nôm cho: {img_path.name} ...", flush=True)
                rec = ocr_single_nom_image_with_cache(
                    client=client,
                    image_path=img_path,
                    book_cache_dir=book_cache_dir,
                    ocr_params=default_params,
                    bbox_padding=bbox_padding,
                )
                new_api_pages += 1
                n_boxes = len(rec.get("boxes", []))
                print(f"    => Thành công ({n_boxes} cột/vùng chữ). Đã lưu cache.")
            except RateLimitExceededError as rle:
                print(f"  [TẠM DỪNG QUOTA] {rle}")
                stop_api_calls = True
                break
            except Exception as exc:
                print(f"  [LỖI API] Không thể OCR ảnh {img_path.name}: {exc}")
                stop_api_calls = True
                break

        exported = export_cached_nom_to_ppocr(
            ch_dir, book_cache_dir, bbox_padding=bbox_padding
        )
        if exported > 0:
            print(f"   Đã cập nhật ch/Label.txt & ch/fileState.txt ({exported}/{len(ch_images)} trang).")
