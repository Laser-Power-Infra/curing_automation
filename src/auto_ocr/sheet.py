"""Enters what a photo says into the Google Sheet, by the "Sheet entry" rules in rules.py."""

import re
import threading
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials

from . import rules
from .config import setting

CURING, BOILER = "Curing Log", "Boiler Temp Log"
FUEL = "Boiler Running On (Diesel / Wood)"
_lock = threading.Lock()  # two photos at once must not pick the same new row


def _rows(table: list[list[str]]) -> list[tuple[int, dict]]:
    """(sheet row number, {column: value}) for every row that has something in column A."""
    header = table[0]
    return [
        (n, dict(zip(header, [c.strip() for c in row] + [""] * len(header))))
        for n, row in enumerate(table[1:], start=2)
        if row and row[0].strip()
    ]


def _new_row(rows: list[tuple[int, dict]]) -> int:
    return rows[-1][0] + 1 if rows else 2


def _operator(sender: str | None, people: list[list[str]], notes: list[str]) -> str:
    """Person Master name for the sender's WhatsApp number ('919933773265@s.whatsapp.net')."""
    digits = re.sub(r"\D", "", (sender or "").split("@")[0])[-10:]
    if len(digits) < 10:
        return ""
    for person in people[1:]:
        if len(person) > 2 and re.sub(r"\D", "", person[2])[-10:] == digits:
            return person[0].strip()
    notes.append(f"Operator: sender {digits} is not in {rules.PERSON_SHEET}, left blank")
    return ""


def changes(result: dict, tables: dict[str, list[list[str]]], sender: str | None = None) -> tuple[list[dict], list[str]]:
    """The cells to fill for one photo, and notes about anything left alone. Touches nothing."""
    out: list[dict] = []
    notes: list[str] = []

    def fill(sheet: str, row: int, existing: dict, new: dict) -> None:
        for column, value in new.items():
            old = existing.get(column, "")
            if value and not old:
                out.append({"sheet": sheet, "row": row, "column": column, "value": value})
            elif value and old != value:
                notes.append(f"{sheet} row {row}: {column} is {old!r}, photo says {value!r}; left as it is")

    def recent(row: dict, taken: str) -> bool:
        try:
            age = datetime.strptime(taken, rules.DATE_FORMAT) - datetime.strptime(row["Curing Start Date"], rules.DATE_FORMAT)
        except (KeyError, ValueError):
            return False
        return timedelta(0) <= age <= timedelta(days=rules.SIGN_MATCH_DAYS)

    kind, photo_rows = result.get("kind"), result.get("rows") or []
    curing, boiler = _rows(tables[CURING]), _rows(tables[BOILER])

    if kind == "boiler_temp" and photo_rows:
        new = {**photo_rows[0], "Operator": _operator(sender, tables[rules.PERSON_SHEET], notes)}
        same = [(n, r) for n, r in boiler if (r["Date"], r["Time"]) == (new["Date"], new["Time"])]
        if same:
            fill(BOILER, *same[-1], new)
        else:
            if not new.get(FUEL):
                new[FUEL] = next((r[FUEL] for _, r in reversed(boiler) if r["Date"] == new["Date"] and r[FUEL]), "")
            fill(BOILER, _new_row(boiler), {}, new)

    elif kind == "curing_log":
        row_no = _new_row(curing)
        for new in photo_rows:
            if not (new.get("Lot No") and new.get("Core Drum No")):
                notes.append("Curing Log: lot or drum number not read, nothing entered")
                continue
            key = (new["Lot No"], new["Core Drum No"])
            same = [(n, r) for n, r in curing if (r["Lot No"], r["Core Drum No"]) == key]
            if same:
                fill(CURING, *same[-1], new)
            else:
                fill(CURING, row_no, {}, new)
                row_no += 1

    elif kind == "tank_sign" and photo_rows:
        sign = photo_rows[0]
        if sign.get(FUEL):
            for n, r in boiler:
                if r["Date"] == sign["Date"] and not r[FUEL]:  # fuel can change during a day: blanks only
                    fill(BOILER, n, {}, {FUEL: sign[FUEL]})
        lot = [(n, r) for n, r in curing
               if r["Core Drum No"] == sign["Core Drum No"] and not r["Curing End Date"] and recent(r, sign["Date"])]
        if not lot:
            notes.append(f"{sign['Event'] or 'sign'} photo: no open lot with drum {sign['Core Drum No']!r} in the Curing Log")
        elif sign["Event"] == "OUT":
            fill(CURING, *lot[-1], {"Curing End Date": sign["Date"], "Curing End Time": sign["Time"]})
        elif sign["Event"] == "IN":
            fill(CURING, *lot[-1], {"Chamber / Tank": sign["Chamber / Tank"],
                                    "Curing Start Date": sign["Date"], "Curing Start Time": sign["Time"]})
    return out, notes


def _letter(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA"""
    return (_letter(index // 26 - 1) if index >= 26 else "") + chr(65 + index % 26)


def write(result: dict, sender: str | None = None, dry_run: bool = False) -> dict:
    """Read the sheet, work out the cells to fill, fill them (unless dry_run). Returns what was done."""
    credentials = Credentials.from_service_account_info(
        {
            "client_email": setting("GOOGLE_SERVICE_ACCOUNT_EMAIL"),
            "private_key": setting("GOOGLE_PRIVATE_KEY").replace("\\n", "\n"),
            "token_uri": "https://oauth2.googleapis.com/token",
        },
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    book = gspread.authorize(credentials).open_by_key(rules.SPREADSHEET_ID)
    names = [CURING, BOILER, rules.PERSON_SHEET]
    with _lock:
        tables = dict(zip(names, book.values_batch_get([f"'{n}'" for n in names])["valueRanges"]))
        tables = {n: t.get("values", [[]]) for n, t in tables.items()}
        cells, notes = changes(result, tables, sender)
        if cells and not dry_run:
            data = [
                # RAW would store "23-Nov-26" as text; USER_ENTERED makes it a real date, like typing it.
                {"range": f"'{c['sheet']}'!{_letter(tables[c['sheet']][0].index(c['column']))}{c['row']}",
                 "values": [[c["value"]]]}
                for c in cells
            ]
            book.values_batch_update({"valueInputOption": "USER_ENTERED", "data": data})
    return {"sheet_changes": cells, "notes": notes, "dry_run": dry_run}
