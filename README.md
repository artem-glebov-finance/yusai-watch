# Yusai-tei slot watcher

Watches the public slot API of yusai.kyoto and sends a Telegram message when a new slot
with `MIN_SEATS`+ free places appears on the configured dates.

A GitHub Actions run loops for ~5.7 h (a check every `INTERVAL` minutes, default 15),
then dispatches the next run. An hourly schedule restarts the chain if it breaks.
When all dates have passed, the workflow disables itself.

- Secrets: `TG_TOKEN`, `TG_CHAT_ID`, `DATES` (`YYYY-MM-DD[@HH:MM]`, comma-separated).
- Variables (optional): `MIN_SEATS` (2), `INTERVAL` (15).
- Logs print counters only.
