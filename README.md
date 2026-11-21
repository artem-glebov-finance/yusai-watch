# Yusai-tei slot watcher

Watches the public slot API of yusai.kyoto and sends a Telegram message when a new slot
with `MIN_SEATS`+ free places appears on the configured dates.

A GitHub Actions run loops for ~5.7 h (a check every `INTERVAL` minutes, default 15),
then dispatches the next run. An hourly schedule restarts the chain if it breaks.
When all dates have passed, the workflow disables itself.

- Secrets: `TG_TOKEN`, `TG_CHAT_ID`, `DATES` (`YYYY-MM-DD[@HH:MM]`, comma-separated).
- Variables (optional): `MIN_SEATS` (2), `INTERVAL` (15).
- Logs print counters only.

## Katsuo-ji parking watcher (`katsuoji_watch.py`, workflow `katsuoji-watch`)

Watches the public Urakata calendar API behind the asoview booking page for the Katsuo-ji
weekend car park and sends a Telegram message when a 2-hour slot starting in the
`KATSU_FROM`–`KATSU_TO` window frees up. Same self-chaining loop; a check every `KATSU_INTERVAL` seconds (60).

- Secrets: `TG_TOKEN`, `TG_CHAT_ID`.
- Variables (optional): `KATSU_DATE` (2026-11-28), `KATSU_FROM` (10:00), `KATSU_TO` (14:00), `KATSU_UNTIL`, `KATSU_INTERVAL`.
