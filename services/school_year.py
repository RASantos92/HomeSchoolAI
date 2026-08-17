"""School year calendar configuration — day-level granularity.

Stores specific calendar dates that are off (holidays, breaks, etc.).
The generation layer works at week granularity (month 1-10, week 1-4); a school
week is treated as vacation if 3+ of its weekday dates are marked off.

Configuration is household-wide (one shared file, not per-student). Backed by
data/school_year_config.json; falls back to Texas 2026-27 defaults when the
file is missing or corrupt.
"""
import calendar as _cal
import datetime
import json
from pathlib import Path

from services import paths

MONTH_NAMES: dict = {
    1: "August",
    2: "September",
    3: "October",
    4: "November",
    5: "December",
    6: "January",
    7: "February",
    8: "March",
    9: "April",
    10: "May",
}

# Maps school month ordinal → (year_offset, calendar_month_number)
# year_offset 0 = school_year_start, 1 = school_year_start + 1
SCHOOL_MONTH_CALENDAR: dict = {
    1:  (0, 8),
    2:  (0, 9),
    3:  (0, 10),
    4:  (0, 11),
    5:  (0, 12),
    6:  (1, 1),
    7:  (1, 2),
    8:  (1, 3),
    9:  (1, 4),
    10: (1, 5),
}

# Texas public school 2026-27 default vacation days
TEXAS_2026_VACATION_DAYS: list = [
    # Labor Day
    {"date": "2026-09-07", "label": "Labor Day"},
    # Thanksgiving break (full week Nov 23-27)
    {"date": "2026-11-23", "label": "Thanksgiving Break"},
    {"date": "2026-11-24", "label": "Thanksgiving Break"},
    {"date": "2026-11-25", "label": "Thanksgiving Break"},
    {"date": "2026-11-26", "label": "Thanksgiving Break"},
    {"date": "2026-11-27", "label": "Thanksgiving Break"},
    # Winter Break (Dec 21 – Jan 2)
    {"date": "2026-12-21", "label": "Winter Break"},
    {"date": "2026-12-22", "label": "Winter Break"},
    {"date": "2026-12-23", "label": "Winter Break"},
    {"date": "2026-12-24", "label": "Winter Break"},
    {"date": "2026-12-25", "label": "Christmas"},
    {"date": "2026-12-28", "label": "Winter Break"},
    {"date": "2026-12-29", "label": "Winter Break"},
    {"date": "2026-12-30", "label": "Winter Break"},
    {"date": "2026-12-31", "label": "Winter Break"},
    {"date": "2027-01-01", "label": "New Year's Day"},
    {"date": "2027-01-02", "label": "Winter Break"},
    # MLK Jr. Day
    {"date": "2027-01-18", "label": "MLK Jr. Day"},
    # Spring Break (week of Mar 15)
    {"date": "2027-03-15", "label": "Spring Break"},
    {"date": "2027-03-16", "label": "Spring Break"},
    {"date": "2027-03-17", "label": "Spring Break"},
    {"date": "2027-03-18", "label": "Spring Break"},
    {"date": "2027-03-19", "label": "Spring Break"},
    # Good Friday
    {"date": "2027-03-26", "label": "Good Friday"},
    # Memorial Day
    {"date": "2027-05-31", "label": "Memorial Day"},
]


def default_config() -> dict:
    return {
        "school_year_start": 2026,
        "first_day": "2026-08-17",
        "last_day": "2027-05-28",
        "vacation_days": list(TEXAS_2026_VACATION_DAYS),
    }


def load_config() -> dict:
    path: Path = paths.school_year_config_file()
    try:
        data = json.loads(path.read_text())
        if "vacation_days" not in data:
            return default_config()
        data.setdefault("school_year_start", 2026)
        return data
    except Exception:
        return default_config()


def save_config(config: dict) -> None:
    path: Path = paths.school_year_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def get_vacation_dates(config: dict) -> set:
    """Returns the set of ISO date strings (YYYY-MM-DD) that are marked off."""
    return {vd["date"] for vd in config.get("vacation_days", [])}


def is_vacation_day(config: dict, date_str: str) -> bool:
    return date_str in get_vacation_dates(config)


def school_month_to_calendar_month(school_month: int) -> int:
    """Convert a school-year month ordinal (1-10, Aug=1...May=10) into the
    real calendar month (1-12) empowerHSA's month_number expects.

    empowerHSA's YearlyBreakdown assigns month_number sequentially from the
    real calendar month it was first called in (wrapping after 12), not from
    a 1-10 school-year ordinal - callers must translate before every
    Parent/API call that takes a month, or requests silently target the
    wrong month (or 404 for school months 6/7, which map to literal June/July,
    never generated since the school year skips summer)."""
    _, cal_month = SCHOOL_MONTH_CALENDAR[school_month]
    return cal_month


def _week_weekdays(config: dict, school_month: int, school_week: int) -> list:
    """Return ISO date strings for Mon-Fri that fall in the given school week.

    Week 1 = days 1-7 of the calendar month, week 2 = days 8-14, etc.
    Only weekdays (Mon-Fri) are included.
    """
    year_start = config.get("school_year_start", 2026)
    year_offset, cal_month = SCHOOL_MONTH_CALENDAR[school_month]
    year = year_start + year_offset
    day_start = (school_week - 1) * 7 + 1
    day_end = min(school_week * 7, _cal.monthrange(year, cal_month)[1])
    result = []
    for day in range(day_start, day_end + 1):
        d = datetime.date(year, cal_month, day)
        if d.weekday() < 5:
            result.append(d.isoformat())
    return result


def is_vacation_week(config: dict, school_month: int, school_week: int) -> bool:
    """True when 3 or more weekdays in the school week are marked as vacation."""
    vac = get_vacation_dates(config)
    days = _week_weekdays(config, school_month, school_week)
    if not days:
        return False
    return sum(1 for d in days if d in vac) >= min(3, len(days))


def get_school_weeks(config: dict) -> list:
    """All (school_month, school_week) pairs that are NOT vacation weeks."""
    return [
        (m, w)
        for m in range(1, 11)
        for w in range(1, 5)
        if not is_vacation_week(config, m, w)
    ]


def vacation_label(config: dict, date_str: str) -> str:
    """Returns the stored label for a specific vacation date, or ''."""
    for vd in config.get("vacation_days", []):
        if vd["date"] == date_str:
            return vd.get("label", "")
    return ""


def date_to_school_coords(config: dict, target_date: datetime.date):
    """Map a calendar date to (school_month, school_week), or None if outside all school months."""
    year_start = config.get("school_year_start", 2026)
    for school_month, (year_offset, cal_month) in SCHOOL_MONTH_CALENDAR.items():
        year = year_start + year_offset
        if target_date.year == year and target_date.month == cal_month:
            school_week = min((target_date.day - 1) // 7 + 1, 4)
            return (school_month, school_week)
    return None


def is_school_day(config: dict, target_date: datetime.date) -> bool:
    """True if target_date is a weekday within [first_day, last_day] and not a vacation day."""
    try:
        first = datetime.date.fromisoformat(config.get("first_day", "2026-08-17"))
        last = datetime.date.fromisoformat(config.get("last_day", "2027-05-28"))
    except ValueError:
        return False
    if not (first <= target_date <= last):
        return False
    if target_date.weekday() >= 5:
        return False
    return not is_vacation_day(config, target_date.isoformat())


def next_school_day(config: dict, from_date: datetime.date):
    """Return the next school day on or after from_date, or None if past last_day."""
    try:
        last = datetime.date.fromisoformat(config.get("last_day", "2027-05-28"))
    except ValueError:
        return None
    d = from_date
    while d <= last:
        if is_school_day(config, d):
            return d
        d += datetime.timedelta(days=1)
    return None


def get_smart_week(config: dict) -> tuple:
    """Return (school_month, school_week) to pre-fill the weekly breakdown form.

    Uses today's week when school is in session; falls back to the first (or last)
    non-vacation week when school hasn't started (or has ended); advances past
    vacation weeks automatically.
    """
    school_weeks = get_school_weeks(config)
    if not school_weeks:
        return (1, 1)
    try:
        first = datetime.date.fromisoformat(config.get("first_day", "2026-08-17"))
        last = datetime.date.fromisoformat(config.get("last_day", "2027-05-28"))
    except ValueError:
        return school_weeks[0]

    today = datetime.date.today()
    if today < first:
        return school_weeks[0]
    if today > last:
        return school_weeks[-1]

    coords = date_to_school_coords(config, today)
    if not coords:
        return school_weeks[0]

    school_month, school_week = coords
    all_weeks = [(m, w) for m in range(1, 11) for w in range(1, 5)]
    try:
        start_idx = all_weeks.index((school_month, school_week))
    except ValueError:
        start_idx = 0

    for m, w in all_weeks[start_idx:]:
        if not is_vacation_week(config, m, w):
            return (m, w)

    return school_weeks[-1]


def get_smart_day(config: dict):
    """Return (school_month, school_week, day_name) for the current or next school day.

    Returns None if today is past the last day of school.
    """
    _DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    today = datetime.date.today()
    target = next_school_day(config, today)
    if not target:
        return None
    coords = date_to_school_coords(config, target)
    if not coords:
        return None
    school_month, school_week = coords
    day_name = _DAY_NAMES[target.weekday()]
    return (school_month, school_week, day_name)
