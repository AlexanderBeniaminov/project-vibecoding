import os
import sys
import datetime
import time
from groq import Groq
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.sheets import (
    get_client, get_worksheet, get_color_name, paint_cell,
    get_flag, set_flag, reset_weekly_flags
)

load_dotenv()

# === КОНФИГУРАЦИЯ ===

CURRENT_YEAR_SHEET = '2026 старый'
ROW_WEEK_NUMBERS  = 2
ROW_DATE_LABELS   = 3
ROW_REVENUE_CHECK = 6

# Строки с динамикой к предыдущему периоду (executive summary)
DYNAMICS_ROWS = {
    36: 'Выручка к пред. пер.',
    37: 'Гости к пред. пер.',
    38: 'Ср. чек к пред. пер.',
}

METRICS = [
    # ДОХОДЫ
    {'row': 6,  'label': 'Доход НФ за неделю (руб.)',      'yoy_row': 11,   'section': 'income'},
    {'row': 7,  'label': 'Выручка % к плану',               'yoy_row': None, 'section': 'income'},
    {'row': 8,  'label': 'Выполнение плана месяца (%)',      'yoy_row': None, 'section': 'income'},
    {'row': 10, 'label': 'Прогноз выручки месяца (руб.)',   'yoy_row': None, 'section': 'income'},
    {'row': 13, 'label': 'Выручка Монблан (руб.)',          'yoy_row': 21,   'section': 'income'},
    {'row': 14, 'label': 'Чеков Монблан',                   'yoy_row': None, 'section': 'income'},
    {'row': 17, 'label': 'F&B % от оборота',                'yoy_row': None, 'section': 'income'},
    {'row': 23, 'label': 'Фурако/бани (руб.)',              'yoy_row': None, 'section': 'income'},
    {'row': 24, 'label': 'Беседки/мангалы (руб.)',          'yoy_row': None, 'section': 'income'},
    {'row': 25, 'label': 'Прочее (руб.)',                   'yoy_row': None, 'section': 'income'},
    {'row': 27, 'label': 'Кол-во завтраков',                'yoy_row': None, 'section': 'income'},
    {'row': 29, 'label': 'Конверсия завтраков (%)',         'yoy_row': None, 'section': 'income'},

    # ЗАГРУЗКА И ПРОДАЖИ
    {'row': 45, 'label': 'ADR (руб.)',                      'yoy_row': None, 'section': 'sales'},
    {'row': 47, 'label': 'Загрузка коттеджей (%)',          'yoy_row': None, 'section': 'sales', 'target': '12% / 19.8%'},
    {'row': 48, 'label': 'Ср. пребывание кот. (дней)',      'yoy_row': None, 'section': 'sales'},
    {'row': 49, 'label': 'Загрузка Даниэль (%)',            'yoy_row': None, 'section': 'sales'},
    {'row': 51, 'label': 'Загрузка Ален (%)',               'yoy_row': None, 'section': 'sales'},
    {'row': 53, 'label': 'Доля отмен (%)',                  'yoy_row': None, 'section': 'sales'},
    {'row': 64, 'label': 'Прямые продажи vs OTA (%)',       'yoy_row': None, 'section': 'sales'},
    {'row': 40, 'label': 'План выручки след. мес. (руб.)',  'yoy_row': None, 'section': 'sales'},
    {'row': 41, 'label': 'Забронировано след. мес. (руб.)', 'yoy_row': None, 'section': 'sales'},
    {'row': 43, 'label': '% выполн. плана след. мес.',      'yoy_row': None, 'section': 'sales'},

    # СЕГМЕНТЫ
    {'row': 67, 'label': 'ДР: броней',                      'yoy_row': None, 'section': 'segments', 'target': '125 к июню'},
    {'row': 69, 'label': 'ДР: проживаний',                  'yoy_row': None, 'section': 'segments'},
    {'row': 70, 'label': 'ДР: сумма (руб.)',                'yoy_row': None, 'section': 'segments'},
    {'row': 77, 'label': 'Группы: броней',                  'yoy_row': None, 'section': 'segments', 'target': '6 к июню'},
    {'row': 79, 'label': 'Группы: проживаний',              'yoy_row': None, 'section': 'segments'},
    {'row': 80, 'label': 'Группы: сумма (руб.)',            'yoy_row': None, 'section': 'segments'},
    {'row': 72, 'label': 'Корпоративы: броней',             'yoy_row': None, 'section': 'segments'},
    {'row': 75, 'label': 'Корпоративы: сумма (руб.)',       'yoy_row': None, 'section': 'segments'},
    {'row': 82, 'label': 'Физики: броней',                  'yoy_row': None, 'section': 'segments'},
    {'row': 85, 'label': 'Физики: сумма (руб.)',            'yoy_row': None, 'section': 'segments'},
    {'row': 56, 'label': '% повторных гостей',              'yoy_row': None, 'section': 'segments'},

    # КАЧЕСТВО
    {'row': 55, 'label': 'Гостей всего',                    'yoy_row': None, 'section': 'quality'},
    {'row': 58, 'label': 'NPS',                             'yoy_row': None, 'section': 'quality'},
    {'row': 59, 'label': 'Отзывы кот. (кол-во)',            'yoy_row': None, 'section': 'quality'},
    {'row': 60, 'label': 'Отзывы кот. (негат. %)',          'yoy_row': None, 'section': 'quality'},
    {'row': 61, 'label': 'Отзывы хостелы (кол-во)',         'yoy_row': None, 'section': 'quality'},
    {'row': 62, 'label': 'Отзывы хостелы (негат. %)',       'yoy_row': None, 'section': 'quality'},

    # ОПЕРАЦИИ И ДЕНЬГИ
    {'row': 33, 'label': 'Остаток на счёте (руб.)',         'yoy_row': None, 'section': 'ops'},
    {'row': 34, 'label': 'Остаток в кассе (руб.)',          'yoy_row': None, 'section': 'ops'},
    {'row': 31, 'label': 'Кредит. задолж. (руб.)',          'yoy_row': None, 'section': 'ops'},
    {'row': 32, 'label': 'Дебит. задолж. (руб.)',           'yoy_row': None, 'section': 'ops'},
    {'row': 88, 'label': 'Ремонт: заявок',                  'yoy_row': None, 'section': 'ops'},
    {'row': 89, 'label': 'Ремонт: выполнено',               'yoy_row': None, 'section': 'ops'},
    {'row': 90, 'label': 'Ремонт: не выполнено',            'yoy_row': None, 'section': 'ops'},
    {'row': 92, 'label': 'Уборки коттеджи',                 'yoy_row': None, 'section': 'ops'},
    {'row': 93, 'label': 'Из них стыковочных (кот.)',       'yoy_row': None, 'section': 'ops'},
    {'row': 94, 'label': 'Уборки хостелы',                  'yoy_row': None, 'section': 'ops'},
    {'row': 97, 'label': 'Звонков входящих',                'yoy_row': None, 'section': 'ops'},
    {'row': 98, 'label': 'Неотвеченных звонков',            'yoy_row': None, 'section': 'ops'},
    {'row': 99, 'label': 'Доля без ответа (%)',             'yoy_row': None, 'section': 'ops'},
    {'row': 101,'label': 'Проверок стандартов',             'yoy_row': None, 'section': 'ops'},
    {'row': 102,'label': 'ФОТ горничные+техники (руб.)',    'yoy_row': None, 'section': 'ops'},
    {'row': 103,'label': 'ФОТ F&B персонал (руб.)',         'yoy_row': None, 'section': 'ops'},
]

SECTION_LABELS = {
    'income':   '💰 ДОХОДЫ',
    'sales':    '📊 ЗАГРУЗКА И ПРОДАЖИ',
    'segments': '👥 СЕГМЕНТЫ ГОСТЕЙ',
    'quality':  '⭐ КАЧЕСТВО СЕРВИСА',
    'ops':      '⚙️ ОПЕРАЦИИ И ДЕНЬГИ',
}

SECTION_HEADER_COLORS = {
    'income':   {'red': 0.13, 'green': 0.49, 'blue': 0.27},
    'sales':    {'red': 0.13, 'green': 0.30, 'blue': 0.65},
    'segments': {'red': 0.35, 'green': 0.20, 'blue': 0.60},
    'quality':  {'red': 0.00, 'green': 0.50, 'blue': 0.55},
    'ops':      {'red': 0.35, 'green': 0.42, 'blue': 0.55},
}

BG_COLORS = {
    'red':    {'red': 1.0,  'green': 0.8,  'blue': 0.8},
    'yellow': {'red': 1.0,  'green': 1.0,  'blue': 0.6},
    'green':  {'red': 0.78, 'green': 0.94, 'blue': 0.81},
}

TITLE_BG    = {'red': 0.13, 'green': 0.29, 'blue': 0.53}
EXEC_BG     = {'red': 0.18, 'green': 0.38, 'blue': 0.55}
DYNAMICS_BG = {'red': 0.88, 'green': 0.91, 'blue': 0.96}
WHITE_TEXT  = {'red': 1.0,  'green': 1.0,  'blue': 1.0}


def get_current_week():
    today = datetime.date.today()
    iso = today.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def parse_number(value):
    if value is None or value == '':
        return None
    cleaned = str(value).replace(' ', '').replace('\xa0', '').replace(',', '.').replace('%', '')
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def call_claude(system_prompt, user_message):
    client = Groq(api_key=os.environ['GROQ_API_KEY'])
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model='llama-3.3-70b-versatile',
                max_tokens=500,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user',   'content': user_message},
                ],
            )
            return response.choices[0].message.content
        except Exception as e:
            if attempt < 2:
                print(f'  Ошибка Groq API (попытка {attempt + 1}): {e}. Жду 5 сек...')
                time.sleep(5)
            else:
                raise RuntimeError(f'Groq API недоступен: {e}')


def find_week_column(ws, target_week=None):
    week_row    = ws.row_values(ROW_WEEK_NUMBERS)
    revenue_row = ws.row_values(ROW_REVENUE_CHECK)
    date_row    = ws.row_values(ROW_DATE_LABELS)

    last_col, last_week_num, last_date = None, '', ''
    for i, cell in enumerate(week_row):
        num = cell.strip().replace('\xa0', '').replace(' ', '')
        if num.isdigit():
            if target_week is not None:
                if num == str(target_week):
                    return i, num, (date_row[i].strip() if i < len(date_row) else '')
            else:
                if i < len(revenue_row) and revenue_row[i].strip().replace('\xa0', '').replace(' ', ''):
                    last_col, last_week_num, last_date = i, num, (date_row[i].strip() if i < len(date_row) else '')

    return last_col, last_week_num, last_date


def read_column_data(ws, col_idx):
    all_data = ws.get_all_values()
    return {row_num: row[col_idx] for row_num, row in enumerate(all_data, 1) if col_idx < len(row)}


def get_failed_tasks(strategy_sheet_id, client_gs):
    try:
        ws_statuses = get_worksheet(client_gs, strategy_sheet_id, 'Статусы')
        statuses    = ws_statuses.get_all_records()
        ws_archive  = get_worksheet(client_gs, strategy_sheet_id, 'Архив')
        archive     = ws_archive.get_all_values()
    except Exception as e:
        print(f'  Предупреждение: не удалось прочитать статусы/архив: {e}')
        return [], [], {}

    NOT_DONE = {'нет', 'не выполнено', 'не выполнена', ''}
    failed, by_person = [], {}

    for r in statuses:
        task = r.get('Задача', '')
        if not task:
            continue
        name    = r.get('Исполнитель', 'Неизвестный')
        status  = str(r.get('Статус', '')).lower().strip()
        is_done = status not in NOT_DONE

        if name not in by_person:
            by_person[name] = {'total': 0, 'done': 0}
        by_person[name]['total'] += 1
        if is_done:
            by_person[name]['done'] += 1
        else:
            failed.append({'исполнитель': name, 'задача': task, 'комментарий': r.get('Комментарий', '—')})

    for s in by_person.values():
        s['pct'] = round(s['done'] / s['total'] * 100) if s['total'] > 0 else 0

    total_t = sum(s['total'] for s in by_person.values())
    total_d = sum(s['done'] for s in by_person.values())
    task_stats = {
        'total':     total_t,
        'done':      total_d,
        'pct':       round(total_d / total_t * 100) if total_t > 0 else None,
        'by_person': by_person,
    }

    repeated = []
    if archive and len(archive) > 2:
        archive_tasks, failed_keys = [], {(t['исполнитель'], t['задача']) for t in failed}
        for row in reversed(archive):
            if row and row[0].startswith('Неделя'):
                break
            if any(row):
                archive_tasks.append(row)
        repeated = [{'исполнитель': r[0], 'задача': r[2]} for r in archive_tasks if len(r) >= 3 and (r[0], r[2]) in failed_keys]

    return failed, repeated, task_stats


def fmt_cell(ws, cell_range, bold=False, font_size=10, bg=None, wrap=False, font_color=None):
    fmt = {'textFormat': {'bold': bold, 'fontSize': font_size}}
    if font_color:
        fmt['textFormat']['foregroundColor'] = font_color
    if bg:
        fmt['backgroundColor'] = bg
    if wrap:
        fmt['wrapStrategy'] = 'WRAP'
    ws.format(cell_range, fmt)


def write_digest_formatted(ws_digest, week_label, metric_results, task_stats, failed_tasks, repeated_failures, conclusion):
    ws_digest.clear()

    # Снимаем все merge — артефакты предыдущих версий
    try:
        ss = ws_digest.spreadsheet
        sheet_id = ws_digest.id
        meta = ss.fetch_sheet_metadata()
        digest_meta = next((s for s in meta.get('sheets', []) if s.get('properties', {}).get('sheetId') == sheet_id), {})
        merges = digest_meta.get('merges', [])
        if merges:
            unmerge_requests = [{'unmergeCells': {'range': m}} for m in merges]
            ss.batch_update({'requests': unmerge_requests})
    except Exception:
        pass

    rows = []

    # Строка 1: главный заголовок
    rows.append([f'ДАЙДЖЕСТ  |  {week_label}', '', '', '', ''])

    # Строка 2: пустая
    rows.append(['', '', '', '', ''])

    # Секции с метриками
    section_header_rows = {}
    metric_row_map = {}

    current_section = None
    for m in metric_results:
        sec = m['section']
        if sec != current_section:
            if current_section is not None:
                rows.append(['', '', '', '', ''])
            rows.append([SECTION_LABELS[sec], '', '', '', ''])
            section_header_rows[sec] = len(rows)
            current_section = sec

        yoy = f"  ({m['delta_pct']:+.1f}%)" if m.get('delta_pct') is not None else ''
        rows.append([m['label'], m['display'] + yoy, '', '', ''])
        metric_row_map[m['label']] = len(rows)

        if m['label'] == 'ADR (руб.)' and m.get('revpar') is not None:
            rows.append(['RevPAR (руб.)', str(m['revpar']), '', '', ''])
            if m.get('revpac') is not None:
                rows.append(['RevPAC (руб.)', str(m['revpac']), '', '', ''])

    rows.append(['', '', '', '', ''])

    # Выполнение задач по исполнителям
    task_section_header_row = None
    task_exec_rows = []
    if task_stats and task_stats.get('by_person'):
        rows.append([
            '⚡ ВЫПОЛНЕНИЕ ЗАДАЧ ПРОШЛОЙ НЕДЕЛИ',
            f'Итого: {task_stats["pct"]}% ({task_stats["done"]} из {task_stats["total"]})',
            '', '', '',
        ])
        task_section_header_row = len(rows)
        for name, s in task_stats['by_person'].items():
            rows.append([name, f'{s["done"]} из {s["total"]}  ({s["pct"]}%)', '', '', ''])
            task_exec_rows.append((len(rows), s['pct']))
        rows.append(['', '', '', '', ''])

    # Невыполненные задачи
    failed_header_row = None
    if failed_tasks:
        rows.append(['❌ НЕ ВЫПОЛНЕНО НА ПРОШЛОЙ НЕДЕЛЕ', '', '', '', ''])
        failed_header_row = len(rows)
        for t in failed_tasks:
            is_repeated = any(
                r['задача'] == t['задача'] and r['исполнитель'] == t['исполнитель']
                for r in repeated_failures
            )
            marker = '⚠️ ПОВТОРНО  ' if is_repeated else ''
            rows.append([f'{marker}{t["исполнитель"]}', t['задача'], t['комментарий'], '', ''])
        rows.append(['', '', '', '', ''])

    # Аналитический вывод
    conclusion_header_row = len(rows) + 1
    rows.append(['💡 АНАЛИТИЧЕСКИЙ ВЫВОД', '', '', '', ''])
    conclusion_row = len(rows) + 1
    rows.append([conclusion, '', '', '', ''])

    ws_digest.update(values=rows, range_name='A1', value_input_option='RAW')

    # === ФОРМАТИРОВАНИЕ ===

    # Базовый шрифт 14 для всего листа
    ws_digest.format('A1:E300', {'textFormat': {'fontSize': 14}})

    fmt_cell(ws_digest, 'A1:E1', bold=True, font_size=16, bg=TITLE_BG, font_color=WHITE_TEXT)

    for sec, row_idx in section_header_rows.items():
        fmt_cell(ws_digest, f'A{row_idx}:E{row_idx}', bold=True, font_size=14,
                 bg=SECTION_HEADER_COLORS[sec], font_color=WHITE_TEXT)

    for m in metric_results:
        row_idx = metric_row_map.get(m['label'])
        if row_idx and m.get('color') in BG_COLORS:
            ws_digest.format(f'B{row_idx}', {'backgroundColor': BG_COLORS[m['color']]})

    if task_section_header_row:
        fmt_cell(ws_digest, f'A{task_section_header_row}:E{task_section_header_row}', bold=True, font_size=14,
                 bg={'red': 0.70, 'green': 0.40, 'blue': 0.10}, font_color=WHITE_TEXT)
        for row_idx, pct in task_exec_rows:
            if pct == 100:
                ws_digest.format(f'B{row_idx}', {'backgroundColor': BG_COLORS['green']})
            elif pct < 50:
                ws_digest.format(f'B{row_idx}', {'backgroundColor': BG_COLORS['red']})

    if failed_header_row:
        fmt_cell(ws_digest, f'A{failed_header_row}:E{failed_header_row}', bold=True, font_size=14,
                 bg={'red': 0.80, 'green': 0.23, 'blue': 0.23}, font_color=WHITE_TEXT)

    fmt_cell(ws_digest, f'A{conclusion_header_row}', bold=True, font_size=14)
    fmt_cell(ws_digest, f'A{conclusion_row}:E{conclusion_row}', wrap=True, font_size=14)

    try:
        ss = ws_digest.spreadsheet
        sheet_id = ws_digest.id
        ss.batch_update({'requests': [
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': 0, 'endIndex': 1},
                'properties': {'pixelSize': 300}, 'fields': 'pixelSize',
            }},
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': 1, 'endIndex': 2},
                'properties': {'pixelSize': 220}, 'fields': 'pixelSize',
            }},
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': 2, 'endIndex': 3},
                'properties': {'pixelSize': 200}, 'fields': 'pixelSize',
            }},
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'COLUMNS', 'startIndex': 3, 'endIndex': 4},
                'properties': {'pixelSize': 60}, 'fields': 'pixelSize',
            }},
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'ROWS', 'startIndex': 0, 'endIndex': 1},
                'properties': {'pixelSize': 50}, 'fields': 'pixelSize',
            }},
            {'updateDimensionProperties': {
                'range': {'sheetId': sheet_id, 'dimension': 'ROWS',
                          'startIndex': conclusion_row - 1, 'endIndex': conclusion_row},
                'properties': {'pixelSize': 120}, 'fields': 'pixelSize',
            }},
        ]})
    except Exception as e:
        print(f'  Предупреждение: не удалось задать размеры: {e}')


def main():
    print('=== Агент 1: Аналитик ===')

    # Выбор недели: python3 agent1_analyst.py 15  → анализ за неделю 15
    target_week = None
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_week = int(sys.argv[1])
        print(f'Выбрана неделя: {target_week}')

    current_week = get_current_week()
    print(f'Текущая неделя: {current_week}')

    finance_sheet_id  = os.environ['FINANCE_SHEET_ID']
    strategy_sheet_id = os.environ['STRATEGY_SHEET_ID']

    print('Подключаюсь к Google Sheets...')
    client_gs = get_client()

    ws_status = get_worksheet(client_gs, finance_sheet_id, 'Статус системы')

    if target_week is None:
        reset_weekly_flags(ws_status, current_week)
        if get_flag(ws_status, 'анализ_готов') == 'да':
            print('Анализ уже выполнен на этой неделе. Выхожу.')
            return

    print(f'Читаю лист "{CURRENT_YEAR_SHEET}"...')
    try:
        ws_current  = get_worksheet(client_gs, finance_sheet_id, CURRENT_YEAR_SHEET)
        ws_analysis = get_worksheet(client_gs, finance_sheet_id, 'Анализ')
    except Exception as e:
        print(f'ОШИБКА: не удалось открыть листы: {e}')
        sys.exit(1)

    col_idx, week_num, date_label = find_week_column(ws_current, target_week)
    if col_idx is None:
        msg = f'Неделя {target_week} не найдена в таблице.' if target_week else 'Данные не внесены.'
        print(f'ПРЕДУПРЕЖДЕНИЕ: {msg}')
        if target_week is None:
            set_flag(ws_status, 'данные_внесены', 'нет')
            ws_digest = get_worksheet(client_gs, finance_sheet_id, 'Дайджест')
            ws_digest.update(values=[[f'Данные за неделю {current_week} не внесены']], range_name='A1', value_input_option='RAW')
            set_flag(ws_status, 'дайджест_записан', 'да')
        return

    week_label = f'Неделя {week_num}  |  {date_label}'
    print(f'Анализирую: {week_label}')
    if target_week is None:
        set_flag(ws_status, 'данные_внесены', 'да')

    col_data = read_column_data(ws_current, col_idx)

    # Обрабатываем метрики
    metric_results = []
    analysis_data  = [['Метрика', 'Значение', 'К пр. году', 'Цвет']]
    adr_val = None

    for m in METRICS:
        raw = col_data.get(m['row'], '').strip()
        val = parse_number(raw)

        if val is None:
            print(f'  {m["label"]}: нет данных')
            continue

        if m['label'] == 'ADR (руб.)':
            adr_val = val

        delta_pct, color, yoy_display = None, 'white', '—'
        if m.get('yoy_row'):
            yoy_raw = col_data.get(m['yoy_row'], '').strip()
            yoy_val = parse_number(yoy_raw)
            if yoy_val is not None:
                delta_pct = yoy_val - 100
                color     = get_color_name(delta_pct)
                yoy_display = f'{yoy_val:.0f}%'

        display = raw.replace('\xa0', ' ')
        result = {
            'label':     m['label'],
            'display':   display,
            'delta_pct': delta_pct,
            'color':     color,
            'section':   m['section'],
            'target':    m.get('target'),
        }
        metric_results.append(result)
        analysis_data.append([m['label'], display, yoy_display, color])

        yoy_text = f' (к пр. году: {delta_pct:+.1f}%)' if delta_pct is not None else ''
        print(f'  {m["label"]}: {raw}{yoy_text} → {color}')

    # RevPAR = ADR × загрузка / 100
    # RevPAC = Доход НФ / (Гостей × ср. пребывание) — выручка на гостя-ночь
    loading_res = next((r for r in metric_results if 'Загрузка коттеджей' in r['label']), None)
    stay_res    = next((r for r in metric_results if 'Ср. пребывание' in r['label']), None)
    revenue_res = next((r for r in metric_results if 'Доход НФ' in r['label']), None)
    guests_res  = next((r for r in metric_results if r['label'] == 'Гостей всего'), None)
    if adr_val and loading_res:
        loading_num = parse_number(loading_res['display'])
        if loading_num is not None:
            revpar = round(adr_val * loading_num / 100)
            revpac = None
            if revenue_res and guests_res and stay_res:
                rev_num   = parse_number(revenue_res['display'])
                guest_num = parse_number(guests_res['display'])
                stay_num  = parse_number(stay_res['display'])
                if rev_num and guest_num and stay_num and guest_num > 0 and stay_num > 0:
                    revpac = round(rev_num / (guest_num * stay_num))
            for r in metric_results:
                if r['label'] == 'ADR (руб.)':
                    r['revpar'] = revpar
                    if revpac is not None:
                        r['revpac'] = revpac
            print(f'  RevPAR: {revpar} руб. (расчётный)')
            if revpac:
                print(f'  RevPAC: {revpac} руб. (расчётный)')

    # Средний чек на гостя = Доход НФ / Гостей всего → добавляем в секцию income
    _revenue = parse_number(next((r['display'] for r in metric_results if 'Доход НФ' in r['label']), ''))
    _guests  = parse_number(next((r['display'] for r in metric_results if r['label'] == 'Гостей всего'), ''))
    avg_check_str = '—'
    if _revenue and _guests and _guests > 0:
        avg_check_str = str(round(_revenue / _guests))
        print(f'  Средний чек на гостя: {avg_check_str} руб. (расчётный)')
        idx = next((i for i, r in enumerate(metric_results) if 'Доход НФ' in r['label']), -1)
        if idx >= 0:
            metric_results.insert(idx + 1, {
                'label': 'Средний чек на гостя (руб.)', 'display': avg_check_str,
                'delta_pct': None, 'color': 'white', 'section': 'income', 'target': None,
            })

    # Лист Анализ
    print("Записываю в лист 'Анализ'...")
    ws_analysis.clear()
    ws_analysis.update(values=analysis_data, range_name='A1')
    for i, r in enumerate(metric_results):
        if r['color'] != 'white':
            paint_cell(ws_analysis, f'B{i + 2}', r['color'])

    if target_week is None:
        set_flag(ws_status, 'анализ_готов', 'да')

    # Динамика к предыдущему периоду
    dynamics = {}
    for drow, dlabel in DYNAMICS_ROWS.items():
        raw = col_data.get(drow, '').strip()
        if raw:
            val = parse_number(raw)
            if val is not None:
                sign = '+' if val > 0 else ''
                dynamics[dlabel] = f'{sign}{val:.1f}%'
            else:
                dynamics[dlabel] = raw

    # Невыполненные задачи
    print('Читаю статусы прошлой недели...')
    failed_tasks, repeated_failures, task_stats = get_failed_tasks(strategy_sheet_id, client_gs)
    if task_stats.get('total'):
        print(f'  Задач всего: {task_stats["total"]}, выполнено: {task_stats["done"]} ({task_stats["pct"]}%)')
    if failed_tasks:
        print(f'  Невыполненных: {len(failed_tasks)}, повторно: {len(repeated_failures)}')

    # Расчётные показатели для AI-анализа
    calcs = []
    revpar_for_ai = next((r.get('revpar') for r in metric_results if r.get('revpar')), None)
    revpac_for_ai = next((r.get('revpac') for r in metric_results if r.get('revpac')), None)
    if revpar_for_ai:
        calcs.append(f'RevPAR = {revpar_for_ai} руб.')
    if revpac_for_ai:
        calcs.append(f'RevPAC = {revpac_for_ai} руб. (выручка на гостя-ночь)')
    if avg_check_str != '—':
        calcs.append(f'Средний чек на гостя = {avg_check_str} руб.')
    if task_stats.get('pct') is not None:
        calcs.append(f'Выполнение задач пр. недели = {task_stats["pct"]}% ({task_stats["done"]}/{task_stats["total"]})')

    revenue_val = parse_number(next((r['display'] for r in metric_results if 'Доход НФ' in r['label']), ''))
    ota_val     = parse_number(next((r['display'] for r in metric_results if 'OTA' in r['label']), ''))
    if revenue_val and ota_val and ota_val > 0:
        ota_loss = round(revenue_val * ota_val / 100 * 0.20)
        calcs.append(f'Потери на OTA-комиссии (~20%) = {int(ota_loss):,} руб.'.replace(',', ' '))

    fb_cheques = parse_number(next((r['display'] for r in metric_results if 'Чеков Монблан' in r['label']), ''))
    guests_val = parse_number(next((r['display'] for r in metric_results if r['label'] == 'Гостей всего'), ''))
    if fb_cheques and guests_val and guests_val > 0:
        calcs.append(f'F&B конверсия (чеков/гостей) = {round(fb_cheques / guests_val * 100, 1)}%')

    styk_val      = parse_number(next((r['display'] for r in metric_results if 'стыковочных' in r['label']), ''))
    cleanings_val = parse_number(next((r['display'] for r in metric_results if r['label'] == 'Уборки коттеджи'), ''))
    if styk_val and cleanings_val and cleanings_val > 0:
        calcs.append(f'Стыковочные уборки = {round(styk_val / cleanings_val * 100, 1)}% от всех уборок кот.')

    # Строим сообщение для AI
    lines = [
        f'[{m["section"].upper()}] {m["label"]}: {m["display"]}' +
        (f' (к пр.году: {m["delta_pct"]:+.1f}%)' if m.get('delta_pct') is not None else '')
        for m in metric_results
    ]
    if dynamics:
        lines.append('\n[ДИНАМИКА К ПРЕД. ПЕРИОДУ]')
        lines += [f'{k}: {v}' for k, v in dynamics.items()]
    if calcs:
        lines.append('\n[РАСЧЁТНЫЕ ПОКАЗАТЕЛИ]')
        lines += calcs
    if failed_tasks:
        lines.append('\n[НЕ ВЫПОЛНЕНО ПРОШЛОЙ НЕДЕЛЕЙ]')
        lines += [f'{t["исполнитель"]}: {t["задача"]}' for t in failed_tasks]

    system_prompt = (
        'Ты — аналитик управляющей компании горнолыжного курорта ВК Губаха. '
        'Апрель–ноябрь — межсезонье, низкая загрузка нормальна. Пиковый сезон: декабрь–март.\n\n'
        'Проанализируй данные и обязательно оцени взаимосвязи:\n'
        '1. ADR ↔ Загрузка: растёт ли RevPAR — это главный индикатор ценовой политики\n'
        '2. OTA-доля: укажи потери маржи в рублях (они в [РАСЧЁТНЫЕ ПОКАЗАТЕЛИ])\n'
        '3. Pipeline (% плана след. месяца): если <40% — критический сигнал для продаж\n'
        '4. Стыковочные уборки: высокий % при коротком пребывании = перегруз персонала\n'
        '5. F&B конверсия: низкий % — упущенная выручка Монблан\n\n'
        'Структура ответа: 1) Главный риск недели. 2) Главная возможность. 3) 2-3 приоритета для команды.\n'
        'Только факты из данных. Без общих фраз. 5-7 предложений.'
    )

    print('Формирую аналитический вывод...')
    try:
        conclusion = call_claude(system_prompt, 'Данные недели:\n' + '\n'.join(lines))
        conclusion = conclusion.strip()
    except Exception as e:
        print(f'  Предупреждение: ИИ недоступен: {e}')
        conclusion = 'Автоматический анализ временно недоступен.'

    # Записываем форматированный дайджест
    print('Записываю дайджест...')
    ws_digest = get_worksheet(client_gs, finance_sheet_id, 'Дайджест')
    write_digest_formatted(ws_digest, week_label, metric_results, task_stats, failed_tasks, repeated_failures, conclusion)

    if target_week is None:
        set_flag(ws_status, 'дайджест_записан', 'да')

    print('\n✅ Агент 1 завершил работу.')
    print(f'   Проанализировано метрик: {len(metric_results)}')
    print(f'   Невыполненных задач: {len(failed_tasks)}')
    print(f'   Дайджест записан в лист "Дайджест"')


if __name__ == '__main__':
    main()
