# LiveSoccerTV test

Denne versjonen bruker:

- football-data.org til kamper
- LiveSoccerTV til TV-/streamingkanalnavn

Den henter kun navn på lovlige rettighetshavere/kanaler. Den henter ingen strømmer.

Erstatt:
- src/config.py
- src/feed.py
- requirements.txt
- .github/workflows/daily-tv-guide.yml

Legg også til:
- src/tv_livesoccertv.py

Test med:
Actions -> Daily football TV guide -> Run workflow
Send demo-data = AV
Antall dager = 7

Merk: LiveSoccerTV har ikke et offentlig API. Denne integrasjonen leser nettsidens HTML og kan derfor slutte å virke hvis siden endres eller blokkerer automatiske forespørsler.
