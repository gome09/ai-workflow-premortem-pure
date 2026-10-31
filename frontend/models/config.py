# frontend/models/config.py
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
DEMO_AUTO_AUTH = os.getenv("DEMO_AUTO_AUTH", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
DEMO_USER_EMAIL = os.getenv("DEMO_USER_EMAIL", "demo@example.com")
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "demo-password-123")
