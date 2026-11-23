# Katsuo-ji parking watcher (`katsuoji_watch.py`, workflow `katsuoji-watch`)

Watches the public Urakata calendar API behind the asoview booking page for the Katsuo-ji
weekend car park and sends a Telegram message when a 2-hour slot starting in the
`KATSU_FROM`–`KATSU_TO` window frees up. A GitHub Actions run loops for several hours and then dispatches the next run; a check every `KATSU_INTERVAL` seconds (60).

- Secrets: `TG_TOKEN`, `TG_CHAT_ID`.
- Variables (optional): `KATSU_DATE` (2026-11-28), `KATSU_FROM` (10:00), `KATSU_TO` (14:00), `KATSU_UNTIL`, `KATSU_INTERVAL`.

# Saihoji watcher (`saihoji_watch.py`, workflow `saihoji-watch`)

Reads the public Nichi-nichi sanpai calendar page of Saihoji (intosaihoji.com) and sends a
Telegram message when a non-member entry slot on `SAIHO_DATE` has at least `SAIHO_SEATS` spots.
Same self-chaining loop as above; a check every `SAIHO_INTERVAL` seconds (300).

- Variables (optional): `SAIHO_DATE` (2026-11-25), `SAIHO_SEATS` (2), `SAIHO_UNTIL`, `SAIHO_INTERVAL`.
