"""
Script tạo gói dữ liệu mẫu 2 cặp trang hoàn chỉnh (Phương án A - Phần Tựa)
để nộp kiểm tra tiến độ cuối ngày Chủ Nhật 08/11/2026:
- Cặp 1: Trang Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg` <-> Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg`
- Cặp 2: Trang Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg` <-> Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg`

Đảm bảo tuân thủ 100% Quy định đồ án_v1.1.pdf:
1. Thư mục `ch/`: ảnh .jpg, `Label.txt` (cột dọc từ phải sang trái, không bao gồm số trang/tiêu đề lề), `fileState.txt` (trạng thái 1).
2. Thư mục `vi/`: ảnh .jpg, `Label.txt` (dòng ngang từ trên xuống dưới, không bao gồm số trang/chân trang), `fileState.txt` (trạng thái 1).
3. File `<Tên sách>.csv`: 4 cột (`img_id`, `sentence_id`, `SinoNom_Char`, `ChuQN_txt`), nối câu bị ngắt do chuyển trang.
4. File `<Tên sách>.xlsx`: Tô màu từng chữ (`#000000` đen / `#FF0000` đỏ) dựa trên `HanNomDictionaryIndex`, đạt >= 95% độ tương đồng.
"""

import json
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import load_config
from src.step4_ppocr_formatter import (
    sort_boxes_quoc_ngu,
    sort_boxes_sinonom_vertical,
    write_ppocr_files,
)
from src.step5_dictionary_loader import HanNomDictionaryIndex
from src.step6_text_cleaner_aligner import AlignedSentencePair, build_sentence_id
from src.step7_exporter_evaluator import (
    export_aligned_csv,
    export_aligned_xlsx_and_evaluate,
    extract_quoc_ngu_syllables,
    extract_sinonom_chars,
)


def get_sample_ch_annotations() -> dict:
    """
    Trả về danh sách bounding box chuẩn PPOCRLabel cho 2 trang chữ Nôm:
    - T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg (7 cột dọc từ phải sang trái)
    - T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg (7 cột dọc từ phải sang trái)
    Đã lọc bỏ số trang/tiêu đề lề trái và chuẩn hóa ký tự PUA + hiệu đính chính xác theo mộc bản.
    """
    boxes_440 = [
        {
            "transcription": "冊翁聖離姑移烏呐𧗱事議𠸦吧敬勉德婆。",
            "points": [[586, 85], [625, 85], [624, 875], [585, 875]],
        },
        {
            "transcription": "序。",
            "points": [[503, 121], [563, 121], [563, 207], [503, 207]],
        },
        {
            "transcription": "些爫冊尼、爲𢚸敬勉、吧朱𤏬名慄聖德妑瑪移亞𠬠",
            "points": [[441, 84], [482, 84], [482, 1016], [441, 1016]],
        },
        {
            "transcription": "𣈗𠬠欣。丕欺英㛪筭䀡冊尼、乙羅拱爲𠬠𢚸敬勉媄",
            "points": [[364, 86], [406, 86], [411, 1021], [369, 1021]],
        },
        {
            "transcription": "德主𡗶、共約泑悶𦖑呐旦等慄論苓𢚸英㛪夭勉。爲",
            "points": [[295, 88], [334, 88], [337, 1018], [298, 1018]],
        },
        {
            "transcription": "丕或𮎦㛪固𦖑埃呐浪、勤之爫冊尼、芇固少之冊慄",
            "points": [[222, 93], [261, 93], [264, 1015], [225, 1015]],
        },
        {
            "transcription": "通太窖嘹、固名㗂初𠉞。時碎嗔𮎦㛪𥙩𠳒翁袍𪘵昆",
            "points": [[150, 94], [189, 94], [193, 1015], [154, 1015]],
        },
    ]

    boxes_439 = [
        {
            "transcription": "麻疎共几𧘇浪、事議𠸦慄聖德婆瑪移亞、庄恪之如",
            "points": [[574, 99], [613, 98], [615, 1012], [576, 1012]],
        },
        {
            "transcription": "𦰟源恒𣻆渃𡬈連、庄包𣇞歇、共羅如湖𢌌𡚚、渃彊沚",
            "points": [[501, 97], [539, 96], [545, 1013], [507, 1013]],
        },
        {
            "transcription": "𠓨、時強𢌌𠚢、吧強𢀲時強渃𨖲。義羅慄聖童貞、𠁟𩛂",
            "points": [[426, 100], [468, 99], [472, 1016], [430, 1016]],
        },
        {
            "transcription": "每福德、過智𠊛些議𠸦庄稱當特、朱𢧚翁聖泑俱星",
            "points": [[357, 102], [395, 102], [395, 1016], [357, 1016]],
        },
        {
            "transcription": "呐譬喻浪、油麻各分中命𠊛些、呂𢧚𥚇奇默𢚸、拱庄",
            "points": [[286, 100], [325, 101], [322, 1012], [283, 1012]],
        },
        {
            "transcription": "理芇麻議𠸦𠊛朱堵特。",
            "points": [[213, 101], [255, 102], [253, 520], [211, 520]],
        },
        {
            "transcription": "碎拱㐌固意六察各冊𢀲𡮈呐旦事奇創慄聖德婆、雙",
            "points": [[144, 104], [182, 105], [175, 1015], [137, 1015]],
        },
    ]

    return {
        "T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg": sort_boxes_sinonom_vertical(boxes_440),
        "T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg": sort_boxes_sinonom_vertical(boxes_439),
    }


def get_sample_vi_annotations() -> dict:
    """
    Trả về danh sách bounding box chuẩn PPOCRLabel cho 2 trang chữ Quốc ngữ:
    - T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg (14 dòng ngang từ trên xuống dưới)
    - T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg (14 dòng ngang từ trên xuống dưới)
    Không bao gồm số trang (19, 20), số tham chiếu (440, 439) và tiêu đề chân trang.
    """
    boxes_019 = [
        {
            "transcription": "SÁCH ÔNG THÁNH LI-GÔ-RI-Ô",
            "points": [[125, 168], [602, 168], [602, 215], [125, 215]],
        },
        {
            "transcription": "NÓI VỀ SỰ NGỢI KHEN VÀ KÍNH",
            "points": [[100, 219], [631, 219], [631, 270], [100, 270]],
        },
        {
            "transcription": "MẾN ĐỨC BÀ",
            "points": [[249, 271], [482, 271], [482, 317], [249, 317]],
        },
        {
            "transcription": "Tựa",
            "points": [[325, 370], [409, 370], [409, 408], [325, 408]],
        },
        {
            "transcription": "Ta làm sách này vì lòng kính mến và cho",
            "points": [[162, 458], [642, 458], [642, 487], [162, 487]],
        },
        {
            "transcription": "sáng danh Rất Thánh Đức Bà Ma-ri-a một",
            "points": [[96, 496], [642, 496], [642, 525], [96, 525]],
        },
        {
            "transcription": "ngày một hơn. Vậy khi anh em toan xem sách",
            "points": [[99, 533], [642, 533], [642, 562], [99, 562]],
        },
        {
            "transcription": "này, ắt là cũng vì một lòng kính mến Mẹ Đức",
            "points": [[100, 568], [639, 568], [639, 599], [100, 599]],
        },
        {
            "transcription": "Chúa Trời, cùng ước ao muốn nghe nói đến",
            "points": [[99, 604], [642, 604], [642, 635], [99, 635]],
        },
        {
            "transcription": "Đấng rất trọn lành lòng anh em yêu mến. Vì",
            "points": [[100, 641], [643, 641], [643, 673], [100, 673]],
        },
        {
            "transcription": "vậy, hoặc anh em có nghe ai nói rằng : Cần",
            "points": [[100, 678], [643, 678], [643, 710], [100, 710]],
        },
        {
            "transcription": "chi làm sách này ? Nào có thiếu gì sách rất",
            "points": [[100, 715], [644, 715], [644, 745], [100, 745]],
        },
        {
            "transcription": "thông thái khéo léo có danh tiếng xưa nay ?",
            "points": [[101, 755], [646, 755], [646, 783], [101, 783]],
        },
        {
            "transcription": "Thì tôi xin anh em lấy lời ông Pha-lăng-côn",
            "points": [[103, 790], [644, 790], [644, 820], [103, 820]],
        },
    ]

    boxes_020 = [
        {
            "transcription": "mà thưa cùng kẻ ấy rằng : Sự ngợi khen Rất",
            "points": [[132, 161], [678, 161], [678, 191], [132, 191]],
        },
        {
            "transcription": "Thánh Đức Bà Ma-ri-a chẳng khác gì như ngọn",
            "points": [[136, 198], [677, 198], [677, 227], [136, 227]],
        },
        {
            "transcription": "nguồn hằng tuôn nước xuống liền chẳng bao",
            "points": [[133, 234], [678, 234], [678, 263], [133, 263]],
        },
        {
            "transcription": "giờ hết, cùng là như hồ rộng lớn, nước càng",
            "points": [[129, 270], [677, 270], [677, 300], [129, 300]],
        },
        {
            "transcription": "chảy vào thì càng rộng ra và càng lớn, thì càng",
            "points": [[131, 307], [677, 307], [677, 337], [131, 337]],
        },
        {
            "transcription": "nước lên, nghĩa là Rất Thánh Đồng Trinh gồm",
            "points": [[133, 345], [676, 345], [676, 374], [133, 374]],
        },
        {
            "transcription": "no mọi phúc đức quá trí người ta ngợi khen",
            "points": [[132, 382], [676, 382], [676, 411], [132, 411]],
        },
        {
            "transcription": "chẳng xứng đáng được. Cho nên, ông Thánh",
            "points": [[131, 419], [676, 419], [676, 447], [131, 447]],
        },
        {
            "transcription": "Âu-gu-tinh nói ví dụ rằng : Dù mà các phần",
            "points": [[131, 454], [676, 454], [676, 483], [131, 483]],
        },
        {
            "transcription": "trong mình người ta trở nên lưỡi cả mặc lòng",
            "points": [[132, 490], [676, 490], [676, 520], [132, 520]],
        },
        {
            "transcription": "cũng chẳng lẽ nào mà ngợi khen Người cho đủ",
            "points": [[131, 527], [675, 527], [675, 556], [131, 556]],
        },
        {
            "transcription": "được.",
            "points": [[131, 562], [194, 562], [194, 590], [131, 590]],
        },
        {
            "transcription": "Tôi cũng đã có ý lục xét các sách lớn",
            "points": [[195, 628], [676, 628], [676, 661], [195, 661]],
        },
        {
            "transcription": "nhỏ nói đến sự cả sáng Rất Thánh Đức Bà, song",
            "points": [[131, 669], [674, 669], [674, 699], [131, 699]],
        },
    ]

    return {
        "T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg": sort_boxes_quoc_ngu(boxes_019),
        "T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg": sort_boxes_quoc_ngu(boxes_020),
    }


def get_sample_aligned_pairs() -> list:
    """
    Trả về danh sách các cặp câu dóng hàng Hán Nôm - Quốc ngữ của 2 cặp trang mẫu:
    - Cặp trang 1 (`T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg` <-> `.019.jpg`): 6 câu (.440.1 -> .440.6),
      trong đó câu .440.6 nối câu bị ngắt ở cuối trang 440/019 sang đầu trang 439/020 đúng Quy định Trang 8.
    - Cặp trang 2 (`T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg` <-> `.020.jpg`): 2 câu (.439.1 -> .439.2).
    """
    img_440 = "T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg"
    img_439 = "T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg"

    raw_440 = [
        (
            "冊翁聖離姑移烏呐𧗱事議𠸦吧敬勉德婆。",
            "SÁCH ÔNG THÁNH LI-GÔ-RI-Ô NÓI VỀ SỰ NGỢI KHEN VÀ KÍNH MẾN ĐỨC BÀ",
        ),
        (
            "序。",
            "Tựa",
        ),
        (
            "些爫冊尼、爲𢚸敬勉、吧朱𤏬名慄聖德妑瑪移亞𠬠𣈗𠬠欣。",
            "Ta làm sách này vì lòng kính mến và cho sáng danh Rất Thánh Đức Bà Ma-ri-a một ngày một hơn.",
        ),
        (
            "丕欺英㛪筭䀡冊尼、乙羅拱爲𠬠𢚸敬勉媄德主𡗶、共約泑悶𦖑呐旦等慄論苓𢚸英㛪夭勉。",
            "Vậy khi anh em toan xem sách này, ắt là cũng vì một lòng kính mến Mẹ Đức Chúa Trời, cùng ước ao muốn nghe nói đến Đấng rất trọn lành lòng anh em yêu mến.",
        ),
        (
            "爲丕或𮎦㛪固𦖑埃呐浪、勤之爫冊尼、芇固少之冊慄通太窖嘹、固名㗂初𠉞。",
            "Vì vậy, hoặc anh em có nghe ai nói rằng : Cần chi làm sách này ? Nào có thiếu gì sách rất thông thái khéo léo có danh tiếng xưa nay ?",
        ),
        # Câu 6 ở cuối trang 440 bị ngắt chuyển sang đầu trang 439 -> ghép vào trang bắt đầu (440) theo Quy định Trang 8
        (
            "時碎嗔𮎦㛪𥙩𠳒翁袍𪘵昆麻疎共几𧘇浪、事議𠸦慄聖德婆瑪移亞、庄恪之如𦰟源恒𣻆渃𡬈連、庄包𣇞歇、共羅如湖𢌌𡚚、渃彊沚𠓨、時強𢌌𠚢、吧強𢀲時強渃𨖲。",
            "Thì tôi xin anh em lấy lời ông Pha-lăng-côn mà thưa cùng kẻ ấy rằng : Sự ngợi khen Rất Thánh Đức Bà Ma-ri-a chẳng khác gì như ngọn nguồn hằng tuôn nước xuống liền chẳng bao giờ hết, cùng là như hồ rộng lớn, nước càng chảy vào thì càng rộng ra và càng lớn, thì càng nước lên,",
        ),
    ]

    raw_439 = [
        (
            "義羅慄聖童貞、𠁟𩛂每福德、過智𠊛些議𠸦庄稱當特、朱𢧚翁聖泑俱星呐譬喻浪、油麻各分中命𠊛些、呂𢧚𥚇奇默𢚸、拱庄理芇麻議𠸦𠊛朱堵特。",
            "nghĩa là Rất Thánh Đồng Trinh gồm no mọi phúc đức quá trí người ta ngợi khen chẳng xứng đáng được. Cho nên, ông Thánh Âu-gu-tinh nói ví dụ rằng : Dù mà các phần trong mình người ta trở nên lưỡi cả mặc lòng cũng chẳng lẽ nào mà ngợi khen Người cho đủ được.",
        ),
        (
            "碎拱㐌固意六察各冊𢀲𡮈呐旦事奇創慄聖德婆、雙",
            "Tôi cũng đã có ý lục xét các sách lớn nhỏ nói đến sự cả sáng Rất Thánh Đức Bà, song",
        ),
    ]

    pairs = []
    for idx, (sn, qn) in enumerate(raw_440, start=1):
        pairs.append(
            AlignedSentencePair(
                img_id=img_440,
                sentence_id=build_sentence_id(img_440, idx),
                sino_nom_char=sn,
                chu_qn_txt=qn,
            )
        )
    for idx, (sn, qn) in enumerate(raw_439, start=1):
        pairs.append(
            AlignedSentencePair(
                img_id=img_439,
                sentence_id=build_sentence_id(img_439, idx),
                sino_nom_char=sn,
                chu_qn_txt=qn,
            )
        )
    return pairs


def segment_column_chars(im_gray, col_box: dict) -> list:
    """
    Tách 1 cột dọc chữ Nôm thành danh sách các bounding box cho TỪNG CHỮ (1 box = 1 chữ)
    để xuất ra file `Label_char.txt` và `fileState_char.txt` theo Quy định Trang 4, 6, 7.
    """
    import numpy as np

    chars = extract_sinonom_chars(col_box["transcription"])
    n = len(chars)
    pts = col_box["points"]
    x1 = min(p[0] for p in pts)
    x2 = max(p[0] for p in pts)
    y1 = min(p[1] for p in pts)
    y2 = max(p[1] for p in pts)
    if n == 1:
        return [{"transcription": chars[0], "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]}]

    crop = (im_gray[y1 : y2 + 1, x1 : x2 + 1] < 175).astype(np.float32)
    ink_y = np.where(crop.sum(axis=1) >= 2)[0]
    if len(ink_y) > 0:
        y1_tight = y1 + int(ink_y[0])
        y2_tight = y1 + int(ink_y[-1])
    else:
        y1_tight, y2_tight = y1, y2

    crop = (im_gray[y1_tight : y2_tight + 1, x1 : x2 + 1] < 175).astype(np.float32)
    row_proj = crop.sum(axis=1)
    h = y2_tight - y1_tight + 1
    step = h / n

    cuts = [0]
    for k in range(1, n):
        center = k * step
        w_half = max(3, int(step * 0.12))
        lo = max(cuts[-1] + int(step * 0.72), int(round(center)) - w_half)
        hi = min(h - int((n - k) * step * 0.72), int(round(center)) + w_half)
        if lo < hi:
            idxs = np.arange(lo, hi + 1)
            scores = row_proj[lo : hi + 1] + 0.5 * ((idxs - center) ** 2)
            best_y = int(idxs[int(np.argmin(scores))])
            cuts.append(best_y)
        else:
            cuts.append(int(round(center)))
    cuts.append(h)

    char_boxes = []
    for i, ch in enumerate(chars):
        cy1 = y1_tight + cuts[i]
        cy2 = y1_tight + cuts[i + 1] - 1
        sub = crop[cuts[i] : cuts[i + 1], :]
        ink_rows = np.where(sub.sum(axis=1) > 0)[0]
        ink_cols = np.where(sub.sum(axis=0) > 0)[0]
        ry1 = max(y1, cy1 + int(ink_rows[0]) - 2) if len(ink_rows) > 0 else cy1
        ry2 = min(y2, cy1 + int(ink_rows[-1]) + 2) if len(ink_rows) > 0 else cy2
        rx1 = max(0, x1 + int(ink_cols[0]) - 2) if len(ink_cols) > 0 else x1
        rx2 = min(im_gray.shape[1] - 1, x1 + int(ink_cols[-1]) + 2) if len(ink_cols) > 0 else x2
        char_boxes.append(
            {"transcription": ch, "points": [[rx1, ry1], [rx2, ry1], [rx2, ry2], [rx1, ry2]]}
        )
    return char_boxes


def get_sample_ch_char_annotations(ch_dir: Path, ch_col_annotations: dict) -> dict:
    """Tạo dữ liệu bounding box cấp độ từng chữ (1 box = 1 chữ) cho `Label_char.txt`."""
    import numpy as np

    char_annotations = {}
    for img_name, col_boxes in ch_col_annotations.items():
        im_gray = np.asarray(Image.open(ch_dir / img_name).convert("L"))
        cboxes = []
        for cb in col_boxes:
            cboxes.extend(segment_column_chars(im_gray, cb))
        char_annotations[img_name] = cboxes
    return char_annotations


def render_bbox_preview(img_path: Path, boxes: list, out_preview_path: Path, color: str = "red", show_index: bool = True) -> None:
    """Vẽ bounding box và số thứ tự đọc lên ảnh để kiểm tra trực quan."""
    out_preview_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(im)
    for i, b in enumerate(boxes, start=1):
        pts = [tuple(p) for p in b["points"]]
        draw.polygon(pts, outline=color, width=2 if not show_index else 3)
        if show_index:
            x0, y0 = pts[0]
            draw.rectangle([x0, max(0, y0 - 20), x0 + 26, y0], fill=color)
            draw.text((x0 + 4, max(0, y0 - 18)), f"#{i}", fill="white")
    im.save(out_preview_path, quality=92)


def main() -> None:
    cfg = load_config()
    group_id = cfg["project"]["group_id"]
    book_name = "T1_Thánh Mẫu Phương Danh (Tập 1)"

    out_book_dir = Path(cfg["paths"]["output_dir"]) / book_name
    cache_book_dir = Path(cfg["paths"]["cache_dir"]) / "ocr_nom" / book_name

    sample_root = PROJECT_ROOT / "submission" / f"{group_id}_sample"
    sample_book_dir = sample_root / book_name
    sample_ch_dir = sample_book_dir / "ch"
    sample_vi_dir = sample_book_dir / "vi"

    if sample_root.exists():
        shutil.rmtree(sample_root)
    sample_ch_dir.mkdir(parents=True, exist_ok=True)
    sample_vi_dir.mkdir(parents=True, exist_ok=True)

    ch_annotations = get_sample_ch_annotations()
    vi_annotations = get_sample_vi_annotations()

    # 1. Cập nhật cache JSON của 440 và 439 với boxes đã hiệu đính
    for img_name, boxes in ch_annotations.items():
        cache_f = cache_book_dir / f"{Path(img_name).stem}.json"
        if cache_f.exists():
            data = json.loads(cache_f.read_text(encoding="utf-8"))
            data["boxes"] = boxes
            cache_f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Copy 2 cặp ảnh vào gói sample và ghi cả Label.txt (cột dọc) + Label_char.txt (từng chữ)
    for img_name in ch_annotations:
        src_img = out_book_dir / "ch" / img_name
        shutil.copy2(src_img, sample_ch_dir / img_name)
    write_ppocr_files(sample_ch_dir, ch_annotations, is_char_level=False)
    ch_char_annotations = get_sample_ch_char_annotations(sample_ch_dir, ch_annotations)
    write_ppocr_files(sample_ch_dir, ch_char_annotations, is_char_level=True)
    write_ppocr_files(out_book_dir / "ch", ch_char_annotations, is_char_level=True)

    for img_name in vi_annotations:
        src_img = out_book_dir / "vi" / img_name
        shutil.copy2(src_img, sample_vi_dir / img_name)
    write_ppocr_files(sample_vi_dir, vi_annotations, is_char_level=False)

    # Đồng thời cập nhật luôn Label.txt và fileState.txt trong output/<Tên sách>/vi và ch
    write_ppocr_files(out_book_dir / "vi", vi_annotations, is_char_level=False)

    # 3. Nạp từ điển Hán Nôm và xuất CSV + XLSX tô màu + tính độ tương đồng
    print("Đang nạp bộ từ điển Hán Nôm (dictionaries-04-11-2026)...")
    entries_dir = Path(cfg["paths"]["dictionary_entries_dir"])
    dict_index = HanNomDictionaryIndex(entries_dir=entries_dir)
    sources = [
        "btcn.jsonl",
        "dv.jsonl",
        "hannom_rcv.jsonl",
        "hvdic.jsonl",
        "dnqatv_wikisource.jsonl",
        "cjkvi_variants.jsonl",
    ]
    dict_index.load_sources(sources)

    pairs = get_sample_aligned_pairs()

    # Kiểm tra độ khớp số lượng âm tiết 1-1 trên từng câu
    print("\n=== KIỂM TRA DÓNG HÀNG CÂU (SENTENCE ALIGNMENT) ===")
    for p in pairs:
        sn_chars = extract_sinonom_chars(p.sino_nom_char)
        qn_words = extract_quoc_ngu_syllables(p.chu_qn_txt)
        mismatches = [
            f"{c}({w})"
            for c, w in zip(sn_chars, qn_words)
            if not dict_index.is_match(c, w)
        ]
        print(
            f"  - {p.sentence_id}: {len(sn_chars)} chữ Nôm <-> {len(qn_words)} âm tiết Quốc ngữ "
            f"({'KHỚP 1-1' if len(sn_chars) == len(qn_words) else 'LỆCH!'}) | Đỏ ({len(mismatches)}): {', '.join(mismatches)}"
        )

    csv_sample_path = sample_book_dir / f"{book_name}.csv"
    xlsx_sample_path = sample_book_dir / f"{book_name}.xlsx"
    export_aligned_csv(pairs, csv_sample_path, is_pure_text=False)
    eval_report = export_aligned_xlsx_and_evaluate(
        pairs, xlsx_sample_path, dict_index, is_pure_text=False
    )

    # Copy CSV & XLSX sang cả output/<Tên sách>/
    shutil.copy2(csv_sample_path, out_book_dir / f"{book_name}.csv")
    shutil.copy2(xlsx_sample_path, out_book_dir / f"{book_name}.xlsx")

    print("\n=== KẾT QUẢ ĐÁNH GIÁ ĐỘ TƯƠNG ĐỒNG (.XLSX) ===")
    print(f"  - Tổng số chữ (total_chars) : {eval_report['total_chars']}")
    print(f"  - Số chữ đen (black_chars)  : {eval_report['black_chars']}")
    print(f"  - Số chữ đỏ (red_chars)     : {eval_report['red_chars']}")
    print(f"  - Độ tương đồng (%)         : {eval_report['similarity_percent']}% (Yêu cầu >= 95%)")
    print(f"  - Đạt chuẩn nộp bài         : {'ĐẠT (PASSED)' if eval_report['passed_95_threshold'] else 'CHƯA ĐẠT'}")

    # 4. Đóng gói file ZIP nộp mẫu
    zip_path = PROJECT_ROOT / "submission" / f"{group_id}_sample.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(sample_book_dir.rglob("*")):
            if file_path.is_file():
                arcname = file_path.relative_location(sample_root) if hasattr(file_path, "relative_location") else file_path.relative_to(sample_root)
                zf.write(file_path, arcname)

    print(f"\n=== ĐÃ TẠO GÓI NỘP MẪU THÀNH CÔNG ===")
    print(f"  - Thư mục mẫu : {sample_book_dir}")
    print(f"  - File nén ZIP: {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")

    # 5. Tạo ảnh preview bounding box vào thư mục submission/preview/
    preview_dir = PROJECT_ROOT / "submission" / "preview"
    for img_name, boxes in ch_annotations.items():
        p_num = Path(img_name).stem.split(".")[-1]
        render_bbox_preview(
            sample_ch_dir / img_name,
            boxes,
            preview_dir / f"preview_ch_{p_num}.jpg",
            color="#D93025",
            show_index=True,
        )
        render_bbox_preview(
            sample_ch_dir / img_name,
            ch_char_annotations[img_name],
            preview_dir / f"preview_ch_{p_num}_char.jpg",
            color="#00897B",
            show_index=False,
        )
    for img_name, boxes in vi_annotations.items():
        render_bbox_preview(
            sample_vi_dir / img_name,
            boxes,
            preview_dir / f"preview_vi_{Path(img_name).stem.split('.')[-1]}.jpg",
            color="#1A73E8",
        )
    print(f"  - Ảnh preview : {preview_dir}")


if __name__ == "__main__":
    main()
