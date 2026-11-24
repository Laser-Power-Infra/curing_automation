"""Hour meter group: photo (+ the text sent with it) -> one cell of LASER EQUIPMENT READING.

The rules are in rules.py, section 8.
"""

import threading
from datetime import date, datetime
from pathlib import Path

from . import rules
from .extract import extract_hours
from .sheet import open_book

HEADER_ROWS = 4  # name, equipment ID, location, "DATE"
_lock = threading.Lock()  # two photos at once must not both add the day's row


# ── Which text belongs to a photo ───────────────────────────────────────────
def _sender(m: dict) -> str:
    return m["key"].get("participant") or m["key"].get("participantAlt") or m.get("pushName") or ""


def _text(m: dict) -> str:
    msg = m.get("message") or {}
    return msg.get("conversation") or (msg.get("extendedTextMessage") or {}).get("text") or ""


def _caption(m: dict) -> str:
    return ((m.get("message") or {}).get("imageMessage") or {}).get("caption") or ""


def text_for(photo: dict, messages: list[dict]) -> str:
    """The photo's caption, plus each text the same person sent within TEXT_WINDOW seconds whose
    nearest photo is this one (so 2 photos each followed by a text get the right text)."""
    t0, who = int(photo["messageTimestamp"]), _sender(photo)
    mine = [m for m in messages if _sender(m) == who and abs(int(m["messageTimestamp"]) - t0) <= rules.TEXT_WINDOW]
    photos = [m for m in mine if m.get("messageType") == "imageMessage" and m["key"]["id"] != photo["key"]["id"]] + [photo]
    # the text typed on the photo itself; from Evolution's stored copy if the webhook copy lacks it
    parts = [next((_caption(m) for m in [photo, *messages] if m["key"]["id"] == photo["key"]["id"] and _caption(m)), "")]
    for m in mine:
        if not _text(m):
            continue
        t = int(m["messageTimestamp"])
        # nearest photo; on a tie the one sent before the text (people send the photo, then type)
        nearest = min(photos, key=lambda p: (abs(int(p["messageTimestamp"]) - t), int(p["messageTimestamp"]) > t))
        if nearest is photo:
            parts.append(_text(m))
    return "\n".join(p.strip() for p in parts if p.strip())


# ── Reading the photo ───────────────────────────────────────────────────────
def _table() -> list[list[str]]:
    return open_book(rules.HOURS_SPREADSHEET_ID).worksheet(rules.HOURS_SHEET).get_all_values()


def equipment(table: list[list[str]]) -> str:
    """'ID | name | location' for every machine column."""
    names, ids, places = (table[i] + [""] * len(table[1]) for i in range(3))
    return "\n".join(f"{ids[c].strip()} | {' '.join(names[c].split())} | {' '.join(places[c].split())}"
                     for c in range(1, len(table[1])) if ids[c].strip())


def read(image: Path, text: str) -> dict:
    x = extract_hours(image, text, equipment(_table()))
    return {"file": image.name, "kind": "hour_meter", "sheet": rules.HOURS_SHEET, "text": text,
            "rows": [{"equipment_id": x.equipment_id.strip(), "reading": x.reading}], "uncertain": x.uncertain}


# ── Sheet entry ─────────────────────────────────────────────────────────────
def _day(cell: str) -> date | None:
    try:
        return datetime.strptime(cell.strip(), rules.DATE_FORMAT).date()
    except ValueError:
        return None


def _number(cell: str) -> float | None:
    try:
        return float(cell.replace(",", ""))
    except ValueError:
        return None


def _letter(index: int) -> str:
    return (_letter(index // 26 - 1) if index >= 26 else "") + chr(65 + index % 26)


def changes(found: dict, table: list[list[str]], day: date) -> tuple[list[dict], list[str]]:
    """The cell to fill for one reading, and notes about anything left alone. Touches nothing."""
    machine, reading = found.get("equipment_id", ""), found.get("reading")
    ids = [c.strip().upper() for c in table[1]]
    if not machine or machine.upper() not in ids[1:]:
        return [], [f"machine {machine!r} is not in row 2 of {rules.HOURS_SHEET}, nothing entered"]
    if reading is None:
        return [], [f"{machine}: no reading on the photo, nothing entered"]
    col = ids.index(machine.upper(), 1)

    days = [(n, _day(row[0])) for n, row in enumerate(table, 1) if n > HEADER_ROWS and row and _day(row[0])]
    row_no = next((n for n, d in days if d == day), None)
    cells = []
    if row_no is None:
        row_no = len(table) + 1
        cells.append({"sheet": rules.HOURS_SHEET, "row": row_no, "column": "DATE", "cell": f"A{row_no}",
                      "value": day.strftime(rules.DATE_FORMAT)})
    history = [(d, table[n - 1][col]) for n, d in days if n < row_no and d < day and len(table[n - 1]) > col
               and _number(table[n - 1][col]) is not None]
    earlier = [v for _, v in history]
    whole = len(earlier) >= rules.WHOLE_NUMBER_CHECK and all("." not in v for v in earlier[-rules.WHOLE_NUMBER_CHECK:])
    value = str(int(reading)) if whole else str(round(reading, 2))

    old = table[row_no - 1][col].strip() if row_no <= len(table) and len(table[row_no - 1]) > col else ""
    if old:
        note = [] if _number(old) == _number(value) else [
            f"{machine} on {day:%d-%b-%y} is already {old!r}, photo says {value!r}; left as it is"]
        return [], note
    if history:
        last_day, last = history[-1]
        if not _number(last) <= reading <= _number(last) + 24 * (day - last_day).days:
            return [], [f"{machine}: photo says {reading}, last reading {last} on {last_day:%d-%b-%y}; looks misread, left blank"]
    cells.append({"sheet": rules.HOURS_SHEET, "row": row_no, "column": machine, "cell": f"{_letter(col)}{row_no}", "value": value})
    return cells, []


def write(result: dict, day: date, dry_run: bool = False) -> dict:
    """Read the tab, work out the cell to fill, fill it (unless dry_run). Returns what was done."""
    sheet = open_book(rules.HOURS_SPREADSHEET_ID).worksheet(rules.HOURS_SHEET)
    with _lock:
        cells, notes = changes(result["rows"][0], sheet.get_all_values(), day)
        if cells and not dry_run:
            # USER_ENTERED: the date becomes a real date and the reading a number, like typing it
            sheet.batch_update([{"range": c["cell"], "values": [[c["value"]]]} for c in cells], value_input_option="USER_ENTERED")
    return {"sheet_changes": cells, "notes": notes, "dry_run": dry_run}
