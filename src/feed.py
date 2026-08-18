from __future__ import annotations

import json
from pathlib import Path
import requests

from .config import FEED_URL


def load_feed(demo: bool = False) -> dict:
    if demo:
        path = Path("data/demo_matches.json")
        return json.loads(path.read_text(encoding="utf-8"))

    if FEED_URL:
        response = requests.get(FEED_URL, timeout=25)
        response.raise_for_status()
        return response.json()

    path = Path("data/matches.json")
    return json.loads(path.read_text(encoding="utf-8"))
