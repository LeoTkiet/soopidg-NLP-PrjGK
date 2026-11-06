"""
Bước 5 & 6: Đọc và lập chỉ mục Bộ dữ liệu Từ điển Hán Nôm và Quốc ngữ
(D:/PrjGK/dictionaries-04-11-2026/entries/*.jsonl - Schema v1).
Phục vụ:
1. Kiểm tra chính tả (Spellcheck) và đối chiếu chữ Hán Nôm - âm đọc Quốc ngữ.
2. Tính năng dóng hàng (Alignment) dựa trên âm đọc 1-1.
3. Tô màu đen (đúng nghĩa/âm đọc) và màu đỏ (sai nghĩa/không tìm thấy trong từ điển) trong file .xlsx.
"""

import json
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Set


class HanNomDictionaryIndex:
    """Bộ lập chỉ mục ánh xạ Chữ Hán Nôm <-> Tập âm đọc Quốc ngữ / Hán Việt / Nôm & Chữ dị thể."""

    def __init__(self, entries_dir: Path) -> None:
        self.entries_dir = entries_dir
        # char -> set of lowercase NFC readings (qn, hv, nom)
        self.char_to_readings: Dict[str, Set[str]] = defaultdict(set)
        # char -> set of variant chars
        self.char_to_variants: Dict[str, Set[str]] = defaultdict(set)

    @staticmethod
    def normalize_text(text: str) -> str:
        """Chuẩn hóa NFC và chữ thường theo đúng đặc tả từ điển (Trang 3)."""
        return unicodedata.normalize("NFC", text.strip().lower())

    def load_sources(self, source_filenames: Iterable[str]) -> None:
        """
        Đọc các file .jsonl trong thư mục entries/ và nạp vào bộ nhớ.
        Cấu trúc mỗi bản ghi (Entry):
        - head: chữ Hán/Nôm (hoặc từ Quốc ngữ với dnqatv_wikisource)
        - script: 'han', 'nom', 'qn', ...
        - forms: [{'text': ..., 'script': ...}]
        - readings: [{'value': ..., 'system': 'qn'|'hv'|'nom'|...}]
        - variants: [{'char': ..., 'type': ...}]
        """
        for fname in source_filenames:
            fpath = self.entries_dir / fname
            if not fpath.exists():
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._index_entry(entry)

    def _index_entry(self, entry: dict) -> None:
        head = unicodedata.normalize("NFC", entry.get("head", ""))
        script = entry.get("script", "")
        readings = entry.get("readings", [])
        forms = entry.get("forms", [])
        variants = entry.get("variants", [])

        # Thu thập âm đọc tiếng Việt (qn, hv, nom)
        vi_readings: Set[str] = set()
        for r in readings:
            if r.get("system") in ("qn", "hv", "nom") and r.get("value"):
                vi_readings.add(self.normalize_text(r["value"]))

        if script in ("han", "nom") and head:
            for r_val in vi_readings:
                self.char_to_readings[head].add(r_val)
            for v in variants:
                v_char = v.get("char")
                if v_char:
                    self.char_to_variants[head].add(v_char)
                    self.char_to_variants[v_char].add(head)

        elif script == "qn" and head:
            # Với từ điển Quốc ngữ (như dnqatv_wikisource), head là Quốc ngữ, forms chứa chữ Nôm/Hán
            qn_word = self.normalize_text(head)
            for form in forms:
                if form.get("script") in ("han", "nom") and form.get("text"):
                    f_text = unicodedata.normalize("NFC", form["text"])
                    self.char_to_readings[f_text].add(qn_word)

    def is_match(self, sinonom_char: str, quoc_ngu_syllable: str) -> bool:
        """
        Kiểm tra chữ Hán Nôm và âm tiết Quốc ngữ có khớp nhau trong từ điển (hoặc qua chữ dị thể) không.
        Quy định (Trang 9):
        - Giống nhau về nghĩa/âm trong từ điển -> True (Tô màu đen).
        - Khác nhau hoặc không tìm thấy trong từ điển -> False (Tô màu đỏ).
        """
        char_nfc = unicodedata.normalize("NFC", sinonom_char.strip())
        qn_norm = self.normalize_text(quoc_ngu_syllable)

        if not char_nfc or not qn_norm:
            return False

        # Kiểm tra trực tiếp
        if qn_norm in self.char_to_readings.get(char_nfc, set()):
            return True

        # Kiểm tra thông qua chữ dị thể (variants)
        for var_char in self.char_to_variants.get(char_nfc, set()):
            if qn_norm in self.char_to_readings.get(var_char, set()):
                return True

        return False

