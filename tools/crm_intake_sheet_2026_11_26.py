"""
Лист «🧾 Приймання» у CRM-таблиці «Pralnya» (2026-11-26): один рядок = одна річ.

Запуск (з папки бота, де лежить JSON сервіс-акаунта):

    py tools/crm_intake_sheet_2026_11_26.py            # пробний прогін: лише показує зміни
    py tools/crm_intake_sheet_2026_11_26.py --apply    # створює/оновлює лист

Повторний запуск безпечний: дані не чіпає, лише заголовки, списки і підсвічування.

Чому так зроблено:
- Тільки випадаючі списки, без прапорців і без ARRAYFORMULA: бот дописуватиме сюди рядки
  (append_row), а прапорці (FALSE) і формули на весь стовпець змушують Google дописувати
  нові рядки в самий низ листа.
- Бирка (PV-123-1) — звичайне значення, не формула: фізична бирка вже на речі,
  тож номер не має змінюватися, якщо хтось видалить рядок вище.
- Підсвічування:
  червоний рядок — ризик є, а згоди клієнта немає;
  помаранчеве «Фото» — є плями/ризик/пошкодження/сильний знос, а фото немає;
  жовта «Бирка» — така бирка вже є;
  червоний «Номер замовлення» — такого номера немає ні в Лист1, ні в Atelier.
"""

import argparse
import sys

import gspread

from crm_cleanup_2026_11_26 import DEFAULT_CREDS, SPREADSHEET_ID, grid, validation_request

TITLE = "🧾 Приймання"
ROWS = 2000

# (заголовок, ширина px, список значень або None, підказка в примітці заголовка)
COLUMNS = [
    ("Дата приймання", 110, None, "рррр-мм-дд. Бот ставить сам."),
    ("Номер замовлення", 130, None, "Номер з Лист1 (PV-/ORD-) або Atelier (AT-/ATL-)."),
    ("Бирка", 120, None, "Номер замовлення + порядковий номер речі: PV-123-1, PV-123-2…"),
    ("Річ", 170, None, "Наприклад: пуховик короткий, сорочка, комплект постелі."),
    ("К-сть одиниць", 70, None, "Для комплектів і пар: комплект постелі = 4 (підковдра, простирадло, 2 наволочки)."),
    ("Послуга", 110, ["Прання", "Аквачистка", "Прасування", "Ательє", "Інше"], None),
    ("Матеріал / наповнювач", 150, None, "З ярлика: склад тканини; для пуховиків — пух/синтетика."),
    ("Колір / бренд", 120, None, None),
    ("Плями", 80, ["Немає", "Є"], "Якщо «Є» — опишіть у «Дефекти / коментар» і зробіть фото."),
    ("Знос", 90, ["Немає", "Помірний", "Сильний"], "Потертості, катишки, вигорання."),
    ("Фурнітура", 120, ["Ок", "Пошкоджена", "Відсутня частина", "Немає"], "Ґудзики, блискавки, кнопки, пряжки, декор."),
    ("Ярлик", 110, ["Є", "Немає", "Нечитабельний"], "Без ярлика режим догляду підбирається на ризик клієнта."),
    ("Дефекти / коментар", 220, None, "Дірки, шви, запах, усадка, сліди попередньої чистки."),
    ("Зі слів клієнта", 180, None, "Що клієнт або кур'єр повідомили при заборі."),
    ("Вміст кишень", 110, ["Порожні", "Знайдено"], "Якщо «Знайдено» — що саме, у коментарі; повернути клієнту."),
    ("Ризик", 70, ["Немає", "Є"], "Може змінитися колір/форма, декор, клей, старі плями не виводяться повністю."),
    ("Згода клієнта", 90, ["Так", "Ні", "—"], "Обов'язково, якщо «Ризик» = «Є»."),
    ("Фото", 120, None, "Обов'язково при плямах, ризику, пошкодженнях. Посилання або ID фото з бота."),
    ("Ціна, ₴", 80, None, "Ціна за річ після огляду (погоджена з клієнтом)."),
    ("Прийняв", 100, None, "Хто проводив огляд на стійці."),
    ("Квитанція в Telegram", 120, None, "Дата відправки квитанції клієнту. Бот ставить сам."),
    ("Підтверджено в Telegram", 120, None, "Дата, коли клієнт натиснув «✅ Підтверджую»."),
    ("Підпис на папері", 100, ["Так"], "«Так», коли клієнт підписав роздруковану квитанцію."),
    ("Видано", 110, None, "Дата видачі речі клієнту (від неї рахуються 14 днів на приховані недоліки)."),
]


def letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


COL = {name: letter(i) for i, (name, *_rest) in enumerate(COLUMNS)}
LAST = letter(len(COLUMNS) - 1)


def cond_rule(sheet_id, a1, formula, rgb):
    r, g, b = rgb
    return {"addConditionalFormatRule": {"index": 0, "rule": {
        "ranges": [grid(sheet_id, a1)],
        "booleanRule": {
            "condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": formula}]},
            "format": {"backgroundColor": {"red": r, "green": g, "blue": b}},
        },
    }}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--creds", default=DEFAULT_CREDS)
    args = ap.parse_args()

    gc = gspread.service_account(filename=args.creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    sheets = {ws.title: ws for ws in ss.worksheets()}
    print("Таблиця:", ss.title, "| режим:", "ЗАПИС" if args.apply else "пробний прогін (нічого не змінюється)")

    ws = sheets.get(TITLE)
    if ws is None:
        print(f"\n== Новий лист «{TITLE}» ({ROWS} рядків, {len(COLUMNS)} колонок A–{LAST})")
        current = []
    else:
        print(f"\n== Лист «{TITLE}» вже існує: оновлю заголовки, списки і підсвічування (дані не чіпаю)")
        current = ws.row_values(1)
        if len(ws.get_all_values()) > 1:
            print(f"   у листі вже {len(ws.get_all_values()) - 1} рядків даних — вони залишаються як є")

    print("\nКолонки:")
    for i, (name, _w, values, hint) in enumerate(COLUMNS):
        old = current[i] if i < len(current) else ""
        mark = "" if old == name else (f"   (було: {old})" if old else "")
        extra = f"  [список: {', '.join(values)}]" if values else ""
        print(f"  {letter(i)}: {name}{extra}{mark}")

    print("\nПідсвічування:")
    print("  рядок червоний: Ризик = «Є», а Згода клієнта ≠ «Так»")
    print("  Фото помаранчеве: плями / ризик / пошкоджена фурнітура / сильний знос, а фото немає")
    print("  Бирка жовта: дублікат")
    print("  Номер замовлення червоний: немає в Лист1 (M) і в Atelier (J)")
    print("  Ціна: лише число ≥ 0")

    if not args.apply:
        print("\nПробний прогін завершено. Якщо все правильно: py tools/crm_intake_sheet_2026_11_26.py --apply")
        return

    if ws is None:
        ws = ss.add_worksheet(title=TITLE, rows=ROWS, cols=len(COLUMNS))
    sid = ws.id
    ws.update(range_name=f"A1:{LAST}1", values=[[c[0] for c in COLUMNS]], value_input_option="RAW")

    # прибрати старі правила підсвічування цього листа, щоб повторний запуск не дублював їх
    meta = ss.fetch_sheet_metadata({"fields": "sheets(properties(sheetId),conditionalFormats)"})
    old_rules = next((len(s.get("conditionalFormats", [])) for s in meta["sheets"]
                      if s["properties"]["sheetId"] == sid), 0)
    reqs = [{"deleteConditionalFormatRule": {"sheetId": sid, "index": 0}} for _ in range(old_rules)]

    reqs.append({"updateSheetProperties": {
        "properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 3}},
        "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}})
    reqs.append({"repeatCell": {
        "range": grid(sid, f"A1:{LAST}1"),
        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}, "wrapStrategy": "WRAP",
                                       "verticalAlignment": "MIDDLE",
                                       "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 0.98}}},
        "fields": "userEnteredFormat(textFormat,wrapStrategy,verticalAlignment,backgroundColor)"}})
    for i, (name, width, values, hint) in enumerate(COLUMNS):
        reqs.append({"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
            "properties": {"pixelSize": width}, "fields": "pixelSize"}})
        if hint:
            reqs.append({"repeatCell": {"range": grid(sid, f"{letter(i)}1"),
                                        "cell": {"note": hint}, "fields": "note"}})
        if values:
            reqs.append(validation_request(sid, f"{letter(i)}2:{letter(i)}{ROWS}", values))

    price = COL["Ціна, ₴"]
    reqs.append({"setDataValidation": {"range": grid(sid, f"{price}2:{price}{ROWS}"), "rule": {
        "condition": {"type": "NUMBER_GREATER_THAN_EQ", "values": [{"userEnteredValue": "0"}]},
        "strict": True, "inputMessage": "Ціна за річ, ₴"}}})

    c = COL
    reqs.append(cond_rule(sid, f"A2:{LAST}{ROWS}",
                          f'=AND(${c["Ризик"]}2="Є",${c["Згода клієнта"]}2<>"Так")', (0.98, 0.80, 0.80)))
    reqs.append(cond_rule(sid, f'{c["Фото"]}2:{c["Фото"]}{ROWS}',
                          f'=AND(${c["Фото"]}2="",OR(${c["Плями"]}2="Є",${c["Ризик"]}2="Є",'
                          f'${c["Фурнітура"]}2="Пошкоджена",${c["Знос"]}2="Сильний"))', (1.0, 0.85, 0.6)))
    reqs.append(cond_rule(sid, f'{c["Бирка"]}2:{c["Бирка"]}{ROWS}',
                          f'=AND(${c["Бирка"]}2<>"",COUNTIF(${c["Бирка"]}$2:${c["Бирка"]}${ROWS},${c["Бирка"]}2)>1)',
                          (1.0, 0.95, 0.6)))
    reqs.append(cond_rule(sid, f'{c["Номер замовлення"]}2:{c["Номер замовлення"]}{ROWS}',
                          f'=AND(${c["Номер замовлення"]}2<>"",'
                          f'COUNTIF(INDIRECT("\'Лист1\'!M2:M"),${c["Номер замовлення"]}2)'
                          f'+COUNTIF(INDIRECT("Atelier!J2:J"),${c["Номер замовлення"]}2)=0)', (0.98, 0.80, 0.80)))

    ss.batch_update({"requests": reqs})
    print(f"\nГотово: лист «{TITLE}» створено/оновлено.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        sys.exit(f"Не знайдено файл ключа: {e.filename}. Запустіть з папки бота або вкажіть --creds.")
