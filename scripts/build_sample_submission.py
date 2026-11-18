"""
Script tạo gói dữ liệu mẫu 2 cặp trang hoàn chỉnh chuẩn Quy định đồ án v2.4 (16/11/2026)
kèm cập nhật mở rộng bounding box chữ Nôm theo góp ý của giảng viên:
- Cặp 1: Trang Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg` <-> Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg`
- Cặp 2: Trang Nôm `T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg` <-> Quốc ngữ `T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg`

Tuân thủ 100% Quy định đồ án v2.4:
1. Thư mục `ch/`: ảnh .jpg, `Label.txt` (cột dọc từ phải sang trái, đã mở rộng lề pad_x=+6px, pad_y=+8px
   có chống chồng lấn để bao trọn 100% nét chữ Nôm), `fileState.txt` (trạng thái 1).
2. Thư mục `vi/`: ảnh .jpg, `Label.txt` (dòng ngang từ trên xuống dưới, loại bỏ vết in xuyên trang,
   số trang và chân trang), `fileState.txt` (trạng thái 1).
3. File `<Tên sách>_image_map.json`: ánh xạ cặp trang `ch` <-> `vi` theo đúng thứ tự đọc T1.
4. File `<Tên sách>.csv` & `<Tên sách>.xlsx`: 5 cột chuẩn v2.4 (`img_id`, `sentence_id`, `ch_txt`, `vi_txt`, `text_diff`),
   tính `text_diff` tự động bằng thuật toán Levenshtein + từ điển Hán Nôm, tô màu RGB chuẩn Excel khớp 100% `text_diff`.
5. Chạy bộ kiểm tra tự động bắt buộc (`validate_book_v24`) trước khi đóng gói ZIP.
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
    expand_sinonom_boxes,
    sort_boxes_quoc_ngu,
    sort_boxes_sinonom_vertical,
    write_ppocr_files,
)
from src.step5_dictionary_loader import HanNomDictionaryIndex
from src.step6_text_cleaner_aligner import SinoNomAligner
from src.step7_exporter_evaluator import (
    export_aligned_csv,
    export_aligned_xlsx_and_evaluate,
    extract_quoc_ngu_syllables,
    extract_sinonom_chars,
)
from src.step8_packager import validate_book_v24


def get_raw_sample_ch_annotations() -> dict:
    """
    Danh sách bounding box gốc từ API Kim Hán Nôm (trước khi mở rộng lề) cho 2 trang Nôm mẫu.
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


def get_sample_ch_annotations(pad_x: int = 6, pad_y: int = 8, min_col_gap: int = 2) -> dict:
    """
    Áp dụng thuật toán mở rộng bounding box chữ Nôm có bảo vệ chống chồng lấn
    theo góp ý của giảng viên (hạn chế cắt mất nét chữ Nôm).
    """
    raw = get_raw_sample_ch_annotations()
    return {
        img_name: expand_sinonom_boxes(
            boxes,
            img_width=800,
            img_height=1135,
            pad_x=pad_x,
            pad_y=pad_y,
            min_col_gap=min_col_gap,
        )
        for img_name, boxes in raw.items()
    }


def get_sample_vi_annotations() -> dict:
    """
    Danh sách bounding box chuẩn PPOCRLabel cho 2 trang chữ Quốc ngữ (019.jpg và 020.jpg).
    """
    boxes_019 = [
        {"transcription": "SÁCH ÔNG THÁNH LI-GÔ-RI-Ô", "points": [[125, 168], [602, 168], [602, 215], [125, 215]]},
        {"transcription": "NÓI VỀ SỰ NGỢI KHEN VÀ KÍNH", "points": [[100, 219], [631, 219], [631, 270], [100, 270]]},
        {"transcription": "MẾN ĐỨC BÀ", "points": [[249, 271], [482, 271], [482, 317], [249, 317]]},
        {"transcription": "Tựa", "points": [[325, 370], [409, 370], [409, 408], [325, 408]]},
        {"transcription": "Ta làm sách này vì lòng kính mến và cho", "points": [[162, 458], [642, 458], [642, 487], [162, 487]]},
        {"transcription": "sáng danh Rất Thánh Đức Bà Ma-ri-a một", "points": [[96, 496], [642, 496], [642, 525], [96, 525]]},
        {"transcription": "ngày một hơn. Vậy khi anh em toan xem sách", "points": [[99, 533], [642, 533], [642, 562], [99, 562]]},
        {"transcription": "này, ắt là cũng vì một lòng kính mến Mẹ Đức", "points": [[100, 568], [639, 568], [639, 599], [100, 599]]},
        {"transcription": "Chúa Trời, cùng ước ao muốn nghe nói đến", "points": [[99, 604], [642, 604], [642, 635], [99, 635]]},
        {"transcription": "Đấng rất trọn lành lòng anh em yêu mến. Vì", "points": [[100, 641], [643, 641], [643, 673], [100, 673]]},
        {"transcription": "vậy, hoặc anh em có nghe ai nói rằng : Cần", "points": [[100, 678], [643, 678], [643, 710], [100, 710]]},
        {"transcription": "chi làm sách này ? Nào có thiếu gì sách rất", "points": [[100, 715], [644, 715], [644, 745], [100, 745]]},
        {"transcription": "thông thái khéo léo có danh tiếng xưa nay ?", "points": [[101, 755], [646, 755], [646, 783], [101, 783]]},
        {"transcription": "Thì tôi xin anh em lấy lời ông Pha-lăng-côn", "points": [[103, 790], [644, 790], [644, 820], [103, 820]]},
    ]

    boxes_020 = [
        {"transcription": "mà thưa cùng kẻ ấy rằng : Sự ngợi khen Rất", "points": [[132, 161], [678, 161], [678, 191], [132, 191]]},
        {"transcription": "Thánh Đức Bà Ma-ri-a chẳng khác gì như ngọn", "points": [[136, 198], [677, 198], [677, 227], [136, 227]]},
        {"transcription": "nguồn hằng tuôn nước xuống liền chẳng bao", "points": [[133, 234], [678, 234], [678, 263], [133, 263]]},
        {"transcription": "giờ hết, cùng là như hồ rộng lớn, nước càng", "points": [[129, 270], [677, 270], [677, 300], [129, 300]]},
        {"transcription": "chảy vào thì càng rộng ra và càng lớn, thì càng", "points": [[131, 307], [677, 307], [677, 337], [131, 337]]},
        {"transcription": "nước lên, nghĩa là Rất Thánh Đồng Trinh gồm", "points": [[133, 345], [676, 345], [676, 374], [133, 374]]},
        {"transcription": "no mọi phúc đức quá trí người ta ngợi khen", "points": [[132, 382], [676, 382], [676, 411], [132, 411]]},
        {"transcription": "chẳng xứng đáng được. Cho nên, ông Thánh", "points": [[131, 419], [676, 419], [676, 447], [131, 447]]},
        {"transcription": "Âu-gu-tinh nói ví dụ rằng : Dù mà các phần", "points": [[131, 454], [676, 454], [676, 483], [131, 483]]},
        {"transcription": "trong mình người ta trở nên lưỡi cả mặc lòng", "points": [[132, 490], [676, 490], [676, 520], [132, 520]]},
        {"transcription": "cũng chẳng lẽ nào mà ngợi khen Người cho đủ", "points": [[131, 527], [675, 527], [675, 556], [131, 556]]},
        {"transcription": "được.", "points": [[131, 562], [194, 562], [194, 590], [131, 590]]},
        {"transcription": "Tôi cũng đã có ý lục xét các sách lớn", "points": [[195, 628], [676, 628], [676, 661], [195, 661]]},
        {"transcription": "nhỏ nói đến sự cả sáng Rất Thánh Đức Bà, song", "points": [[131, 669], [674, 669], [674, 699], [131, 699]]},
    ]

    return {
        "T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg": sort_boxes_quoc_ngu(boxes_019),
        "T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg": sort_boxes_quoc_ngu(boxes_020),
    }


def get_sample_aligned_pairs(aligner: SinoNomAligner) -> list:
    """
    Trả về 8 cặp câu dóng hàng chuẩn v2.4 (kèm `text_diff` tính bằng Levenshtein + từ điển).
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
        pairs.append(aligner.build_pair(img_440, idx, sn, qn, is_phonetic=True))
    for idx, (sn, qn) in enumerate(raw_439, start=1):
        pairs.append(aligner.build_pair(img_439, idx, sn, qn, is_phonetic=True))
    return pairs


def render_bbox_preview(
    img_path: Path,
    boxes: list,
    out_preview_path: Path,
    color: str = "#00897B",
    show_index: bool = True,
) -> None:
    """Vẽ bounding box và số thứ tự đọc lên ảnh để kiểm tra trực quan."""
    out_preview_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(im)
    for i, b in enumerate(boxes, start=1):
        pts = [tuple(p) for p in b["points"]]
        draw.polygon(pts, outline=color, width=3)
        if show_index:
            x0, y0 = pts[0]
            draw.rectangle([x0, max(0, y0 - 20), x0 + 26, y0], fill=color)
            draw.text((x0 + 4, max(0, y0 - 18)), f"#{i}", fill="white")
    im.save(out_preview_path, quality=92)


def render_before_after_comparison(
    img_path: Path,
    old_boxes: list,
    new_boxes: list,
    out_path: Path,
) -> None:
    """Vẽ chồng khung cũ (đỏ nét mảnh) và khung mới sau khi mở rộng (xanh lục nét đậm) để minh họa cập nhật."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(img_path).convert("RGB")
    draw = ImageDraw.Draw(im)
    for b in old_boxes:
        draw.polygon([tuple(p) for p in b["points"]], outline="#D93025", width=1)
    for i, b in enumerate(new_boxes, start=1):
        pts = [tuple(p) for p in b["points"]]
        draw.polygon(pts, outline="#0F9D58", width=3)
        x0, y0 = pts[0]
        draw.rectangle([x0, max(0, y0 - 20), x0 + 26, y0], fill="#0F9D58")
        draw.text((x0 + 4, max(0, y0 - 18)), f"#{i}", fill="white")
    im.save(out_path, quality=92)


def main() -> None:
    cfg = load_config()
    group_id = cfg["project"]["group_id"]
    book_name = "T1_Thánh Mẫu Phương Danh (Tập 1)"
    pad_cfg = cfg.get("kimhannom_api", {}).get("bbox_padding", {})
    pad_x = int(pad_cfg.get("sinonom_pad_x", 6))
    pad_y = int(pad_cfg.get("sinonom_pad_y", 8))
    min_col_gap = int(pad_cfg.get("min_col_gap", 2))

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

    raw_ch_annotations = get_raw_sample_ch_annotations()
    ch_annotations = get_sample_ch_annotations(pad_x=pad_x, pad_y=pad_y, min_col_gap=min_col_gap)
    vi_annotations = get_sample_vi_annotations()

    # 1. Cập nhật cache JSON với boxes đã mở rộng
    for img_name, boxes in ch_annotations.items():
        cache_f = cache_book_dir / f"{Path(img_name).stem}.json"
        if cache_f.exists():
            data = json.loads(cache_f.read_text(encoding="utf-8"))
            data["boxes"] = boxes
            cache_f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. Copy 2 cặp ảnh và xuất Label.txt + fileState.txt chuẩn PPOCRLabel
    for img_name in ch_annotations:
        shutil.copy2(out_book_dir / "ch" / img_name, sample_ch_dir / img_name)
    write_ppocr_files(sample_ch_dir, ch_annotations, is_char_level=False)
    write_ppocr_files(out_book_dir / "ch", ch_annotations, is_char_level=False)

    for img_name in vi_annotations:
        shutil.copy2(out_book_dir / "vi" / img_name, sample_vi_dir / img_name)
    write_ppocr_files(sample_vi_dir, vi_annotations, is_char_level=False)
    write_ppocr_files(out_book_dir / "vi", vi_annotations, is_char_level=False)

    # 3. Xuất file ánh xạ hình ảnh chuẩn v2.4 (`<Tên sách>_image_map.json`) cho 2 cặp mẫu
    sample_image_map = {
        "pairs": [
            {
                "ch": ["T1_Thánh Mẫu Phương Danh (Tập 1).440.jpg"],
                "vi": ["T1_Thánh Mẫu Phương Danh (Tập 1).019.jpg"],
            },
            {
                "ch": ["T1_Thánh Mẫu Phương Danh (Tập 1).439.jpg"],
                "vi": ["T1_Thánh Mẫu Phương Danh (Tập 1).020.jpg"],
            },
        ]
    }
    (sample_book_dir / f"{book_name}_image_map.json").write_text(
        json.dumps(sample_image_map, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 4. Nạp bộ từ điển Hán Nôm từ cache nhị phân (`cache/dict_index.pkl`)
    print("Đang nạp bộ từ điển Hán Nôm (cache/dict_index.pkl)...")
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
    from_cache = dict_index.load_or_build_cache(
        sources, cache_path=Path(cfg["paths"]["cache_dir"]) / "dict_index.pkl"
    )
    print(f"  -> Đã nạp từ điển ({'từ cache .pkl' if from_cache else 'xây dựng cache mới'}).")

    # 5. Dóng hàng câu bằng Levenshtein & xuất CSV + XLSX chuẩn v2.4 (5 cột + text_diff)
    aligner = SinoNomAligner(dictionary_index=dict_index)
    pairs = get_sample_aligned_pairs(aligner)

    print("\n=== KIỂM TRA DÓNG HÀNG CÂU & TEXT_DIFF (QUY ĐỊNH v2.4) ===")
    for p in pairs:
        sn_chars = extract_sinonom_chars(p.ch_txt)
        qn_words = extract_quoc_ngu_syllables(p.vi_txt)
        red_items = [
            f"{it['nom_sub_text']}({it['vi_sub_text']})"
            for it in (p.text_diff or [])
            if it.get("type") == "error"
        ]
        print(
            f"  - {p.sentence_id}: {len(sn_chars)} chữ Nôm <-> {len(qn_words)} âm tiết Quốc ngữ | "
            f"Error ({len(red_items)}): {', '.join(red_items)}"
        )

    csv_sample_path = sample_book_dir / f"{book_name}.csv"
    xlsx_sample_path = sample_book_dir / f"{book_name}.xlsx"
    export_aligned_csv(pairs, csv_sample_path, is_pure_text=False)
    eval_report = export_aligned_xlsx_and_evaluate(
        pairs, xlsx_sample_path, dict_index, is_pure_text=False
    )

    shutil.copy2(csv_sample_path, out_book_dir / f"{book_name}.csv")
    shutil.copy2(xlsx_sample_path, out_book_dir / f"{book_name}.xlsx")

    print("\n=== KẾT QUẢ ĐÁNH GIÁ ĐỘ TƯƠNG ĐỒNG (CÔNG THỨC v2.4 TRANG 25) ===")
    print(f"  - Tổng số chữ Nôm tính điểm : {eval_report['scored_nom_chars']}")
    print(f"  - Số chữ đen (black_chars)  : {eval_report['black_chars']}")
    print(f"  - Số chữ đỏ (red_chars)     : {eval_report['red_chars']}")
    print(f"  - Số chữ vàng (warn_chars)  : {eval_report['warn_chars']} ({eval_report['warn_ratio_percent']}%)")
    print(f"  - Số hàng null              : {eval_report['null_rows']} ({eval_report['null_ratio_percent']}%)")
    print(f"  - Độ tương đồng (%)         : {eval_report['similarity_percent']}% (Yêu cầu >= 95%)")
    print(f"  - Đạt chuẩn nộp bài         : {'ĐẠT (PASSED)' if eval_report['passed_95_threshold'] else 'CHƯA ĐẠT'}")

    # 6. Chạy bộ kiểm tra tự động bắt buộc v2.4 (Trang 6, 10, 19)
    print("\n=== KIỂM TRA TỰ ĐỘNG BẮT BUỘC (MANDATORY VALIDATOR v2.4) ===")
    val_res = validate_book_v24(sample_book_dir, book_name, require_pdf=False)
    n_err = len(val_res["errors"])
    status_str = "PASS (0 lỗi)" if val_res["passed"] else f"FAIL ({n_err} lỗi)"
    print(f"  - Kết quả kiểm tra tự động  : {status_str}")
    for err in val_res["errors"]:
        print(f"    [LỖI] {err}")
    for warn in val_res["warnings"]:
        print(f"    [CẢNH BÁO] {warn}")
    if not val_res["passed"]:
        sys.exit(1)

    # 7. Đóng gói file ZIP mẫu chuẩn v2.4
    zip_path = PROJECT_ROOT / "submission" / f"{group_id}_sample.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(sample_book_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(sample_root))

    # 8. Tạo ảnh preview và ảnh so sánh Trước / Sau mở rộng box Nôm
    preview_dir = PROJECT_ROOT / "submission" / "preview"
    for img_name, boxes in ch_annotations.items():
        p_num = Path(img_name).stem.split(".")[-1]
        render_bbox_preview(
            sample_ch_dir / img_name,
            boxes,
            preview_dir / f"preview_ch_{p_num}.jpg",
            color="#0F9D58",
            show_index=True,
        )
        render_before_after_comparison(
            sample_ch_dir / img_name,
            raw_ch_annotations[img_name],
            boxes,
            preview_dir / f"preview_ch_{p_num}_before_after.jpg",
        )
    for img_name, boxes in vi_annotations.items():
        p_num = Path(img_name).stem.split(".")[-1]
        render_bbox_preview(
            sample_vi_dir / img_name,
            boxes,
            preview_dir / f"preview_vi_{p_num}.jpg",
            color="#1A73E8",
            show_index=True,
        )

    print(f"\n=== ĐÃ TẠO GÓI NỘP MẪU CHUẨN v2.4 THÀNH CÔNG ===")
    print(f"  - Padding Nôm : pad_x=+{pad_x}px, pad_y=+{pad_y}px, min_col_gap={min_col_gap}px")
    print(f"  - File nén ZIP: {zip_path} ({zip_path.stat().st_size / 1024:.1f} KB)")
    print(f"  - Ảnh so sánh : {preview_dir / 'preview_ch_440_before_after.jpg'}")


if __name__ == "__main__":
    main()
