# ARCHITECTURE — Пральня Вдома

_Обновлено: 2026-11-25. Составлено по коду веток `main`; настройки Render не проверялись._

## Схема

```
Клиент ──► Сайт (GitHub Pages, pralnyavdoma) ──ссылки t.me/CleanHomeKyivBot?start=order|atelier|b2b──┐
                                                                                                      ▼
Клиент ──► Telegram-бот (Render, Pralnya/PralnyaVdoma.py, aiogram 3 + polling) ──gspread──► Google Sheet «Pralnya»
             │  ИИ: Gemini 2.5 Flash                                                           ▲
             │  фоновые задачи: статусы (5 мин), ателье/B2B статусы, winback (24 ч)            │
             └─ FastAPI «/» только для пинга аптайм-ботом                                       │
                                                                                               │
Клиент ──► Mini App (GitHub Pages, mini/frontend) ──fetch──► API (Render, mini/api.py, FastAPI) ─┘
                                                              ИИ: OpenAI gpt-3.5-turbo
                                                              уведомления клиенту и админу через Bot API
```

## Компоненты

### Бот — `Mykich/Pralnya`
- Один файл `PralnyaVdoma.py` (~3 900 строк): меню, FSM-сценарии (MemoryStorage, состояние теряется при рестарте), админка (`ADMIN_IDS` в коде), рассылки, новости.
- Цены: словарь `PRICE_LIST` + `ITEM_ALIASES`, тексты прайса захардкожены в хендлерах.
- Таблица: сервис-аккаунт из файла `pralnya-feee1a9984bf.json` (в `.gitignore`, в репозиторий не попадает), открывает таблицу по имени «Pralnya».
- Переменные окружения: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`, `PORT`.
- `watcher.py` (локальный перезапуск), `check.py` (список моделей Gemini) — вспомогательные.
- `bot_errors.log` закоммичен в репозиторий (не должен).

### API — `Mykich/mini/api.py`
- Эндпоинты: `GET/POST /api/cabinet`, `POST /api/order` (+ `/api/orders`, `/api/order/`), `POST /api/b2b`, `POST /api/ai`.
- Сервис-аккаунт из `credentials.json`; таблица по имени.
- Переменные окружения: `TELEGRAM_TOKEN`, `ADMIN_CHAT_ID`, `OPENAI_API_KEY`, `PORT`.
- Скидка Pralnya Club: 5% от 2 000 ₴, 10% от 5 000 ₴ трат.

### Mini App — `Mykich/mini/frontend`
- `index.html` + Tailwind CDN, `services.js` (каталог `servicesData`, используется), `data.js` (старый каталог `SERVICES`, не используется), `app.js` (логика, адрес API `mini-mrip.onrender.com`).

### Сайт — `Mykich/pralnyavdoma`
- Статический `index.html`, `style/`, `js/`, `img/`. Папка `textolite/` (PHP-редактор) лишняя.

## Google Sheet «Pralnya»

| Лист | Назначение | Кто пишет |
|---|---|---|
| Лист1 | заказы прачечной, колонки A–S (новые колонки только справа от S: бот и API пишут по позиции) (Дата … telegram_id, Оплата, Дата готовності, Рейтинг) | бот, API; Q–R вручную; S бот |
| Atelier | заявки ателье, A–K | бот, API |
| B2B_General | заявки B2B, A–L (L без заголовка) | бот, API |
| Clients | клиенты, A–G (E–F подписка скрыты) | бот, API |
| 📈 Клієнти | статистика по клиентам: заказы, траты без отменённых, уровень Club, дни без заказа | формулы (ARRAYFORMULA) |
| 🧾 Приймання | приёмка на стойке: одна строка = одна вещь (бирка PV-123-1, состояние, риск/согласие, фото, цена за вещь, квитанция, выдача) | вручную / бот (позже) |
| _Розрахунок (скрытый) | нормализация даты/суммы/telegram_id из Лист1, итоги по клиентам | формулы |
| 📊 Дашборд, 👤 Картка клієнта, 📋 Пайплайн, ✅ Завдання | отчёты и задачи | формулы / вручную |
| Config, News | приветствие, новости | бот (Config B1 не используется) |

## Источники правды (сейчас и цель)

| Данные | Сейчас | Цель |
|---|---|---|
| Цены | `PRICE_LIST` бота, `services.js`, `data.js`, промпт ИИ API, `index.html` сайта | один каталог, из которого читают все |
| Статусы | `ORDER_STATUSES` бота, словарь в `save_new_status`, строки в API, списки на «Пайплайн» | один словарь |
| Дата | бот `дд.мм.рррр`, API `рррр-мм-дд [чч:мм]` | один формат (решить) |
| Номер заказа | PV-/ORD-, AT-/ATL-, B2B- двух видов | один генератор |
