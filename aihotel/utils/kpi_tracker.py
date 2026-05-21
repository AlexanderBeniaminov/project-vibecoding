import os
import datetime

SEASON_START_WEEK = 14   # апрель 2026
JUNE_DEADLINE = datetime.date(2026, 6, 30)
NOVEMBER_DEADLINE = datetime.date(2026, 11, 30)
SEASON_TOTAL_WEEKS = 30  # апрель–ноябрь ~30 недель

KPI_TARGETS = {
    'loading_marketing': 12.0,    # KPI-1
    'loading_project':   19.8,    # KPI-2
    'margin_pct':        8.0,     # KPI-3
    'revenue_rub':       15_369_000,  # KPI-4
    'dr_packages':       125,     # KPI-5
    'group_stays':       6,       # KPI-6
    'travelline_rating': 4.4,     # KPI-7
}

ROW_WEEK_NUMBERS = 2
ROW_REVENUE_CHECK = 6
ROW_REVENUE   = 6
ROW_LOADING   = 47
ROW_DR        = 67
ROW_GROUPS    = 77


def _parse_num(value):
    if not value:
        return None
    cleaned = str(value).replace(' ', '').replace('\xa0', '').replace(',', '.').replace('%', '')
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _weeks_left(deadline: datetime.date) -> int:
    return max(0, (deadline - datetime.date.today()).days // 7)


def _icon(fact, target, tolerance=0.90):
    if fact >= target:
        return '✅'
    if fact >= target * tolerance:
        return '🟡'
    return '🔴'


def build_kpi_progress_block(sheets_client) -> str:
    finance_sheet_id = os.environ['FINANCE_SHEET_ID']

    try:
        ws = sheets_client.open_by_key(finance_sheet_id).worksheet('2026 старый')
        all_values = ws.get_all_values()
    except Exception as e:
        return f"⚠️ KPI-данные недоступны: {e}"

    if len(all_values) < ROW_GROUPS:
        return "⚠️ KPI-данные: таблица короче ожидаемого."

    week_row    = all_values[ROW_WEEK_NUMBERS - 1]
    rev_check   = all_values[ROW_REVENUE_CHECK - 1]
    revenue_row = all_values[ROW_REVENUE - 1]
    loading_row = all_values[ROW_LOADING - 1]
    dr_row      = all_values[ROW_DR - 1]
    groups_row  = all_values[ROW_GROUPS - 1]

    # Колонки с данными начиная с недели 14
    season_cols = []
    for i, cell in enumerate(week_row):
        num = str(cell).strip().replace('\xa0', '').replace(' ', '')
        if num.isdigit() and int(num) >= SEASON_START_WEEK:
            if i < len(rev_check) and _parse_num(rev_check[i]) is not None:
                season_cols.append(i)

    if not season_cols:
        return "⚠️ KPI-данные: нет данных с начала сезона (апрель 2026)."

    last_col = season_cols[-1]
    n_weeks  = len(season_cols)

    def col_vals(row, cols):
        return [v for v in [_parse_num(row[c]) for c in cols if c < len(row)] if v is not None]

    loading_vals   = col_vals(loading_row, season_cols)
    avg_loading    = sum(loading_vals) / len(loading_vals) if loading_vals else None
    revenue_total  = sum(col_vals(revenue_row, season_cols))
    dr_total       = int(sum(col_vals(dr_row, season_cols)))
    groups_total   = int(sum(col_vals(groups_row, season_cols)))

    today          = datetime.date.today()
    iso_week       = today.isocalendar()[1]
    weeks_to_june  = _weeks_left(JUNE_DEADLINE)
    weeks_to_nov   = _weeks_left(NOVEMBER_DEADLINE)

    lines = [
        f"📊 ПРОГРЕСС KPI (неделя {iso_week}, {today.strftime('%d.%m.%Y')})",
        f"Данных за сезон: {n_weeks} нед. | К июню осталось: {weeks_to_june} нед. | К ноябрю: {weeks_to_nov} нед.",
        "",
    ]

    # KPI-1 — Загрузка (маркетинг)
    t1 = KPI_TARGETS['loading_marketing']
    if avg_loading is not None:
        gap1 = t1 - avg_loading
        lines.append(
            f"KPI-1 Загрузка (маркетинг):     ср. {avg_loading:.1f}% | цель {t1}% | {_icon(avg_loading, t1)} | "
            + (f"отстаём {gap1:.1f}%" if gap1 > 0 else f"опережаем {abs(gap1):.1f}%")
        )
    else:
        lines.append(f"KPI-1 Загрузка (маркетинг):     н/д | цель {t1}%")

    # KPI-2 — Загрузка (проектная группа)
    t2 = KPI_TARGETS['loading_project']
    if avg_loading is not None:
        gap2 = t2 - avg_loading
        lines.append(
            f"KPI-2 Загрузка (проект-группа): ср. {avg_loading:.1f}% | цель {t2}% | {_icon(avg_loading, t2)} | "
            + (f"отстаём {gap2:.1f}%" if gap2 > 0 else f"опережаем {abs(gap2):.1f}%")
        )
    else:
        lines.append(f"KPI-2 Загрузка (проект-группа): н/д | цель {t2}%")

    # KPI-3 — Рентабельность (нет в таблице напрямую)
    lines.append(f"KPI-3 Операц. маржа:            н/д | цель {KPI_TARGETS['margin_pct']}% | — (смотри дайджест)")

    # KPI-4 — Выручка накопленная
    t4 = KPI_TARGETS['revenue_rub']
    if revenue_total > 0:
        pct_of_target  = revenue_total / t4 * 100
        expected_pct   = n_weeks / SEASON_TOTAL_WEEKS * 100
        on_track = '✅' if pct_of_target >= expected_pct * 0.9 else ('🟡' if pct_of_target >= expected_pct * 0.75 else '🔴')
        lines.append(
            f"KPI-4 Выручка накопл.:          {revenue_total/1_000_000:.2f}М / {t4/1_000_000:.1f}М | "
            f"{pct_of_target:.0f}% цели | {on_track} (ожид. {expected_pct:.0f}%)"
        )
    else:
        lines.append(f"KPI-4 Выручка накопл.:          н/д | цель {t4/1_000_000:.1f}М")

    # KPI-5 — Пакеты ДР
    t5 = KPI_TARGETS['dr_packages']
    needed_dr = (t5 - dr_total) / weeks_to_june if weeks_to_june > 0 else float('inf')
    lines.append(
        f"KPI-5 Пакеты ДР:                факт {dr_total} / цель {t5} | {_icon(dr_total, t5)} | "
        f"нужно {needed_dr:.1f}/нед к июню"
    )

    # KPI-6 — Групповые заезды
    t6 = KPI_TARGETS['group_stays']
    needed_gr = (t6 - groups_total) / weeks_to_june if weeks_to_june > 0 else float('inf')
    lines.append(
        f"KPI-6 Групп. заезды:            факт {groups_total} / цель {t6} | {_icon(groups_total, t6)} | "
        f"нужно {needed_gr:.2f}/нед к июню"
    )

    # KPI-7 — Рейтинг TravelLine
    lines.append(
        f"KPI-7 Рейтинг TravelLine:       н/д | цель {KPI_TARGETS['travelline_rating']}+ | — | {weeks_to_nov} нед. к ноябрю"
    )

    return "\n".join(lines)
