"""
Bước 5: Chuẩn hóa dữ liệu OCR sang định dạng PPOCRLabel (Label.txt và fileState.txt).
Tuân thủ Quy định chung về file OCR & đánh bounding box (Trang 6 - 7):
- Mỗi dòng trong Label.txt: <folderName>/<imageName>\t[{"transcription": "...", "points": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]}]\n
- Mỗi box chỉ có ĐÚNG 4 điểm.
- Mỗi dòng trong fileState.txt: <folderName>/<imageName>\t1\n (1 = đã hoàn thành, 0 = chưa hoàn thành).
- Hỗ trợ rescale/upscale toạ độ bounding box nếu dùng PPOCRLabel ở độ phân giải 1K rồi đưa về độ phân giải gốc.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


def validate_bbox_item(item: Dict[str, Any]) -> bool:
    """Kiểm tra 1 đối tượng bounding box có đúng trường transcription và đúng 4 điểm hay không."""
    if "transcription" not in item or "points" not in item:
        return False
    points = item["points"]
    if not isinstance(points, list) or len(points) != 4:
        return False
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            return False
    return True


def sort_boxes_sinonom_vertical(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sắp xếp thứ tự bounding box cho chữ Nôm viết dọc:
    Từ phải sang trái (x giảm dần), trong cùng cột thì từ trên xuống dưới (y tăng dần).
    TODO (Thành viên 1 & 2): Tinh chỉnh ngưỡng phân cụm cột dọc (column clustering threshold) cho sách 2 trang (T1).
    """
    return sorted(
        boxes,
        key=lambda b: (-b["points"][0][0], b["points"][0][1]),
    )


def sort_boxes_quoc_ngu(boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sắp xếp thứ tự bounding box cho chữ Quốc ngữ:
    Từ trên xuống dưới (y tăng dần), từ trái sang phải (x tăng dần).
    """
    return sorted(
        boxes,
        key=lambda b: (b["points"][0][1], b["points"][0][0]),
    )


def scale_bboxes(
    boxes: List[Dict[str, Any]], scale_x: float, scale_y: float
) -> List[Dict[str, Any]]:
    """
    Upscale / Rescale tọa độ bounding box khi dùng PPOCRLabel trên ảnh thu nhỏ 1K
    rồi chuyển ngược về độ phân giải gốc của ảnh.
    """
    scaled = []
    for box in boxes:
        new_box = dict(box)
        new_box["points"] = [
            [int(round(pt[0] * scale_x)), int(round(pt[1] * scale_y))]
            for pt in box["points"]
        ]
        scaled.append(new_box)
    return scaled


def write_ppocr_files(
    folder_path: Path,
    annotations: Dict[str, List[Dict[str, Any]]],
    is_char_level: bool = False,
) -> Tuple[Path, Path]:
    """
    Ghi cặp file Label.txt & fileState.txt (hoặc Label_char.txt & fileState_char.txt)
    vào thư mục đích (ví dụ: ch/ hoặc vi/).
    - annotations: dict ánh xạ từ image_filename (vd: 'Book.001.jpg') -> danh sách bounding box.
    """
    folder_name = folder_path.name
    label_filename = "Label_char.txt" if is_char_level else "Label.txt"
    state_filename = "fileState_char.txt" if is_char_level else "fileState.txt"

    label_path = folder_path / label_filename
    state_path = folder_path / state_filename

    with (
        open(label_path, "w", encoding="utf-8", newline="\n") as f_label,
        open(state_path, "w", encoding="utf-8", newline="\n") as f_state,
    ):
        for img_name in sorted(annotations.keys()):
            boxes = annotations[img_name]
            for b in boxes:
                if not validate_bbox_item(b):
                    raise ValueError(f"Box không hợp lệ trong ảnh {img_name}: {b}")

            rel_img_path = f"{folder_name}/{img_name}"
            json_str = json.dumps(boxes, ensure_ascii=False, separators=(",", ":"))
            f_label.write(f"{rel_img_path}\t{json_str}\n")
            f_state.write(f"{rel_img_path}\t1\n")

    return label_path, state_path

