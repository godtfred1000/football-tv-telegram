import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "").strip()
FOOTBALL_DATA_API_TOKEN = os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()

COUNTRIES = {
    "NO": ("🇳🇴", "Norge"),
    "SE": ("🇸🇪", "Sverige"),
    "DK": ("🇩🇰", "Danmark"),
    "AU": ("🇦🇺", "Australia"),
    "UK": ("🇬🇧", "England/UK"),
}

ALLOWED_COMPETITIONS = {
    "UEFA Champions League",
    "Champions League",
    "Premier League",
}
