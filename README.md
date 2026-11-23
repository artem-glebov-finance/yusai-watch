# Katsuo-ji parking watcher (`katsuoji_watch.py`, workflow `katsuoji-watch`)

Watches the public Urakata calendar API behind the asoview booking page for the Katsuo-ji
weekend car park and sends a Telegram message when a 2-hour slot starting in the
`KATSU_FROM`–`KATSU_TO` window frees up. A GitHub Actions run loops for several hours and then dispatches the next run; a check every `KATSU_INTERVAL` seconds (60).

- Secrets: `TG_TOKEN`, `TG_CHAT_ID`.
- Variables (optional): `KATSU_DATE` (2026-11-28), `KATSU_FROM` (10:00), `KATSU_TO` (14:00), `KATSU_UNTIL`, `KATSU_INTERVAL`.
