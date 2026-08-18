# Football TV Guide → Telegram

Automatisk Telegram-kanal for TV-oversikt over:

- UEFA Champions League
- Premier League

Land:

- 🇳🇴 Norge
- 🇸🇪 Sverige
- 🇩🇰 Danmark
- 🇦🇺 Australia
- 🇬🇧 England/UK

## 1. Opprett Telegram-kanalen

Opprett en kanal i Telegram og velg et offentlig kanalnavn, for eksempel:

`@footballtvguide`

## 2. Opprett bot

1. Åpne `@BotFather` i Telegram.
2. Send `/newbot`.
3. Velg navn og brukernavn.
4. Kopier bot-tokenet.
5. Legg boten til som administrator i Telegram-kanalen.
6. Gi boten rettighet til å poste meldinger.

## 3. GitHub Secrets

I GitHub-repositoriet:

`Settings → Secrets and variables → Actions → New repository secret`

Legg inn:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHANNEL` — eksempel `@footballtvguide`
- `FOOTBALL_TV_FEED_URL` — valgfri i første versjon

## 4. Test uten Telegram

```bash
pip install -r requirements.txt
python bot.py --demo --print-only
```

## 5. Test mot Telegram

Når token og kanal er satt som miljøvariabler:

```bash
python bot.py --demo
```

Eller kjør workflowen manuelt under GitHub → Actions og huk av `Send demo-data`.

## 6. Automatisk kjøring

GitHub Actions starter kl. 07:05 og 08:05 UTC. Scriptet sjekker `Europe/Oslo` og publiserer bare når lokal tid er 09:xx. Dette håndterer norsk sommer-/vintertid.

## Datamodell

TV-feed skal returnere:

```json
{
  "matches": [
    {
      "competition": "Premier League",
      "kickoff": "2026-08-18T21:00:00+02:00",
      "home": "Team A",
      "away": "Team B",
      "broadcasts": {
        "NO": ["Viaplay"],
        "SE": ["Viaplay"],
        "DK": ["Viaplay"],
        "AU": ["Stan Sport"],
        "UK": ["Sky Sports"]
      }
    }
  ]
}
```

## Neste del

Neste steg er å koble på én eller flere ekte TV-guide-/kampkilder og normalisere dem til formatet over. Resten av boten trenger da ikke endres.
