#!/usr/bin/env python3
"""Монитор слотов Сайходзи (西芳寺, «храм мхов», Nichi-nichi sanpai) → Telegram.

Источник: публичная страница календаря (без логина), все слоты месяца лежат прямо в HTML:
  https://intosaihoji.com/en/booking/nichinichi?year=YYYY&month=M
Для каждого дня блок «reservation status on November 25, 2026», в нём колонки
Non-members / Members; слот = <div class="selectList__item__select" data-can-booking="0|1">
со статусом «Closed», «N spots remaining» или «〇 Available».

Считаем только Non-members (Members — для членов Saihokai). Слот подходит, если
data-can-booking="1" и мест ≥ SAIHO_SEATS («Available» = много). Сообщение уходит, когда
подходящий слот появляется (его не было подходящим при прошлой проверке).
Состояние — в saihoji-state.json.

Режимы:
  python3 saihoji_watch.py            — одна проверка
  python3 saihoji_watch.py --loop     — проверки каждые SAIHO_INTERVAL сек в течение LOOP_MINUTES мин;
                                        после SAIHO_UNTIL создаёт файл SAIHO_DONE
  python3 saihoji_watch.py --status   — показать слоты дня, ничего не слать
  python3 saihoji_watch.py --test     — тестовое сообщение в Telegram

Переменные окружения: TG_TOKEN, TG_CHAT_ID, SAIHO_DATE (2026-11-25), SAIHO_SEATS (2),
  SAIHO_UNTIL (JST, по умолчанию дата + 11:30), SAIHO_INTERVAL (300), LOOP_MINUTES (340).
"""
import datetime as dt
import html
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request

JST = dt.timezone(dt.timedelta(hours=9))
DATE = os.environ.get("SAIHO_DATE") or "2026-11-25"
SEATS = int(os.environ.get("SAIHO_SEATS") or "2")
UNTIL = os.environ.get("SAIHO_UNTIL") or f"{DATE}T11:30"
INTERVAL = int(os.environ.get("SAIHO_INTERVAL") or "300")
LOOP_MINUTES = int(os.environ.get("LOOP_MINUTES") or "340")
D = dt.date.fromisoformat(DATE)
URL = f"https://intosaihoji.com/en/booking/nichinichi?year={D.year}&month={D.month}"
BOOK_URL = "https://intosaihoji.com/en/booking/nichinichi"
HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "saihoji-state.json")
DONE = os.path.join(HERE, "SAIHO_DONE")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
WD = "пн вт ср чт пт сб вс".split()
MANY = 99

SLOT_RE = re.compile(
    r'selectList__item__select"[^>]*data-member-only="(\d)"[^>]*data-can-booking="(\d)"[^>]*>'
    r'\s*<span class="date">\s*([\d:]+)[^<]*</span>(.*?)</div>', re.S)


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def slots():
    """[(HH:MM, can_booking, free, status_text)] для Non-members на DATE."""
    page = fetch()
    label = f"reservation status on {D.strftime('%B')} {D.day}, {D.year}"
    i = page.find(label)
    if i < 0:
        raise ValueError("day block not found")
    j = page.find("reservation status on", i + len(label))
    block = page[i:j if j > 0 else len(page)]
    out = []
    for member, can, t, rest in SLOT_RE.findall(block):
        if member != "0":
            continue
        status = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", rest))).strip()
        m = re.search(r"(\d+)\s*spots? remaining", status)
        if m:
            free = int(m.group(1))
        elif "Available" in status:
            free = MANY
        else:
            free = 0
        out.append((t, can == "1", free if can == "1" else 0, status))
    if not out:
        raise ValueError("no non-member slots parsed")
    return out


def good(all_slots):
    return [(t, n) for t, can, n, _ in all_slots if can and n >= SEATS]


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
    return f"{D.day}.{D.month:02d} ({WD[D.weekday()]})"


def fmt(lst):
    return "\n".join(f"  {t} — " + ("много мест" if n >= MANY else f"{n} мест") for t, n in lst)


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
    target = f"{DATE} x{SEATS}"
    if prev and prev.get("target") != target:
        prev = None
    st = dict(prev or {})
    st["target"] = target
    try:
        all_slots = slots()
    except Exception as e:
        st["errors"] = st.get("errors", 0) + 1
        print("fetch error:", type(e).__name__, getattr(e, "code", ""), str(e)[:60])
        if st["errors"] == 3:
            send(f"⚠️ Сайходзи: 3 проверки подряд не удались ({type(e).__name__}). Пробую дальше.")
        save_state(st)
        return
    if st.get("errors", 0) >= 3:
        send("✅ Сайходзи: страница снова читается, мониторинг продолжается.")
    st["errors"] = 0

    ok = good(all_slots)
    seen = set(st.get("ok", []))
    new = [x for x in ok if x[0] not in seen]
    st["ok"] = [t for t, _ in ok]
    st["last_check"] = dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S JST")
    singles = [t for t, can, n, _ in all_slots if can and 0 < n < SEATS]
    print(st["last_check"], "slots:", len(all_slots), f"ok(>={SEATS}):", len(ok), "new:", len(new),
          "below:", len(singles))

    head = f"Сайходзи {human_date()}, нужно {SEATS} места в одном слоте"
    if prev is None:
        now = ("уже есть:\n" + fmt(ok)) if ok else "подходящих слотов нет" + (
            f" (по 1 месту: {', '.join(singles)})" if singles else "")
        send(f"👀 Мониторинг запущен.\n{head}, проверка раз в {INTERVAL // 60} мин.\n\n{now}")
    elif new:
        send(f"🌿 <b>Сайходзи: появились места!</b>\n{head}\n\n{fmt(new)}\n\n"
             f'<a href="{BOOK_URL}">Забронировать</a> → залогиниться → 25 → Non-members → время → Next step.')
    save_state(st)


def finished():
    return dt.datetime.now(JST) > dt.datetime.fromisoformat(UNTIL).replace(tzinfo=JST)


def loop():
    stop = time.time() + LOOP_MINUTES * 60
    while True:
        if finished():
            send(f"🏁 Мониторинг Сайходзи {human_date()} завершён.")
            open(DONE, "w").close()
            print("past SAIHO_UNTIL -> DONE")
            return
        check()
        if time.time() + INTERVAL > stop:
            return
        time.sleep(INTERVAL + random.uniform(0, 20))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--loop":
        loop()
    elif arg == "--status":
        for t, can, n, s in slots():
            print(f"{'*' if can and n >= SEATS else ' '} {t} can={int(can)} free={n:>2}  {s}")
    elif arg == "--test":
        send(f"✅ Тест: монитор Сайходзи на связи ({human_date()}, {SEATS} места в одном слоте).")
    else:
        check()


if __name__ == "__main__":
    main()
