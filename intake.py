"""
Приймання речей на стійці (адмін-меню бота) і квитанція клієнту.

Кнопки адмін-меню:
  «📥 Приймання»          — огляд речей замовлення по одній, запис у лист «🧾 Приймання»,
                            наприкінці квитанція клієнту (Telegram + PDF) і PDF адміну для друку.
  «🧾 Квитанція»           — зібрати квитанцію з того, що вже є в листі (наприклад, якщо
                            приймання заповнювали вручну в таблиці) і надіслати ще раз.
Клієнт натискає «✅ Підтверджую» — дата підтвердження пишеться в лист.

Підключення: intake.register(dp, ...) у PralnyaVdoma.py ДО загального обробника тексту
chat_with_gemini, інакше він перехоплює повідомлення.
"""

import logging
import re

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import receipt as R

INTAKE_SHEET = "🧾 Приймання"
BTN_INTAKE = "📥 Приймання"
BTN_RECEIPT = "🧾 Квитанція"
BTN_SKIP = "⏭️ Пропустити"
BTN_BACK = "🔙 Назад до адмін-меню"

SERVICES = ["Прання", "Аквачистка", "Прасування", "Ательє", "Інше"]
# поле → (підпис, варіанти; перший — «норма»)
CONDITION_FIELDS = [
    (R.H_STAINS, "Плями", ["Немає", "Є"]),
    (R.H_WEAR, "Знос", ["Немає", "Помірний", "Сильний"]),
    (R.H_HARDWARE, "Фурнітура", ["Ок", "Пошкоджена", "Відсутня частина", "Немає"]),
    (R.H_LABEL, "Ярлик", ["Є", "Немає", "Нечитабельний"]),
    (R.H_POCKETS, "Кишені", ["Порожні", "Знайдено"]),
    (R.H_RISK, "Ризик", ["Немає", "Є"]),
]


class Intake(StatesGroup):
    order = State()
    item_name = State()
    service = State()
    qty = State()
    material = State()
    color = State()
    condition = State()
    consent = State()
    defects = State()
    said = State()
    photo = State()
    price = State()
    confirm = State()


class ReceiptAgain(StatesGroup):
    order = State()


skip_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=BTN_SKIP)], [KeyboardButton(text=BTN_BACK)]], resize_keyboard=True
)
back_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BTN_BACK)]], resize_keyboard=True)


def photo_required(item):
    return (
        item.get(R.H_STAINS) == "Є"
        or item.get(R.H_RISK) == "Є"
        or item.get(R.H_HARDWARE) == "Пошкоджена"
        or item.get(R.H_WEAR) == "Сильний"
    )


def normalize_number(text):
    return re.sub(r"\s+", "", str(text or "")).upper()


def register(dp, spreadsheet, bot, admin_ids, admin_kb, *, recognize_items, club_percent_for, esc):
    """
    recognize_items(text) -> (total, [{"name","price",...}])  — розпізнавання з прайсу бота
    club_percent_for(telegram_id, phone, exclude_amount) -> int — знижка Pralnya Club
    esc(text) -> str — екранування HTML
    """

    def is_admin(user_id):
        return user_id in admin_ids

    # ------------------------------------------------------------ таблиця

    def intake_ws():
        return spreadsheet.worksheet(INTAKE_SHEET)

    def find_order(number):
        """Замовлення з «Лист1» (M) або заявка з «Atelier» (J)."""
        for title, number_header, mapping in (
            ("Лист1", "Номер замовлення",
             {"name": "Ім'я", "phone": "Телефон", "address": "Квартира", "items": "Речі",
              "tg": "telegram_id", "amount": "Сума"}),
            ("Atelier", "Номер заявки",
             {"name": "Ім'я", "phone": None, "address": None, "items": "Опис",
              "tg": "Telegram ID", "amount": "Сума"}),
        ):
            ws = spreadsheet.worksheet(title)
            rows = ws.get_all_values()
            if not rows:
                continue
            headers = rows[0]
            if number_header not in headers:
                continue
            col = headers.index(number_header)
            for r, row in enumerate(rows[1:], start=2):
                if len(row) > col and normalize_number(row[col]) == number:
                    def get(h):
                        if not h or h not in headers:
                            return ""
                        i = headers.index(h)
                        return str(row[i]).strip() if len(row) > i else ""
                    order = {k: get(h) for k, h in mapping.items()}
                    order.update({"number": number, "sheet": title, "row": r})
                    return order
        return None

    def intake_rows(number):
        """Рядки приймання цього замовлення як словники «заголовок → значення» + номер рядка."""
        ws = intake_ws()
        rows = ws.get_all_values()
        if not rows:
            return [], []
        headers = rows[0]
        col = headers.index(R.H_ORDER)
        items = []
        for r, row in enumerate(rows[1:], start=2):
            if len(row) > col and normalize_number(row[col]) == number:
                item = {h: (row[i] if i < len(row) else "") for i, h in enumerate(headers)}
                item["_row"] = r
                items.append(item)
        return headers, items

    def append_item(item):
        ws = intake_ws()
        headers = ws.row_values(1)
        ws.append_row([str(item.get(h, "")) for h in headers], value_input_option="RAW",
                      table_range="A1")

    def set_for_rows(headers, items, header, value):
        if header not in headers or not items:
            return
        ws = intake_ws()
        col = headers.index(header) + 1
        ws.batch_update([
            {"range": gspread_a1(item["_row"], col), "values": [[value]]} for item in items
        ], value_input_option="RAW")

    def write_total(order, total):
        """Погоджена сума → «Сума» замовлення; попередня зберігається в «Попередня сума» (Лист1)."""
        ws = spreadsheet.worksheet(order["sheet"])
        headers = ws.row_values(1)
        amount_col = headers.index("Сума") + 1
        if order["sheet"] == "Лист1":
            if "Попередня сума" not in headers:
                ws.update_cell(1, len(headers) + 1, "Попередня сума")
                headers.append("Попередня сума")
            prev_col = headers.index("Попередня сума") + 1
            current_prev = ws.cell(order["row"], prev_col).value
            if not str(current_prev or "").strip():
                ws.update_cell(order["row"], prev_col, order.get("amount", ""))
        ws.update_cell(order["row"], amount_col, total)

    # ------------------------------------------------------------ квитанція

    async def send_receipt(message, order, items, accepted_by=""):
        """Квитанція клієнту (текст + кнопка + PDF) і PDF адміну. Повертає True, якщо клієнт отримав."""
        exclude = R.parse_price(order.get("amount")) if order["sheet"] == "Лист1" else 0
        percent = 0
        if order["sheet"] == "Лист1":
            try:
                percent = club_percent_for(order.get("tg"), order.get("phone"), exclude)
            except Exception:
                logging.error("Квитанція: не вдалося порахувати Pralnya Club", exc_info=True)
        subtotal, total = R.totals(items, percent)
        pdf_bytes = R.build_pdf(order, items, percent, accepted_by)
        filename = f"Kvytantsiia_{order['number']}.pdf"

        try:
            write_total(order, total)
        except Exception:
            logging.error("Квитанція: не вдалося записати суму", exc_info=True)

        await message.answer_document(
            BufferedInputFile(pdf_bytes, filename=filename),
            caption=f"🖨 Квитанція {order['number']} для друку і підпису. До сплати: {R.fmt_money(total)} ₴",
        )

        tg = str(order.get("tg") or "").strip()
        if not tg.isdigit() or tg == "123456789":
            await message.answer("⚠️ У замовлення немає Telegram ID клієнта — квитанцію лише роздрукуйте.",
                                 reply_markup=admin_kb)
            return False

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Підтверджую", callback_data=f"rcpt:{order['number']}"[:64])
        ]])
        texts = R.telegram_texts(order, items, percent)
        try:
            for i, text in enumerate(texts):
                last = i == len(texts) - 1
                await bot.send_message(int(tg), text, reply_markup=kb if last else None)
            await bot.send_document(int(tg), BufferedInputFile(pdf_bytes, filename=filename))
        except Exception as e:
            logging.error(f"Квитанція: клієнт {tg} недоступний: {e}")
            await message.answer("⚠️ Не вдалося надіслати квитанцію клієнту в Telegram "
                                 "(бот заблоковано або чат не знайдено). Роздрукуйте PDF.",
                                 reply_markup=admin_kb)
            return False

        headers, rows = intake_rows(order["number"])
        set_for_rows(headers, rows, R.H_SENT, R.now_kyiv().strftime("%Y-%m-%d %H:%M"))
        await message.answer(f"📨 Квитанцію {order['number']} надіслано клієнту. "
                             "Після «✅ Підтверджую» дата з'явиться в таблиці.", reply_markup=admin_kb)
        return True

    # ------------------------------------------------------------ клавіатури

    def service_kb():
        rows = [[InlineKeyboardButton(text=s, callback_data=f"ik:svc:{i}")] for i, s in enumerate(SERVICES)]
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def qty_kb():
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=str(n), callback_data=f"ik:qty:{n}") for n in (1, 2, 3, 4, 6)
        ]])

    def condition_kb(item):
        rows = []
        for i, (header, label, options) in enumerate(CONDITION_FIELDS):
            value = item.get(header, options[0])
            mark = "" if value == options[0] else " ⚠️"
            rows.append([InlineKeyboardButton(text=f"{label}: {value}{mark}", callback_data=f"ik:cnd:{i}")])
        rows.append([InlineKeyboardButton(text="✅ Далі", callback_data="ik:cnd:ok")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def consent_kb():
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Так, згоден", callback_data="ik:cns:Так"),
            InlineKeyboardButton(text="Ні", callback_data="ik:cns:Ні"),
        ]])

    def photo_done_kb():
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Фото досить, далі", callback_data="ik:pht:ok")
        ]])

    def price_kb(suggested):
        rows = []
        if suggested:
            rows.append([InlineKeyboardButton(text=f"✅ {R.fmt_money(suggested)} ₴ (за прайсом)",
                                              callback_data=f"ik:prc:{int(suggested)}")])
        return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None

    def confirm_kb():
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Зберегти і наступна річ", callback_data="ik:end:next")],
            [InlineKeyboardButton(text="✅ Зберегти і завершити приймання", callback_data="ik:end:done")],
            [InlineKeyboardButton(text="🗑 Скасувати цю річ", callback_data="ik:end:drop")],
        ])

    def item_summary(item):
        lines = [
            f"🏷 <b>{esc(item[R.H_TAG])}</b> — {esc(item[R.H_ITEM])} × {esc(item.get(R.H_QTY, 1))}",
            f"Послуга: {esc(item.get(R.H_SERVICE, '—'))}",
        ]
        extra = " / ".join(x for x in [item.get(R.H_MATERIAL), item.get(R.H_COLOR)] if x)
        if extra:
            lines.append(f"Матеріал / колір: {esc(extra)}")
        lines.append(f"Стан: {esc(R.condition_text(item))}")
        if item.get(R.H_SAID):
            lines.append(f"Зі слів клієнта: {esc(item[R.H_SAID])}")
        risk = R.risk_text(item)
        if risk:
            lines.append(f"⚠️ {esc(risk)}")
        photos = len([p for p in str(item.get(R.H_PHOTO, "")).split() if p])
        lines.append(f"Фото: {photos}")
        lines.append(f"💰 {R.fmt_money(R.parse_price(item.get(R.H_PRICE)))} ₴")
        return "\n".join(lines)

    # ------------------------------------------------------------ кроки

    async def ask_item_name(message, state):
        data = await state.get_data()
        await state.set_state(Intake.item_name)
        await message.answer(
            f"👕 Річ № {data['next_n']} (бирка <b>{esc(data['order']['number'])}-{data['next_n']}</b>).\n"
            "Назва речі? Наприклад: «пуховик короткий», «сорочка», «комплект постелі».",
            reply_markup=back_kb,
        )

    async def ask_photo(message, state):
        data = await state.get_data()
        item = data["item"]
        await state.set_state(Intake.photo)
        if photo_required(item):
            await message.answer("📸 Надішліть фото дефекту / ризикової зони (обов'язково). "
                                 "Можна кілька фото по одному.", reply_markup=back_kb)
        else:
            await message.answer("📸 Фото не обов'язкове. Надішліть фото або натисніть «Пропустити».",
                                 reply_markup=skip_kb)

    async def ask_price(message, state):
        data = await state.get_data()
        item = data["item"]
        suggested = 0
        try:
            _total, recognized = recognize_items(item[R.H_ITEM])
            if recognized:
                suggested = recognized[0].get("price") or 0
                qty = int(item.get(R.H_QTY) or 1) if str(item.get(R.H_QTY) or "1").isdigit() else 1
                if qty > 1 and "комплект" not in item[R.H_ITEM].lower():
                    suggested *= qty
        except Exception:
            logging.error("Приймання: не вдалося підказати ціну", exc_info=True)
        await state.update_data(suggested=suggested)
        await state.set_state(Intake.price)
        hint = "Натисніть ціну за прайсом або введіть свою (число, ₴)." if suggested else "Введіть ціну, ₴ (число)."
        await message.answer(f"💰 Вартість цієї речі після огляду? {hint}", reply_markup=back_kb)
        kb = price_kb(suggested)
        if kb:
            await message.answer("За прайсом:", reply_markup=kb)

    async def show_confirm(message, state):
        data = await state.get_data()
        await state.set_state(Intake.confirm)
        await message.answer(item_summary(data["item"]), reply_markup=confirm_kb())

    # ------------------------------------------------------------ обробники

    @dp.message(F.text == BTN_INTAKE)
    async def intake_start(message: Message, state: FSMContext):
        if not is_admin(message.from_user.id):
            return
        await state.clear()
        await state.set_state(Intake.order)
        await message.answer("📥 Приймання. Введіть номер замовлення (PV-…, ORD-…) або заявки ательє (AT-…, ATL-…):",
                             reply_markup=back_kb)

    @dp.message(Intake.order, F.text)
    async def intake_order(message: Message, state: FSMContext):
        number = normalize_number(message.text)
        try:
            order = find_order(number)
            _headers, existing = intake_rows(number) if order else ([], [])
        except Exception:
            logging.error("Приймання: помилка читання таблиці", exc_info=True)
            await message.answer("❗ Не вдалося прочитати таблицю. Спробуйте ще раз.")
            return
        if not order:
            await message.answer("🔎 Такого номера немає ні в Лист1, ні в Atelier. Перевірте і введіть ще раз.")
            return
        tags = [i.get(R.H_TAG, "") for i in existing]
        nums = [int(t.rsplit("-", 1)[1]) for t in tags if re.fullmatch(r".+-\d+", t or "")]
        next_n = max(nums or [len(existing)]) + 1
        accepted_by = message.from_user.full_name or (message.from_user.username or "")
        await state.update_data(order=order, next_n=next_n, saved=len(existing), accepted_by=accepted_by)
        note = f"\nУже прийнято речей: {len(existing)} — продовжуємо нумерацію." if existing else ""
        await message.answer(
            f"🧾 <b>{esc(number)}</b> · {esc(order.get('name'))}\n"
            f"Речі зі слів клієнта: {esc(order.get('items') or '—')}{note}"
        )
        await ask_item_name(message, state)

    @dp.message(Intake.item_name, F.text)
    async def intake_item_name(message: Message, state: FSMContext):
        data = await state.get_data()
        number = data["order"]["number"]
        item = {
            R.H_DATE: R.now_kyiv().strftime("%Y-%m-%d"),
            R.H_ORDER: number,
            R.H_TAG: f"{number}-{data['next_n']}",
            R.H_ITEM: message.text.strip(),
            R.H_ACCEPTED_BY: data.get("accepted_by", ""),
            **{h: opts[0] for h, _l, opts in CONDITION_FIELDS},
        }
        await state.update_data(item=item)
        await state.set_state(Intake.service)
        await message.answer("🧺 Послуга:", reply_markup=service_kb())

    @dp.callback_query(Intake.service, F.data.startswith("ik:svc:"))
    async def intake_service(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_SERVICE] = SERVICES[int(callback.data.split(":")[2])]
        await state.update_data(item=item)
        await state.set_state(Intake.qty)
        await callback.message.edit_text(f"🧺 Послуга: <b>{item[R.H_SERVICE]}</b>")
        await callback.message.answer("🔢 Кількість одиниць (для комплектів і пар). Кнопка або число:",
                                      reply_markup=qty_kb())
        await callback.answer()

    async def set_qty(message, state, qty):
        data = await state.get_data()
        item = data["item"]
        item[R.H_QTY] = str(qty)
        await state.update_data(item=item)
        await state.set_state(Intake.material)
        await message.answer("🧵 Матеріал / наповнювач (з ярлика), наприклад «вовна 80%», «пух 90/10»:",
                             reply_markup=skip_kb)

    @dp.callback_query(Intake.qty, F.data.startswith("ik:qty:"))
    async def intake_qty_cb(callback: CallbackQuery, state: FSMContext):
        qty = int(callback.data.split(":")[2])
        await callback.message.edit_text(f"🔢 Кількість: <b>{qty}</b>")
        await set_qty(callback.message, state, qty)
        await callback.answer()

    @dp.message(Intake.qty, F.text)
    async def intake_qty_text(message: Message, state: FSMContext):
        if not message.text.strip().isdigit() or int(message.text.strip()) < 1:
            await message.answer("Введіть число, наприклад 1 або 4.")
            return
        await set_qty(message, state, int(message.text.strip()))

    @dp.message(Intake.material, F.text)
    async def intake_material(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_MATERIAL] = "" if message.text == BTN_SKIP else message.text.strip()
        await state.update_data(item=item)
        await state.set_state(Intake.color)
        await message.answer("🎨 Колір / бренд:", reply_markup=skip_kb)

    @dp.message(Intake.color, F.text)
    async def intake_color(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_COLOR] = "" if message.text == BTN_SKIP else message.text.strip()
        await state.update_data(item=item)
        await state.set_state(Intake.condition)
        await message.answer("🔍 Стан речі. Натискайте на рядок, щоб змінити значення, потім «Далі»:",
                             reply_markup=condition_kb(item))

    @dp.callback_query(Intake.condition, F.data.startswith("ik:cnd:"))
    async def intake_condition(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        key = callback.data.split(":")[2]
        if key != "ok":
            header, _label, options = CONDITION_FIELDS[int(key)]
            current = item.get(header, options[0])
            item[header] = options[(options.index(current) + 1) % len(options)] if current in options else options[0]
            await state.update_data(item=item)
            await callback.message.edit_reply_markup(reply_markup=condition_kb(item))
            await callback.answer()
            return
        await callback.message.edit_text(f"🔍 Стан: <b>{esc(R.condition_text(item))}</b>"
                                         + (" · ⚠️ ризик" if item.get(R.H_RISK) == "Є" else ""))
        await callback.answer()
        if item.get(R.H_RISK) == "Є":
            await state.set_state(Intake.consent)
            await callback.message.answer(
                "⚠️ Є ризик (колір, форма, декор, старі плями). Клієнт погоджується на обробку?",
                reply_markup=consent_kb())
        else:
            item[R.H_CONSENT] = "—"
            await state.update_data(item=item)
            await ask_defects(callback.message, state)

    async def ask_defects(message, state):
        data = await state.get_data()
        item = data["item"]
        await state.set_state(Intake.defects)
        needs = bool(R.condition_parts(item)) or item.get(R.H_RISK) == "Є"
        text = ("✍️ Опишіть дефекти і ризики: де пляма, що з фурнітурою, що знайдено в кишенях тощо."
                if needs else "✍️ Коментар про стан (дірки, шви, запах, усадка) — або «Пропустити».")
        await message.answer(text, reply_markup=skip_kb)

    @dp.callback_query(Intake.consent, F.data.startswith("ik:cns:"))
    async def intake_consent(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_CONSENT] = callback.data.split(":")[2]
        await state.update_data(item=item)
        await callback.message.edit_text(f"⚠️ Ризик · згода клієнта: <b>{item[R.H_CONSENT]}</b>")
        await callback.answer()
        if item[R.H_CONSENT] == "Ні":
            await callback.message.answer("ℹ️ Без згоди річ з ризиком краще не приймати. "
                                          "Якщо все ж приймаєте (наприклад, лише ательє) — опишіть умови в коментарі.")
        await ask_defects(callback.message, state)

    @dp.message(Intake.defects, F.text)
    async def intake_defects(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_DEFECTS] = "" if message.text == BTN_SKIP else message.text.strip()
        await state.update_data(item=item)
        await state.set_state(Intake.said)
        await message.answer("🗣 Що повідомив клієнт або кур'єр про цю річ (пляма від чого, що турбує)?",
                             reply_markup=skip_kb)

    @dp.message(Intake.said, F.text)
    async def intake_said(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        item[R.H_SAID] = "" if message.text == BTN_SKIP else message.text.strip()
        await state.update_data(item=item)
        await ask_photo(message, state)

    @dp.message(Intake.photo, F.photo)
    async def intake_photo(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        ids = [p for p in str(item.get(R.H_PHOTO, "")).split() if p]
        ids.append(message.photo[-1].file_id)
        item[R.H_PHOTO] = " ".join(ids)
        await state.update_data(item=item)
        await message.answer(f"📸 Фото {len(ids)} збережено. Ще фото або:", reply_markup=photo_done_kb())

    @dp.callback_query(Intake.photo, F.data == "ik:pht:ok")
    async def intake_photo_done(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await ask_price(callback.message, state)

    @dp.message(Intake.photo, F.text)
    async def intake_photo_text(message: Message, state: FSMContext):
        data = await state.get_data()
        item = data["item"]
        has_photo = bool(str(item.get(R.H_PHOTO, "")).strip())
        if message.text == BTN_SKIP and not photo_required(item):
            await ask_price(message, state)
        elif has_photo:
            await ask_price(message, state)
        else:
            await message.answer("📸 Для речі з плямами / ризиком / пошкодженням фото обов'язкове. Надішліть фото.")

    async def set_price(message, state, price):
        data = await state.get_data()
        item = data["item"]
        item[R.H_PRICE] = str(int(price)) if float(price).is_integer() else str(price)
        await state.update_data(item=item)
        await show_confirm(message, state)

    @dp.callback_query(Intake.price, F.data.startswith("ik:prc:"))
    async def intake_price_cb(callback: CallbackQuery, state: FSMContext):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()
        await set_price(callback.message, state, int(callback.data.split(":")[2]))

    @dp.message(Intake.price, F.text)
    async def intake_price_text(message: Message, state: FSMContext):
        value = R.parse_price(message.text)
        if value <= 0 and message.text.strip() != "0":
            await message.answer("Введіть ціну числом, наприклад 850.")
            return
        await set_price(message, state, value)

    @dp.callback_query(Intake.confirm, F.data.startswith("ik:end:"))
    async def intake_confirm(callback: CallbackQuery, state: FSMContext):
        action = callback.data.split(":")[2]
        data = await state.get_data()
        item, order = data["item"], data["order"]
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer()

        if action == "drop":
            await callback.message.answer("🗑 Річ не збережено.")
            await ask_item_name(callback.message, state)
            return

        try:
            append_item(item)
        except Exception:
            logging.error("Приймання: не вдалося записати річ", exc_info=True)
            await callback.message.answer("❗ Не вдалося записати в таблицю. Натисніть ще раз.",
                                          reply_markup=confirm_kb())
            return
        saved = data.get("saved", 0) + 1
        await state.update_data(next_n=data["next_n"] + 1, saved=saved, item=None)
        await callback.message.answer(f"💾 {esc(item[R.H_TAG])} збережено. Прикріпіть бирку до речі.")

        if action == "next":
            await ask_item_name(callback.message, state)
            return

        await state.clear()
        try:
            _headers, items = intake_rows(order["number"])
            await send_receipt(callback.message, order, items, data.get("accepted_by", ""))
        except Exception:
            logging.error("Приймання: помилка квитанції", exc_info=True)
            await callback.message.answer("❗ Речі збережено, але квитанцію сформувати не вдалося. "
                                          f"Спробуйте «{BTN_RECEIPT}».", reply_markup=admin_kb)

    # «Скасувати» в будь-якому кроці — кнопкою «Назад до адмін-меню» (обробник у PralnyaVdoma.py)

    @dp.message(F.text == BTN_RECEIPT)
    async def receipt_start(message: Message, state: FSMContext):
        if not is_admin(message.from_user.id):
            return
        await state.clear()
        await state.set_state(ReceiptAgain.order)
        await message.answer("🧾 Номер замовлення, для якого сформувати квитанцію з листа «🧾 Приймання»:",
                             reply_markup=back_kb)

    @dp.message(ReceiptAgain.order, F.text)
    async def receipt_order(message: Message, state: FSMContext):
        number = normalize_number(message.text)
        try:
            order = find_order(number)
            _headers, items = intake_rows(number) if order else ([], [])
        except Exception:
            logging.error("Квитанція: помилка читання таблиці", exc_info=True)
            await message.answer("❗ Не вдалося прочитати таблицю. Спробуйте ще раз.")
            return
        if not order:
            await message.answer("🔎 Такого номера немає ні в Лист1, ні в Atelier.")
            return
        if not items:
            await message.answer("📭 Для цього номера ще немає речей у листі «🧾 Приймання».")
            return
        await state.clear()
        accepted_by = next((i.get(R.H_ACCEPTED_BY) for i in items if i.get(R.H_ACCEPTED_BY)), "")
        await send_receipt(message, order, items, accepted_by)

    @dp.callback_query(F.data.startswith("rcpt:"))
    async def receipt_confirmed(callback: CallbackQuery):
        number = normalize_number(callback.data.split(":", 1)[1])
        try:
            order = find_order(number)
            if not order or str(order.get("tg")).strip() != str(callback.from_user.id):
                await callback.answer("Цю квитанцію може підтвердити лише власник замовлення.", show_alert=True)
                return
            headers, items = intake_rows(number)
            stamp = R.now_kyiv().strftime("%Y-%m-%d %H:%M")
            set_for_rows(headers, [i for i in items if not str(i.get(R.H_CONFIRMED, "")).strip()],
                         R.H_CONFIRMED, stamp)
        except Exception:
            logging.error("Квитанція: помилка підтвердження", exc_info=True)
            await callback.answer("Сталася помилка, спробуйте ще раз трохи пізніше.", show_alert=True)
            return
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("✅ Дякуємо! Квитанцію підтверджено. Ми повідомимо Вас, щойно речі будуть готові.")
        await callback.answer()
        for admin_id in admin_ids:
            try:
                await bot.send_message(admin_id, f"✅ Клієнт {esc(order.get('name'))} підтвердив квитанцію "
                                                 f"<b>{esc(number)}</b>.")
            except Exception:
                logging.error("Квитанція: не вдалося повідомити адміна", exc_info=True)

    @dp.callback_query(F.data.startswith("ik:"))
    async def intake_stale_button(callback: CallbackQuery):
        await callback.answer("Ця кнопка вже неактивна.")


def gspread_a1(row, col):
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"
