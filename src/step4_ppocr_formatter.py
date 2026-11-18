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


def sort_boxes_sinonom_vertical(
    boxes: List[Dict[str, Any]], col_tolerance: int = 25
) -> List[Dict[str, Any]]:
    """
    Sắp xếp thứ tự bounding box cho chữ Nôm viết dọc:
    Từ phải sang trái (cột x giảm dần theo ngưỡng phân cụm col_tolerance),
    trong cùng cột thì từ trên xuống dưới (y tăng dần).
    """
    if not boxes:
        return []

    # Phân cụm các box có tâm X gần nhau (<= col_tolerance) vào cùng một cột dọc
    items = []
    for b in boxes:
        pts = b["points"]
        cx = sum(p[0] for p in pts) / 4.0
        cy = min(p[1] for p in pts)
        items.append((cx, cy, b))

    # Sắp xếp giảm dần theo cx để gom cụm cột từ phải sang trái
    items.sort(key=lambda x: -x[0])
    columns: List[List[Tuple[float, float, Dict[str, Any]]]] = []
    for item in items:
        if not columns:
            columns.append([item])
        else:
            mean_cx = sum(x[0] for x in columns[-1]) / len(columns[-1])
            if abs(item[0] - mean_cx) <= col_tolerance:
                columns[-1].append(item)
            else:
                columns.append([item])

    sorted_boxes: List[Dict[str, Any]] = []
    for col in columns:
        col.sort(key=lambda x: x[1])  # Trên xuống dưới trong cùng một cột
        sorted_boxes.extend(x[2] for x in col)
    return sorted_boxes


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


def _order_quad_tl_tr_br_bl(pts: List[List[int]]) -> List[List[int]]:
    """Chuẩn hóa thứ tự 4 đỉnh của đa giác về đúng [TL, TR, BR, BL]."""
    sorted_by_y = sorted(pts, key=lambda p: (p[1], p[0]))
    top_two = sorted(sorted_by_y[:2], key=lambda p: p[0])
    bot_two = sorted(sorted_by_y[2:], key=lambda p: p[0])
    return [list(top_two[0]), list(top_two[1]), list(bot_two[1]), list(bot_two[0])]


def expand_sinonom_boxes(
    boxes: List[Dict[str, Any]],
    img_width: int = 800,
    img_height: int = 1135,
    pad_x: int = 6,
    pad_y: int = 8,
    min_col_gap: int = 2,
) -> List[Dict[str, Any]]:
    """
    Mở rộng kích thước bounding box cho chữ Nôm theo góp ý của giảng viên:
    - Tăng lề ngang `pad_x` (mặc định +6px mỗi bên) và lề dọc `pad_y` (mặc định +8px mỗi đầu)
      để bao trọn hoàn toàn các nét phẩy/mác và nét đầu-cuối cột của chữ Nôm, tránh cắt nét.
    - Tự động bảo vệ chống chồng lấn giữa hai cột liền kề có khoảng Y giao nhau (giữ khoảng hở >= min_col_gap).
    - Kẹp tọa độ an toàn trong biên ảnh [0, img_width - 1] x [0, img_height - 1].
    """
    if not boxes:
        return []

    expanded: List[Dict[str, Any]] = []
    for box in boxes:
        tl, tr, br, bl = _order_quad_tl_tr_br_bl(box["points"])
        new_pts = [
            [max(0, tl[0] - pad_x), max(0, tl[1] - pad_y)],
            [min(img_width - 1, tr[0] + pad_x), max(0, tr[1] - pad_y)],
            [min(img_width - 1, br[0] + pad_x), min(img_height - 1, br[1] + pad_y)],
            [max(0, bl[0] - pad_x), min(img_height - 1, bl[1] + pad_y)],
        ]
        new_box = dict(box)
        new_box["points"] = new_pts
        expanded.append(new_box)

    # Bảo vệ chống chồng lấn ngang giữa các cột lân cận có khoảng Y giao nhau
    # Sắp xếp tạm theo tâm X tăng dần (từ trái sang phải)
    indexed = sorted(
        enumerate(expanded),
        key=lambda kv: sum(p[0] for p in kv[1]["points"]) / 4.0,
    )
    for idx_pos in range(len(indexed) - 1):
        _, left_box = indexed[idx_pos]
        _, right_box = indexed[idx_pos + 1]
        lp = left_box["points"]
        rp = right_box["points"]

        ly_min = min(p[1] for p in lp)
        ly_max = max(p[1] for p in lp)
        ry_min = min(p[1] for p in rp)
        ry_max = max(p[1] for p in rp)
        # Chỉ kiểm tra va chạm nếu 2 cột có phần Y chồng lên nhau đáng kể
        if min(ly_max, ry_max) - max(ly_min, ry_min) <= 10:
            continue

        # Kiểm tra đỉnh trên (TR của left vs TL của right) và đỉnh dưới (BR của left vs BL của right)
        for l_corner, r_corner in ((1, 0), (2, 3)):
            if lp[l_corner][0] + min_col_gap > rp[r_corner][0]:
                mid = (lp[l_corner][0] + rp[r_corner][0]) // 2
                lp[l_corner][0] = max(0, mid - min_col_gap // 2)
                rp[r_corner][0] = min(img_width - 1, lp[l_corner][0] + min_col_gap)

    return sort_boxes_sinonom_vertical(expanded)


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

