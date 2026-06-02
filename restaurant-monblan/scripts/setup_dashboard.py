#!/usr/bin/env python3
"""
setup_dashboard.py — строит лист «Дашборд»:
  сравнение KPI нед.1-5 2026 vs 2025, сигналы, AI-блоки.
"""
import warnings; warnings.filterwarnings('ignore')
from google.oauth2 import service_account
from googleapiclient.discovery import build

SS        = '1Wcvn2mJFgOfcdm3mUQpYLoU92H3_bhGUJA_NnBwbDNI'
DASH_GID  = 1669207980
CREDS     = 'credentials.json'

WEEKLY    = 'Еженедельно'
DASH      = 'Дашборд'

KPIS = [
    ('Выручка всего',          4,  'money'),
    ('Кухня',                  5,  'money'),
    ('Бар',                    7,  'money'),
    ('Кол-во гостей',          31, 'count'),
    ('Ср. чек на гостя',       38, 'money'),
    ('Кол-во чеков',           42, 'count'),
    ('Средний счёт',           47, 'money'),
    ('Утро — выручка',         10, 'money'),
    ('День — выручка',         12, 'money'),
    ('Вечер — выручка',        14, 'money'),
    ('Оборачиваемость столов', 52, 'decimal'),
    ('Ср. чек на блюдо',       48, 'money'),
]
N = len(KPIS)  # 12

# ── Строки дашборда (1-based) ─────────────────────────────────────
R_TITLE   = 1
R_SEL     = 2
R_SEP1    = 3
R_CMP     = 4
R_HDR     = 5
R_D0      = 6          # первая строка KPI
R_DN      = 6 + N - 1  # = 17
R_SEP2    = 18
R_SIG     = 19
R_REDH    = 20
R_RED1, R_RED2, R_RED3 = 21, 22, 23
R_YELH    = 24
R_YEL1, R_YEL2, R_YEL3 = 25, 26, 27
R_GRNH    = 28
R_GRN1, R_GRN2, R_GRN3 = 29, 30, 31
R_SEP3    = 32
R_CAUSE   = 33
R_C1,R_C2,R_C3 = 34, 35, 36
R_REC     = 37
R_R1,R_R2,R_R3 = 38, 39, 40
R_MGMT    = 41
R_M1,R_M2,R_M3 = 42, 43, 44
TOTAL_VIS = 44         # последняя видимая строка

# Скрытые данные
H25 = 50   # строки 50–61: KPI[0..11] 2025, cols B–F = нед.1-5
H26 = 62   # строки 62–73: KPI[0..11] 2026, cols B–F = нед.1-5

# Колонки 2025 нед.1-5 в Еженедельно: B-F (indices 2-6)
# Колонки 2026 нед.1-5: BB-BF (indices 54-58)
COLS_2025 = ['B', 'C', 'D', 'E', 'F']
COLS_2026 = ['BB', 'BC', 'BD', 'BE', 'BF']

# ── Цвета ─────────────────────────────────────────────────────────
def c(r, g, b): return {'red': r/255, 'green': g/255, 'blue': b/255}

COL = {
    'navy':   c(26, 58, 92),
    'blue':   c(45,106,159),
    'lblue':  c(74,127,181),
    'white':  c(255,255,255),
    'lgray':  c(240,240,240),
    'dgray':  c(50, 50, 50),
    'sep':    c(220,220,220),
    'red_h':  c(180, 50, 50),
    'red_bg': c(255,204,204),
    'yel_h':  c(153,120,  0),
    'yel_bg': c(255,242,204),
    'grn_h':  c( 25, 98, 42),
    'grn_bg': c(217,234,211),
    'ai_bg':  c(248,249,250),
    'ai_h':   c( 61, 61, 61),
    'row1':   c(255,255,255),
    'row2':   c(248,249,250),
}


def col_letter(n):
    s = ''
    while n > 0:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def rng(r1, c1, r2, c2):
    return {'sheetId': DASH_GID,
            'startRowIndex': r1 - 1, 'endRowIndex': r2,
            'startColumnIndex': c1 - 1, 'endColumnIndex': c2}


def get_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDS, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return build('sheets', 'v4', credentials=creds)


def read_kpi_data(svc):
    """Читает KPI данные для нед.1-5 из 2025 и 2026."""
    data = {}  # data[(year, week)][kpi_idx] = value

    def read_block(cols_letters, year):
        # Читаем нужные строки KPI за все 5 недель одним запросом
        kpi_rows = [k[1] for k in KPIS]
        min_row = min(kpi_rows)
        max_row = max(kpi_rows)
        start_col, end_col = cols_letters[0], cols_letters[-1]
        r = f"'{WEEKLY}'!{start_col}{min_row}:{end_col}{max_row}"
        res = svc.spreadsheets().values().get(
            spreadsheetId=SS, range=r,
            valueRenderOption='UNFORMATTED_VALUE').execute()
        vals = res.get('values', [])
        # vals[row_offset][col_offset]
        row_map = {kpi_row: i for i, kpi_row in enumerate(range(min_row, max_row + 1))}

        for wk_i, col in enumerate(cols_letters):
            week = wk_i + 1
            data[(year, week)] = []
            for kpi_label, kpi_row, fmt in KPIS:
                row_off = row_map.get(kpi_row, -1)
                if row_off < 0 or row_off >= len(vals):
                    data[(year, week)].append(0)
                    continue
                row_data = vals[row_off]
                if wk_i < len(row_data):
                    v = row_data[wk_i]
                    try:
                        data[(year, week)].append(float(v))
                    except (ValueError, TypeError):
                        data[(year, week)].append(0)
                else:
                    data[(year, week)].append(0)

    read_block(COLS_2025, 2025)
    read_block(COLS_2026, 2026)
    return data


def build_requests(data):
    """Возвращает список batchUpdate requests для форматирования."""
    reqs = []

    # ── Размеры колонок ───────────────────────────────────────────
    col_widths = [(1, 230), (2, 125), (3, 125), (4, 90), (5, 55)]
    for col, width in col_widths:
        reqs.append({'updateDimensionProperties': {
            'range': {'sheetId': DASH_GID, 'dimension': 'COLUMNS',
                      'startIndex': col - 1, 'endIndex': col},
            'properties': {'pixelSize': width}, 'fields': 'pixelSize'}})

    # ── Высоты строк ─────────────────────────────────────────────
    row_heights = {
        R_TITLE: 36, R_SEL: 30, R_SEP1: 6,
        R_CMP: 26, R_HDR: 24,
        R_SEP2: 6, R_SIG: 26,
        R_REDH: 22, R_YELH: 22, R_GRNH: 22,
        R_SEP3: 6, R_CAUSE: 22, R_REC: 22, R_MGMT: 22,
    }
    for row in range(R_D0, R_DN + 1):
        row_heights[row] = 22
    for row in [R_RED1,R_RED2,R_RED3,R_YEL1,R_YEL2,R_YEL3,R_GRN1,R_GRN2,R_GRN3,
                R_C1,R_C2,R_C3,R_R1,R_R2,R_R3,R_M1,R_M2,R_M3]:
        row_heights[row] = 22

    for row, h in row_heights.items():
        reqs.append({'updateDimensionProperties': {
            'range': {'sheetId': DASH_GID, 'dimension': 'ROWS',
                      'startIndex': row - 1, 'endIndex': row},
            'properties': {'pixelSize': h}, 'fields': 'pixelSize'}})

    def cell_fmt(row, col1, col2, bg=None, fg=None, bold=False, size=10,
                 halign=None, valign='MIDDLE', wrap=False):
        fmt = {}
        if bg:
            fmt['backgroundColor'] = bg
        # textFormat всегда если есть bold/size/fg
        tf = {}
        if bold: tf['bold'] = bold
        if size != 10: tf['fontSize'] = size
        if fg:   tf['foregroundColor'] = fg
        if tf:   fmt['textFormat'] = tf
        if halign: fmt['horizontalAlignment'] = halign
        fmt['verticalAlignment'] = valign
        if wrap: fmt['wrapStrategy'] = 'WRAP'
        f_list = []
        if bg:   f_list.append('backgroundColor')
        if tf:   f_list.append('textFormat')
        if halign: f_list.append('horizontalAlignment')
        f_list += ['verticalAlignment']
        if wrap: f_list.append('wrapStrategy')
        reqs.append({'repeatCell': {
            'range': rng(row, col1, row, col2),
            'cell': {'userEnteredFormat': fmt},
            'fields': 'userEnteredFormat(' + ','.join(f_list) + ')'}})

    # ── Стили строк ───────────────────────────────────────────────
    # Заголовок
    cell_fmt(R_TITLE, 1, 5, bg=COL['navy'], fg=COL['white'], bold=True, size=13, halign='CENTER')
    # Селектор
    cell_fmt(R_SEL, 1, 5, bg=COL['lgray'], size=10)
    cell_fmt(R_SEL, 1, 1, bg=COL['lgray'], bold=True)
    # Разделители
    for r in [R_SEP1, R_SEP2, R_SEP3]:
        cell_fmt(r, 1, 5, bg=COL['sep'])
    # Заголовок секции сравнения
    cell_fmt(R_CMP, 1, 5, bg=COL['blue'], fg=COL['white'], bold=True, size=10, halign='CENTER')
    # Шапка таблицы
    cell_fmt(R_HDR, 1, 5, bg=COL['lblue'], fg=COL['white'], bold=True, size=9, halign='CENTER')
    # KPI строки (чередование)
    for i in range(N):
        row = R_D0 + i
        bg = COL['row1'] if i % 2 == 0 else COL['row2']
        cell_fmt(row, 1, 5, bg=bg, size=9)
        cell_fmt(row, 1, 1, bg=COL['lgray'], bold=False)  # столбец A
        cell_fmt(row, 2, 3, bg=bg, halign='RIGHT')
        cell_fmt(row, 4, 4, bg=bg, halign='CENTER')
        cell_fmt(row, 5, 5, bg=bg, halign='CENTER')

    # Секция сигналов
    cell_fmt(R_SIG, 1, 5, bg=COL['dgray'], fg=COL['white'], bold=True, size=10, halign='CENTER')
    cell_fmt(R_REDH, 1, 5, bg=COL['red_bg'], fg=COL['red_h'], bold=True, size=9)
    cell_fmt(R_YELH, 1, 5, bg=COL['yel_bg'], fg=COL['yel_h'], bold=True, size=9)
    cell_fmt(R_GRNH, 1, 5, bg=COL['grn_bg'], fg=COL['grn_h'], bold=True, size=9)
    for r in [R_RED1,R_RED2,R_RED3]:
        cell_fmt(r, 1, 5, bg=COL['red_bg'], size=9)
    for r in [R_YEL1,R_YEL2,R_YEL3]:
        cell_fmt(r, 1, 5, bg=COL['yel_bg'], size=9)
    for r in [R_GRN1,R_GRN2,R_GRN3]:
        cell_fmt(r, 1, 5, bg=COL['grn_bg'], size=9)

    # AI секции
    for r_hdr, rows in [(R_CAUSE,[R_C1,R_C2,R_C3]),
                        (R_REC,  [R_R1,R_R2,R_R3]),
                        (R_MGMT, [R_M1,R_M2,R_M3])]:
        cell_fmt(r_hdr, 1, 5, bg=COL['ai_h'], fg=COL['white'], bold=True, size=9)
        for r in rows:
            cell_fmt(r, 1, 5, bg=COL['ai_bg'], size=9, wrap=True)

    # ── Объединения ───────────────────────────────────────────────
    for (r1, c1, r2, c2) in [
        (R_TITLE, 1, R_TITLE, 5),
        (R_CMP,   1, R_CMP,   5),
        (R_SIG,   1, R_SIG,   5),
        (R_REDH,  1, R_REDH,  5),
        (R_YELH,  1, R_YELH,  5),
        (R_GRNH,  1, R_GRNH,  5),
        (R_CAUSE, 1, R_CAUSE, 5),
        (R_REC,   1, R_REC,   5),
        (R_MGMT,  1, R_MGMT,  5),
    ] + [(r, 1, r, 5) for r in [R_RED1,R_RED2,R_RED3,R_YEL1,R_YEL2,R_YEL3,R_GRN1,R_GRN2,R_GRN3]] \
      + [(r, 1, r, 5) for r in [R_C1,R_C2,R_C3,R_R1,R_R2,R_R3,R_M1,R_M2,R_M3]]:
        reqs.append({'mergeCells': {
            'range': rng(r1, c1, r2, c2), 'mergeType': 'MERGE_ALL'}})

    # ── Условное форматирование ───────────────────────────────────
    # Цветим строки KPI по значению Δ% в столбце D
    # Стратегия: добавляем в порядке убывания приоритета (index=0 → наивысший)
    # Порядок добавления: сначала жёлтый (самый низкий), потом зелёный, потом красный
    data_range = rng(R_D0, 1, R_DN, 5)
    d = f'D{R_D0}'  # например D6

    # Жёлтый: Δ% < -3% (любое снижение > 3%) — будет перекрыт красным
    reqs.append({'addConditionalFormatRule': {'index': 0, 'rule': {
        'ranges': [data_range],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA',
                          'values': [{'userEnteredValue': f'=${d}<-3%'}]},
            'format': {'backgroundColor': COL['yel_bg']}}}}})

    # Зелёный: Δ% > 5%
    reqs.append({'addConditionalFormatRule': {'index': 0, 'rule': {
        'ranges': [data_range],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA',
                          'values': [{'userEnteredValue': f'=${d}>5%'}]},
            'format': {'backgroundColor': COL['grn_bg']}}}}})

    # Красный: Δ% < -10% — перекрывает жёлтый
    reqs.append({'addConditionalFormatRule': {'index': 0, 'rule': {
        'ranges': [data_range],
        'booleanRule': {
            'condition': {'type': 'CUSTOM_FORMULA',
                          'values': [{'userEnteredValue': f'=${d}<-10%'}]},
            'format': {'backgroundColor': COL['red_bg']}}}}})

    # ── Заморозка (только строки — объединённые ячейки мешают заморозке колонок)
    reqs.append({'updateSheetProperties': {
        'properties': {'sheetId': DASH_GID,
                       'gridProperties': {'frozenRowCount': 2}},
        'fields': 'gridProperties.frozenRowCount'}})

    # ── Числовые форматы для колонок B, C, D ─────────────────────
    # Колонка D (Δ%): формат 0%
    reqs.append({'repeatCell': {
        'range': rng(R_D0, 4, R_DN, 4),
        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '0%'}}},
        'fields': 'userEnteredFormat.numberFormat'}})
    # Колонки B, C: форматируем по типу KPI
    for i, (label, kpi_row, fmt) in enumerate(KPIS):
        row = R_D0 + i
        if fmt == 'money':
            pat = {'type': 'NUMBER', 'pattern': '#,##0'}
        elif fmt == 'count':
            pat = {'type': 'NUMBER', 'pattern': '#,##0'}
        else:
            pat = {'type': 'NUMBER', 'pattern': '0.##'}
        for col in [2, 3]:
            reqs.append({'repeatCell': {
                'range': rng(row, col, row, col),
                'cell': {'userEnteredFormat': {'numberFormat': pat}},
                'fields': 'userEnteredFormat.numberFormat'}})

    # ── Граница таблицы KPI ───────────────────────────────────────
    reqs.append({'updateBorders': {
        'range': rng(R_HDR, 1, R_DN, 5),
        'innerHorizontal': {'style': 'SOLID', 'width': 1, 'color': COL['lgray']},
        'innerVertical':   {'style': 'SOLID', 'width': 1, 'color': COL['lgray']},
    }})

    return reqs


def build_values(data):
    """Возвращает данные для записи: видимые лейблы + скрытые числа + формулы."""
    rows = []

    def row(r, vals):
        rows.append({'range': f"'{DASH}'!A{r}",
                     'values': [vals]})

    # Заголовок
    row(R_TITLE, ['ДАШБОРД — МОНБЛАН'])
    row(R_SEL,   ['Выберите неделю 2026 (1–5):', 1])  # B2 = 1 по умолчанию

    # Заголовок секции
    row(R_CMP,  ['📊  СРАВНЕНИЕ ПОКАЗАТЕЛЕЙ  —  2025 vs 2026'])

    # Шапка таблицы — динамический заголовок (ru_RU: разделитель «;»)
    rows.append({'range': f"'{DASH}'!A{R_HDR}",
                 'values': [['Показатель',
                              f'=$B$2&"-я нед. 2025"',
                              f'=$B$2&"-я нед. 2026"',
                              'Δ%', '●']]})

    # KPI строки: формулы из скрытых данных (ru_RU → «;» как разделитель аргументов)
    for i in range(N):
        r = R_D0 + i
        r25 = H25 + i
        r26 = H26 + i
        rows.append({'range': f"'{DASH}'!A{r}", 'values': [[
            KPIS[i][0],
            f'=INDEX($B${r25}:$F${r25};1;$B$2)',
            f'=INDEX($B${r26}:$F${r26};1;$B$2)',
            f'=IFERROR(IF(B{r}=0;"—";(C{r}-B{r})/B{r});"—")',
            f'=IF(D{r}="—";"";IF(D{r}<-0,1;"🔴";IF(D{r}<-0,03;"🟡";IF(D{r}>0,05;"🟢";"⚪"))))',
        ]]})

    # Сигналы — формулы FILTER (ru_RU: «;»)
    D_RNG = f'$D${R_D0}:$D${R_DN}'
    A_RNG = f'$A${R_D0}:$A${R_DN}'
    def sig(r, condition, idx):
        return {'range': f"'{DASH}'!A{r}",
                'values': [[f'=IFERROR(INDEX(FILTER({A_RNG};ISNUMBER({D_RNG});{D_RNG}{condition});{idx});"—")']]}

    row(R_SIG,  ['🚨  СИГНАЛЫ НЕДЕЛИ'])
    row(R_REDH, ['🔴  ПРОБЛЕМНЫЕ ЗОНЫ  (отклонение > −10%)'])
    rows += [sig(R_RED1,'<-0,1',1), sig(R_RED2,'<-0,1',2), sig(R_RED3,'<-0,1',3)]

    row(R_YELH, ['🟡  ТРЕБУЮТ ВНИМАНИЯ  (−10% до −3%)'])
    rows += [
        {'range': f"'{DASH}'!A{R_YEL1}", 'values': [[f'=IFERROR(INDEX(FILTER({A_RNG};ISNUMBER({D_RNG});{D_RNG}>=-0,1;{D_RNG}<-0,03);1);"—")']]},
        {'range': f"'{DASH}'!A{R_YEL2}", 'values': [[f'=IFERROR(INDEX(FILTER({A_RNG};ISNUMBER({D_RNG});{D_RNG}>=-0,1;{D_RNG}<-0,03);2);"—")']]},
        {'range': f"'{DASH}'!A{R_YEL3}", 'values': [[f'=IFERROR(INDEX(FILTER({A_RNG};ISNUMBER({D_RNG});{D_RNG}>=-0,1;{D_RNG}<-0,03);3);"—")']]}
    ]

    row(R_GRNH, ['🟢  РАБОТАЕТ ХОРОШО  (рост > +5%)'])
    rows += [sig(R_GRN1,'>0,05',1), sig(R_GRN2,'>0,05',2), sig(R_GRN3,'>0,05',3)]

    # AI блоки — заглушки (заполнит GAS-скрипт)
    row(R_CAUSE, ['🔍  ВОЗМОЖНЫЕ ПРИЧИНЫ  (AI-анализ)'])
    for r in [R_C1, R_C2, R_C3]:
        row(r, ['← Нажмите «Обновить AI-анализ» для заполнения'])

    row(R_REC, ['💡  РЕКОМЕНДАЦИИ  (AI)'])
    for r in [R_R1, R_R2, R_R3]:
        row(r, ['← Нажмите «Обновить AI-анализ» для заполнения'])

    row(R_MGMT, ['📋  УПРАВЛЕНЧЕСКИЕ ВЫВОДЫ  (AI)'])
    for r in [R_M1, R_M2, R_M3]:
        row(r, ['← Нажмите «Обновить AI-анализ» для заполнения'])

    # ── Скрытые данные (строки 50-73) ────────────────────────────
    for i, (label, kpi_row, fmt) in enumerate(KPIS):
        # 2025
        vals_2025 = [data.get((2025, wk), [0]*N)[i] for wk in range(1, 6)]
        rows.append({'range': f"'{DASH}'!B{H25+i}",
                     'values': [vals_2025]})
        # 2026
        vals_2026 = [data.get((2026, wk), [0]*N)[i] for wk in range(1, 6)]
        rows.append({'range': f"'{DASH}'!B{H26+i}",
                     'values': [vals_2026]})

    return rows


def add_data_validation(svc):
    """Добавляет выпадающий список 1-5 на B2."""
    svc.spreadsheets().batchUpdate(spreadsheetId=SS, body={'requests': [{
        'setDataValidation': {
            'range': rng(R_SEL, 2, R_SEL, 2),
            'rule': {
                'condition': {'type': 'ONE_OF_LIST',
                              'values': [{'userEnteredValue': str(i)} for i in range(1, 6)]},
                'showCustomUi': True, 'strict': True,
            }
        }
    }]}).execute()


def hide_rows(svc):
    """Скрывает вспомогательные строки 50-75."""
    svc.spreadsheets().batchUpdate(spreadsheetId=SS, body={'requests': [{
        'updateDimensionProperties': {
            'range': {'sheetId': DASH_GID, 'dimension': 'ROWS',
                      'startIndex': H25 - 1, 'endIndex': H26 + N},
            'properties': {'hiddenByUser': True},
            'fields': 'hiddenByUser',
        }
    }]}).execute()


def main():
    print('Подключаемся...')
    svc = get_service()

    print('1. Читаем данные из Еженедельно...')
    data = read_kpi_data(svc)
    for (yr, wk), vals in sorted(data.items()):
        print(f'   {yr} нед.{wk}: Выручка={vals[0]:,.0f}  Гости={vals[3]:.0f}')

    print('\n2. Очищаем лист Дашборд...')
    svc.spreadsheets().batchUpdate(spreadsheetId=SS, body={'requests': [
        {'updateCells': {'range': {'sheetId': DASH_GID},
                         'fields': 'userEnteredValue,userEnteredFormat'}},
        {'unmergeCells':  {'range': {'sheetId': DASH_GID}}},
        {'clearBasicFilter': {'sheetId': DASH_GID}},
    ]}).execute()

    print('3. Применяем форматирование...')
    fmt_reqs = build_requests(data)
    # Шлём пачками по 30
    for i in range(0, len(fmt_reqs), 30):
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SS,
            body={'requests': fmt_reqs[i:i+30]}).execute()
    print(f'   Запросов форматирования: {len(fmt_reqs)}')

    print('4. Записываем значения и формулы...')
    val_rows = build_values(data)
    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=SS,
        body={'valueInputOption': 'USER_ENTERED', 'data': val_rows}).execute()
    print(f'   Диапазонов данных: {len(val_rows)}')

    print('5. Добавляем dropdown для выбора недели...')
    add_data_validation(svc)

    print('6. Скрываем вспомогательные строки...')
    hide_rows(svc)

    print('\n✅ Дашборд построен!')
    print(f'   Видимые строки: 1–{TOTAL_VIS}')
    print(f'   Скрытые данные: {H25}–{H26+N-1}')
    print(f'   KPI метрик: {N}')
    print('\nСледующий шаг: добавьте monblan_dashboard.gs в Apps Script')
    print('для AI-анализа (Claude API).')


if __name__ == '__main__':
    main()
