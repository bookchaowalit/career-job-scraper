"""
Shared configuration for book-job-scraping.

Paths and env loading go through scripts/repo_paths.py so core and scripts
share one repo root (no legacy monorepo parents[N] layout).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# core/config.py → repo root is parent; scripts/ holds shared path helpers
_CORE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _CORE_DIR.parent
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from repo_paths import (  # noqa: E402
    DATA_DIR,
    REPO_ROOT as PROJECT_ROOT,
    SCRIPTS_DIR,
    load_env,
)

load_env()

# Telegram Bot — single source of truth
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram(message: str, chat_id: str | None = None) -> bool:
    """Send a Telegram message. Returns True on success."""
    token = TELEGRAM_BOT_TOKEN
    chat = chat_id or TELEGRAM_CHAT_ID
    if not token or not chat:
        print(
            "[WARN] Telegram not configured — set TELEGRAM_BOT_TOKEN "
            "and TELEGRAM_CHAT_ID in .env"
        )
        return False
    try:
        import requests

        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False
