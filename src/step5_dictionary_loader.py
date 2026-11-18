"""
Bước 5 & 6: Đọc và lập chỉ mục Bộ dữ liệu Từ điển Hán Nôm và Quốc ngữ
(D:/PrjGK/dictionaries-04-11-2026/entries/*.jsonl - Schema v1).
Phục vụ:
1. Kiểm tra chính tả (Spellcheck) và đối chiếu chữ Hán Nôm - âm đọc Quốc ngữ.
2. Tính năng dóng hàng (Alignment) dựa trên âm đọc 1-1.
3. Tô màu đen (đúng nghĩa/âm đọc) và màu đỏ (sai nghĩa/không tìm thấy trong từ điển) trong file .xlsx.
"""

import json
import pickle
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple


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
        relations = entry.get("relations", [])

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
            for rel in relations:
                rel_to = rel.get("to")
                if rel_to:
                    self.char_to_variants[head].add(rel_to)
                    self.char_to_variants[rel_to].add(head)

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

    def get_readings(self, sinonom_char: str) -> Set[str]:
        """Trả về toàn bộ tập âm đọc Quốc ngữ của chữ Hán Nôm (gồm cả chữ dị thể)."""
        char_nfc = unicodedata.normalize("NFC", sinonom_char.strip())
        if not char_nfc:
            return set()
        readings = set(self.char_to_readings.get(char_nfc, set()))
        for var_char in self.char_to_variants.get(char_nfc, set()):
            readings.update(self.char_to_readings.get(var_char, set()))
        return readings

    def load_or_build_cache(
        self,
        source_filenames: Iterable[str],
        cache_path: Optional[Path] = None,
    ) -> bool:
        """
        Nạp chỉ mục từ điển từ file cache nhị phân (`cache/dict_index.pkl`) nếu các file JSONL gốc
        chưa thay đổi (giảm thời gian nạp từ ~15 giây xuống < 0.2 giây).
        Trả về True nếu nạp từ cache, False nếu vừa xây dựng lại cache mới.
        """
        src_list = list(source_filenames)
        sig: List[Tuple[str, float, int]] = []
        for fname in src_list:
            fpath = self.entries_dir / fname
            if fpath.exists():
                st = fpath.stat()
                sig.append((fname, round(st.st_mtime, 2), st.st_size))

        if cache_path and cache_path.exists():
            try:
                with open(cache_path, "rb") as f:
                    payload = pickle.load(f)
                if payload.get("signature") == sig:
                    self.char_to_readings = defaultdict(set, payload["char_to_readings"])
                    self.char_to_variants = defaultdict(set, payload["char_to_variants"])
                    return True
            except Exception:
                pass

        self.load_sources(src_list)
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(
                    {
                        "signature": sig,
                        "char_to_readings": dict(self.char_to_readings),
                        "char_to_variants": dict(self.char_to_variants),
                    },
                    f,
                    protocol=pickle.HIGHEST_PROTOCOL,
                )
        return False

