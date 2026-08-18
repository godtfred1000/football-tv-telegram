Bytt disse tre filene i GitHub:
- src/config.py
- src/feed.py
- .github/workflows/daily-tv-guide.yml

Test deretter:
Actions -> Daily football TV guide -> Run workflow
La Send demo-data stå AV.

Hvis du får 401: sjekk SportMonks-tokenet.
Hvis du får 403: SportMonks-planen mangler trolig tilgang til liga/TV-data.
