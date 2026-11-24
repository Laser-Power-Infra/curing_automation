"""Turns the raw fields read from a photo into sheet rows, by applying rules.py."""

import re
from datetime import datetime, timedelta

from . import rules


def photo_time(filename: str) -> datetime | None:
    """'WhatsApp Image 2026-11-20 at 11.24.23 AM.jpeg' -> 2026-11-20 11:24:23"""
    m = re.search(r"(\d{4}-\d{2}-\d{2}) at (\d{1,2}\.\d{2}\.\d{2} [AP]M)", filename)
    return datetime.strptime(" ".join(m.groups()), "%Y-%m-%d %I.%M.%S %p") if m else None


def _at(when: str | None, not_before: datetime | None = None) -> datetime | None:
    """'YYYY-MM-DD HH:MM' as read. A bare 'HH:MM' means the first such time after `not_before`."""
    if not when or not (" " in when or not_before):
        return None
    if " " in when:
        return datetime.strptime(when, "%Y-%m-%d %H:%M")
    t = datetime.combine(not_before.date(), datetime.strptime(when, "%H:%M").time())
    return t if t >= not_before else t + timedelta(days=1)


def _stamp(t: datetime | None) -> tuple[str, str]:
    return (t.strftime(rules.DATE_FORMAT), rules.format_time(t)) if t else ("", "")


def _dropdown(x, column: str, value) -> str:
    """The dropdown's own spelling of `value`, or blank (and reported) if it is not an option."""
    if value in (None, ""):
        return ""
    for option in rules.DROPDOWNS[column]:
        if option.strip() == str(value).strip():
            return option
    x.uncertain.append(f"{column}: {value!r} is not in the dropdown, left blank")
    return ""


def _tank(x) -> str:
    name = rules.TANK_NAME.format(n=x.tank_no) if x.tank_no is not None else ""
    return _dropdown(x, "Chamber / Tank", name)


def _temp(x, n: int) -> str:
    value, (low, high) = getattr(x, f"temp_{n}"), rules.TEMP_RANGE
    if value is None:
        return ""
    if not low <= value <= high:
        x.uncertain.append(f"Water Tank {n} Temp: {value} is outside {low}-{high}, left blank")
        return ""
    return str(value)


def curing_rows(x) -> list[dict]:
    page_date = x.page_date and datetime.strptime(x.page_date, "%Y-%m-%d")
    start = _at(x.in_time, page_date)
    end = _at(x.off, _at(x.temp90, start) or start)  # Off = 90°C time + hours, so a bare time comes after it
    values = {
        "Lot No": x.lot_no or "",
        "Core Production Date": _stamp(page_date)[0],
        "Product": _dropdown(x, "Product", x.product),
        "Chamber / Tank": _tank(x),
        "Curing Start Date": _stamp(start)[0],
        "Curing Start Time": _stamp(start)[1],
        "Curing End Date": _stamp(end)[0],
        "Curing End Time": _stamp(end)[1],
    }
    rows = []
    for drum in x.drums or [None]:
        if drum:
            values["Core Drum No"] = re.sub(r"\D", "", drum.drum_no)
            values["Length (m)"] = f"{sum(drum.lengths_m):g}"
        rows.append({col: values.get(col, "") for col in rules.CURING_COLUMNS})
    return rows


def boiler_row(x, taken_at: datetime) -> dict:
    date, clock = _stamp(taken_at)
    fuel = _dropdown(x, "Boiler Running On (Diesel / Wood)", x.fuel)
    # Operator is filled at sheet entry, from who sent the photo.
    values = [date, clock, rules.reading_for(taken_at.time()), *(_temp(x, n) for n in (1, 2, 3)), fuel, ""]
    return dict(zip(rules.BOILER_COLUMNS, values))


def tank_record(x, taken_at: datetime) -> dict:
    """Not a sheet row: what a tank sign photo says, for the later combining step."""
    date, clock = _stamp(taken_at)
    return {
        "Event": x.event or "",
        "Date": date,
        "Time": clock,
        "Core Drum No": re.sub(r"\D", "", x.drum_no or ""),
        "Chamber / Tank": _tank(x),
        "Boiler Running On (Diesel / Wood)": _dropdown(x, "Boiler Running On (Diesel / Wood)", x.fuel),
    }
