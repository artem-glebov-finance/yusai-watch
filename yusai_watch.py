#!/usr/bin/env python3
"""Монитор свободных мест в галерее Юсай-тэй (祐斎亭, Арасияма) → Telegram.

Источник: публичный API сайта yusai.kyoto (тот же, что дёргает страница бронирования).
Шлёт сообщение, когда на нужные даты появляется слот с >= MIN_SEATS мест,
которого не было при прошлой проверке. Состояние — в state.json.

Режимы:
  python3 yusai_watch.py            — одна проверка
  python3 yusai_watch.py --loop     — проверки каждые INTERVAL мин в течение LOOP_MINUTES мин;
                                      когда все даты прошли, создаёт файл DONE
  python3 yusai_watch.py --status   — показать текущие места, ничего не слать (локально)
  python3 yusai_watch.py --test     — отправить тестовое сообщение в Telegram
  python3 yusai_watch.py --whoami   — показать chat_id тех, кто написал боту (локально)

Переменные окружения: TG_TOKEN, TG_CHAT_ID, MIN_SEATS, INTERVAL, LOOP_MINUTES,
  DATES — даты через запятую, у даты можно указать окно: YYYY-MM-DD@14:00 (с), @-12:00 (до), @10:00-12:00.
В публичных логах печатаются только счётчики, без дат и ID.
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

API = "https://yusaitei-2024-server-keakosfy4q-an.a.run.app/api/v1"
COURSES = {
    5692539581497344: "紅葉期 (осень, ¥3000)",
    5691948318851072: "紅葉初期 (ранняя осень, ¥2000)",
    5632499082330112: "обычный (¥2000)",
}
BOOK_URL = ("https://yusai.kyoto/reserve/reserve?"
            + "&".join(f"courseIds={c}" for c in sorted(COURSES)))
JST = dt.timezone(dt.timedelta(hours=9))
def _window(spec):
    """'14:00' → с 14:00; '-12:00' → до 12:00 (не включая); '10:00-12:00' → окно."""
    lo, _, hi = spec.partition("-")
    return (lo or "00:00", hi or "24:00")


WINDOWS = {d: _window(w) for d, _, w in
           (x.strip().partition("@") for x in (os.environ.get("DATES") or "").split(",")) if d}
DATES = sorted(WINDOWS)
MIN_SEATS = int(os.environ.get("MIN_SEATS") or "2")
INTERVAL = int(os.environ.get("INTERVAL") or "15")
LOOP_MINUTES = int(os.environ.get("LOOP_MINUTES") or "340")
CLOSE = "17:30"  # галерея закрывается — после этого времени последнего дня мониторить нечего
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
WD = "пн вт ср чт пт сб вс".split()
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Origin": "https://yusai.kyoto", "Referer": "https://yusai.kyoto/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_slots():
    """[(date 'YYYY-MM-DD', 'HH:MM', remaining, course_id)] для DATES, только будущие слоты."""
    start = dt.datetime.fromisoformat(min(DATES)).replace(tzinfo=JST)
    end = dt.datetime.fromisoformat(max(DATES)).replace(tzinfo=JST) + dt.timedelta(days=1)
    now = dt.datetime.now(JST)
    out = []
    for cid in COURSES:
        q = urllib.parse.urlencode({"courseID": cid, "dateTimeStartFrom": start.isoformat(),
                                    "dateTimeStartTo": end.isoformat()})
        data = get_json(f"{API}/availableSlots?{q}")
        for s in data.get("availableSlots") or []:
            t = dt.datetime.fromisoformat(s["dateTimeStart"].replace("Z", "+00:00")).astimezone(JST)
            d = t.strftime("%Y-%m-%d")
            hm = t.strftime("%H:%M")
            if d not in WINDOWS or not (WINDOWS[d][0] <= hm < WINDOWS[d][1]) or t < now or s.get("privatelyReserved"):
                continue
            out.append((d, hm, int(s.get("remainingSlots") or 0), cid))
    return sorted(out)


def tg(method, **params):
    token = os.environ["TG_TOKEN"]
    body = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", body, timeout=30) as r:
        return json.load(r)


def send(text):
    chat = os.environ.get("TG_CHAT_ID")
    if not os.environ.get("TG_TOKEN") or not chat:
        print("[no telegram config] would send:\n" + text)
        return
    try:
        tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview="true")
    except Exception as e:
        print("telegram error:", type(e).__name__, getattr(e, "code", ""))


def human_date(d):
    x = dt.date.fromisoformat(d)
    return f"{x.day}.{x.month:02d} ({WD[x.weekday()]})"


def fmt(slots):
    lines, cur = [], None
    for d, hm, n, cid in slots:
        if d != cur:
            cur = d
            lines.append(f"\n<b>{human_date(d)}</b>")
        lines.append(f"  {hm} — {n} мест · {COURSES[cid]}")
    return "\n".join(lines).strip()


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def check():
    prev = load_state()
    st = dict(prev or {})
    try:
        slots = fetch_slots()
    except Exception as e:  # сеть / API
        st["errors"] = st.get("errors", 0) + 1
        print("fetch error:", type(e).__name__, getattr(e, "code", ""))
        if st["errors"] == 3:
            send(f"⚠️ Юсай-тэй: 3 проверки подряд не удались ({e}). Попробую дальше.")
        save_state(st)
        return
    if st.get("errors", 0) >= 3:
        send("✅ Юсай-тэй: API снова отвечает, мониторинг продолжается.")
    st["errors"] = 0

    good = [s for s in slots if s[2] >= MIN_SEATS]
    key = lambda s: f"{s[0]} {s[1]} {s[3]}"
    seen = set(st.get("available", []))
    new = [s for s in good if key(s) not in seen]
    st["available"] = sorted(key(s) for s in good)
    st["last_check"] = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")
    print(st["last_check"], "slots:", len(slots), "with >=", MIN_SEATS, ":", len(good), "new:", len(new))

    if prev is None:
        def span(lo, hi):
            return ("весь день" if (lo, hi) == ("00:00", "24:00") else
                    f"до {hi}" if lo == "00:00" else f"с {lo}" if hi == "24:00" else f"{lo}–{hi}")
        dates = ", ".join(f"{human_date(d)} {span(*WINDOWS[d])}" for d in DATES)
        body = fmt(good) if good else "сейчас мест нет"
        send(f"👀 Мониторинг Юсай-тэй запущен.\nДаты: {dates}, от {MIN_SEATS} мест, проверка каждые {INTERVAL} мин.\n\n{body}")
    elif new:
        send(f"🍁 <b>Юсай-тэй: появились места!</b>\n\n{fmt(new)}\n\n"
             f'<a href="{BOOK_URL}">Забронировать</a> — места разбирают быстро.')
    save_state(st)


def finished():
    return dt.datetime.now(JST) > dt.datetime.fromisoformat(f"{max(DATES)}T{CLOSE}").replace(tzinfo=JST)


def loop():
    stop = time.time() + LOOP_MINUTES * 60
    while True:
        if finished():
            send("🏁 Мониторинг Юсай-тэй завершён: все даты прошли.")
            open("DONE", "w").close()
            print("all dates passed -> DONE")
            return
        check()
        nxt = (int(time.time()) // (INTERVAL * 60) + 1) * INTERVAL * 60 + 60  # ровные отметки + 1 мин
        if nxt > stop:
            return
        time.sleep(max(1, nxt - time.time()))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if not DATES and arg not in ("--test", "--whoami"):
        sys.exit("DATES не задан")
    if arg == "--loop":
        loop()
    elif arg == "--status":
        slots = fetch_slots()
        print(fmt([s for s in slots if s[2] > 0]) or "мест нет")
        print(f"\n(всего слотов {len(slots)}, окна {WINDOWS})")
    elif arg == "--test":
        send("✅ Тест: бот мониторинга Юсай-тэй на связи.")
    elif arg == "--whoami":
        me = tg("getMe").get("result", {})
        hook = tg("getWebhookInfo").get("result", {}).get("url")
        ups = tg("getUpdates").get("result", [])
        print(f"bot: @{me.get('username')}  webhook: {hook or '-'}  updates: {len(ups)}")
        for u in ups:
            m = u.get("message") or u.get("my_chat_member") or {}
            c = m.get("chat") or {}
            print("chat_id:", c.get("id"), c.get("type"), c.get("username") or c.get("title") or "")
    else:
        check()


if __name__ == "__main__":
    main()
