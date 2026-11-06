"""
Module đọc cấu hình dự án từ config.yaml và biến môi trường (.env).
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv

# Tải biến môi trường từ file .env
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
)


def load_config(config_path: Path = PROJECT_ROOT / "config.yaml") -> Dict[str, Any]:
    """Đọc file cấu hình YAML và kết hợp thông tin từ biến môi trường."""
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg.setdefault("auth", {})
    cfg["auth"]["base_url"] = os.getenv(
        "KIMHANNOM_BASE_URL", "https://kimhannom.fit.hcmus.edu.vn"
    )
    cfg["auth"]["email"] = os.getenv("KIMHANNOM_EMAIL", "")
    cfg["auth"]["password"] = os.getenv("KIMHANNOM_PASSWORD", "")
    cfg["auth"]["bearer_token"] = os.getenv("KIMHANNOM_BEARER_TOKEN", "")
    cfg["auth"]["user_agent"] = os.getenv("KIMHANNOM_USER_AGENT", DEFAULT_USER_AGENT)
    cfg["project"]["group_id"] = os.getenv(
        "GROUP_ID", cfg.get("project", {}).get("group_id", "MSSV1_MSSV2_MSSV3")
    )

    return cfg

