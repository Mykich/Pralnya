"""
Прайс бота з єдиного джерела цін.

Джерело: GET {PRICES_URL} (API Mini App, файл mini/catalog/prices.json).
Якщо API недоступний (сплячий Render, мережа) — запасна копія prices_fallback.json поруч із ботом.

PRICE_LIST, ITEM_ALIASES, PER_KG_ITEMS — ті самі словники, що й раніше використовував бот;
refresh_prices() оновлює їх «на місці», тому імпортовані посилання лишаються актуальними.
"""

import asyncio
import html
import json
import logging
import os

import aiohttp

PRICES_URL = os.getenv("PRICES_URL", "https://mini-mrip.onrender.com/api/prices")
FALLBACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices_fallback.json")
REFRESH_SECONDS = 3600

PRICE_DATA: dict = {}
PRICE_LIST: dict = {}  # назва позиції -> ціна
ITEM_ALIASES: dict = {}  # назва позиції -> слова, за якими її впізнаємо в тексті замовлення
PER_KG_ITEMS: set = set()  # позиції з ціною за кг (сума після зважування)
PRICE_SOURCE = "—"


def _validate(data: dict) -> dict:
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("у прайсі немає позицій")
    for item in items:
        if not item.get("name") or not isinstance(item.get("price"), (int, float)) or item["price"] <= 0:
            raise ValueError(f"некоректна позиція: {item}")
    return data


def _apply(data: dict, source: str):
    global PRICE_SOURCE
    PRICE_DATA.clear()
    PRICE_DATA.update(data)
    PRICE_LIST.clear()
    ITEM_ALIASES.clear()
    PER_KG_ITEMS.clear()
    for item in data["items"]:
        # Розпізнавання тексту — лише для позицій з aliases (у «Прасуванні» ті самі назви,
        # що й у «Пранні», тому без aliases вони не потрапляють у PRICE_LIST і не перезаписують ціну)
        if not item.get("aliases"):
            continue
        name = item["name"]
        PRICE_LIST[name] = item["price"]
        ITEM_ALIASES[name] = list(item["aliases"])
        if item.get("unit") == "кг":
            PER_KG_ITEMS.add(name)
    PRICE_SOURCE = f"{source}, версія {data.get('version', '?')}"


def load_fallback():
    with open(FALLBACK_PATH, encoding="utf-8") as f:
        _apply(_validate(json.load(f)), "запасна копія")


async def refresh_prices() -> bool:
    """Підтягує прайс з API. Повертає True, якщо вдалося; інакше лишає попередній."""
    try:
        timeout = aiohttp.ClientTimeout(total=60)  # сплячий Render прокидається до хвилини
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(PRICES_URL) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
        _apply(_validate(data), "API")
        return True
    except Exception as e:
        logging.error(f"Прайс з API не отримано, лишаю {PRICE_SOURCE}: {e}")
        return False


async def periodic_prices():
    while True:
        await refresh_prices()
        print(f"💰 Прайс: {len(PRICE_LIST)} позицій ({PRICE_SOURCE})")
        await asyncio.sleep(REFRESH_SECONDS)


# ---------- Тексти для меню «Прайс» ----------

def _fmt_price(item: dict) -> str:
    unit = item.get("unit", "шт")
    suffix = "" if unit == "шт" else f" / {unit}"
    return f"{int(item['price'])} грн{suffix}"


def section_lines(key: str) -> str:
    items = [i for i in PRICE_DATA.get("items", []) if i.get("section") == key]
    return "\n".join(f"{html.escape(i['name'])} — {_fmt_price(i)}" for i in items)


def section_title(key: str) -> str:
    for s in PRICE_DATA.get("sections", []):
        if s.get("key") == key:
            return s.get("title", key)
    return key


def price_note() -> str:
    note = PRICE_DATA.get("note") or (
        "Остаточна вартість залежить від матеріалу, стану речі та складності обробки. "
        "Перед початком роботи ми погоджуємо вартість із клієнтом."
    )
    return f"📌 {html.escape(note)}\n\n"


def b2b_text() -> tuple:
    b2b = PRICE_DATA.get("b2b") or {}
    prefix = "від " if b2b.get("price_from") else ""
    unit = b2b.get("unit", "кг")
    lines = "\n".join(
        f"{html.escape(i['name'])} — {prefix}{int(i['price'])} грн / {unit}" for i in b2b.get("items", [])
    )
    minimum = ""
    if b2b.get("min_kg") or b2b.get("min_amount"):
        minimum = f"Мінімальне B2B-замовлення — {b2b.get('min_kg', 0)} кг або {b2b.get('min_amount', 0)} грн.\n\n"
    return lines, minimum


def delivery_text() -> str:
    d = PRICE_DATA.get("delivery") or {}
    rows = []
    for z in d.get("zones", []):
        if not z.get("price"):
            rows.append(f"• {html.escape(z['name'])} — безкоштовно")
        else:
            way = " в один бік" if d.get("price_is_one_way") else ""
            free = f", безкоштовно від {z['free_from']} грн" if z.get("free_from") else ""
            rows.append(f"• {html.escape(z['name'])} — {z['price']} грн{way}{free}")
    tail = []
    if d.get("min_order_outside"):
        tail.append(f"Мінімальне замовлення з доставкою за межі ЖК — {d['min_order_outside']} грн.")
    if d.get("turnaround"):
        tail.append(f"Повертаємо чисті речі протягом {d['turnaround']}.")
    return "\n".join(rows) + ("\n\n" + "\n".join(tail) if tail else "")


def inspection_list() -> str:
    return "\n".join(f"• {html.escape(x)}" for x in PRICE_DATA.get("inspection_only", []))


# Прайс доступний одразу після імпорту — із запасної копії; API оновить його у фоні.
load_fallback()
