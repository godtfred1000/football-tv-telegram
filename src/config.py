import os

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL = os.getenv("TELEGRAM_CHANNEL", "").strip()

FOOTBALL_DATA_API_TOKEN = os.getenv("FOOTBALL_DATA_API_TOKEN", "").strip()

# Gratis v1-nøkkel hos TheSportsDB er 123.
# Hvis du senere får en egen/premium nøkkel, kan den legges inn som GitHub Secret
# med navnet THESPORTSDB_API_KEY uten at koden må endres.
THESPORTSDB_API_KEY = os.getenv("THESPORTSDB_API_KEY", "123").strip() or "123"

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
