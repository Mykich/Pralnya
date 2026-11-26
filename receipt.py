"""
Квитанція приймання: текст для Telegram і PDF для друку та підпису.

Чисті функції без Telegram і Google: на вхід — замовлення і рядки листа «🧾 Приймання»
(словники «заголовок → значення»), на вихід — текст / байти PDF.
"""

import html
import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo

    KYIV = ZoneInfo("Europe/Kyiv")
except Exception:  # немає tzdata — беремо час сервера
    KYIV = None

BUSINESS_NAME = "Пральня Вдома"
BUSINESS_ADDRESS = "м. Київ, вул. Бульварно-Кудрявська, 17А"
BUSINESS_PHONE = "+380 93 577 11 90"

# Текст умов — той самий, що в FAQ сайту (погоджений 2026-11-25)
TERMS = (
    "Під час приймання ми оглянули кожну річ і зафіксували її стан у цій квитанції. "
    "Речі з підвищеним ризиком прийняті лише з Вашої згоди. "
    "Якщо результат Вас не влаштовує, ми безкоштовно повторно обробимо річ або виправимо її в ательє. "
    "Видимі недоліки, будь ласка, перевіряйте під час отримання, приховані — повідомте нам "
    "протягом 14 днів, зберігши квитанцію та річ."
)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Заголовки листа «🧾 Приймання» (як у tools/crm_intake_sheet_2026_11_26.py)
H_DATE = "Дата приймання"
H_ORDER = "Номер замовлення"
H_TAG = "Бирка"
H_ITEM = "Річ"
H_QTY = "К-сть одиниць"
H_SERVICE = "Послуга"
H_MATERIAL = "Матеріал / наповнювач"
H_COLOR = "Колір / бренд"
H_STAINS = "Плями"
H_WEAR = "Знос"
H_HARDWARE = "Фурнітура"
H_LABEL = "Ярлик"
H_DEFECTS = "Дефекти / коментар"
H_SAID = "Зі слів клієнта"
H_POCKETS = "Вміст кишень"
H_RISK = "Ризик"
H_CONSENT = "Згода клієнта"
H_PHOTO = "Фото"
H_PRICE = "Ціна, ₴"
H_ACCEPTED_BY = "Прийняв"
H_SENT = "Квитанція в Telegram"
H_CONFIRMED = "Підтверджено в Telegram"
H_SIGNED = "Підпис на папері"
H_ISSUED = "Видано"


def now_kyiv():
    return datetime.now(KYIV) if KYIV else datetime.now()


def parse_price(value):
    text = "".join(ch for ch in str(value or "") if ch.isdigit() or ch in ",.")
    text = text.replace(",", ".")
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def fmt_money(value):
    value = round(float(value or 0))
    return f"{value:,}".replace(",", " ")


def condition_parts(item):
    """Список відхилень від норми для однієї речі (порожній — без видимих дефектів)."""
    parts = []
    if item.get(H_STAINS) == "Є":
        parts.append("плями")
    if item.get(H_WEAR) in ("Помірний", "Сильний"):
        parts.append(f"знос: {item[H_WEAR].lower()}")
    if item.get(H_HARDWARE) in ("Пошкоджена", "Відсутня частина"):
        parts.append(f"фурнітура: {item[H_HARDWARE].lower()}")
    if item.get(H_LABEL) == "Немає":
        parts.append("без ярлика")
    elif item.get(H_LABEL) == "Нечитабельний":
        parts.append("ярлик нечитабельний")
    if item.get(H_POCKETS) == "Знайдено":
        parts.append("у кишенях знайдено речі (повернемо Вам)")
    return parts


def condition_text(item):
    parts = condition_parts(item)
    text = ", ".join(parts) if parts else "без видимих дефектів"
    comment = str(item.get(H_DEFECTS) or "").strip()
    if comment:
        text += f"; {comment}"
    return text


def risk_text(item):
    if item.get(H_RISK) != "Є":
        return ""
    consent = item.get(H_CONSENT) or "—"
    return f"є ризик, згода клієнта: {consent.lower()}"


def totals(items, club_percent=0):
    """(сума за прайсом, сума до сплати)."""
    subtotal = sum(parse_price(i.get(H_PRICE)) for i in items)
    total = round(subtotal * (1 - club_percent / 100)) if club_percent else round(subtotal)
    return subtotal, total


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=False)


def telegram_texts(order, items, club_percent=0, limit=3800):
    """
    Квитанція для Telegram (HTML). Повертає список повідомлень: якщо речей багато,
    текст ділиться на частини, кнопку «Підтверджую» ставлять під останньою.
    """
    date = now_kyiv().strftime("%d.%m.%Y")
    head = (
        f"🧾 <b>Квитанція № {_e(order['number'])}</b>\n"
        f"{BUSINESS_NAME} · {date}\n\n"
        "Ми уважно оглянули Ваші речі на прийманні:\n\n"
    )
    blocks = []
    for n, item in enumerate(items, start=1):
        qty = str(item.get(H_QTY) or "").strip()
        qty_text = f" × {_e(qty)}" if qty and qty != "1" else ""
        block = (
            f"{n}. <b>{_e(item.get(H_ITEM))}</b>{qty_text} · бирка {_e(item.get(H_TAG))}\n"
            f"   Стан: {_e(condition_text(item))}\n"
        )
        risk = risk_text(item)
        if risk:
            block += f"   ⚠️ {_e(risk.capitalize())}\n"
        block += f"   Вартість: {fmt_money(parse_price(item.get(H_PRICE)))} ₴\n\n"
        blocks.append(block)

    subtotal, total = totals(items, club_percent)
    if club_percent:
        tail = (
            f"За прайсом: {fmt_money(subtotal)} ₴\n"
            f"💎 Знижка Pralnya Club −{club_percent}%\n"
            f"<b>До сплати: {fmt_money(total)} ₴</b>\n\n"
        )
    else:
        tail = f"<b>До сплати: {fmt_money(total)} ₴</b>\n\n"
    tail += (
        f"{TERMS}\n\n"
        "Будь ласка, перевірте опис і натисніть «✅ Підтверджую». "
        "Якщо щось не так — просто напишіть нам, ми все уточнимо."
    )

    messages, current = [], head
    for block in blocks:
        if len(current) + len(block) > limit:
            messages.append(current)
            current = ""
        current += block
    if len(current) + len(tail) > limit:
        messages.append(current)
        current = ""
    messages.append(current + tail)
    return messages


def build_pdf(order, items, club_percent=0, accepted_by=""):
    """PDF-квитанція (A4) з місцями для підписів. Повертає bytes."""
    from fpdf import FPDF
    from fpdf.fonts import FontFace

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 8, BUSINESS_NAME, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 9)
    pdf.cell(0, 5, f"{BUSINESS_ADDRESS} · {BUSINESS_PHONE}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    date = str(items[0].get(H_DATE) or "") if items else ""
    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 7, f"Квитанція приймання № {order['number']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 5, f"Дата приймання: {date or now_kyiv().strftime('%Y-%m-%d')}", new_x="LMARGIN", new_y="NEXT")
    client = " · ".join(x for x in [order.get("name"), order.get("phone"), order.get("address")] if x)
    if client:
        pdf.multi_cell(0, 5, f"Клієнт: {client}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pdf.set_font("DejaVu", "", 8.5)
    headings = ("№", "Бирка", "Річ", "Кіл.", "Стан і примітки", "Ризик / згода", "Ціна, ₴")
    with pdf.table(
        col_widths=(7, 31, 34, 13, 54, 25, 16),
        text_align=("CENTER", "LEFT", "LEFT", "CENTER", "LEFT", "LEFT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD", fill_color=(232, 240, 250)),
        line_height=4.2,
    ) as table:
        table.row(headings)
        for n, item in enumerate(items, start=1):
            name = str(item.get(H_ITEM) or "")
            extra = " / ".join(x for x in [item.get(H_MATERIAL), item.get(H_COLOR)] if x)
            if extra:
                name += f"\n{extra}"
            state = condition_text(item)
            said = str(item.get(H_SAID) or "").strip()
            if said:
                state += f"\nЗі слів клієнта: {said}"
            table.row((
                str(n), str(item.get(H_TAG) or ""), name, str(item.get(H_QTY) or "1"),
                state, risk_text(item) or "—", fmt_money(parse_price(item.get(H_PRICE))),
            ))

    subtotal, total = totals(items, club_percent)
    pdf.ln(2)
    pdf.set_font("DejaVu", "", 10)
    if club_percent:
        pdf.cell(0, 5, f"За прайсом: {fmt_money(subtotal)} ₴   ·   Знижка Pralnya Club −{club_percent}%",
                 align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 7, f"До сплати: {fmt_money(total)} ₴", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.multi_cell(0, 4.2, TERMS, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(
        0, 4.2,
        "Своїм підписом клієнт підтверджує, що опис речей і їхнього стану відповідає дійсності, "
        "а з умовами обробки речей з підвищеним ризиком ознайомлений.",
        new_x="LMARGIN", new_y="NEXT",
    )

    pdf.ln(10)
    pdf.set_font("DejaVu", "", 10)
    y = pdf.get_y()
    pdf.cell(85, 5, "Клієнт: ____________________", new_x="RIGHT", new_y="TOP")
    pdf.cell(0, 5, f"Прийняв: ____________________ {accepted_by}".rstrip(), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 7.5)
    pdf.set_y(y + 5)
    pdf.cell(85, 4, "                (підпис)", new_x="RIGHT", new_y="TOP")
    pdf.cell(0, 4, "                  (підпис)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 5, "Речі отримав, претензій до видимого стану не маю: ____________________   Дата: ___________",
             new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())
