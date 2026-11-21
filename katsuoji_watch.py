#!/usr/bin/env python3
"""Монитор свободных слотов парковки Кацуо-дзи (勝尾寺マイカー駐車場, выходные) → Telegram.

Источник: публичный API системы бронирования Urakata (его же дёргает страница asoview):
  https://katsuo-ji-temple.urkt.in/api/direct/courses/22796/calendars/{date}?language_type=ja
Слот = время начала (каждый час 08:00–19:00), бронь на 2 часа. Свободен, если
available_seat_count > 0 (статус тогда «realtime»; «full» — занято, «close» — не продаётся).
Места возвращаются при отменах и когда сгорают брони без «本予約».

Шлёт сообщение, когда в окне KATSU_FROM–KATSU_TO появляется свободный слот, которого
не было при прошлой проверке. Состояние — в katsuoji-state.json.

Режимы:
  python3 katsuoji_watch.py            — одна проверка
  python3 katsuoji_watch.py --loop     — проверки каждые KATSU_INTERVAL сек в течение LOOP_MINUTES мин;
                                         после KATSU_UNTIL создаёт файл KATSU_DONE
  python3 katsuoji_watch.py --status   — показать все слоты дня, ничего не слать
  python3 katsuoji_watch.py --test     — тестовое сообщение в Telegram

Переменные окружения: TG_TOKEN, TG_CHAT_ID, KATSU_DATE (2026-11-28), KATSU_FROM (10:00),
  KATSU_TO (14:00) — окно времени начала слота, KATSU_UNTIL (JST, по умолчанию дата + KATSU_TO),
  KATSU_INTERVAL (60), LOOP_MINUTES (340).
В публичных логах печатаются только счётчики.
"""
import datetime as dt
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request

COURSE = 22796
API = f"https://katsuo-ji-temple.urkt.in/api/direct/courses/{COURSE}/calendars"
BOOK_URL = f"https://www.asoview.com/channel/activities/ja/katsuo-ji-temple/offices/4241/courses/{COURSE}/calendars"
JST = dt.timezone(dt.timedelta(hours=9))
DATE = os.environ.get("KATSU_DATE") or "2026-11-28"
FROM = os.environ.get("KATSU_FROM") or "10:00"
TO = os.environ.get("KATSU_TO") or "14:00"
UNTIL = os.environ.get("KATSU_UNTIL") or f"{DATE}T{TO}"
INTERVAL = int(os.environ.get("KATSU_INTERVAL") or "60")
LOOP_MINUTES = int(os.environ.get("LOOP_MINUTES") or "340")
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "katsuoji-state.json")
DONE = os.path.join(HERE, "KATSU_DONE")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
WD = "пн вт ср чт пт сб вс".split()


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json",
                                               "Origin": "https://www.asoview.com",
                                               "Referer": "https://www.asoview.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def slots():
    """[(HH:MM, status, free)] на DATE, все часы."""
    data = get_json(f"{API}/{DATE}?language_type=ja")
    return sorted((s["time"], s.get("status"), int(s.get("available_seat_count") or 0)) for s in data)


def free_in_window(all_slots):
    return [(t, n) for t, _, n in all_slots if FROM <= t <= TO and n > 0]


def tg(method, **params):
    body = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{os.environ['TG_TOKEN']}/{method}", body, timeout=30) as r:
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


def human_date():
    x = dt.date.fromisoformat(DATE)
    return f"{x.day}.{x.month:02d} ({WD[x.weekday()]})"


def end2h(t):
    h, m = map(int, t.split(":"))
    return f"{h + 2:02d}:{m:02d}"


def fmt(free):
    return "\n".join(f"  {t}–{end2h(t)}" + (f" — {n} мест" if n > 1 else "") for t, n in free)


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
    target = f"{DATE} {FROM}-{TO}"
    if prev and prev.get("target") != target:
        prev = None  # другая дата или окно — начинаем с чистого листа
    st = dict(prev or {})
    st["target"] = target
    try:
        all_slots = slots()
    except Exception as e:
        st["errors"] = st.get("errors", 0) + 1
        print("fetch error:", type(e).__name__, getattr(e, "code", ""))
        if st["errors"] == 5:
            send(f"⚠️ Парковка Кацуо-дзи: 5 проверок подряд не удались ({type(e).__name__}). Пробую дальше.")
        save_state(st)
        return
    if st.get("errors", 0) >= 5:
        send("✅ Парковка Кацуо-дзи: API снова отвечает, мониторинг продолжается.")
    st["errors"] = 0

    free = free_in_window(all_slots)
    seen = set(st.get("free", []))
    new = [x for x in free if x[0] not in seen]
    st["free"] = [t for t, _ in free]
    st["last_check"] = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    print(st["last_check"], "slots:", len(all_slots), "free in window:", len(free), "new:", len(new))

    head = f"Парковка Кацуо-дзи {human_date()}, заезд {FROM}–{TO}"
    if prev is None:
        now = ("свободно:\n" + fmt(free)) if free else "сейчас всё занято"
        send(f"👀 Мониторинг запущен.\n{head}, проверка раз в минуту.\n\n{now}")
    elif new:
        send(f"🚗 <b>Кацуо-дзи: освободилась парковка!</b>\n{head}\n\n{fmt(new)}\n\n"
             f'<a href="{BOOK_URL}">Забронировать на asoview</a> → дата → время → 予約申込に進む. '
             "Потом сразу подтвердить по ссылке из письма (本予約).")
    save_state(st)


def finished():
    return dt.datetime.now(JST) > dt.datetime.fromisoformat(UNTIL).replace(tzinfo=JST)


def loop():
    stop = time.time() + LOOP_MINUTES * 60
    while True:
        if finished():
            send(f"🏁 Мониторинг парковки Кацуо-дзи {human_date()} завершён.")
            open(DONE, "w").close()
            print("past KATSU_UNTIL -> DONE")
            return
        check()
        if time.time() + INTERVAL > stop:
            return
        time.sleep(INTERVAL + random.uniform(0, 8))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--loop":
        loop()
    elif arg == "--status":
        for t, s, n in slots():
            mark = "*" if FROM <= t <= TO else " "
            print(f"{mark} {t} {s:9} free={n}")
    elif arg == "--test":
        send(f"✅ Тест: монитор парковки Кацуо-дзи на связи ({human_date()}, заезд {FROM}–{TO}).")
    else:
        check()


if __name__ == "__main__":
    main()
