import uvicorn
from datetime import datetime
import traceback
import json # Добавь в самый верх файла, если еще нет
import requests

from fastapi.staticfiles import StaticFiles

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Any
import gspread
from oauth2client.service_account import ServiceAccountCredentials
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
# === Уведомление клиенту ===
TELEGRAM_TOKEN = "7779234071:AAFErwDEU8-gobibHl_M94je9nbvs5DwIS4" 
ADMIN_CHAT_ID = "987895270" 

def send_tg_message(chat_id, text):
    """Функция для отправки сообщений через Telegram API"""
    if not chat_id:
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML" # Позволяет использовать <b>жирный</b> текст и <i>курсив</i>
    }
    try:
        response = requests.post(url, json=payload)
        if not response.ok:
            print(f"⚠️ Ошибка отправки ТГ: {response.text}")
    except Exception as e:
        print(f"⚠️ Ошибка сети при отправке ТГ: {e}")



# === Уведомление клиенту ===

# --- 1. GET: Загрузка кабинета ---


# --- Подключение к Google Таблицам ---
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

CREDS = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE) 
GS_CLIENT = gspread.authorize(CREDS)

SPREADSHEET_NAME = "Pralnya" 
spreadsheet = GS_CLIENT.open(SPREADSHEET_NAME)

# Подключаем листы
sheet_clients = spreadsheet.worksheet("Clients")
sheet_orders = spreadsheet.worksheet("Лист1")
sheet_atelier = spreadsheet.worksheet("Atelier")
sheet_b2b = spreadsheet.worksheet("B2B2.0")

# --- Модели данных ---
class ClientProfile(BaseModel):
    telegram_id: Any
    first_name: Optional[str] = ""
    phone: Optional[str] = ""
    apartment: Optional[str] = ""

class OrderData(BaseModel):
    user_id: Optional[Any] = None
    telegram_id: Optional[Any] = None
    username: Optional[str] = ""
    phone: Optional[str] = ""
    name: Optional[str] = ""
    address: Optional[str] = ""
    items: Optional[Any] = ""
    service: Optional[str] = ""
    price: Optional[Any] = 0
    date: Optional[str] = ""
    comment: Optional[str] = ""

class B2BData(BaseModel):
    company: str
    phone: str
    details: Optional[str] = ""
    telegram_id: Optional[Any] = None
    name: Optional[str] = ""

class AIMessageData(BaseModel):
    message: str
    telegram_id: Optional[Any] = None
    
router = APIRouter()

# --- 1. GET: Загрузка кабинета ---
@app.get("/api/cabinet")
async def get_cabinet(user_id: int):
    try:
        user_str_id = str(user_id)
        client_data = {"name": "", "phone": "", "apartment": "", "discount": 0}
        
        # 1. Ищем данные клиента
        all_clients = sheet_clients.get_all_records()
        for row in all_clients:
            if str(row.get("telegram_id", "")) == user_str_id:
                client_data = {
                    "name": row.get("name", ""),
                    "phone": str(row.get("phone", "")),
                    "apartment": str(row.get("apartment", "")),
                    "discount": 0
                }
                break
        
        client_orders = []
        
        # 2. Собираем заказы ПРАЧЕЧНОЙ
        all_orders = sheet_orders.get_all_records()
        for row in all_orders:
            order_tg_id = str(row.get("telegram_id", "")) 
            order_phone = str(row.get("Телефон", ""))
            
            if order_tg_id == user_str_id or (client_data["phone"] and order_phone == client_data["phone"]):
                client_orders.append({
                    "id": str(row.get("Номер замовлення", "")),
                    "status": row.get("Статус", "Прийнято"),
                    "items": str(row.get("Речі", "")),
                    "date": str(row.get("Дата", "")),
                    "price": format_price(row.get("Сума", "")),
                    "type": "laundry" # Добавили тип, чтобы JS понимал, что это прачечная
                })
                
        # 3. Собираем заявки АТЕЛЬЕ
        all_atelier = sheet_atelier.get_all_records()
        for row in all_atelier:
            # Ищем по колонке "Telegram ID", как ты назвал ее в листе Atelier
            order_tg_id = str(row.get("Telegram ID", ""))
            
            if order_tg_id == user_str_id:
                client_orders.append({
                    "id": str(row.get("Номер заявки", "")),
                    "status": row.get("Статус", "⏳ Очікує огляду"),
                    "items": str(row.get("Опис", "")),
                    "date": str(row.get("Дата", "")),
                    "price": "Після огляду",
                    "type": "atelier" # Эта метка поможет нам на фронтенде вывести иконку ножниц
                })
        
        return {"client": client_data, "orders": client_orders}
        
    except Exception as e:
        print(f"❌ Ошибка при получении данных: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 2. POST: Сохранение профиля ---
@app.post("/api/cabinet")
async def update_cabinet(profile: ClientProfile):
    try:
        user_str_id = str(profile.telegram_id)
        all_clients = sheet_clients.get_all_records()
        
        row_index = None
        for i, row in enumerate(all_clients, start=2):  
            if str(row.get("telegram_id", "")) == user_str_id:
                row_index = i
                break

        if row_index:
            sheet_clients.update_cell(row_index, 2, profile.first_name)
            sheet_clients.update_cell(row_index, 3, profile.phone)
            sheet_clients.update_cell(row_index, 4, profile.apartment)
        else:
            new_row = [profile.telegram_id, profile.first_name, profile.phone, profile.apartment, "", ""]
            sheet_clients.append_row(new_row)
        return {"status": "success"}
    except Exception as e:
        print(f"❌ Ошибка при сохранении профиля: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# --- 3. POST: Создание заказа (Прачечная / Ателье) ---
@app.post("/api/orders")  # Check your endpoint name (/api/order or /api/orders)
@app.post("/api/order")
@app.post("/api/order/")
async def create_order(order: OrderData):
    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")

        # === РАЗВИЛКА: ЕСЛИ ЭТО АТЕЛЬЕ ===
        if order.service == "atelier":
            order_id = f"ATL-{int(now.timestamp())}"
            item_names = []
            
            # 1. Создаем переменную для подсчета общей суммы
            total_price = 0 
            
            raw_items = order.items
            
            if isinstance(raw_items, str):
                try:
                    raw_items = json.loads(raw_items)
                except:
                    pass

            if isinstance(raw_items, list):
                for item in raw_items:
                    if hasattr(item, "dict"):
                        item = item.dict()
                        
                    if isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        quantity = int(item.get("quantity", 1) or 1)
                        
                        # 2. Достаем цену из каждого товара
                        item_price = float(item.get("price", 0))
                        
                        if name:
                            # 3. Считаем сумму: цена * количество
                            total_price += item_price * quantity
                            
                            if quantity > 1:
                                item_names.append(f"• {name} — {quantity} шт.")
                            else:
                                item_names.append(f"• {name}")
                                
            if not item_names:
                item_names.append("• Послуги ательє (деталі не розпізнано)")

            items_text = "\n".join(item_names)
            
            # 4. Форматируем сумму, чтобы было красиво (отсекаем нули)
            formatted_price = f"{int(total_price)} ₴"

            # 5. Собираем строку для таблицы
           # 5. Собираем строку для таблицы (с твоим новым порядком колонок)
            new_row = [
                date_str,                 # 1-я: Дата
                order.name,               # 2-я: Имя
                str(order.telegram_id),   # 3-я: Telegram ID
                order.username or "",     # 4-я: Username
                items_text,               # 5-я: Послуги (Названия)
                "",                       # 6-я: Фото
                "⏳ Очікує огляду",        # 7-я: Статус
                "",                       # 8-я: Комментарий/Колонка
                "",                       # 9-я: Останній повідомлений статус
                order_id,                 # 10-я: Номер заявки
                formatted_price           # 11-я: СУМА
            ]

            sheet_atelier.append_row(new_row)
            print(f"✅ Заявка в Ательє {order_id} успішно записана! Сума: {formatted_price}")

            # === НОВИЙ БЛОК: УВЕДОМЛЕНИЯ В TELEGRAM (АТЕЛЬЕ) ===
            
            # 1. Сообщение для клиента
            client_text = (
                f"✅ <b>Заявку успішно відправлено!</b>\n\n"
                f"<b>Номер:</b> {order_id}\n"
                f"<b>Послуги:</b>\n{items_text}\n"
                f"<b>Орієнтовна сума:</b> {formatted_price}\n\n"
                f"Майстер зв'яжеться з вами найближчим часом! ✂️"
            )
            # Отправляем клиенту по его telegram_id
            send_tg_message(order.telegram_id, client_text)
            
            # 2. Сообщение для администратора (Тебе и Светлане Николаевне)
            admin_text = (
                f"✂️ <b>НОВА ЗАЯВКА (Ательє)</b> ✂️\n\n"
                f"<b>Номер:</b> {order_id}\n"
                f"<b>Клієнт:</b> {order.name}\n"
                f"<b>Телефон:</b> {order.phone}\n"
                f"<b>Адреса:</b> {order.address}\n"
                f"<b>Послуги:</b>\n{items_text}\n"
                f"<b>Орієнтовна сума:</b> {formatted_price}\n"
                f"<b>Коментар:</b> {order.comment or 'Немає'}"
            )
            # Отправляем в админский чат
            send_tg_message(ADMIN_CHAT_ID, admin_text)
            
            # ====================================================

            return {
                "status": "success",
                "order_id": order_id
            }
 # === ИНАЧЕ: ЭТО СТАНДАРТНЫЙ ЗАКАЗ (ПРАЧЕЧНАЯ) ===
        else:
            # 1. Красиво форматируем вещи с учетом количества
            items_str = ""
            total_price = float(order.price or 0)
            
            if isinstance(order.items, list):
                item_names = []
                calc_price = 0
                for item in order.items:
                    if isinstance(item, dict):
                        name = item.get("name", "Річ")
                        price = float(item.get("price", 0))
                        qty = int(item.get("quantity", 1))
                        
                        if qty > 1:
                            item_names.append(f"{name} ({qty} шт)")
                        else:
                            item_names.append(name)
                            
                        calc_price += price * qty
                
                items_str = ", ".join(item_names)
                if total_price == 0:
                    total_price = calc_price
            else:
                items_str = str(order.items or "Послуги пральні")

            # 2. Генерируем ID для прачечной
            order_id = f"ORD-{int(now.timestamp())}"
            
            # 3. Собираем массив строк для Прачечной
            new_row = [
                now.strftime("%Y-%m-%d"),
                order.name,
                order.phone,
                order.address,
                items_str,
                order.comment,
                "",
                "",
                "Прийнято",
                "",
                total_price,
                "",
                order_id,
                "",
                "",
                str(order.telegram_id)
            ]
            
            sheet_orders.append_row(new_row)
            print(f"✅ Заказ {order_id} ({items_str}) успішно записано!")
            
            # === НОВИЙ БЛОК: УВЕДОМЛЕНИЯ В TELEGRAM (ПРАЧЕЧНАЯ) ===
            
            # 1. Сообщение для клиента
            client_text = (
                f"🫧 <b>Ваше замовлення прийнято!</b>\n\n"
                f"<b>Номер:</b> {order_id}\n"
                f"<b>Речі:</b> {items_str}\n"
                f"<b>Сума:</b> {int(total_price)} ₴\n\n"
                f"Дякуємо, що обрали PralnyaVdoma! 💙"
            )
            send_tg_message(order.telegram_id, client_text)
            
            # 2. Сообщение для адміністратора 
            admin_text = (
                f"🫧 <b>НОВЕ ЗАМОВЛЕННЯ (Пральня)</b> 🫧\n\n"
                f"<b>Номер:</b> {order_id}\n"
                f"<b>Клієнт:</b> {order.name}\n"
                f"<b>Телефон:</b> {order.phone}\n"
                f"<b>Квартира:</b> {order.address}\n"
                f"<b>Речі:</b> {items_str}\n"
                f"<b>Сума:</b> {int(total_price)} ₴\n"
                f"<b>Коментар:</b> {order.comment or 'Немає'}"
            )
            send_tg_message(ADMIN_CHAT_ID, admin_text)
            
            # ====================================================

            return {"status": "success", "order_id": order_id}

    except Exception as e:
        print("❌ Ошибка при создании заказа:")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    
# --- 4. POST: Заявка B2B (Співпраця) ---
@app.post("/api/b2b")
async def create_b2b_request(data: B2BData):
    try:
        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d %H:%M")

        new_row = [
            date_str,
            data.company,
            data.phone,
            data.details or "",
            str(data.telegram_id or ""),
            "Нова заявка"
        ]

        sheet_b2b.append_row(new_row)
        print(f"✅ B2B заявка від {data.company} успішно збережена!")

        # 1. Повідомлення клієнту в Телеграм
        client_text = (
            f"🤝 <b>Дякуємо за запит на співпрацю!</b>\n\n"
            f"<b>Компанія:</b> {data.company}\n"
            f"Наш менеджер зв'яжеться з вами найближчим часом для обговорення індивідуальних умов."
        )
        if data.telegram_id:
            send_tg_message(data.telegram_id, client_text)

        # 2. Повідомлення адміністратору (в адмінський чат)
        admin_text = (
            f"💼 <b>НОВА B2B ЗАЯВКА (Співпраця)</b> 💼\n\n"
            f"<b>Компанія:</b> {data.company}\n"
            f"<b>Телефон:</b> {data.phone}\n"
            f"<b>Деталі:</b> {data.details or 'Не вказано'}\n"
            f"<b>Telegram ID:</b> {data.telegram_id or 'Невідомо'}"
        )
        send_tg_message(ADMIN_CHAT_ID, admin_text)

        return {"status": "success"}

    except Exception as e:
        print(f"❌ Помилка створення B2B заявки: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def format_price(val):
    if not val:
        return "0 грн"
    
    # 1. Очищаем строку от неразрывных пробелов и меняем запятые на точки
    clean_str = str(val).replace('\xa0', '').replace(' ', '').strip()
    clean_str = clean_str.replace(',', '.')
    clean_str = clean_str.replace('грн', '').replace('₴', '').strip()
    
    try:
        num = float(clean_str)
        
        # 2. Если сумма гигантская и круглая (например, 35000.0), 
        # значит она пришла в копейках. Переводим в гривны:
        if num >= 10000 and num % 100 == 0:
            num = num / 100
            
        # 3. САМОЕ ВАЖНОЕ: Оборачиваем в int(), чтобы отсечь нули после точки.
        # Теперь вместо "350.00" мы отдаем строго "350 грн".
        # JS на фронтенде больше не сможет "склеить" нули!
        return f"{int(num)} грн"
    
    except ValueError:
        # Если пришел совсем странный текст, который нельзя превратить в число
        return str(val) if "грн" in str(val) else f"{val} грн"

# --- 5. POST: AI Чат Консультант ---
@app.post("/api/ai")
async def ai_chat(data: AIMessageData):
    try:
        user_msg = data.message.lower()

        # Системные знания о PralnyaVdoma (Промпт контекста)
        # Сюда мы в будущем подключаем вызов API Gemini / OpenAI
        
        # Временный умный ответчик на основе ключевых слов (пока не вставили ключ API):
        if "цін" in user_msg or "скільки" in user_msg or "кошт" in user_msg:
            reply = "💡 <b>Наші базові тарифи:</b>\n\n• Прання сорочки / футболки — 80 ₴\n• Прання штанів / джинсів — 120 ₴\n• Чистка зимової куртки — від 350 ₴\n\nПовний каталог послуг ви можете переглянути у вкладці <b>'Замовити'</b>!"
        elif "атель" in user_msg or "пошити" in user_msg or "ремонт" in user_msg:
            reply = "✂️ <b>Послуги Ательє:</b>\n\nМи виконуємо ремонт одягу, вкорочування штанів, заміну блискавок та підгонку по фігурі.\n\nЗавітайте у вкладку <b>'Ательє'</b>, щоб залишити заявку на огляд майстра!"
        elif "плям" in user_msg or "вино" in user_msg or "кава" in user_msg:
            reply = "🧪 <b>Порада від експерта:</b>\n\nГоловне правило — не розтирайте пляму серветкою і не замочуйте окропом! Промокніть сухою серветкою та якомога швидше передайте річ нам на аквачистку. Ми приберемо її без шкоди для тканини."
        else:
            reply = f"Я зрозумів ваше запитання: <i>'{data.message}'</i>.\n\nЯк ваші помічники з <b>PralnyaVdoma</b>, ми з радістю допоможемо! Для точного розрахунку або оформлення послуги просто скористайтесь нашими меню або зверніться до менеджера."

        return {"status": "success", "reply": reply}

    except Exception as e:
        print(f"❌ Помилка AI: {e}")
        raise HTTPException(status_code=500, detail=str(e))

import os

if __name__ == "__main__":
    # Render сам выдает нужный порт
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)