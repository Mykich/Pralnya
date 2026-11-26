"""
Наведення порядку в CRM-таблиці «Pralnya» (2026-11-26).

Запуск (з папки репозиторію Pralnya, де лежить JSON сервіс-акаунта бота):

    pip install gspread
    python tools/crm_cleanup_2026_11_26.py                 # пробний прогін: лише показує зміни
    python tools/crm_cleanup_2026_11_26.py --apply         # вносить зміни

Ключ сервіс-акаунта за замовчуванням: pralnya-feee1a9984bf.json (той самий, що в бота).
Інший шлях: --creds шлях/до/файлу.json

Перед --apply зробіть копію таблиці: Файл → Створити копію.

Що робить скрипт (усе повторюване: другий запуск нічого не зламає):
 1. Новий прихований лист «_Розрахунок»: нормалізує дату, суму, telegram_id і статус
    кожного замовлення з «Лист1» (старі рядки мають різні формати) і рахує підсумки по клієнтах.
 2. Новий лист «📈 Клієнти»: замовлення, витрати без скасованих, рівень Pralnya Club,
    дні без замовлення. Рахується автоматично і для нових клієнтів.
    Формули прибираються з Clients H–J: бот дописує рядки в Clients, і для нових
    клієнтів ці формули були порожні (а J3:J7 посилалися на рядок 2).
 3. «📊 Дашборд»: формули через «_Розрахунок» (будь-який формат дати, без скасованих),
    статус «Прийнято» прибрано, топ-5 клієнтів з іменами за витратами.
 4. «📋 Пайплайн»: статус «Прийнято» прибрано.
 5. «👤 Картка клієнта»: кількість і сума замовлень без скасованих.
 6. Випадаючі списки статусів (як у боті та Mini App):
    Лист1 I, Atelier G, B2B_General J. Старий статус ательє «⏳ Очікує огляду» → «Нова».
 7. B2B_General L1: заголовок «Останній повідомлений статус».
 8. Ховає колонки підписки: Clients E–F, Лист1 H (дані лишаються, на майбутнє).
 9. Видаляє тестового клієнта 123456789 (Clients, Лист1, Atelier).
10. Видаляє порожні/застарілі листи: Лист10, Consultations, 📖 Знахідки.

Бот і API не змінюються: вони пишуть у ті самі колонки A–S, нічого всередину не вставляється.
"""

import argparse
import re
import sys

import gspread

SPREADSHEET_ID = "1O-qSkFX9hDwRLwbHlKLtmr5ybDGeAmCPuj0nSrJnTlo"
DEFAULT_CREDS = "pralnya-feee1a9984bf.json"

ORDER_STATUSES = ["Очікує", "🧺 В роботі", "🚚 Доставляється", "✅ Виконано", "❌ Скасовано"]
ATELIER_STATUSES = ["Нова", "В роботі", "Готово", "Скасовано"]
B2B_STATUSES = ["Нова заявка", "В процесі переговорів", "Погоджено", "Відхилено"]
OLD_ATELIER_STATUS_MAP = {"⏳ Очікує огляду": "Нова"}
TEST_TELEGRAM_ID = "123456789"
SHEETS_TO_DELETE = ["Лист10", "Consultations", "📖 Знахідки"]

CALC = "_Розрахунок"
CLIENTS_REPORT = "📈 Клієнти"
C = f"'{CALC}'"
R = f"'{CLIENTS_REPORT}'"
L = "'Лист1'"

# ---------------------------------------------------------------- формули

CALC_HEADERS = [["Дата", "Ключ клієнта", "Сума", "Статус", "Активне (1/0)", "",
                 "Ключ клієнта", "Замовлень", "Витрачено", "Останнє замовлення", "",
                 "Ключ клієнта (ательє)", "Заявок ательє"]]

CALC_FORMULAS = {
    # Дата: справжня дата, «рррр-мм-дд [чч:мм]» або «дд.мм.рррр [чч:мм]» → дата
    "A2": (f'=ARRAYFORMULA(IF({L}!A2:A="",,IF(ISNUMBER({L}!A2:A),INT({L}!A2:A),'
           f'IFERROR(IF(MID({L}!A2:A,3,1)=".",DATE(MID({L}!A2:A,7,4),MID({L}!A2:A,4,2),LEFT({L}!A2:A,2)),'
           f'DATEVALUE(LEFT({L}!A2:A,10))),))))'),
    # Ключ клієнта: "tg" + telegram_id як текст (щоб число і текст збігалися)
    "B2": f'=ARRAYFORMULA(IF({L}!A2:A="",,IF(TRIM(TO_TEXT({L}!P2:P))="",,"tg"&TRIM(TO_TEXT({L}!P2:P)))))',
    # Сума: число або текст на кшталт «1 910,00» / «450 ₴» → ціле число
    "C2": (f'=ARRAYFORMULA(IF({L}!A2:A="",,IF(ISNUMBER({L}!K2:K),{L}!K2:K,'
           f'IFERROR(VALUE(REGEXREPLACE(REGEXREPLACE(TO_TEXT({L}!K2:K),"[,.][0-9]{{1,2}}\\s*$",""),"[^0-9]","")),0))))'),
    "D2": f'=ARRAYFORMULA(IF({L}!A2:A="",,{L}!I2:I))',
    # Активне = не скасоване (та сама логіка, що в api.py для Pralnya Club)
    "E2": (f'=ARRAYFORMULA(IF({L}!A2:A="",,IF(REGEXMATCH(TO_TEXT({L}!I2:I),"Скасовано")'
           f'+(LEN(TRIM(TO_TEXT({L}!G2:G)))>0),0,1)))'),
    # Підсумки по клієнту (лише активні замовлення)
    "G2": ('=IFERROR(QUERY(A2:E,"select B, sum(E), sum(C), max(A) where B is not null and E = 1 '
           "group by B label sum(E) '', sum(C) '', max(A) ''\",0),)"),
    # Заявки ательє по клієнту (без скасованих)
    "L2": ('=IFERROR(QUERY({ARRAYFORMULA(IF(TRIM(TO_TEXT(Atelier!C2:C))="",,"tg"&TRIM(TO_TEXT(Atelier!C2:C)))),'
           'Atelier!G2:G},"select Col1, count(Col1) where Col1 is not null and (Col2 is null or Col2 <> \'Скасовано\') '
           "group by Col1 label count(Col1) ''\",0),)"),
}

REPORT_HEADERS = [["telegram_id", "Ім'я", "Телефон", "Замовлень (пральня)", "Заявок ательє",
                   "Витрачено, ₴ (без скасованих)", "Pralnya Club", "Останнє замовлення",
                   "Днів без замовлення"]]

REPORT_FORMULAS = {
    "A2": '=ARRAYFORMULA(IF(TRIM(TO_TEXT(Clients!A2:A))="",,TRIM(TO_TEXT(Clients!A2:A))))',
    "B2": '=ARRAYFORMULA(IF(A2:A="",,Clients!B2:B))',
    "C2": '=ARRAYFORMULA(IF(A2:A="",,Clients!C2:C))',
    "D2": f'=ARRAYFORMULA(IF(A2:A="",,IFERROR(VLOOKUP("tg"&A2:A,{C}!G2:J,2,0),0)))',
    "E2": f'=ARRAYFORMULA(IF(A2:A="",,IFERROR(VLOOKUP("tg"&A2:A,{C}!L2:M,2,0),0)))',
    "F2": f'=ARRAYFORMULA(IF(A2:A="",,IFERROR(VLOOKUP("tg"&A2:A,{C}!G2:J,3,0),0)))',
    # Пороги як в api.py get_loyalty_discount: 2000 ₴ → 5%, 5000 ₴ → 10%
    "G2": '=ARRAYFORMULA(IF(A2:A="",,IF(F2:F>=5000,"10%",IF(F2:F>=2000,"5%","—"))))',
    "H2": f'=ARRAYFORMULA(IF(A2:A="",,IFERROR(VLOOKUP("tg"&A2:A,{C}!G2:J,4,0),)))',
    "I2": '=ARRAYFORMULA(IF(A2:A="",,IF(H2:H="","—",TODAY()-H2:H)))',
}


def month_sum(k, absolute=False):
    """Сума активних замовлень за місяць, k місяців тому (0 = поточний)."""
    d = "$" if absolute else ""
    rng = lambda col: f"{C}!{d}{col}{d}2:{d}{col}"
    return (f'=SUMIFS({rng("C")},{rng("A")},">="&(EOMONTH(TODAY(),{-(k + 1)})+1),'
            f'{rng("A")},"<="&EOMONTH(TODAY(),{-k}),{rng("E")},1)')


DASHBOARD = {
    "A5": f"=SUM({C}!E2:E)",
    "C5": f"=COUNTIFS({C}!A2:A,TODAY(),{C}!E2:E,1)",
    "E5": month_sum(0),
    "G5": f"=IFERROR(ROUND(SUMIFS({C}!C2:C,{C}!E2:E,1)/SUM({C}!E2:E),0),0)",
    # Статуси замовлень: без «Прийнято»
    **{f"A{10 + i}": s for i, s in enumerate(ORDER_STATUSES)},
    **{f"B{10 + i}": f"=COUNTIF({L}!I2:I2000,A{10 + i})" for i in range(len(ORDER_STATUSES))},
    "A15": "", "B15": "",
    # Топ-5 клієнтів за витратами (ім'я + сума), одна формула на D10:E14
    "D10": (f'=IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({{{R}!B2:B,{R}!F2:F}},{R}!F2:F>0),2,FALSE),5,2),"—")'),
    "E10": "", "D11": "", "E11": "", "D12": "", "E12": "", "D13": "", "E13": "", "D14": "", "E14": "",
    "B21": f'=COUNTIF({L}!I2:I2000,"Очікує")',
    **{f"B{25 + i}": month_sum(5 - i, absolute=True) for i in range(6)},
}

PIPELINE = {
    **{f"E{6 + i}": s for i, s in enumerate(ORDER_STATUSES)},
    **{f"F{6 + i}": f"=COUNTIF({L}!I2:I2000,E{6 + i})" for i in range(len(ORDER_STATUSES))},
    "E11": "", "F11": "",
    "A14": "Статуси збігаються з ботом і Mini App (оновлено 2026-11-26). Змінюйте статус лише з випадаючого списку.",
}

CARD = {
    "A12": "Замовлень (пральня, без скасованих)",
    "B12": f'=IF($B$5="","",IFERROR(VLOOKUP("tg"&$B$5,{C}!G2:J,2,0),0))',
    "A13": "Всього витрачено (без скасованих)",
    "B13": f'=IF($B$5="","",IFERROR(VLOOKUP("tg"&$B$5,{C}!G2:J,3,0),0))',
    "B14": f'=IF($B$5="","",IFERROR(VLOOKUP("tg"&$B$5,{C}!L2:M,2,0),0))',
}


# ---------------------------------------------------------------- допоміжне

def col_index(letter):
    n = 0
    for ch in letter:
        n = n * 26 + ord(ch.upper()) - 64
    return n - 1


def grid(sheet_id, a1):
    """'I2:I2000' / 'E:F' → GridRange."""
    m = re.fullmatch(r"([A-Z]+)(\d*)(?::([A-Z]+)(\d*))?", a1)
    c1, r1, c2, r2 = m.group(1), m.group(2), m.group(3) or m.group(1), m.group(4)
    g = {"sheetId": sheet_id, "startColumnIndex": col_index(c1), "endColumnIndex": col_index(c2) + 1}
    if r1:
        g["startRowIndex"] = int(r1) - 1
    if r2 or r1:
        g["endRowIndex"] = int(r2 or r1)
    return g


def validation_request(sheet_id, a1, values):
    return {"setDataValidation": {
        "range": grid(sheet_id, a1),
        "rule": {
            "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
            "strict": True,
            "showCustomUi": True,
        },
    }}


def hide_request(sheet_id, a1):
    g = grid(sheet_id, a1)
    return {"updateDimensionProperties": {
        "range": {"sheetId": sheet_id, "dimension": "COLUMNS",
                  "startIndex": g["startColumnIndex"], "endIndex": g["endColumnIndex"]},
        "properties": {"hiddenByUser": True},
        "fields": "hiddenByUser",
    }}


def date_format_request(sheet_id, a1):
    return {"repeatCell": {
        "range": grid(sheet_id, a1),
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
        "fields": "userEnteredFormat.numberFormat",
    }}


class Plan:
    def __init__(self, ss, apply):
        self.ss = ss
        self.apply = apply
        self.requests = []          # структурні зміни (batch_update)
        self.cells = []             # (worksheet, a1, value)

    def note(self, text):
        print(text)

    def set_cells(self, ws, mapping, title=None):
        print(f"\n== {title or ws.title}")
        current = {}
        if ws is not None:
            # одне читання на лист (ліміт Google ~60 читань на хвилину)
            block = ws.get("A1:Z60", value_render_option="FORMULA")
            for a1 in mapping:
                m = re.fullmatch(r"([A-Z]+)(\d+)", a1)
                r, c = int(m.group(2)) - 1, col_index(m.group(1))
                current[a1] = block[r][c] if r < len(block) and c < len(block[r]) else None
        for a1, new in mapping.items():
            old = current.get(a1)
            if (old or "") == (new or ""):
                continue
            print(f"  {a1}: {short(old)}  →  {short(new)}")
            self.cells.append((ws.title if ws is not None else title, a1, new))


def short(v, n=110):
    s = "" if v is None else str(v)
    s = s.replace("\n", " ")
    return "(пусто)" if s == "" else (s if len(s) <= n else s[:n] + "…")


# ---------------------------------------------------------------- основна логіка

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="внести зміни (без нього — пробний прогін)")
    ap.add_argument("--creds", default=DEFAULT_CREDS, help="JSON-ключ сервіс-акаунта")
    args = ap.parse_args()

    gc = gspread.service_account(filename=args.creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    sheets = {ws.title: ws for ws in ss.worksheets()}
    plan = Plan(ss, args.apply)
    print("Таблиця:", ss.title, "| режим:", "ЗАПИС" if args.apply else "пробний прогін (нічого не змінюється)")

    # 1–2. Нові листи
    for title, hidden, rows, cols in [(CALC, True, 3000, 13), (CLIENTS_REPORT, False, 1000, 9)]:
        if title in sheets:
            print(f"\n== {title}: вже існує, оновлю формули")
        else:
            print(f"\n== Новий лист «{title}»" + (" (прихований)" if hidden else ""))
            if args.apply:
                ws = ss.add_worksheet(title=title, rows=rows, cols=cols)
                if hidden:
                    ss.batch_update({"requests": [{"updateSheetProperties": {
                        "properties": {"sheetId": ws.id, "hidden": True}, "fields": "hidden"}}]})
                sheets[title] = ws

    def cells_for(title, headers, formulas):
        mapping = {}
        for i, h in enumerate(headers[0]):
            mapping[f"{chr(65 + i)}1"] = h
        mapping.update(formulas)
        plan.set_cells(sheets.get(title), mapping, title=title)

    cells_for(CALC, CALC_HEADERS, CALC_FORMULAS)
    cells_for(CLIENTS_REPORT, REPORT_HEADERS, REPORT_FORMULAS)

    # Clients H–J: формули переїжджають у «📈 Клієнти»
    clients = sheets["Clients"]
    hj = clients.get("H1:J", value_render_option="FORMULA")
    filled = [(r, row) for r, row in enumerate(hj, start=1) if any(str(x).strip() for x in row)]
    if filled:
        print(f"\n== Clients: очищую H1:J{len(hj)} ({len(filled)} рядків з формулами/заголовками → «{CLIENTS_REPORT}»)")

    # 3–5. Дашборд, Пайплайн, Картка
    plan.set_cells(sheets["📊 Дашборд"], DASHBOARD)
    plan.set_cells(sheets["📋 Пайплайн"], PIPELINE)
    plan.set_cells(sheets["👤 Картка клієнта"], CARD)

    # 6. Старі статуси ательє
    atelier = sheets["Atelier"]
    at_rows = atelier.get_all_values()
    fixes = {}
    for r, row in enumerate(at_rows[1:], start=2):
        for col, idx in (("G", 6), ("I", 8)):
            v = row[idx] if len(row) > idx else ""
            if v in OLD_ATELIER_STATUS_MAP:
                fixes[f"{col}{r}"] = OLD_ATELIER_STATUS_MAP[v]
    if fixes:
        plan.set_cells(atelier, fixes, title="Atelier (старі статуси)")

    # 7. B2B L1
    plan.set_cells(sheets["B2B_General"], {"L1": "Останній повідомлений статус"})

    # 6. Випадаючі списки
    print("\n== Випадаючі списки статусів")
    for title, a1, values in [("Лист1", "I2:I2000", ORDER_STATUSES),
                              ("Atelier", "G2:G1000", ATELIER_STATUSES),
                              ("B2B_General", "J2:J1000", B2B_STATUSES)]:
        print(f"  {title}!{a1}: {', '.join(values)}")
        plan.requests.append(validation_request(sheets[title].id, a1, values))

    # 8. Приховати колонки підписки
    print("\n== Приховати колонки підписки: Clients E:F, Лист1 H")
    plan.requests.append(hide_request(clients.id, "E:F"))
    plan.requests.append(hide_request(sheets["Лист1"].id, "H:H"))

    # 9. Тестовий клієнт 123456789
    to_delete = []   # (worksheet, row_number, preview)
    for title, idx in (("Clients", 0), ("Лист1", 15), ("Atelier", 2)):
        rows = sheets[title].get_all_values()
        for r, row in enumerate(rows[1:], start=2):
            if len(row) > idx and str(row[idx]).strip() == TEST_TELEGRAM_ID:
                to_delete.append((sheets[title], r, " | ".join(x for x in row[:6] if x)))
    print(f"\n== Видалити рядки тестового клієнта {TEST_TELEGRAM_ID}: {len(to_delete)}")
    for ws, r, preview in to_delete:
        print(f"  {ws.title} рядок {r}: {short(preview, 90)}")

    # 10. Порожні/застарілі листи
    del_sheets = [t for t in SHEETS_TO_DELETE if t in sheets]
    print(f"\n== Видалити листи: {', '.join(del_sheets) or 'немає'}")
    for t in del_sheets:
        vals = sheets[t].get_all_values()
        print(f"  {t}: {sum(1 for row in vals if any(x.strip() for x in row))} непорожніх рядків")

    if not args.apply:
        print("\nПробний прогін завершено. Якщо все виглядає правильно: зробіть копію таблиці і запустіть з --apply.")
        return

    # ---------------- запис
    print("\nЗаписую…")
    if filled:
        clients.batch_clear([f"H1:J{len(hj)}"])
    by_sheet = {}
    for title, a1, value in plan.cells:
        by_sheet.setdefault(title, []).append({"range": a1, "values": [[value]]})
    for title, data in by_sheet.items():
        sheets[title].batch_update(data, value_input_option="USER_ENTERED")
    plan.requests.append(date_format_request(sheets[CALC].id, "A2:A3000"))
    plan.requests.append(date_format_request(sheets[CALC].id, "J2:J3000"))
    plan.requests.append(date_format_request(sheets[CLIENTS_REPORT].id, "H2:H1000"))
    plan.requests.append({"repeatCell": {
        "range": grid(sheets[CLIENTS_REPORT].id, "A1:I1"),
        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
        "fields": "userEnteredFormat.textFormat.bold"}})
    plan.requests.append({"updateSheetProperties": {
        "properties": {"sheetId": sheets[CLIENTS_REPORT].id, "gridProperties": {"frozenRowCount": 1}},
        "fields": "gridProperties.frozenRowCount"}})
    ss.batch_update({"requests": plan.requests})
    # рядки видаляємо знизу вгору, щоб номери не зсувалися
    for ws, r, _ in sorted(to_delete, key=lambda x: (x[0].title, -x[1])):
        ws.delete_rows(r)
    for t in del_sheets:
        ss.del_worksheet(sheets[t])
    print("Готово. Перевірте «📊 Дашборд», «📈 Клієнти» і «📋 Пайплайн».")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        sys.exit(f"Не знайдено файл ключа: {e.filename}. Запустіть з папки бота або вкажіть --creds.")
