import asyncio
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai
import logging
import traceback
import re
import threading
import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, CommandObject
from aiogram.fsm.state import State, StatesGroup, any_state
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import gspread
from gspread.exceptions import WorksheetNotFound
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardRemove
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from collections import Counter
app = FastAPI()

origins = [
    "https://mykich.github.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok", "message": "Pralnya Vdoma API is running"}
ADMIN_IDS = [987895270]

ORDER_STATUSES = [
    "Очікує",
    "🧺 В роботі",
    "🚚 Доставляється",
    "✅ Виконано",
    "❌ Скасовано",
]

ORDER_COLUMNS = {
    "date": "Дата",
    "name": "Ім'я",
    "phone": "Телефон",
    "apartment": "Квартира",
    "items": "Речі",
    "time": "Час",
    "cancel": "Скасування",
    "subscription": "Підписка",
    "status": "Статус",
    "notified": "Повідомлено",
    "amount": "Сума",
    "photo": "Фото",
    "order_number": "Номер замовлення",
    "last_notified_status": "Останній повідомлений статус",
    "recognized": "Розпізнано",
}

PRICE_NOTE = (
    "📌 Ціни вказані орієнтовно. Остаточна вартість залежить від матеріалу, "
    "розміру, стану речі, плям, декору та складності обробки.\n"
    "Перед початком роботи ми погоджуємо вартість із клієнтом.\n\n"
)

STATUS_MESSAGES = {
    "Очікує": "⏳ Ваше замовлення очікує обробки.",
    "🧺 В роботі": "🧺 Ваше замовлення вже в роботі.",
    "🚚 Доставляється": "🚚 Ваше замовлення вже доставляється.",
    "✅ Виконано": "✅ Ваше замовлення виконано! Можете забрати його або очікуйте доставку 🧺",
    "❌ Скасовано": "❌ Ваше замовлення скасовано.",
}

# --- ошибки ---
logging.basicConfig(
    filename="bot_errors.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s",
    encoding="utf-8",
)

# --- цены ---
PRICE_LIST = {
    # 🧺 Прання
    "сорочка": 250,
    "футболка": 180,
    "майка": 170,
    "штани": 250,
    "джинси": 280,
    "шорти": 180,
    "худі": 350,
    "світшот": 350,
    "светр": 320,
    "кофта": 350,
    "блуза": 240,
    "спідниця": 240,
    # 💧 Аквачистка / 🧥 Верхній одяг
    "сукня": 450,
    "куртка": 850,
    "вітровка": 650,
    "куртка демісезонна": 850,
    "куртка джинсова": 780,
    "пуховик короткий": 1200,
    "пуховик довгий": 1450,
    "пуховик": 1450,
    "пальто текстильне": 950,
    "піджак": 750,
    "плащ": 1000,
    "тренч": 1000,
    "жилет": 750,
    # 🛏️ Домашній текстиль
    "постіль": 550,
    "постіль з прасуванням": 550,
    "рушники": 120,
    "халат": 350,
    "плед": 550,
    "покривало": 850,
    "ковдра синтетична": 850,
    "ковдра пухова": 1200,
    "подушка": 350,
    "подушка велика": 700,
    "наматрацник": 800,
    # 🧵 Ательє
    "підшити штани": 300,
    "вкоротити рукави": 350,
    "заміна блискавки": 400,
    "укоротити сукню": 450,
    "ремонт шва": 250,
    "ремонт кишень": 300,
    "дрібний ремонт": 200,
}
ITEM_ALIASES = {
    "піджак": [
        "піджак",
        "пиджак",
        "піджаки",
        "пиджаки",
        "жакет",
        "жакети",
        "блейзер",
        "блейзери",
    ],
    "сорочка": [
        "сорочка",
        "сорочки",
        "сорочку",
        "рубашка",
        "рубашки",
        "рубаха",
        "рубашку",
    ],
    "футболка": ["футболка", "футболки", "футболочку", "футболку"],
    "майка": ["майка", "майки"],
    "штани": [
        "штани",
        "штані",
        "брюки",
        "брюк",
        "брючки",
        "пара штанів",
        "пара брюк",
        "штаны",
    ],
    "джинси": ["джинси", "джинсы", "джинс"],
    "шорти": ["шорти", "шорты"],
    "худі": ["худі", "худи"],
    "блуза": ["блуза", "блузка", "блузку", "блузи"],
    "спідниця": ["спідниця", "спідницю", "спідниці", "юбка", "юбку", "юбки"],
    "світшот": ["світшот", "свитшот"],
    "светр": ["светр", "свитер", "джемпер"],
    "кофта": ["кофта", "кофту", "кофты", "кофти"],
    "сукня": ["сукня", "сукні", "платье", "сукню", "платья", "платье", "платьице"],
    "куртка": ["куртка", "курточка", "куртку"],
    "куртка": ["куртка", "куртки", "куртку", "курточка", "курточки", "курточку"],
    "куртка демісезонна": [
        "демісезонна куртка",
        "куртка демісезонна",
        "демисезонная куртка",
    ],
    "куртка джинсова": [
        "куртка джинсова",
        "джинсова куртка",
        "джинсовая куртка",
        "джинсовка",
    ],
    "пуховик короткий": ["короткий пуховик", "пуховик короткий"],
    "пуховик довгий": [
        "довгий пуховик",
        "длинный пуховик",
        "пуховик довгий",
        "пуховик длинный",
    ],
    "пуховик": [
        "пуховик",
        "пуховики",
        "пуховика",
        "пухова куртка",
        "пуховая куртка",
        "пуфер",
    ],
    "пальто текстильне": [
        "пальто",
        "текстильне пальто",
        "текстильное пальто",
        "пальто текстильное",
    ],
    "плащ": ["плащ"],
    "тренч": ["тренч"],
    "жилет": ["жилет", "жилетка"],
    "постіль": [
        "постіль",
        "постільна білизна",
        "постель",
        "постельное белье",
        "комплект постільної білизни",
        "кпб",
    ],
    "постіль з прасуванням": [
        "постіль з прасуванням",
        "постель с глажкой",
        "постільна білизна з прасуванням",
    ],
    "рушники": ["рушники", "полотенца", "рушник", "полотенце"],
    "халат": ["халат"],
    "плед": ["плед", "пледи", "пледы"],
    "покривало": ["покривало", "покрывало", "покривала", "покрывала"],
    "ковдра синтетична": [
        "ковдра синтетична",
        "синтетична ковдра",
        "синтетическое одеяло",
    ],
    "ковдра пухова": ["ковдра пухова", "пухова ковдра", "пуховое одеяло"],
    "подушка": ["подушка", "подушки", "подушка мала", "маленька подушка"],
    "подушка велика": ["подушка велика", "большая подушка", "велика подушка"],
    "наматрацник": ["наматрацник", "наматрасник"],
    "підшити штани": [
        "підшити штани",
        "подшить брюки",
        "подшить штаны",
        "укоротити штани",
    ],
    "вкоротити рукави": ["вкоротити рукави", "укоротить рукава", "вкоротити рукав"],
    "укоротити сукню": [
        "укоротити сукню",
        "укоротити спідницю",
        "укоротить платье",
        "укоротить юбку",
    ],
    "заміна блискавки": [
        "заміна блискавки",
        "заміна блискавки у штанах",
        "заміна блискавки у куртці",
        "заменить молнию",
        "замена молнии",
        "замена молнии в штанах",
        "замена молнии в куртке",
    ],
    "ремонт шва": ["ремонт шва", "зашить шов", "зашити шов"],
    "ремонт кишень": [
        "ремонт кишень",
        "ремонт карманов",
        "зашити кишеню",
        "зашить карман",
    ],
    "дрібний ремонт": ["дрібний ремонт", "мелкий ремонт", "невеликий ремонт"],
}


def normalize_phone(phone):
    """Оставляет только цифры номера телефона"""
    return "".join(filter(str.isdigit, str(phone or "")))


# --- конец ---
def is_menu_button(text):
    return text in MENU_BUTTONS


class OrderLaundry(StatesGroup):
    apartment = State()
    items = State()
    photo = State()
    time = State()
    phone = State()


class ConsultationState(StatesGroup):
    atelier = State()
    b2b = State()


class Broadcast(StatesGroup):
    waiting_text = State()


class Settings(StatesGroup):
    change_welcome = State()


class ChatWithAdmin(StatesGroup):
    waiting_for_message = State()
    waiting_for_admin_reply = State()


class StatusChange(StatesGroup):
    waiting_phone = State()
    waiting_new_status = State()


class News(StatesGroup):
    waiting_text = State()


class ViewOrderPhoto(StatesGroup):
    waiting_order_number = State()


load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# --- Налаштування Gemini (ШІ) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

system_instruction = """
Ти — професійний консультант преміальної пральні та ательє «Pralnya Vdoma», що працює в елітному житловому комплексі в Києві.

========================
РОЛЬ
========================
Ти представляєш компанію Pralnya Vdoma та спілкуєшся з клієнтами від її імені.
Твоя головна мета — допомогти клієнту отримати потрібну послугу швидко, зрозуміло та комфортно.

========================
СТИЛЬ СПІЛКУВАННЯ
========================
• Завжди звертайся до клієнта на «Ви».
• Будь ввічливим, доброзичливим і професійним.
• Відповідай українською мовою.
• Пиши коротко, зрозуміло та по суті.
• Не використовуй канцеляризмів і складних формулювань.
• Якщо відповідь можна дати двома реченнями — не пиши десять.

========================
ПОСЛУГИ
========================
Pralnya Vdoma надає:
• професійне прання;
• делікатну аквачистку;
• прасування;
• догляд за постільною білизною;
• професійне ательє (ремонт, реставрація, підгонка одягу);
• доставку речей (за наявності цієї послуги).

Основні переваги:
• професійне обладнання;
• безпечна якісна хімія;
• уважне ставлення до речей;
• власне ательє.

========================
ПРАВИЛА ВІДПОВІДЕЙ
========================
• Відповідай лише на питання, пов'язані з Pralnya Vdoma.
• Якщо інформація відсутня або невідома — чесно повідом про це.
• Ніколи не вигадуй ціни, строки або умови.
• Якщо клієнт питає про вартість — запропонуй переглянути розділ «Прайс».
• Якщо клієнт хоче оформити замовлення — запропонуй скористатися кнопкою «Здати речі».

========================
ПІДТРИМКА ПРОДАЖУ
========================
Після відповіді, якщо це доречно, запропонуй наступний крок:
• оформити замовлення;
• переглянути прайс;
• скористатися послугами ательє;
• поставити додаткові питання.

Не будь нав'язливим. Якщо клієнт просто запитує інформацію — не тисни на нього.

========================
ОБМЕЖЕННЯ
========================
Не відповідай на питання, які не стосуються діяльності Pralnya Vdoma.
Не обговорюй політику, релігію чи інші сторонні теми.
Не виконуй роль універсального чат-бота.

========================
ФОРМАТ ВІДПОВІДІ
========================
Відповідай природно, як досвідчений адміністратор преміального сервісу.
Мета кожної відповіді — допомогти клієнту, створити довіру та, якщо доречно, підвести його до оформлення замовлення.
"""
gemini_model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    system_instruction=system_instruction,
)


# ===== Gemini Service Start=====
async def generate_gemini_response(
    prompt: str,
    retries: int = 2,
    timeout: int = 20,
) -> str | None:
    """
    Безопасный вызов Gemini.

    - не блокирует Event Loop;
    - ограничивает время ожидания;
    - повторяет временные ошибки;
    - проверяет пустой ответ.
    """

    for attempt in range(retries + 1):

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(gemini_model.generate_content, prompt),
                timeout=timeout,
            )

            if response is None:
                raise ValueError("Gemini returned None")

            text = getattr(response, "text", None)

            if not text or not text.strip():
                raise ValueError("Gemini returned empty response")

            return text.strip()

        except asyncio.TimeoutError:

            logging.warning(
                "Gemini timeout (%s/%s)",
                attempt + 1,
                retries + 1,
            )

        except Exception as e:

            error_name = type(e).__name__
            error_text = str(e)

            logging.warning(
                "Gemini error (%s/%s): %s | %s",
                attempt + 1,
                retries + 1,
                error_name,
                error_text,
            )
            logging.exception("Gemini full traceback")

            # Если это ошибка конфигурации —
            # повторять бессмысленно
            if "401" in error_text or "403" in error_text:
                break

        if attempt < retries:
            await asyncio.sleep(2)

    return None


# ===== Gemini Service End =====

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "pralnya-feee1a9984bf.json", scope
)
client_gsheets = gspread.authorize(creds)

spreadsheet = client_gsheets.open("Pralnya")

sheet = spreadsheet.sheet1
atelier_sheet = spreadsheet.worksheet("Atelier")
# Переключаем подключение на новый общий лист
b2b_sheet = spreadsheet.worksheet("B2B_General")

sheet_clients = spreadsheet.worksheet("Clients")
sheet_orders = spreadsheet.worksheet("Лист1")


session = AiohttpSession()
bot = Bot(
    token=TELEGRAM_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="Здати речі"),
            KeyboardButton(text="Графік та доставка"),
        ],
        [KeyboardButton(text="Прайс"), KeyboardButton(text="Підписка")],
        [KeyboardButton(text="Види чистки"), KeyboardButton(text="Зв’язатися з нами")],
        [
            KeyboardButton(text="🧵 Заявка в ательє"),
            KeyboardButton(text="🏢 B2B / прання по кг"),
        ],
        [KeyboardButton(text="👤 Особистий кабінет")],
        [
            KeyboardButton(text="🧾 Мої замовлення"),
            KeyboardButton(text="❌ Скасувати замовлення"),
        ],
    ],
    resize_keyboard=True,
)


account_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧾 Мої замовлення")],
        [
            KeyboardButton(text="📦 Активне замовлення"),
            KeyboardButton(text="💳 Підписка"),
        ],
        [KeyboardButton(text="🏠 Головне меню")],
    ],
    resize_keyboard=True,
)

schedule_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🕐 Графік роботи"),
            KeyboardButton(text="🚚 Умови доставки"),
        ],
        [KeyboardButton(text="🔙 Назад до меню")],
    ],
    resize_keyboard=True,
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📦 Заявки"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🧵 Заявки ательє"), KeyboardButton(text="🏢 B2B-заявки")],
        [
            KeyboardButton(text="📸 Фото замовлення"),
            KeyboardButton(text="✏️ Змінити статус замовлення"),
        ],
        [KeyboardButton(text="📣 Розсилка"), KeyboardButton(text="📢 Новини")],
        [KeyboardButton(text="⚙️ Налаштування")],
        [KeyboardButton(text="🔙 Назад")],
    ],
    resize_keyboard=True,
)

statistics_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Аналітика")],
        [KeyboardButton(text="🔙 Назад до адмін-меню")],
    ],
    resize_keyboard=True,
)

broadcast_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Назад до адмін-меню")]], resize_keyboard=True
)

status_change_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Назад до адмін-меню")]], resize_keyboard=True
)

photo_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📸 Додати фото")],
        [KeyboardButton(text="⏭️ Пропустити")],
    ],
    resize_keyboard=True,
)

price_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🧺 Прання"),
            KeyboardButton(text="🧥 Верхній одяг"),
        ],
        [
            KeyboardButton(text="🛏️ Домашній текстиль"),
            KeyboardButton(text="🧵 Ательє"),
        ],
        [KeyboardButton(text="🏢 B2B / по кг"), KeyboardButton(text="⚠️ Після огляду")],
        [KeyboardButton(text="🔙 Назад до меню")],
    ],
    resize_keyboard=True,
)
order_process_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏠 Головне меню")],
    ],
    resize_keyboard=True,
)

MENU_BUTTONS = {
    "Здати речі",
    "Графік та доставка",
    "Прайс",
    "Підписка",
    "💳 Підписка",
    "Види чистки",
    "Зв’язатися з нами",
    "👤 Особистий кабінет",
    "🧾 Мої замовлення",
    "📦 Активне замовлення",
    "❌ Скасувати замовлення",
    "🧵 Заявка в ательє",
    "🏢 B2B / прання по кг",
    "🏠 Головне меню",
    "🔔 Оформити підписку",
    "🔙 Повернутись до меню",
    "🔙 Назад до меню",
    "📦 Заявки",
    "📊 Статистика",
    "🧵 Заявки ательє",
    "🏢 B2B-заявки",
    "📸 Фото замовлення",
    "✏️ Змінити статус замовлення",
    "📣 Розсилка",
    "📢 Новини",
    "⚙️ Налаштування",
    "🔙 Назад",
    "🔙 Назад до адмін-меню",
}

# --- новое старт ---
status_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Очікує"), KeyboardButton(text="🧺 В роботі")],
        [KeyboardButton(text="🚚 Доставляється"), KeyboardButton(text="✅ Виконано")],
        [KeyboardButton(text="❌ Скасовано")],
        [KeyboardButton(text="🔙 Назад до адмін-меню")],
    ],
    resize_keyboard=True,
)


# --- новое старт ---
@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас немає доступу.")
        return
    await state.update_data(prev_menu="user")
    await message.answer("👑 Адмін-панель. Оберіть дію:", reply_markup=admin_kb)


@dp.message(F.text == "📦 Заявки")
async def show_orders(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        records = sheet.get_all_values()

        if not records or len(records) < 2:
            await message.answer("📭 Замовлень поки немає.")
            return

        headers = records[0]
        rows = records[1:]

        date_index = headers.index("Дата")
        name_index = headers.index("Ім'я")
        phone_index = headers.index("Телефон")
        apartment_index = headers.index("Квартира")
        items_index = headers.index("Речі")
        time_index = headers.index("Час")
        cancel_index = headers.index("Скасування")
        status_index = headers.index("Статус")
        amount_index = headers.index("Сума")
        order_number_index = headers.index("Номер замовлення")
        recognized_index = headers.index("Розпізнано")

        def get_value(row, index, default="—"):
            if len(row) > index and str(row[index]).strip():
                return str(row[index]).strip()
            return default

        active_orders = []

        for row in reversed(rows):
            cancel = get_value(row, cancel_index, "")
            status = get_value(row, status_index, "Очікує")

            if cancel:
                continue

            if "виконано" in status.lower():
                continue

            active_orders.append(row)

        active_orders = active_orders[:7]

        if not active_orders:
            await message.answer("📭 Активних замовлень немає.")
            return

        text = "📦 <b>Активні замовлення:</b>\n\n"

        for i, row in enumerate(active_orders, start=1):
            order_number = get_value(row, order_number_index)
            date = get_value(row, date_index)
            name = get_value(row, name_index)
            phone = get_value(row, phone_index)
            apartment = get_value(row, apartment_index)
            items = get_value(row, items_index)
            time_text = get_value(row, time_index)
            status = get_value(row, status_index, "Очікує")
            amount = get_value(row, amount_index, "0")
            recognized = get_value(
                row, recognized_index, "Буде уточнено адміністратором"
            )

            text += (
                f"<b>{i}. 🧾 {order_number}</b>\n"
                f"📅 {date}\n"
                f"👤 {name}\n"
                f"📞 {phone}\n"
                f"🏢 Квартира: <b>{apartment}</b>\n"
                f"👚 Речі: {items}\n"
                f"🔎 Розпізнано: {recognized}\n"
                f"🕓 Час: {time_text}\n"
                f"📦 Статус: <b>{status}</b>\n"
                f"💰 Сума: <b>{amount} грн</b>\n\n"
            )

        await message.answer(text)

    except Exception as e:
        print(f"❌ Помилка при отриманні замовлень: {e}")
        logging.error("Помилка при отриманні замовлень", exc_info=True)
        await message.answer("❗ Сталася помилка при завантаженні заявок.")


@dp.message(F.text == "📸 Фото замовлення")
async def ask_order_photo_number(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    await message.answer(
        "🆔 Введіть номер замовлення, фото якого потрібно переглянути:",
        reply_markup=status_change_menu_kb,
    )

    await state.set_state(ViewOrderPhoto.waiting_order_number)


@dp.message(ViewOrderPhoto.waiting_order_number)
async def show_order_photo(message: Message, state: FSMContext):
    if message.text == "🔙 Назад до адмін-меню":
        await state.clear()
        await message.answer("🔧 Повернення до адмін-меню:", reply_markup=admin_kb)
        return

    order_number = message.text.strip()

    try:
        records = sheet.get_all_values()

        if not records or len(records) < 2:
            await message.answer("📭 Замовлень поки немає.", reply_markup=admin_kb)
            await state.clear()
            return

        headers = records[0]
        rows = records[1:]

        order_number_index = headers.index("Номер замовлення")
        photo_index = headers.index("Фото")
        name_index = headers.index("Ім'я")
        apartment_index = headers.index("Квартира")
        items_index = headers.index("Речі")
        status_index = headers.index("Статус")

        found_order = None

        for row in rows:
            if (
                len(row) > order_number_index
                and row[order_number_index].strip() == order_number
            ):
                found_order = row
                break

        if not found_order:
            await message.answer(
                "❗ Замовлення з таким номером не знайдено.", reply_markup=admin_kb
            )
            await state.clear()
            return

        photo_file_id = (
            found_order[photo_index].strip() if len(found_order) > photo_index else ""
        )

        name = found_order[name_index] if len(found_order) > name_index else "—"
        apartment = (
            found_order[apartment_index] if len(found_order) > apartment_index else "—"
        )
        items = found_order[items_index] if len(found_order) > items_index else "—"
        status = found_order[status_index] if len(found_order) > status_index else "—"

        caption = (
            f"📸 <b>Фото замовлення</b>\n\n"
            f"🆔 Номер: <b>{order_number}</b>\n"
            f"👤 Клієнт: {name}\n"
            f"🏢 Квартира: {apartment}\n"
            f"👚 Речі: {items}\n"
            f"📦 Статус: {status}"
        )

        if photo_file_id:
            await bot.send_photo(
                chat_id=message.chat.id, photo=photo_file_id, caption=caption
            )
        else:
            await message.answer(
                f"{caption}\n\n⚠️ Фото для цього замовлення не було додано.",
                reply_markup=admin_kb,
            )

    except Exception as e:
        print(f"❌ Помилка при перегляді фото замовлення: {e}")
        logging.error("Помилка при перегляді фото замовлення", exc_info=True)
        await message.answer(
            "❗ Помилка при завантаженні фото замовлення.", reply_markup=admin_kb
        )

    await state.clear()


@dp.message(F.text == "🧵 Заявки ательє")
async def admin_atelier_requests(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас немає доступу до цього розділу.")
        return

    try:
        rows = atelier_sheet.get_all_values()[1:]

        if not rows:
            await message.answer("🧵 Заявок ательє поки немає.", reply_markup=admin_kb)
            return

        active_rows = []

        for row in rows:
            status = row[6].strip() if len(row) > 6 and row[6] else "Нова"

            if status not in ["Закрита", "Відмова"]:
                active_rows.append(row)

        if not active_rows:
            await message.answer(
                "🧵 Активних заявок ательє немає.",
                reply_markup=admin_kb,
            )
            return

        last_requests = list(reversed(active_rows))[:5]

        text = "🧵 <b>Останні активні заявки ательє</b>\n\n"

        for i, row in enumerate(last_requests, start=1):
            date = row[0] if len(row) > 0 and row[0] else "—"
            request_number = row[9] if len(row) > 9 and row[9] else "—"
            name = row[1] if len(row) > 1 and row[1] else "—"
            telegram_id = row[2] if len(row) > 2 and row[2] else "—"
            username = row[3] if len(row) > 3 and row[3] else "—"
            description = row[4] if len(row) > 4 and row[4] else "—"
            photo = row[5] if len(row) > 5 and row[5] else "Немає"
            status = row[6] if len(row) > 6 and row[6] else "Нова"
            admin_comment = row[7] if len(row) > 7 and row[7] else "—"

            text += (
                f"{i}. <b>{date}</b>\n"
                f"🆔 Заявка: <b>{request_number}</b>\n"
                f"👤 {name}\n"
                f"🆔 <code>{telegram_id}</code>\n"
                f"🔗 {username}\n"
                f"💬 {description}\n"
                f"📷 Фото: {photo}\n"
                f"📌 Статус: <b>{status}</b>\n"
                f"📝 Коментар: {admin_comment}\n\n"
            )

        await message.answer(text, reply_markup=admin_kb)

    except Exception as e:
        print(f"❌ Помилка завантаження заявок ательє: {e}")
        logging.error("Помилка завантаження заявок ательє", exc_info=True)
        await message.answer(
            "❗ Помилка при завантаженні заявок ательє.",
            reply_markup=admin_kb,
        )


@dp.message(F.text == "🏢 B2B-заявки")
async def admin_b2b_requests(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас немає доступу до цього розділу.")
        return

    try:
        rows = b2b_sheet.get_all_values()[1:]

        if not rows:
            await message.answer("🏢 B2B-заявок поки немає.", reply_markup=admin_kb)
            return

        active_rows = []

        for row in rows:
            status = row[6].strip() if len(row) > 6 and row[6] else "Нова"

            if status not in ["Закрита", "Відмова"]:
                active_rows.append(row)

        if not active_rows:
            await message.answer(
                "🏢 Активних B2B-заявок немає.",
                reply_markup=admin_kb,
            )
            return

        last_requests = list(reversed(active_rows))[:5]

        text = "🏢 <b>Останні активні B2B-заявки</b>\n\n"

        for i, row in enumerate(last_requests, start=1):
            date = row[0] if len(row) > 0 and row[0] else "—"
            request_number = row[9] if len(row) > 9 and row[9] else "—"
            name = row[1] if len(row) > 1 and row[1] else "—"
            telegram_id = row[2] if len(row) > 2 and row[2] else "—"
            username = row[3] if len(row) > 3 and row[3] else "—"
            description = row[4] if len(row) > 4 and row[4] else "—"
            photo = row[5] if len(row) > 5 and row[5] else "Немає"
            status = row[6] if len(row) > 6 and row[6] else "Нова"
            admin_comment = row[7] if len(row) > 7 and row[7] else "—"

            text += (
                f"{i}. <b>{date}</b>\n"
                f"🆔 Заявка: <b>{request_number}</b>\n"
                f"👤 {name}\n"
                f"🆔 <code>{telegram_id}</code>\n"
                f"🔗 {username}\n"
                f"💬 {description}\n"
                f"📷 Фото: {photo}\n"
                f"📌 Статус: <b>{status}</b>\n"
                f"📝 Коментар: {admin_comment}\n\n"
            )

        await message.answer(text, reply_markup=admin_kb)

    except Exception as e:
        print(f"❌ Помилка завантаження B2B-заявок: {e}")
        logging.error("Помилка завантаження B2B-заявок", exc_info=True)
        await message.answer(
            "❗ Помилка при завантаженні B2B-заявок.",
            reply_markup=admin_kb,
        )


@dp.message(F.text == "📊 Статистика")
async def show_statistics_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає доступу.")
        return

    try:
        records = sheet.get_all_values()

        if not records or len(records) < 2:
            await message.answer("📭 Замовлень поки немає.")
            return

        headers = records[0]
        rows = records[1:]

        date_index = headers.index("Дата")
        status_index = headers.index("Статус")
        cancel_index = headers.index("Скасування")
        amount_index = headers.index("Сума")

        today = datetime.now().date()
        seven_days_ago = today - timedelta(days=7)

        today_total = 0
        today_sum = 0

        week_total = 0
        week_sum = 0

        today_statuses = {
            "Очікує": 0,
            "🧺 В роботі": 0,
            "🚚 Доставляється": 0,
            "✅ Виконано": 0,
            "❌ Скасовано": 0,
        }

        week_statuses = {
            "Очікує": 0,
            "🧺 В роботі": 0,
            "🚚 Доставляється": 0,
            "✅ Виконано": 0,
            "❌ Скасовано": 0,
        }

        def parse_amount(value):
            try:
                value = str(value).replace(" ", "").replace(",", ".")
                return float(value) if value else 0
            except:
                return 0

        for row in rows:
            if len(row) <= max(date_index, status_index, cancel_index, amount_index):
                continue

            date_str = row[date_index].strip()
            status = row[status_index].strip() or "Очікує"
            canceled = row[cancel_index].strip()
            amount = parse_amount(row[amount_index])

            if not date_str:
                continue

            try:
                order_date = datetime.strptime(date_str, "%d.%m.%Y").date()
            except ValueError:
                continue

            if canceled and "Скасовано" not in status:
                status = "❌ Скасовано"

            if order_date == today:
                today_total += 1
                today_sum += amount

                if status in today_statuses:
                    today_statuses[status] += 1

            if order_date >= seven_days_ago:
                week_total += 1
                week_sum += amount

                if status in week_statuses:
                    week_statuses[status] += 1

        today_avg = int(today_sum / today_total) if today_total else 0
        week_avg = int(week_sum / week_total) if week_total else 0

        text = (
            f"📊 <b>Статистика замовлень</b>\n\n"
            f"📅 <b>Сьогодні</b>\n"
            f"📦 Всього замовлень: <b>{today_total}</b>\n"
            f"💰 Сума: <b>{int(today_sum)} грн</b>\n"
            f"🧾 Середній чек: <b>{today_avg} грн</b>\n\n"
            f"⏳ Очікує: {today_statuses['Очікує']}\n"
            f"🧺 В роботі: {today_statuses['🧺 В роботі']}\n"
            f"🚚 Доставляється: {today_statuses['🚚 Доставляється']}\n"
            f"✅ Виконано: {today_statuses['✅ Виконано']}\n"
            f"❌ Скасовано: {today_statuses['❌ Скасовано']}\n\n"
            f"📆 <b>За останні 7 днів</b>\n"
            f"📦 Всього замовлень: <b>{week_total}</b>\n"
            f"💰 Сума: <b>{int(week_sum)} грн</b>\n"
            f"🧾 Середній чек: <b>{week_avg} грн</b>\n\n"
            f"⏳ Очікує: {week_statuses['Очікує']}\n"
            f"🧺 В роботі: {week_statuses['🧺 В роботі']}\n"
            f"🚚 Доставляється: {week_statuses['🚚 Доставляється']}\n"
            f"✅ Виконано: {week_statuses['✅ Виконано']}\n"
            f"❌ Скасовано: {week_statuses['❌ Скасовано']}"
        )

        await message.answer(text, reply_markup=statistics_menu)

    except Exception as e:
        print(f"❌ Помилка під час обрахунку статистики: {e}")
        logging.error("Помилка під час обрахунку статистики", exc_info=True)
        await message.answer("❗ Помилка при завантаженні статистики.")


@dp.message(F.text == "📈 Аналітика")
async def show_analytics(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ У вас немає доступу.")
        return

    try:
        records = sheet.get_all_values()

        if not records or len(records) < 2:
            await message.answer("📭 Даних для аналітики поки немає.")
            return

        headers = records[0]
        rows = records[1:]

        name_index = headers.index("Ім'я")
        apartment_index = headers.index("Квартира")
        items_index = headers.index("Речі")
        status_index = headers.index("Статус")
        cancel_index = headers.index("Скасування")
        amount_index = headers.index("Сума")
        subscription_index = headers.index("Підписка")
        recognized_index = headers.index("Розпізнано")
        date_index = headers.index("Дата")
        order_number_index = headers.index("Номер замовлення")

        total_orders = 0
        total_sum = 0
        zero_amount_orders = 0
        paid_orders = 0
        active_subscriptions = 0
        unrecognized_orders = 0
        unrecognized_examples = []

        user_counter = Counter()
        item_counter = Counter()

        def parse_amount(value):
            try:
                value = str(value).replace(" ", "").replace(",", ".")
                return float(value) if value else 0
            except:
                return 0

        for row in rows:
            if len(row) <= max(
                name_index,
                apartment_index,
                items_index,
                status_index,
                cancel_index,
                amount_index,
                subscription_index,
                recognized_index,
                date_index,
                order_number_index,
            ):
                continue

            name = row[name_index].strip()
            apartment = row[apartment_index].strip()
            items = row[items_index].strip()
            status = row[status_index].strip()
            canceled = row[cancel_index].strip()
            amount = parse_amount(row[amount_index])
            subscription = row[subscription_index].strip()
            recognized = row[recognized_index].strip()
            date = row[date_index].strip()
            order_number = row[order_number_index].strip()

            if canceled or "Скасовано" in status:
                continue

            total_orders += 1
            total_sum += amount

            if amount > 0:
                paid_orders += 1

            if amount == 0:
                zero_amount_orders += 1

            if amount == 0 and (not recognized or recognized == "Не розпізнано"):
                unrecognized_orders += 1

                if len(unrecognized_examples) < 5:
                    unrecognized_examples.append(
                        {
                            "order_number": order_number or "—",
                            "date": date or "—",
                            "items": items or "—",
                        }
                    )

            if subscription == "Так":
                active_subscriptions += 1

            if name and apartment:
                user_counter[f"{name} (кв. {apartment})"] += 1

            if recognized and recognized != "Не розпізнано":
                recognized_parts = recognized.split(";")

                for part in recognized_parts:
                    part = part.strip()

                    if not part:
                        continue

                    # Беремо тільки правильно розпізнані рядки формату:
                    # сорочка × 2 — 500 грн
                    if "×" not in part:
                        continue

                    item_name = part.split("×")[0].strip()
                    quantity = 1

                    try:
                        quantity_part = part.split("×")[1].split("—")[0].strip()
                        quantity = int(quantity_part)
                    except Exception:
                        quantity = 1

                    if item_name:
                        item_counter[item_name] += quantity
        avg_check = int(total_sum / total_orders) if total_orders else 0
        avg_check_paid = int(total_sum / paid_orders) if paid_orders else 0

        top_users = user_counter.most_common(5)
        top_items = item_counter.most_common(5)

        text = (
            f"📈 <b>Аналітика бізнесу</b>\n\n"
            f"📦 Всього активних/виконаних замовлень: <b>{total_orders}</b>\n"
            f"💰 Загальна сума: <b>{int(total_sum)} грн</b>\n"
            f"🧾 Середній чек: <b>{avg_check} грн</b>\n"
            f"💳 Замовлень із сумою: <b>{paid_orders}</b>\n"
            f"🧾 Середній чек без нульових: <b>{avg_check_paid} грн</b>\n"
            f"👑 Замовлень з підпискою: <b>{active_subscriptions}</b>\n"
            f"⚠️ Замовлень з сумою 0: <b>{zero_amount_orders}</b>\n"
            f"🔎 Не розпізнано: <b>{unrecognized_orders}</b>\n\n"
            f"🏆 <b>Топ 5 клієнтів:</b>\n"
        )

        if top_users:
            for i, (user, count) in enumerate(top_users, start=1):
                text += f"{i}. {user} — {count} замовлень\n"
        else:
            text += "Поки немає даних.\n"

        text += "\n👚 <b>Топ 5 речей:</b>\n"

        if top_items:
            for i, (item, count) in enumerate(top_items, start=1):
                text += f"{i}. {item} — {count} разів\n"
        else:
            text += "Поки немає даних.\n"

        text += "\n⚠️ <b>Останні нерозпізнані замовлення:</b>\n"

        if unrecognized_examples:
            for i, order in enumerate(unrecognized_examples, start=1):
                text += (
                    f"{i}. {order['order_number']} | {order['date']}\n"
                    f"Речі: {order['items']}\n"
                )
        else:
            text += "Немає нерозпізнаних замовлень.\n"

        await message.answer(text)

    except Exception as e:
        print(f"❌ Помилка аналітики: {e}")
        logging.error("Помилка аналітики", exc_info=True)
        await message.answer("❗ Помилка при завантаженні аналітики.")


@dp.message(F.text == "🔙 Назад до адмін-меню")
async def back_to_admin_menu(message: Message, state: FSMContext):
    await state.clear()  # <<< ОБЯЗАТЕЛЬНО
    await message.answer("🔧 Повернення до адмін-меню:", reply_markup=admin_kb)


@dp.message(F.text == "📣 Розсилка")
async def broadcast_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "📝 Введіть текст новини для розсилки або натисніть <b>«🔙 Назад до адмін-меню»</b>:",
        reply_markup=broadcast_menu_kb,
    )
    await state.set_state(Broadcast.waiting_text)


@dp.message(Broadcast.waiting_text)
async def process_broadcast(message: Message, state: FSMContext):
    text = message.text.strip()

    # 🔙 Назад
    if text == "🔙 Назад до адмін-меню":
        await state.clear()
        await message.answer(
            "↩️ Ви повернулись до адмін-панелі.", reply_markup=admin_kb
        )
        return

    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()
        count = 0

        for client in clients:
            telegram_id = client.get("telegram_id")
            if telegram_id:
                try:
                    await bot.send_message(chat_id=int(telegram_id), text=text)
                    count += 1
                except Exception as e:
                    print(f"❌ Не вдалося надіслати повідомлення {telegram_id}: {e}")
                    logging.error("Не вдалося надіслати повідомлення", exc_info=True)

        await message.answer(
            f"✅ Повідомлення надіслано {count} клієнтам.", reply_markup=admin_kb
        )
    except Exception as e:
        print(f"❌ Помилка розсилки: {e}")
        await message.answer("❗ Помилка при розсилці.", reply_markup=admin_kb)
        logging.error("Помилка розсилки", exc_info=True)

    await state.clear()


# Клавиатура для возврата в админ-меню
status_change_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Назад до адмін-меню")]], resize_keyboard=True
)


@dp.message(F.text == "✏️ Змінити статус замовлення")
async def start_status_change(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "📞 Введіть номер телефону клієнта (тільки цифри):",
        reply_markup=status_change_menu_kb,
    )
    await state.set_state(StatusChange.waiting_phone)


@dp.message(StatusChange.waiting_phone)
async def ask_new_status(message: Message, state: FSMContext):
    if message.text == "🔙 Назад до адмін-меню":
        await state.clear()
        await message.answer("🔧 Повернення до адмін-меню:", reply_markup=admin_kb)
        return

    phone = normalize_phone(message.text)
    await state.update_data(phone=phone)

    try:
        records = sheet.get_all_values()
        headers = records[0]
        rows = list(reversed(records[1:]))

        phone_index = headers.index("Телефон")
        status_index = headers.index("Статус")

        for i, row in enumerate(rows):
            if len(row) > phone_index and normalize_phone(row[phone_index]) == phone:
                current_status = row[status_index] if len(row) > status_index else "—"
                await state.update_data(row_number=len(records) - i)
                await message.answer(
                    f"🔄 Поточний статус: <b>{current_status}</b>\n\n"
                    "👇 Оберіть новий статус:",
                    reply_markup=status_kb,
                )
                await state.set_state(StatusChange.waiting_new_status)
                return

        await message.answer("❗ Замовлення з таким номером телефону не знайдено.")
        await state.clear()

    except Exception as e:
        print(f"❌ Помилка при пошуку замовлення: {e}")
        await message.answer("❗ Помилка при пошуку замовлення.")
        logging.error("Помилка при пошуку замовлення", exc_info=True)
        await state.clear()


@dp.message(StatusChange.waiting_new_status)
async def save_new_status(message: Message, state: FSMContext):

    if message.text == "🔙 Назад до адмін-меню":
        await state.clear()
        await message.answer("🔧 Повернення до адмін-меню:", reply_markup=admin_kb)
        return

    new_status = message.text.strip()

    data = await state.get_data()
    row_number = data.get("row_number")
    phone = data.get("phone")

    try:
        headers = sheet.row_values(1)

        status_col = headers.index("Статус") + 1
        notified_col = headers.index("Повідомлено") + 1

        # обновляем статус
        sheet.update_cell(row_number, status_col, new_status)

        # если НЕ выполнено — сбрасываем уведомление
        if new_status != "✅ Виконано":
            sheet.update_cell(row_number, notified_col, "")

        # ищем клиента
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()

        telegram_id = None

        for client in clients:
            client_phone = normalize_phone(client.get("phone", ""))

            if client_phone[-10:] == phone[-10:]:
                telegram_id = client.get("telegram_id")
                break

        # отправляем уведомление клиенту
        if telegram_id:

            status_messages = {
                "🟡 Очікує": "🟡 Ваше замовлення очікує обробки.",
                "🚚 Забрано": "🚚 Речі вже забрано.",
                "🧺 У пранні": "🧺 Ваші речі вже у пранні.",
                "🧼 Чиститься": "🧼 Речі проходять чистку.",
                "🧵 В ательє": "🧵 Ваші речі зараз в ательє.",
                "🚗 Доставляється": "🚗 Замовлення вже доставляється.",
                "✅ Виконано": "✅ Ваше замовлення виконано!",
            }

            text = status_messages.get(
                new_status, f"📦 Статус вашого замовлення оновлено:\n{new_status}"
            )

            await bot.send_message(
                int(telegram_id), f"📦 <b>Оновлення статусу</b>\n\n{text}"
            )

        await message.answer("✅ Статус успішно оновлено.", reply_markup=admin_kb)

    except Exception as e:
        print(f"❌ Помилка оновлення статусу: {e}")
        await message.answer("❗ Не вдалося оновити статус.")
        logging.error("Помилка оновлення статусу", exc_info=True)

    await state.clear()


@dp.message(F.text == "⚙️ Налаштування")
async def settings_menu(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✏️ Змінити вітальний текст")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )
    await state.update_data(prev_menu="admin_menu")
    await message.answer("⚙️ Оберіть налаштування:", reply_markup=kb)


@dp.message(F.text == "✏️ Змінити вітальний текст")
async def ask_new_welcome_text(message: Message, state: FSMContext):
    await message.answer(
        "✍️ Надішліть новий вітальний текст або натисніть 'Назад' для скасування:"
    )
    await state.set_state(Settings.change_welcome)


@dp.message(Settings.change_welcome)
async def save_new_welcome_text(message: Message, state: FSMContext):
    text = message.text

    # Обработка возврата
    if text == "🔙 Назад":
        await message.answer(
            "↩️ Ви повернулись до налаштувань.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[
                    [KeyboardButton(text="✏️ Змінити вітальний текст")],
                    [KeyboardButton(text="🔙 Назад")],
                ],
                resize_keyboard=True,
            ),
        )
        await state.clear()
        return

    try:
        config_sheet = client_gsheets.open("Pralnya").worksheet("Config")
        config_sheet.update("B1", text)
        await message.answer("✅ Вітальний текст оновлено!", reply_markup=admin_kb)
    except Exception as e:
        await message.answer(f"❌ Помилка: {e}", reply_markup=admin_kb)
        logging.error("Помилка", exc_info=True)

    await state.clear()


@dp.message(F.text == "🔙 Назад")
async def go_back(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    user_data = await state.get_data()
    prev_menu = user_data.get("prev_menu")

    if prev_menu == "admin_menu":
        await state.update_data(
            prev_menu="user"
        )  # на случай если пойдём обратно в главное
        await message.answer(
            "↩️ Ви повернулись до адмін-панелі.", reply_markup=admin_kb
        )
    else:
        await state.clear()
        await message.answer(
            "↩️ Ви повернулись до головного меню.", reply_markup=main_menu
        )


# ✅ Команда /admin end


def get_client_by_telegram_id(telegram_id):
    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()

        found_client = None

        for row in clients:
            saved_id = str(row.get("telegram_id", "")).strip()
            current_id = str(telegram_id).strip()

            if saved_id == current_id:
                # Если нашли клиента с телефоном — сразу возвращаем его
                if normalize_phone(row.get("phone", "")):
                    return row

                # Если телефон пустой — запоминаем, но продолжаем искать ниже
                found_client = row

        return found_client

    except WorksheetNotFound:
        return None
    except Exception as e:
        print(f"❌ Помилка пошуку клієнта: {e}")
        logging.error("Помилка пошуку клієнта", exc_info=True)
        return None


def save_new_client(telegram_id, name, phone, apartment):
    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
    except WorksheetNotFound:
        client_sheet = client_gsheets.open("Pralnya").add_worksheet(
            title="Clients", rows="1000", cols="6"
        )
        client_sheet.append_row(
            [
                "telegram_id",
                "name",
                "phone",
                "apartment",
                "subscription",
                "subscription_expires",
            ]
        )

    try:
        rows = client_sheet.get_all_values()

        if not rows:
            client_sheet.append_row(
                [
                    "telegram_id",
                    "name",
                    "phone",
                    "apartment",
                    "subscription",
                    "subscription_expires",
                ]
            )
            rows = client_sheet.get_all_values()

        headers = rows[0]
        data_rows = rows[1:]

        telegram_id_col = headers.index("telegram_id") + 1
        name_col = headers.index("name") + 1
        phone_col = headers.index("phone") + 1
        apartment_col = headers.index("apartment") + 1

        current_id = str(telegram_id).strip()
        normalized_phone = normalize_phone(phone)

        for i, row in enumerate(data_rows, start=2):
            saved_id = ""

            if len(row) >= telegram_id_col:
                saved_id = str(row[telegram_id_col - 1]).strip()

            if saved_id == current_id:
                client_sheet.update_cell(i, name_col, name)
                client_sheet.update_cell(i, phone_col, normalized_phone)
                client_sheet.update_cell(i, apartment_col, apartment)
                return

        client_sheet.append_row(
            [telegram_id, name, normalized_phone, apartment, "Ні", ""]
        )

    except Exception as e:
        print(f"❌ Помилка збереження клієнта: {e}")
        logging.error("Помилка збереження клієнта", exc_info=True)


def get_config_value(key):
    try:
        config_sheet = client_gsheets.open("Pralnya").worksheet("Config")
        rows = config_sheet.get_all_values()
        for row in rows:
            if len(row) >= 2 and row[0] == key:
                return row[1]
        return None  # если ключ не найден
    except WorksheetNotFound:
        return None


@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    start_arg = command.args
    print(f"✅ /start спрацював. start_arg = {start_arg}")

    # Якщо користувач прийшов із сайту по посиланню ?start=order
    if start_arg == "order":
        await state.clear()

        client = get_client_by_telegram_id(message.from_user.id)

        if client:
            apartment = client.get("apartment", "")
            phone = normalize_phone(client.get("phone", ""))

            if apartment:
                await state.update_data(apartment=apartment)

            if phone:
                await state.update_data(phone=phone)

            # Якщо клієнт є в базі і квартира вже збережена —
            # одразу переходимо до речей
            if apartment:
                await message.answer(
                    "🧺 <b>Оформлення замовлення</b>\n\n"
                    "Я вже знайшов ваші дані в базі, тому можемо одразу перейти до речей.\n\n"
                    "👚 Напишіть, будь ласка, що потрібно передати в роботу.\n"
                    "Наприклад: <b>2 сорочки, джинси та куртка</b>.\n\n"
                    "Якщо ви передумали оформлювати замовлення, натисніть 🏠 Головне меню.",
                    reply_markup=order_process_kb,
                )
                await state.set_state(OrderLaundry.items)
                return

            # Якщо клієнт є, але квартири в базі немає —
            # питаємо номер квартири
            await message.answer(
                "🧺 <b>Оформлення замовлення</b>\n\n"
                "Я поставлю кілька коротких питань, щоб ми могли швидко забрати речі та передати їх у роботу:\n\n"
                "1. Номер квартири\n"
                "2. Що потрібно забрати\n"
                "3. Фото, якщо потрібно\n"
                "4. Зручний час забору\n"
                "5. Телефон для зв’язку\n\n"
                "Якщо ви передумали оформлювати замовлення, натисніть 🏠 Головне меню.\n\n"
                "🏢 Вкажіть, будь ласка, номер квартири, з якої потрібно забрати речі:",
                reply_markup=order_process_kb,
            )
            await state.set_state(OrderLaundry.apartment)
            return

        # Якщо клієнта ще немає в базі —
        # починаємо з номера квартири
        await message.answer(
            "🧺 <b>Оформлення замовлення</b>\n\n"
            "Я поставлю кілька коротких питань, щоб ми могли швидко забрати речі та передати їх у роботу:\n\n"
            "1. Номер квартири\n"
            "2. Що потрібно забрати\n"
            "3. Фото, якщо потрібно\n"
            "4. Зручний час забору\n"
            "5. Телефон для зв’язку\n\n"
            "Якщо ви передумали оформлювати замовлення, натисніть 🏠 Головне меню.\n\n"
            "🏢 Вкажіть, будь ласка, номер квартири, з якої потрібно забрати речі:",
            reply_markup=order_process_kb,
        )
        await state.set_state(OrderLaundry.apartment)
        return

    # Якщо користувач прийшов із сайту на консультацію ательє
    if start_arg == "atelier":
        await state.clear()

        await message.answer(
            "🧵 <b>Консультація ательє</b>\n\n"
            "Опишіть, будь ласка, що потрібно зробити з річчю. "
            "Можна також надіслати фото, щоб майстер краще оцінив задачу.\n\n"
            "Наприклад:\n"
            "• замінити блискавку на куртці\n"
            "• підшити штани\n"
            "• підігнати сукню по фігурі\n\n"
            "Після цього адміністратор зв’яжеться з вами для уточнення деталей.\n\n"
            "Якщо ви передумали, натисніть 🏠 Головне меню.",
            reply_markup=order_process_kb,
        )
        await state.set_state(ConsultationState.atelier)
        return

    # Якщо користувач прийшов із сайту на B2B-заявку
    if start_arg == "b2b":
        await state.clear()

        await message.answer(
            "🏢 <b>B2B / прання по кг</b>\n\n"
            "Напишіть, будь ласка, який текстиль потрібно прати, приблизний обсяг у кг "
            "та як часто потрібна послуга.\n\n"
            "Наприклад:\n"
            "• рушники для салону, 15 кг, 2 рази на тиждень\n"
            "• постільна білизна для апартаментів, 20 кг, щотижня\n\n"
            "Після цього адміністратор зв’яжеться з вами та запропонує умови.\n\n"
            "Якщо ви передумали, натисніть 🏠 Головне меню.",
            reply_markup=order_process_kb,
        )
        await state.set_state(ConsultationState.b2b)
        return

    # Звичайний вхід адміна або клієнта
    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "👑 <b>Адмін-панель Pralnya Vdoma</b>\n\n"
            "Ви увійшли до панелі керування. Оберіть потрібний розділ нижче.",
            reply_markup=admin_kb,
        )
    else:
        welcome_text = (
            "👋 <b>Ласкаво просимо до Pralnya Vdoma</b>\n\n"
            "Персональний догляд за речами у вашому ЖK.\n"
            "Заберемо, делікатно очистимо, попрасуємо та повернемо — без зайвих турбот.\n\n"
            "Оберіть послугу в меню — про решту подбаємо ми."
        )
        await message.answer(welcome_text, reply_markup=main_menu)


@dp.message(ConsultationState.atelier)
async def handle_atelier_consultation(message: Message, state: FSMContext):
    if message.text == "🏠 Головне меню":
        await state.clear()
        await message.answer(
            "🏠 <b>Головне меню</b>\n\n"
            "Ви повернулись до основного меню. Заявку в ательє не було створено.",
            reply_markup=main_menu,
        )
        return

    user = message.from_user
    name = user.full_name
    telegram_id = user.id
    username = f"@{user.username}" if user.username else "—"
    request_number = generate_consultation_number("AT")

    text = message.text or message.caption or "Фото без опису"

    admin_text = (
        "🧵 <b>Нова заявка в ательє</b>\n\n"
        f"🆔 Заявка: <b>{request_number}</b>\n"
        f"👤 Клієнт: <b>{name}</b>\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n"
        f"🔗 Username: {username}\n\n"
        f"💬 Опис:\n{text}"
    )

    photo_file_id = message.photo[-1].file_id if message.photo else ""

    try:
        atelier_sheet.append_row(
            [
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                name,
                telegram_id,
                username,
                text,
                photo_file_id,
                "Нова",
                "",
                "Нова",
                request_number,
            ],
            value_input_option="USER_ENTERED",
        )
        print("✅ Заявка ательє записана в лист Atelier")
    except Exception as e:
        print(f"❌ Помилка запису заявки ательє в лист Atelier: {e}")
        logging.error("Помилка запису заявки ательє в лист Atelier", exc_info=True)

    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                await message.bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=admin_text,
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    admin_id,
                    admin_text,
                    parse_mode="HTML",
                )
        except Exception as e:
            print(f"❌ Помилка відправки заявки ательє адміну {admin_id}: {e}")
            logging.error("Помилка відправки заявки ательє", exc_info=True)

    await message.answer(
        "✅ <b>Заявку в ательє прийнято</b>\n\n"
        f"🆔 Номер заявки: <b>{request_number}</b>\n\n"
        "Майстер перегляне опис або фото речі, після чого адміністратор зв’яжеться з вами "
        "для уточнення деталей, орієнтовної вартості та подальших кроків.",
        reply_markup=main_menu,
    )

    await state.clear()


@dp.message(F.text == "🧵 Заявка в ательє", any_state)
async def start_atelier_from_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🧵 <b>Консультація ательє</b>\n\n"
        "Опишіть, будь ласка, що потрібно зробити з річчю. "
        "Можна також надіслати фото, щоб майстер краще оцінив задачу.\n\n"
        "Наприклад:\n"
        "• замінити блискавку на куртці\n"
        "• підшити штани\n"
        "• підігнати сукню по фігурі\n\n"
        "Після цього адміністратор зв’яжеться з вами для уточнення деталей.\n\n"
        "Якщо ви передумали, натисніть 🏠 Головне меню.",
        reply_markup=order_process_kb,
    )

    await state.set_state(ConsultationState.atelier)


@dp.message(F.text == "🏢 B2B / прання по кг", any_state)
async def start_b2b_from_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🏢 <b>Заявка для бізнесу</b>\n\n"
        "Напишіть, будь ласка, який текстиль потрібно прати, приблизний обсяг у кг "
        "та як часто потрібна послуга.\n\n"
        "Наприклад:\n"
        "• рушники для салону, 15 кг, 2 рази на тиждень\n"
        "• постільна білизна для апартаментів, 20 кг, щотижня\n\n"
        "Після цього адміністратор зв’яжеться з вами та запропонує умови.\n\n"
        "Якщо ви передумали, натисніть 🏠 Головне меню.",
        reply_markup=order_process_kb,
    )

    await state.set_state(ConsultationState.b2b)


@dp.message(ConsultationState.b2b)
async def handle_b2b_consultation(message: Message, state: FSMContext):
    if message.text == "🏠 Головне меню":
        await state.clear()
        await message.answer(
            "🏠 <b>Головне меню</b>\n\n"
            "Ви повернулись до основного меню. B2B-заявку не було створено.",
            reply_markup=main_menu,
        )
        return

    user = message.from_user
    name = user.full_name
    telegram_id = user.id
    username = f"@{user.username}" if user.username else "—"
    request_number = generate_consultation_number("B2B")

    text = message.text or message.caption or "Фото без опису"
    photo_file_id = message.photo[-1].file_id if message.photo else ""

    admin_text = (
        "🏢 <b>Нова B2B-заявка (Бот)</b>\n\n"
        f"🆔 Заявка: <b>{request_number}</b>\n"
        f"👤 Клієнт: <b>{name}</b>\n"
        f"🆔 Telegram ID: <code>{telegram_id}</code>\n"
        f"🔗 Username: {username}\n\n"
        f"💬 Опис:\n{text}"
    )

    # Формируем ровно 12 элементов под структуру B2B_General
    row_data = [
        datetime.now().strftime("%d.%m.%Y %H:%M"),  # 1. Дата
        "Бот",                                      # 2. Джерело
        request_number,                             # 3. Номер заявки
        name,                                       # 4. Клієнт (Ім'я)
        "",                                         # 5. Телефон (если не собираем на этом шаге)
        text,                                       # 6. Опис / Деталі
        photo_file_id,                              # 7. Фото
        str(telegram_id),                           # 8. Telegram ID
        username,                                   # 9. Username
        "Нова заявка",                              # 10. Статус
        "",                                         # 11. Коментар адміна
        ""                                          # 12. Останній повідомлений статус
    ]

    try:
        b2b_sheet.append_row(
            row_data,
            value_input_option="USER_ENTERED",
        )
        print("✅ B2B-заявка записана в лист B2B_General")
    except Exception as e:
        print(f"❌ Помилка запису B2B-заявки в лист B2B_General: {e}")
        logging.error("Помилка запису B2B-заявки в лист B2B_General", exc_info=True)

    for admin_id in ADMIN_IDS:
        try:
            if message.photo:
                await message.bot.send_photo(
                    admin_id,
                    photo=message.photo[-1].file_id,
                    caption=admin_text,
                    parse_mode="HTML",
                )
            else:
                await message.bot.send_message(
                    admin_id,
                    admin_text,
                    parse_mode="HTML",
                )
        except Exception as e:
            print(f"❌ Помилка відправки B2B-заявки адміну {admin_id}: {e}")
            logging.error("Помилка відправки B2B-заявки", exc_info=True)

    await message.answer(
        "✅ <b>B2B-заявку прийнято</b>\n\n"
        f"🆔 Номер заявки: <b>{request_number}</b>\n\n"
        "Адміністратор перегляне ваш запит, оцінить обсяг і регулярність послуги, "
        "після чого зв’яжеться з вами для погодження умов.",
        reply_markup=main_menu,
    )

    await state.clear()


async def check_consultation_statuses(bot: Bot):
    while True:
        try:
            # 🧵 Перевірка заявок Ательє
            atelier_rows = atelier_sheet.get_all_values()[1:]

            for index, row in enumerate(atelier_rows, start=2):
                telegram_id = row[2] if len(row) > 2 else ""
                description = row[4] if len(row) > 4 else "—"
                status = row[6] if len(row) > 6 and row[6] else "Нова"
                admin_comment = row[7] if len(row) > 7 and row[7] else ""
                last_notified_status = row[8] if len(row) > 8 else ""
                request_number = row[9] if len(row) > 9 and row[9] else "—"

                if not telegram_id or status == last_notified_status:
                    continue

                try:
                    await bot.send_message(
                        int(telegram_id),
                        "🧵 <b>Оновлення по заявці ательє</b>\n\n"
                        f"🆔 Заявка: <b>{request_number}</b>\n"
                        f"💬 Заявка: {description}\n"
                        f"📌 Статус: <b>{status}</b>\n"
                        f"📝 Коментар: {admin_comment or '—'}",
                    )

                    atelier_sheet.update_cell(index, 9, status)
                    print(f"✅ Клієнта повідомлено по заявці Ательє, рядок {index}")

                except Exception as e:
                    print(
                        f"❌ Не вдалося повідомити клієнта Atelier, рядок {index}: {e}"
                    )
                    logging.error("Помилка повідомлення клієнта Atelier", exc_info=True)

            # 🏢 Перевірка B2B-заявок
            b2b_rows = b2b_sheet.get_all_values()[1:]

            for index, row in enumerate(b2b_rows, start=2):
                telegram_id = row[2] if len(row) > 2 else ""
                description = row[4] if len(row) > 4 else "—"
                status = row[6] if len(row) > 6 and row[6] else "Нова"
                admin_comment = row[7] if len(row) > 7 and row[7] else ""
                last_notified_status = row[8] if len(row) > 8 else ""
                request_number = row[9] if len(row) > 9 and row[9] else "—"

                if not telegram_id or status == last_notified_status:
                    continue

                try:
                    await bot.send_message(
                        int(telegram_id),
                        "🏢 <b>Оновлення по B2B-заявці</b>\n\n"
                        f"🆔 Заявка: <b>{request_number}</b>\n"
                        f"💬 Заявка: {description}\n"
                        f"📌 Статус: <b>{status}</b>\n"
                        f"📝 Коментар: {admin_comment or '—'}",
                    )

                    b2b_sheet.update_cell(index, 9, status)
                    print(f"✅ Клієнта повідомлено по B2B-заявці, рядок {index}")

                except Exception as e:
                    print(f"❌ Не вдалося повідомити клієнта B2B, рядок {index}: {e}")
                    logging.error("Помилка повідомлення клієнта B2B", exc_info=True)

        except Exception as e:
            print(f"❌ Помилка перевірки статусів консультацій: {e}")
            logging.error("Помилка перевірки статусів консультацій", exc_info=True)

        await asyncio.sleep(60)


@dp.message(F.text == "❌ Скасувати замовлення", any_state)
async def global_cancel(message: Message, state: FSMContext):
    current_state = await state.get_state()
    user_data = await state.get_data()

    # Если клиент не находится в процессе оформления заказа
    if current_state is None or not user_data:
        await message.answer(
            "ℹ️ У вас немає активного оформлення замовлення.", reply_markup=main_menu
        )
        return

    apartment = user_data.get("apartment", "—")
    items = user_data.get("items", "—")
    time_text = user_data.get("time", "—")
    phone = normalize_phone(user_data.get("phone", ""))
    name = message.from_user.full_name
    date = datetime.now().strftime("%d.%m.%Y")
    order_number = generate_order_number()
    recognized_table_text = "Скасовано"

    row_data = [
        date,  # A — Дата
        name,  # B — Ім'я
        phone,  # C — Телефон
        apartment,  # D — Квартира
        items,  # E — Речі
        time_text,  # F — Час
        "❌ Скасовано користувачем",  # G — Скасування
        "—",  # H — Підписка
        "❌ Скасовано",  # I — Статус
        "",  # J — Повідомлено
        0,  # K — Сума
        "",  # L — Фото
        order_number,  # M — Номер замовлення
        "",
        recognized_table_text,  # N — Останній повідомлений статус
    ]

    try:
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
        print("🚫 Скасування записано в таблицю.")
    except Exception as e:
        print(f"❌ Помилка запису скасування: {e}")
        logging.error("Помилка запису скасування", exc_info=True)

    await state.clear()

    await message.answer(
        "❌ Оформлення замовлення скасовано. Ви повернулись до головного меню.",
        reply_markup=main_menu,
    )


@dp.message(F.text == "🏠 Головне меню", any_state)
async def back_to_main_menu(message: Message, state: FSMContext):
    await state.clear()

    if message.from_user.id in ADMIN_IDS:
        await message.answer(
            "🏠 <b>Адмін-меню</b>\n\n" "Ви повернулись до панелі керування.",
            reply_markup=admin_kb,
        )
    else:
        await message.answer(
            "🏠 <b>Головне меню</b>\n\n"
            "Ви повернулись до основного меню. Оберіть потрібну дію нижче.",
            reply_markup=main_menu,
        )


@dp.message(F.text == "Здати речі")
async def start_order(message: Message, state: FSMContext):
    current_state = await state.get_state()

    if current_state is not None:
        await message.answer(
            "ℹ️ Ви вже оформлюєте замовлення.\n\n"
            "Продовжіть поточне оформлення або натисніть ❌ Скасувати замовлення.",
            reply_markup=main_menu,
        )
        return

    telegram_id = message.from_user.id
    client = get_client_by_telegram_id(telegram_id)

    if client:
        name = client["name"]
        apartment = client["apartment"]
        phone = client["phone"]

        await state.update_data(apartment=apartment, phone=phone)

        await message.answer(
            f"👋 <b>{name}</b>, раді бачити вас знову.\n\n"
            f"🏢 Квартира: <b>{apartment}</b>\n\n"
            "👚 Напишіть, будь ласка, які речі потрібно передати в роботу.\n"
            "Наприклад: <b>2 сорочки, джинси та куртка</b>.\n\n"
            "Якщо передумали, натисніть 🏠 Головне меню.",
            reply_markup=order_process_kb,
        )

        await state.set_state(OrderLaundry.items)

    else:
        await message.answer(
            "🧺 <b>Оформлення замовлення</b>\n\n"
            "Почнемо з кількох коротких питань, щоб ми могли забрати речі та передати їх у роботу.\n\n"
            "🏢 Вкажіть, будь ласка, номер квартири, з якої потрібно забрати речі.\n\n"
            "Якщо передумали, натисніть 🏠 Головне меню.",
            reply_markup=order_process_kb,
        )

        await state.set_state(OrderLaundry.apartment)


@dp.message(OrderLaundry.apartment)
async def ask_items(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати замовлення":
        await global_cancel(message, state)
        return
    if is_menu_button(message.text):
        await message.answer(
            "ℹ️ Ви зараз оформлюєте замовлення.\n\n"
            "Напишіть номер квартири або натисніть ❌ Скасувати замовлення.",
            reply_markup=main_menu,
        )
        return
    await state.update_data(apartment=message.text)
    await message.answer(
        "👚 Напишіть, будь ласка, які речі потрібно передати в роботу.\n"
        "Наприклад: <b>2 сорочки, джинси та куртка</b>.",
        reply_markup=order_process_kb,
    )
    await state.set_state(OrderLaundry.items)


@dp.message(OrderLaundry.items)
async def ask_photo(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати замовлення":
        await global_cancel(message, state)
        return
    if is_menu_button(message.text):
        await message.answer(
            "ℹ️ Ви зараз оформлюєте замовлення.\n\n"
            "Напишіть, будь ласка, що потрібно забрати, або натисніть ❌ Скасувати замовлення.",
            reply_markup=main_menu,
        )
        return
    await state.update_data(items=message.text)

    await message.answer(
        "📸 Бажаєте додати фото речей?\n\n"
        "Фото допоможе нам точніше оцінити стан виробу, плями або складність роботи.\n\n"
        "Можете надіслати фото одним повідомленням або натиснути ⏭️ Пропустити.",
        reply_markup=photo_menu,
    )

    await state.set_state(OrderLaundry.photo)


@dp.message(OrderLaundry.photo)
async def process_photo(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати замовлення":
        await global_cancel(message, state)
        return

    # Клиент нажал кнопку "Добавить фото"
    if message.text == "📸 Додати фото":
        await message.answer(
            "📷 Надішліть, будь ласка, фото речей одним повідомленням."
        )
        return

    # Клиент решил пропустить фото
    # Клієнт вирішив пропустити фото
    if message.text == "⏭️ Пропустити":
        await state.update_data(photo="")

        await message.answer(
            "🕓 Вкажіть, будь ласка, зручний день і час для забору речей.\n"
            "Наприклад: <b>сьогодні після 19:00</b> або <b>завтра з 10:00 до 12:00</b>.",
            reply_markup=order_process_kb,
        )

        await state.set_state(OrderLaundry.time)
        return

    # Клиент отправил фото
    if message.photo:
        photo_id = message.photo[-1].file_id
        await state.update_data(photo=photo_id)

        await message.answer(
            "✅ Фото додано до замовлення.\n\n"
            "🕓 Вкажіть, будь ласка, зручний день і час для забору речей.\n"
            "Наприклад: <b>сьогодні після 19:00</b> або <b>завтра з 10:00 до 12:00</b>.",
            reply_markup=order_process_kb,
        )

        await state.set_state(OrderLaundry.time)
        return

    await message.answer(
        "📸 Надішліть фото речей одним повідомленням або натисніть ⏭️ Пропустити.",
        reply_markup=photo_menu,
    )


@dp.message(OrderLaundry.time)
async def ask_phone(message: Message, state: FSMContext):
    if message.text == "❌ Скасувати замовлення":
        await global_cancel(message, state)
        return

    if is_menu_button(message.text):
        await message.answer(
            "ℹ️ Ви зараз оформлюєте замовлення.\n\n"
            "Напишіть зручний день/час або натисніть ❌ Скасувати замовлення.",
            reply_markup=main_menu,
        )
        return

    await state.update_data(time=message.text)

    user_data = await state.get_data()
    saved_phone = normalize_phone(user_data.get("phone", ""))

    if saved_phone:
        await confirm_order_auto_phone(message, state)
    else:
        contact_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📞 Надати номер телефону", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )

        await message.answer(
            "📞 Вкажіть, будь ласка, номер телефону для зв’язку.\n\n"
            "Можете натиснути кнопку нижче, щоб надіслати номер автоматично, "
            "або написати його вручну у форматі <b>+380XXXXXXXXX</b>.\n\n"
            "Менеджер зможе уточнити деталі замовлення або погодити вартість перед початком роботи.",
            reply_markup=contact_keyboard,
        )

        await state.set_state(OrderLaundry.phone)


def calculate_order_amount(items_text):
    total = 0

    if not items_text:
        return 0

    text = str(items_text).lower()
    text = text.replace(",", " ")
    text = text.replace(".", " ")

    word_numbers = {
        "один": 1,
        "одна": 1,
        "одне": 1,
        "раз": 1,
        "два": 2,
        "дві": 2,
        "две": 2,
        "три": 3,
        "чотири": 4,
        "четыре": 4,
        "п'ять": 5,
        "пʼять": 5,
        "пять": 5,
    }

    found_items = []

    sorted_items = sorted(
        ITEM_ALIASES.items(),
        key=lambda x: max(len(alias) for alias in x[1]),
        reverse=True,
    )

    for item_name, aliases in sorted_items:
        price = PRICE_LIST.get(item_name, 0)

        for alias in aliases:
            alias_lower = alias.lower()

            if alias_lower in text:
                quantity = 1

                pattern_digit = r"(\d+)\s+" + re.escape(alias_lower)
                match_digit = re.search(pattern_digit, text)

                if match_digit:
                    quantity = int(match_digit.group(1))
                else:
                    for word, number in word_numbers.items():
                        pattern_word = (
                            r"\b" + re.escape(word) + r"\s+" + re.escape(alias_lower)
                        )

                        if re.search(pattern_word, text):
                            quantity = number
                            break

                total += price * quantity
                found_items.append(item_name)

                text = text.replace(alias_lower, " ")

                break

    return total


def analyze_order_items(items_text):
    total = 0
    recognized_items = []

    if not items_text:
        return total, recognized_items

    text = str(items_text).lower()
    text = text.replace(",", " ")
    text = text.replace(".", " ")

    word_numbers = {
        "один": 1,
        "одна": 1,
        "одне": 1,
        "раз": 1,
        "два": 2,
        "дві": 2,
        "две": 2,
        "три": 3,
        "чотири": 4,
        "четыре": 4,
        "п'ять": 5,
        "пʼять": 5,
        "пять": 5,
    }

    sorted_items = sorted(
        ITEM_ALIASES.items(),
        key=lambda x: max(len(alias) for alias in x[1]),
        reverse=True,
    )

    for item_name, aliases in sorted_items:
        price = PRICE_LIST.get(item_name, 0)

        for alias in aliases:
            alias_lower = alias.lower()

            if alias_lower in text:
                quantity = 1

                pattern_digit = r"(\d+)\s+" + re.escape(alias_lower)
                match_digit = re.search(pattern_digit, text)

                if match_digit:
                    quantity = int(match_digit.group(1))
                else:
                    for word, number in word_numbers.items():
                        pattern_word = (
                            r"\b" + re.escape(word) + r"\s+" + re.escape(alias_lower)
                        )

                        if re.search(pattern_word, text):
                            quantity = number
                            break

                item_total = price * quantity
                total += item_total

                recognized_items.append(
                    {
                        "name": item_name,
                        "quantity": quantity,
                        "price": price,
                        "total": item_total,
                    }
                )

                # Убираем уже распознанную фразу из текста,
                # чтобы она не посчиталась повторно как другая позиция
                text = text.replace(alias_lower, " ")

                break

    return total, recognized_items


def build_recognized_table_text(recognized_items):
    if not recognized_items:
        return "Не розпізнано"

    parts = []

    for item in recognized_items:
        parts.append(f"{item['name']} × {item['quantity']} — {item['total']} грн")

    return "; ".join(parts)


# =========================
# UTILS / ДОПОМІЖНІ ФУНКЦІЇ
# =========================
def is_duplicate_order(phone, items, minutes=10):
    try:
        records = sheet.get_all_values()

        if not records:
            return False

        headers = records[0]
        rows = records[1:]

        phone_index = headers.index("Телефон")
        items_index = headers.index("Речі")
        cancel_index = headers.index("Скасування")
        order_number_index = headers.index("Номер замовлення")

        current_phone = normalize_phone(phone)
        current_items = str(items).strip().lower()

        now = datetime.now()

        for row in reversed(rows):
            if len(row) <= max(
                phone_index, items_index, cancel_index, order_number_index
            ):
                continue

            row_phone = normalize_phone(row[phone_index])
            row_items = str(row[items_index]).strip().lower()
            row_cancel = str(row[cancel_index]).strip()
            row_order_number = str(row[order_number_index]).strip()

            if row_phone[-10:] != current_phone[-10:]:
                continue

            if row_items != current_items:
                continue

            if "Скасовано" in row_cancel:
                continue

            # Пример номера: PV-1779186114
            if row_order_number.startswith("PV-"):
                try:
                    timestamp = int(row_order_number.replace("PV-", ""))
                    order_time = datetime.fromtimestamp(timestamp)

                    if now - order_time <= timedelta(minutes=minutes):
                        return True

                except ValueError:
                    continue

        return False

    except Exception as e:
        print(f"❌ Помилка перевірки дубля замовлення: {e}")
        logging.error("Помилка перевірки дубля замовлення", exc_info=True)
        return False


def generate_order_number():
    return f"PV-{int(datetime.now().timestamp())}"


def generate_consultation_number(prefix: str) -> str:
    return f"{prefix}-{int(datetime.now().timestamp())}"


def get_client_subscription(telegram_id):
    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()
        for client in clients:
            if str(client.get("telegram_id")) == str(telegram_id):
                return client.get("subscription", "Ні")  # если нет данных — "Ні"
    except WorksheetNotFound:
        pass
    return "Ні"


@dp.message(OrderLaundry.phone)
async def confirm_order(message: Message, state: FSMContext):
    phone = ""

    if message.contact:
        phone = normalize_phone(message.contact.phone_number)
    elif message.text:
        phone = normalize_phone(message.text)

    if not phone or len(phone) < 10:
        await message.answer(
            "❗ Будь ласка, натисніть кнопку <b>📞 Надати номер телефону</b> "
            "або напишіть номер вручну у форматі +380XXXXXXXXX."
        )
        return

    user_data = await state.get_data()

    apartment = user_data.get("apartment", "Невідомо")
    items = user_data.get("items", "Невідомо")
    time_text = user_data.get("time", "Невідомо")
    photo_file_id = user_data.get("photo", "")

    date = datetime.now().strftime("%d.%m.%Y")
    order_number = generate_order_number()

    name = message.from_user.full_name

    subscription_status = get_client_subscription(message.from_user.id)
    order_amount, recognized_items = analyze_order_items(items)
    recognized_table_text = build_recognized_table_text(recognized_items)

    if is_duplicate_order(phone, items):
        await message.answer(
            "⚠️ Схоже, таке замовлення вже було створено нещодавно.\n"
            "Ми вже отримали вашу заявку 🧺",
            reply_markup=main_menu,
        )
        await state.clear()
        return

    try:
        save_new_client(message.from_user.id, name, phone, apartment)
    except Exception as e:
        print(f"❌ Помилка збереження клієнта: {e}")
        logging.error("Помилка збереження клієнта", exc_info=True)

    try:
        sheet.append_row(
            [
                date,
                name,
                phone,
                apartment,
                items,
                time_text,
                "",
                subscription_status,
                "Очікує",
                "",
                order_amount,
                photo_file_id,
                order_number,
                "",
                recognized_table_text,
            ]
        )

    except Exception as e:
        print(f"❌ Помилка запису в таблицю: {e}")
        logging.error("Помилка запису в таблицю", exc_info=True)
    recognized_text = ""

    if recognized_items:
        recognized_text = "\n\n🔎 <b>Розпізнано:</b>\n"
        for item in recognized_items:
            recognized_text += (
                f"• {item['name']} × {item['quantity']} — " f"{item['total']} грн\n"
            )
    else:
        recognized_text = (
            "\n\n⚠️ Не вдалося автоматично розпізнати позиції з прайсу.\n"
            "Адміністратор уточнить суму після огляду."
        )

    if order_amount > 0:
        amount_text = f"💰 Орієнтовна сума: <b>{order_amount} грн</b>"
    else:
        amount_text = "💰 Орієнтовна сума буде уточнена адміністратором після огляду."

    # 📩 Отправка админу
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🆕 <b>Нове замовлення!</b>\n\n"
                f"🆔 {order_number}\n"
                f"👤 {name}\n"
                f"📞 {phone}\n"
                f"🏢 Квартира: {apartment}\n"
                f"👚 Речі: {items}\n"
                f"🕓 Час: {time_text}\n"
                f"💰 Орієнтовна сума: {order_amount} грн"
                f"{recognized_text}"
            )

            if photo_file_id:
                await bot.send_photo(
                    chat_id=admin_id, photo=photo_file_id, caption=admin_text
                )
            else:
                await bot.send_message(chat_id=admin_id, text=admin_text)

        except Exception as e:
            print(f"❌ Помилка надсилання адміну: {e}")
            logging.error("Помилка надсилання адміну", exc_info=True)

    await message.answer(
        "✅ <b>Замовлення прийнято</b>\n\n"
        f"🆔 Номер замовлення: <b>{order_number}</b>\n"
        f"🏢 Квартира: <b>{apartment}</b>\n"
        f"👚 Речі: <b>{items}</b>\n"
        f"🕓 Час забору: <b>{time_text}</b>\n"
        f"{amount_text}"
        f"{recognized_text}\n\n"
        "Адміністратор перегляне замовлення, за потреби уточнить деталі "
        "та погодить фінальну вартість перед початком роботи.",
        reply_markup=main_menu,
    )

    await state.clear()


# ------------------------------------------------------


async def confirm_order_auto_phone(message: Message, state: FSMContext):
    user_data = await state.get_data()

    apartment = user_data.get("apartment", "Невідомо")
    items = user_data.get("items", "Невідомо")
    time_text = user_data.get("time", "Невідомо")
    phone = user_data.get("phone", "")
    photo_file_id = user_data.get("photo", "")  # Вытягиваем по правильному ключу

    name = message.from_user.full_name
    date = datetime.now().strftime("%d.%m.%Y")

    subscription_status = get_client_subscription(message.from_user.id)
    order_number = generate_order_number()
    order_amount, recognized_items = analyze_order_items(items)
    recognized_table_text = build_recognized_table_text(recognized_items)

    if is_duplicate_order(phone, items):
        await message.answer(
            "⚠️ Схоже, таке замовлення вже було створено нещодавно.\n"
            "Ми вже отримали вашу заявку 🧺",
            reply_markup=main_menu,
        )
        await state.clear()
        return

    row_data = [
        date,  # 0: Дата
        name,  # 1: Ім'я
        phone,  # 2: Телефон
        apartment,  # 3: Квартира
        items,  # 4: Речі
        time_text,  # 5: Час
        "",  # 6: Скасування
        subscription_status,  # 7: Підписка
        "Очікує",  # 8: Статус
        "",  # 9: Повідомлено
        order_amount,  # 10: Сума
        photo_file_id,  # 11: Фото
        order_number,
        "",  # 12: Номер замовлення
        recognized_table_text,  # 13: Розпізнано
    ]

    try:
        sheet.append_row(row_data, value_input_option="USER_ENTERED")
    except Exception as e:
        print(f"❌ Помилка запису в таблицю: {e}")
        logging.error("Помилка запису в таблицю", exc_info=True)

    recognized_text = ""

    if recognized_items:
        recognized_text = "\n\n🔎 <b>Розпізнано:</b>\n"
        for item in recognized_items:
            recognized_text += (
                f"• {item['name']} × {item['quantity']} — " f"{item['total']} грн\n"
            )
    else:
        recognized_text = (
            "\n\n⚠️ Не вдалося автоматично розпізнати позиції з прайсу.\n"
            "Адміністратор уточнить суму після огляду."
        )

    if order_amount > 0:
        amount_text = f"💰 Орієнтовна сума: <b>{order_amount} грн</b>"
    else:
        amount_text = "💰 Орієнтовна сума буде уточнена адміністратором після огляду."

    await message.answer(
        "✅ <b>Замовлення прийнято</b>\n\n"
        f"🆔 Номер замовлення: <b>{order_number}</b>\n"
        f"🏢 Квартира: <b>{apartment}</b>\n"
        f"👚 Речі: <b>{items}</b>\n"
        f"🕓 Час забору: <b>{time_text}</b>\n"
        f"{amount_text}"
        f"{recognized_text}\n\n"
        "Адміністратор перегляне замовлення, за потреби уточнить деталі "
        "та погодить фінальну вартість перед початком роботи.",
        reply_markup=main_menu,
    )
    # фото админу ------------------------------------------
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🆕 <b>Нове замовлення!</b>\n\n"
                f"🆔 {order_number}\n"
                f"👤 {name}\n"
                f"📞 {phone}\n"
                f"🏢 Квартира: {apartment}\n"
                f"👚 Речі: {items}\n"
                f"🕓 Час: {time_text}\n"
                f"💰 Орієнтовна сума: {order_amount} грн"
                f"{recognized_text}"
            )

            if photo_file_id:
                await bot.send_photo(
                    chat_id=admin_id, photo=photo_file_id, caption=admin_text
                )
            else:
                await bot.send_message(chat_id=admin_id, text=admin_text)

        except Exception as e:
            print(f"❌ Помилка надсилання адміну: {e}")
            logging.error("Помилка надсилання адміну", exc_info=True)

    # -------------------------------------------

    await state.clear()


# ---------------- ПРАЙС --------------------
@dp.message(F.text == "Прайс", any_state)
async def open_price_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "📋 <b>Оберіть розділ прайсу:</b>\n\n"
        "🧺 Прання — повсякденні речі\n"
        "🧥 Верхній одяг — пуховики, куртки, пальта\n"
        "🛏️ Домашній текстиль — постіль, рушники, пледи\n"
        "🧵 Ательє — ремонт та підгонка одягу\n"
        "🏢 B2B / по кг — для партій текстилю\n"
        "⚠️ Після огляду — складні речі",
        reply_markup=price_menu,
    )


@dp.message(F.text == "🧺 Прання", any_state)
async def price_washing(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🧺 <b>Прання</b>\n\n"
        "Для речей щоденного використання, які можна прати у воді.\n\n"
        "👔 Сорочка — від 250 грн\n"
        "👕 Футболка — від 180 грн\n"
        "👕 Майка — від 170 грн\n"
        "👖 Штани — від 250 грн\n"
        "👖 Джинси — від 280 грн\n"
        "🩳 Шорти — від 180 грн\n"
        "🧥 Худі / світшот — від 350 грн\n"
        "🧶 Светр — від 320 грн\n"
        "🧶 Кофта — від 350 грн\n\n"
        f"{PRICE_NOTE}"
        "Щоб оформити замовлення, натисніть <b>«Здати речі»</b>.",
        reply_markup=price_menu,
    )


@dp.message(F.text == "🧥 Верхній одяг", any_state)
async def price_outerwear(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🧥 <b>Верхній одяг</b>\n\n"
        "Догляд за куртками, пуховиками, пальтами та сезонним одягом.\n\n"
        "Вітровка — від 650 грн\n"
        "Куртка демісезонна — від 850 грн\n"
        "Куртка джинсова — від 780 грн\n"
        "Піджак — від 750 грн\n"
        "Пуховик короткий — від 1200 грн\n"
        "Пуховик довгий — від 1450 грн\n"
        "Пальто текстильне — від 950 грн\n"
        "Плащ / тренч — від 1000 грн\n"
        "Жилет — від 750 грн\n\n"
        "⚠️ Шкіра, замша, хутро та речі зі складним декором приймаються тільки після огляду.\n\n"
        f"{PRICE_NOTE}"
        "Щоб оформити замовлення, натисніть <b>«Здати речі»</b>.",
        reply_markup=price_menu,
    )


@dp.message(F.text == "🛏️ Домашній текстиль", any_state)
async def price_home_textile(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🛏️ <b>Домашній текстиль</b>\n\n"
        "Прання та догляд за текстилем для дому: постіль, рушники, пледи, ковдри.\n\n"
        "Постільна білизна комплект — від 550 грн\n"
        "Рушники — від 120 грн / кг\n"
        "Халат — від 350 грн\n"
        "Плед — від 550 грн\n"
        "Покривало — від 850 грн\n"
        "Ковдра синтетична — від 850 грн\n"
        "Ковдра пухова — від 1200 грн\n"
        "Подушка мала — від 350 грн\n"
        "Подушка велика — від 700 грн\n"
        "Наматрацник — від 800 грн\n"
        "Штори / тюль — від 220 грн / м² (залежно від типу)\n\n"
        f"{PRICE_NOTE}"
        "Щоб оформити замовлення, натисніть <b>«Здати речі»</b>.",
        reply_markup=price_menu,
    )


@dp.message(F.text == "🧵 Ательє", any_state)
async def price_atelier(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🧵 <b>Ательє</b>\n\n"
        "Ремонт, підгонка та відновлення одягу будь-якої складності.\n\n"
        "Підшити штани — від 300 грн\n"
        "Вкоротити рукави — від 350 грн\n"
        "Укоротити сукню / спідницю — від 450 грн\n"
        "Заміна блискавки — від 400 грн\n"
        "Ремонт шва — від 250 грн\n"
        "Ремонт кишень — від 300 грн\n"
        "Дрібний ремонт одягу — від 200 грн\n"
        "Підгонка по фігурі — після огляду\n"
        "Заміна підкладки — після огляду\n"
        "Реставрація одягу — після огляду\n\n"
        "📌 Точна вартість залежить від складності роботи, матеріалу виробу та фурнітури.\n\n"
        "Щоб оформити замовлення або консультацію, натисніть <b>«Здати речі»</b>.",
        reply_markup=price_menu,
    )


@dp.message(F.text == "🏢 B2B / по кг", any_state)
async def price_b2b(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🏢 <b>B2B / прання по кг</b>\n\n"
        "Для бізнесу, ОСББ, салонів, студій, апартаментів та регулярних партій текстилю.\n\n"
        "Прання однотипного текстилю — від 90 грн / кг\n"
        "Прання + сушіння — від 110 грн / кг\n"
        "Прання + прасування — від 150 грн / кг\n"
        "Постільна білизна партіями — від 120 грн / кг\n"
        "Рушники партіями — від 100 грн / кг\n\n"
        "📌 B2B-тариф діє для партій одного типу тканини, кольору або призначення.\n\n"
        "Змішані речі рахуються за роздрібним прайсом.\n"
        "Мінімальне B2B-замовлення — від 10 кг або від 1000 грн.\n\n"
        "Для прорахунку напишіть нам кількість, тип текстилю та регулярність замовлень.",
        reply_markup=price_menu,
    )


@dp.message(F.text == "⚠️ Після огляду", any_state)
async def price_after_inspection(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "⚠️ <b>Речі, які приймаємо тільки після огляду</b>\n\n"
        "Деякі вироби потребують попередньої оцінки, щоб ми могли безпечно підібрати спосіб чистки.\n\n"
        "Приймаємо після огляду:\n"
        "• натуральна шкіра\n"
        "• замша\n"
        "• хутро\n"
        "• весільні сукні\n"
        "• дизайнерські речі\n"
        "• речі з великою кількістю декору\n"
        "• речі без ярлика догляду\n"
        "• речі з нестабільним фарбуванням\n"
        "• старі або складні плями\n"
        "• штори / тюль\n\n"
        "🚫 <b>Можемо відмовити у чистці</b>, якщо є високий ризик пошкодження виробу.\n\n"
        "📌 Остаточна вартість та можливість чистки визначаються після огляду технологом.\n"
        "Перед початком роботи ми погоджуємо вартість із клієнтом.\n\n"
        "Щоб передати річ на огляд, натисніть <b>«Здати речі»</b>.",
        reply_markup=price_menu,
    )


# ---------------- ПРАЙС --------------------
@dp.message(F.text == "Графік та доставка", any_state)
async def open_schedule_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🕐 Оберіть розділ:", reply_markup=schedule_menu)


@dp.message(F.text == "🕐 Графік роботи", any_state)
async def send_schedule(message: Message, state: FSMContext):
    await message.answer(
        "🕐 <b>Графік роботи:</b>\n"
        "Пн – Сб: 09:00 – 19:00\n"
        "Нд – за домовленістю\n\n"
        "📌 Уточнюйте можливість термінового замовлення у чаті з адміністратором."
    )


@dp.message(F.text == "🚚 Умови доставки", any_state)
async def send_delivery_info(message: Message, state: FSMContext):
    await message.answer(
        "🚚 <b>Умови доставки:</b>\n"
        "- Забираємо речі з вашої квартири.\n"
        "- Повертаємо в чистому вигляді протягом 24–48 годин.\n"
        "- Безкоштовно в межах ЖК.\n"
        "- За межами ЖК — уточнюйте у менеджера."
    )


@dp.message(F.text == "🔙 Назад до меню", any_state)
async def back_to_main_from_schedule(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("↩️ Ви повернулись до головного меню.", reply_markup=main_menu)


@dp.message(F.text.in_({"Підписка", "💳 Підписка"}), any_state)
async def handle_subscription(message: Message, state: FSMContext):
    await state.clear()

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔔 Оформити підписку")],
            [KeyboardButton(text="🔙 Повернутись до меню")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "💳 <b>Підписка Pralnya Vdoma</b>\n\n"
        "Підписка створена для тих, хто регулярно користується сервісом "
        "і хоче отримувати більше зручності поруч із домом.\n\n"
        "У підписку входить:\n"
        "• <b>20% знижки</b> на пральні послуги;\n"
        "• пріоритетна обробка звернень;\n"
        "• зручний сервіс без зайвих поїздок містом.\n\n"
        "Вартість підписки: <b>600 грн / місяць</b>.\n\n"
        "Щоб оформити підписку, натисніть кнопку нижче.",
        reply_markup=kb,
    )


@dp.message(F.text == "🔙 Повернутись до меню", any_state)
async def return_to_main_menu(message: Message, state: FSMContext):
    await state.clear()

    await message.answer(
        "🏠 <b>Головне меню</b>\n\n"
        "Ви повернулись до основного меню. Оберіть потрібну дію нижче.",
        reply_markup=main_menu,
    )


@dp.message(F.text == "🔔 Оформити підписку", any_state)
async def confirm_subscription(message: Message, state: FSMContext):
    await state.clear()

    telegram_id = str(message.from_user.id)
    name = message.from_user.full_name
    end_date = (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y")

    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        rows = client_sheet.get_all_values()

        if not rows:
            client_sheet.append_row(
                [
                    "telegram_id",
                    "name",
                    "phone",
                    "apartment",
                    "subscription",
                    "subscription_expires",
                ],
                value_input_option="USER_ENTERED",
            )
            rows = client_sheet.get_all_values()

        headers = rows[0]

        required_headers = [
            "telegram_id",
            "name",
            "phone",
            "apartment",
            "subscription",
            "subscription_expires",
        ]

        for header in required_headers:
            if header not in headers:
                next_col = len(headers) + 1
                client_sheet.update_cell(1, next_col, header)
                headers.append(header)

        telegram_id_col = headers.index("telegram_id") + 1
        name_col = headers.index("name") + 1
        subscription_col = headers.index("subscription") + 1
        expires_col = headers.index("subscription_expires") + 1

        updated = False
        data_rows = client_sheet.get_all_values()[1:]

        for i, row in enumerate(data_rows, start=2):
            saved_id = ""

            if len(row) >= telegram_id_col:
                saved_id = str(row[telegram_id_col - 1]).strip()

            if saved_id == telegram_id:
                client_sheet.update_cell(i, name_col, name)
                client_sheet.update_cell(i, subscription_col, "Так")
                client_sheet.update_cell(i, expires_col, end_date)
                updated = True
                break

        if not updated:
            new_row = [""] * len(headers)
            new_row[telegram_id_col - 1] = telegram_id
            new_row[name_col - 1] = name
            new_row[subscription_col - 1] = "Так"
            new_row[expires_col - 1] = end_date

            client_sheet.append_row(new_row, value_input_option="USER_ENTERED")

        await message.answer(
            "✅ <b>Підписку оформлено</b>\n\n"
            f"💳 Підписка активна до: <b>{end_date}</b>\n\n"
            "Тепер для вас діє знижка 20% на пральні послуги та можливість сезонного зберігання речей.\n\n"
            "Дякуємо за довіру до Pralnya Vdoma.",
            reply_markup=main_menu,
        )

    except Exception as e:
        print(f"❌ Помилка підписки: {e}")
        logging.error("Помилка підписки", exc_info=True)
        await message.answer(
            "❗ Сталася помилка при оформленні підписки. "
            "Будь ласка, зверніться до адміністратора.",
            reply_markup=main_menu,
        )


@dp.message(F.text == "Види чистки", any_state)
async def send_cleaning_types(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔹 <b>Машинне прання</b> — стандартне очищення з використанням пральних машин.\n"
        "🔹 <b>Ручна чистка</b> — делікатна обробка вручну з використанням плямовивідного столу.\n"
        "🔹 <b>Озонування</b> — усунення запахів та бактерій за допомогою озону.",
        reply_markup=main_menu,
    )


@dp.message(F.text == "Зв’язатися з нами", any_state)
async def contact_info(message: Message, state: FSMContext):
    await state.clear()

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📞 Написати адміну"),
                KeyboardButton(text="✉️ Зв’язатися через бота"),
            ],
            [KeyboardButton(text="🔙 Назад до меню")],
        ],
        resize_keyboard=True,
    )

    await message.answer(
        "📬 Оберіть зручний спосіб зв’язку з адміністратором:", reply_markup=kb
    )


@dp.message(F.text == "✉️ Зв’язатися через бота")
async def start_contact_via_bot(message: Message, state: FSMContext):
    await state.set_state(ChatWithAdmin.waiting_for_message)
    await message.answer(
        "✍️ Напишіть ваше повідомлення адміністратору. Він відповість вам через цей бот."
    )


@dp.message(ChatWithAdmin.waiting_for_message)
async def forward_user_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user_name = message.from_user.full_name

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📨 Повідомлення від <b>{user_name}</b>:\n\n{message.text}\n\n"
                f"Натисніть /reply_{user_id} щоб відповісти.",
                parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            print(f"❌ Помилка надсилання адміну: {e}")
            logging.error("Помилка надсилання адміну", exc_info=True)

    await message.answer("✅ Повідомлення надіслано. Очікуйте відповідь.")
    await state.clear()


@dp.message(F.text.startswith("/reply_"))
async def reply_to_user_command(message: Message, state: FSMContext):
    parts = message.text.split("_")
    if len(parts) != 2:
        await message.answer("❌ Невірна команда.")
        return

    try:
        target_user_id = int(parts[1])
        await state.update_data(reply_to_user=target_user_id)
        await state.set_state(ChatWithAdmin.waiting_for_admin_reply)
        await message.answer("✍️ Введіть вашу відповідь клієнту:")
    except ValueError:
        await message.answer("❌ Некоректний ID користувача.")


@dp.message(ChatWithAdmin.waiting_for_admin_reply)
async def send_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    target_user_id = data.get("reply_to_user")

    if not target_user_id:
        await message.answer("❌ Не знайдено ID користувача для відповіді.")
        await state.clear()
        return

    try:
        await bot.send_message(
            target_user_id, f"📬 Відповідь від адміністратора:\n\n{message.text}"
        )
        await message.answer("✅ Повідомлення надіслано клієнту.")
    except Exception as e:
        await message.answer(f"❌ Не вдалося надіслати: {e}")
    finally:
        await state.clear()


@dp.message(F.text == "📞 Написати адміну")
async def send_admin_link(message: Message):
    await message.answer(
        "🔗 Напишіть адміністратору напряму: [Перейти в Telegram](https://t.me/@Mykich)",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


@dp.message(F.text == "🔙 Назад до меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("↩️ Ви повернулись до головного меню.", reply_markup=main_menu)


@dp.message(F.text == "📦 Активне замовлення", any_state)
async def active_order_from_account(message: Message, state: FSMContext):
    await state.clear()

    telegram_id = message.from_user.id
    client = get_client_by_telegram_id(telegram_id)

    if not client:
        await message.answer(
            "🔑 Спочатку скористайтесь функцією 'Здати речі', щоб зареєструватись.",
            reply_markup=main_menu,
        )
        return

    phone = normalize_phone(client.get("phone", ""))

    try:
        orders = sheet.get_all_values()[1:]

        active_orders = []

        for row in orders:
            if len(row) <= 10:
                continue

            order_phone = normalize_phone(row[2])

            if order_phone[-10:] != phone[-10:]:
                continue

            status = row[8] if len(row) > 8 else ""

            if "Скасовано" in status:
                continue

            if "Виконано" in status:
                continue

            active_orders.append(row)

        if not active_orders:
            await message.answer(
                "📭 У вас немає активних замовлень.",
                reply_markup=account_kb,
            )
            return

        active_orders = list(reversed(active_orders))

        response = "📦 <b>Ваші активні замовлення</b>\n\n"

        for active in active_orders[:5]:
            order_number = active[12] if len(active) > 12 else "—"
            date = active[0] if len(active) > 0 else "—"
            apartment = active[3] if len(active) > 3 else "—"
            items = active[4] if len(active) > 4 else "—"
            time_text = active[5] if len(active) > 5 else "—"
            status = active[8] if len(active) > 8 else "Очікує"
            amount = active[10] if len(active) > 10 else "0"
            recognized = (
                active[14]
                if len(active) > 14 and active[14]
                else "Буде уточнено адміністратором"
            )

            response += (
                f"📍 <b>Активне замовлення</b>\n\n"
                f"🆔 <b>{order_number}</b>\n"
                f"📅 {date}\n"
                f"🏢 Квартира: <b>{apartment}</b>\n\n"
                f"👚 Речі:\n{items}\n\n"
                f"🔎 Розпізнано:\n{recognized}\n\n"
                f"🕓 Час: <b>{time_text}</b>\n"
                f"📦 Статус: <b>{status}</b>\n"
                f"💰 Сума: <b>{amount} грн</b>\n\n"
                "──────────────\n\n"
            )

        await message.answer(response, reply_markup=account_kb)

    except Exception as e:
        print(f"❌ Помилка активного замовлення: {e}")
        logging.error("Помилка активного замовлення", exc_info=True)
        await message.answer(
            "❗ Помилка при завантаженні активного замовлення.",
            reply_markup=account_kb,
        )


@dp.message(F.text == "🧾 Мої замовлення", any_state)
async def user_orders(message: Message, state: FSMContext):
    await state.clear()

    telegram_id = message.from_user.id
    client = get_client_by_telegram_id(telegram_id)

    if not client:
        await message.answer(
            "🔑 Спочатку скористайтесь функцією 'Здати речі', щоб зареєструватись."
        )
        return

    # Нормализуем телефон
    phone = normalize_phone(client.get("phone", ""))
    name = client.get("name", "Клієнт")

    try:
        orders = sheet.get_all_values()[1:]

        user_orders = []

        for row in orders:
            if len(row) > 2:
                order_phone = normalize_phone(row[2])

                # Сравниваем последние 10 цифр
                if order_phone[-10:] == phone[-10:]:
                    user_orders.append(row)

        if not user_orders:
            await message.answer("📭 У вас ще немає замовлень.")
            return

        last_orders = list(reversed(user_orders))

        # Ищем последнее НЕ отменённое
        latest_order = next(
            (row for row in last_orders if len(row) > 6 and "Скасовано" not in row[6]),
            None,
        )

        active_orders = [
            row for row in last_orders if len(row) > 8 and "Скасовано" not in row[8]
        ]

        response = ""

        # 📍 Активне замовлення
        if active_orders:
            active = active_orders[0]

            recognized_active = (
                active[14]
                if len(active) > 14 and active[14]
                else "Буде уточнено адміністратором"
            )

            response += (
                f"📍 <b>Активне замовлення</b>\n\n"
                f"🆔 <b>{active[12]}</b>\n"
                f"📅 {active[0]}\n"
                f"🏢 Квартира: <b>{active[3]}</b>\n\n"
                f"👚 Речі:\n{active[4]}\n\n"
                f"🔎 Розпізнано:\n{recognized_active}\n\n"
                f"🕓 Час: <b>{active[5]}</b>\n"
                f"📦 Статус: <b>{active[8]}</b>\n"
                f"💰 Сума: <b>{active[10]} грн</b>\n\n"
            )

        # 🧾 Історія
        response += f"🧾 <b>Історія замовлень для {name}:</b>\n\n"

        for i, order in enumerate(last_orders[:5], start=1):
            recognized = (
                order[14]
                if len(order) > 14 and order[14]
                else "Буде уточнено адміністратором"
            )

            response += (
                f"{i}️⃣ <b>{order[12]}</b>\n"
                f"📅 {order[0]}\n"
                f"👚 {order[4]}\n"
                f"🔎 {recognized}\n"
                f"📦 {order[8]}\n\n"
            )

        await message.answer(response, parse_mode="HTML")

    except Exception as e:
        print(f"❌ Помилка при отриманні історії: {e}")
        await message.answer("❗ Помилка при завантаженні замовлень.")
        logging.error("Помилка при отриманні історії", exc_info=True)


def get_or_create_column(worksheet, headers, column_name):
    """
    Повертає 0-based індекс колонки за назвою. Якщо такої колонки в таблиці
    ще нема — сама дописує заголовок і повертає індекс нового стовпця,
    замість того щоб впасти з ValueError і мовчки нічого не робити.
    """
    if column_name in headers:
        return headers.index(column_name)
    new_index = len(headers)
    worksheet.update_cell(1, new_index + 1, column_name)
    headers.append(column_name)
    return new_index


async def notify_completed_orders():
    try:
        orders = sheet.get_all_values()

        if not orders or len(orders) < 2:
            return

        headers = orders[0]
        rows = orders[1:]

        headers_before_creation = list(headers)

        phone_index = get_or_create_column(sheet, headers, "Телефон")
        status_index = get_or_create_column(sheet, headers, "Статус")
        last_notified_status_index = get_or_create_column(sheet, headers, "Останній повідомлений статус")
        order_number_index = get_or_create_column(sheet, headers, "Номер замовлення")
        date_index = get_or_create_column(sheet, headers, "Дата")

        if "Останній повідомлений статус" not in headers_before_creation:
            # Колонку щойно створили — заповнюємо її поточними статусами заднім числом,
            # щоб не розіслати клієнтам "нове" повідомлення по всіх старих замовленнях одразу.
            # Стежити за реальними змінами статусу почнемо з наступного циклу (через 5 хв).
            for idx, row in enumerate(rows, start=2):
                if len(row) > status_index and row[status_index].strip():
                    sheet.update_cell(idx, last_notified_status_index + 1, row[status_index].strip())
            return

        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()

        for i, row in enumerate(rows, start=2):
            if len(row) <= status_index:
                continue

            status = row[status_index].strip()

            if not status:
                continue

            last_notified_status = ""
            if len(row) > last_notified_status_index:
                last_notified_status = row[last_notified_status_index].strip()

            # Якщо цей статус вже відправляли — пропускаємо
            if status == last_notified_status:
                continue

            phone = normalize_phone(row[phone_index]) if len(row) > phone_index else ""
            order_number = (
                row[order_number_index] if len(row) > order_number_index else "—"
            )
            date = row[date_index] if len(row) > date_index else "—"

            if not phone:
                continue

            telegram_id = None

            for client in clients:
                client_phone = normalize_phone(client.get("phone", ""))

                if client_phone[-10:] == phone[-10:]:
                    telegram_id = client.get("telegram_id")
                    break

            if not telegram_id:
                print(f"⚠️ Не знайдено Telegram ID для {phone}")
                continue

            message_text = STATUS_MESSAGES.get(
                status, f"📦 Статус вашого замовлення оновлено: {status}"
            )

            try:
                await bot.send_message(
                    chat_id=int(telegram_id),
                    text=(
                        f"📦 <b>Оновлення замовлення</b>\n\n"
                        f"🆔 Номер: <b>{order_number}</b>\n"
                        f"📅 Дата: {date}\n\n"
                        f"{message_text}"
                    ),
                )

                # Записуємо, що цей статус уже відправлено
                sheet.update_cell(i, last_notified_status_index + 1, status)

                print(f"🔔 Клієнту {phone} надіслано статус: {status}")

            except Exception as e:
                print(f"❌ Помилка відправки статусу для {phone}: {e}")
                logging.error("Помилка відправки статусу клієнту", exc_info=True)

    except Exception as e:
        print(f"❌ Помилка при перевірці статусів: {e}")
        logging.error("Помилка при перевірці статусів", exc_info=True)


@dp.message(F.text == "👤 Особистий кабінет", any_state)
async def personal_account(message: Message, state: FSMContext):
    await state.clear()

    telegram_id = message.from_user.id
    client = get_client_by_telegram_id(telegram_id)

    if not client:
        await message.answer(
            "👤 <b>Особистий кабінет</b>\n\n"
            "Поки що я не знайшов ваш профіль у базі.\n\n"
            "Щоб створити профіль, скористайтесь кнопкою <b>🧺 Здати речі</b> "
            "або оформіть перше замовлення.",
            reply_markup=main_menu,
        )
        return

    name = client.get("name", message.from_user.full_name or "Клієнт")
    apartment = client.get("apartment", "—")
    phone = normalize_phone(client.get("phone", ""))
    subscription = client.get("subscription", "Немає")
    subscription_expires = client.get("subscription_expires", "")

    orders = sheet.get_all_values()[1:]

    user_orders = []
    active_orders = []
    total_sum = 0

    for row in orders:
        if len(row) <= 2:
            continue

        order_phone = normalize_phone(row[2])

        if phone and order_phone[-10:] == phone[-10:]:
            user_orders.append(row)

            status = row[8] if len(row) > 8 else ""
            amount_text = row[10] if len(row) > 10 else "0"

            if "Скасовано" not in status:
                try:
                    total_sum += float(str(amount_text).replace(",", ".") or 0)
                except Exception:
                    pass

            if status and "Виконано" not in status and "Скасовано" not in status:
                active_orders.append(row)

    subscription_text = "Немає"

    if subscription == "Так":
        if subscription_expires:
            subscription_text = f"Активна до {subscription_expires}"
        else:
            subscription_text = "Активна"

    text = (
        "👤 <b>Особистий кабінет</b>\n\n"
        f"👋 Ім’я: <b>{name}</b>\n"
        f"🏢 Квартира: <b>{apartment}</b>\n"
        f"📞 Телефон: <b>{phone or '—'}</b>\n"
        f"💳 Підписка: <b>{subscription_text}</b>\n\n"
        f"📦 Активних замовлень: <b>{len(active_orders)}</b>\n"
        f"🧾 Усього замовлень: <b>{len(user_orders)}</b>\n"
        f"💰 Загальна сума: <b>{int(total_sum)} грн</b>\n\n"
        "Нижче ви можете переглянути свої замовлення або повернутись у головне меню."
    )

    await message.answer(text, reply_markup=account_kb)


@dp.message(F.text == "📢 Новини")
async def start_news(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("📝 Введіть текст новини для розсилки або '🔙 Назад'.")
    await state.set_state(News.waiting_text)


@dp.message(News.waiting_text)
async def send_news(message: Message, state: FSMContext):
    text = message.text.strip()
    if text in ["🔙", "/cancel"]:
        await message.answer(
            "↩️ Ви повернулись до адмін-панелі.", reply_markup=admin_kb
        )
        await state.clear()
        return

    try:
        client_sheet = client_gsheets.open("Pralnya").worksheet("Clients")
        clients = client_sheet.get_all_records()
        count = 0

        for client in clients:
            telegram_id = client.get("telegram_id")
            if telegram_id:
                try:
                    await bot.send_message(
                        int(telegram_id), f"📢 <b>Новина:</b>\n\n{text}"
                    )
                    count += 1
                except Exception as e:
                    print(f"❌ Не вдалося надіслати {telegram_id}: {e}")
                    logging.error("Не вдалося надіслати", exc_info=True)

        # Сохраняем в лист "News"
        try:
            news_sheet = client_gsheets.open("Pralnya").worksheet("News")
        except WorksheetNotFound:
            news_sheet = client_gsheets.open("Pralnya").add_worksheet(
                title="News", rows="100", cols="3"
            )
            news_sheet.append_row(["Дата", "Текст новини", "Кількість користувачів"])

        news_sheet.append_row([datetime.now().strftime("%d.%m.%Y %H:%M"), text, count])

        await message.answer(
            f"✅ Новина надіслана {count} користувачам.", reply_markup=admin_kb
        )
    except Exception as e:
        print(f"❌ Помилка при розсилці новини: {e}")
        logging.error("Помилка при розсилці новини", exc_info=True)
        await message.answer("❗ Помилка при надсиланні новини.", reply_markup=admin_kb)

    await state.clear()


@dp.message(F.text)
async def chat_with_gemini(message: Message, state: FSMContext):
    # Перевіряємо, чи не знаходиться клієнт зараз у процесі оформлення замовлення
    current_state = await state.get_state()
    if current_state is not None:
        return

    # Ігноруємо команди, щоб не ламати логіку (наприклад /start)
    if message.text.startswith("/"):
        return

    # Захист: кнопки меню не відправляємо в Gemini
    if message.text in MENU_BUTTONS:
        await message.answer(
            "Будь ласка, скористайтесь кнопками меню 👇",
            reply_markup=main_menu,
        )
        return

    try:
        # Показуємо статус "друкує...", поки ШІ думає
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        answer = await generate_gemini_response(message.text)

        if answer:
            await message.answer(answer)
        else:
            await message.answer(
                "Перепрошую, сервіс зараз тимчасово недоступний. "
                "Спробуйте ще раз трохи пізніше."
            )

    except Exception as e:
        print(f"❌ Помилка Gemini: {e}")
        logging.error("Помилка Gemini", exc_info=True)
        await message.answer(
            "Перепрошую, зараз я трохи перевантажений. Скористайтеся меню або зверніться до адміністратора."
        )


async def send_winback_messages():
    """
    Раз на добу перевіряє клієнтів, які давно не робили замовлень (30+ днів),
    і надсилає їм тепле нагадування. НЕ обіцяє конкретний відсоток знижки в тексті —
    щоб не розійтися з реальною програмою Pralnya Club (яка рахується в api.py
    від суми витрат) — натомість спрямовує клієнта в кабінет, де цифра завжди актуальна.
    Не спамить повторно — дата останнього win-back повідомлення зберігається в Clients.
    """
    try:
        orders = sheet_orders.get_all_records()
        clients = sheet_clients.get_all_records()
        headers = sheet_clients.row_values(1)

        # Остання дата замовлення для кожного telegram_id
        last_order_date = {}
        for row in orders:
            tg_id = str(row.get("telegram_id", "")).strip()
            date_str = str(row.get("Дата", "")).strip()
            if not tg_id or not date_str:
                continue
            try:
                order_date = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                continue
            if tg_id not in last_order_date or order_date > last_order_date[tg_id]:
                last_order_date[tg_id] = order_date

        # Додаємо колонку для дати win-back, якщо її ще нема
        if "Останній winback" not in headers:
            sheet_clients.update_cell(1, len(headers) + 1, "Останній winback")
            winback_col_index = len(headers) + 1
        else:
            winback_col_index = headers.index("Останній winback") + 1

        now = datetime.now()
        INACTIVE_DAYS = 30
        WINBACK_COOLDOWN_DAYS = 30

        for i, client_row in enumerate(clients, start=2):  # рядок 1 — заголовки
            tg_id = str(client_row.get("telegram_id", "")).strip()
            if not tg_id or tg_id not in last_order_date:
                continue  # ще жодного замовлення — не наш кейс для winback

            days_since_order = (now - last_order_date[tg_id]).days
            if days_since_order < INACTIVE_DAYS:
                continue

            last_winback_str = str(client_row.get("Останній winback", "")).strip()
            if last_winback_str:
                try:
                    last_winback_date = datetime.strptime(last_winback_str, "%Y-%m-%d")
                    if (now - last_winback_date).days < WINBACK_COOLDOWN_DAYS:
                        continue  # вже надсилали нещодавно
                except ValueError:
                    pass

            try:
                await bot.send_message(
                    tg_id,
                    "💙 <b>Давно вас не було!</b>\n\n"
                    "Скучили за вами. Оформіть нове замовлення прямо в застосунку — "
                    "і загляньте в «Кабінет», там завжди видно вашу актуальну знижку Pralnya Club 🧺",
                )
                sheet_clients.update_cell(i, winback_col_index, now.strftime("%Y-%m-%d"))
                await asyncio.sleep(0.2)
            except Exception as e:
                logging.error(f"Не вдалося надіслати winback {tg_id}: {e}")

    except Exception as e:
        logging.error("Помилка send_winback_messages", exc_info=True)
        print(f"❌ Помилка winback: {e}")


async def periodic_winback():
    while True:
        await send_winback_messages()
        await asyncio.sleep(86400)  # раз на добу


async def periodic_notify():
    while True:
        await notify_completed_orders()
        await asyncio.sleep(300)  # каждые 5 минут


async def run_bot_with_restart():
    """
    Polling з автоматичним самовідновленням. Раніше polling і веб-сервер
    були запущені разом через asyncio.gather() — якщо polling падав
    (обрив мережі, конфлікт getUpdates при передеплої на Render тощо),
    виняток гасив ОБИДВІ задачі, і процес завершувався цілком. Render
    міг не піднімати його одразу сам, тому й доводилось рестартити руками.
    Тепер збій у polling просто логується і повторюється — веб-сервер
    (на який ходить АптаймБот) при цьому й не помічає, що щось було.
    """
    while True:
        try:
            await dp.start_polling(bot)
        except Exception as e:
            logging.error(f"⚠️ Бот (polling) впав, перезапускаю через 5 секунд: {e}")
            logging.error(traceback.format_exc())
            await asyncio.sleep(5)


async def main():
    print("✅ Бот запущен!")
    
    # Ваши фоновые задачи
    asyncio.create_task(periodic_notify())
    asyncio.create_task(check_consultation_statuses(bot))
    asyncio.create_task(periodic_winback())
    
    # Настраиваем FastAPI-сервер uvicorn — саме він тримає порт живим для Render/АптаймБот
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app=app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)

    # Бот запускається окремою задачею з самовідновленням, а не gather() —
    # щоб його падіння не тягнуло за собою веб-сервер (і навпаки)
    asyncio.create_task(run_bot_with_restart())
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())