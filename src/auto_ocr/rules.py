"""Every business rule lives in this file. Change a rule here, nowhere else.

Sections:
  1. Which photo goes to which sheet
  2. Sheet columns (and which ones stay blank)
  3. Naming and formats
  4. Reading (Morning / Afternoon / Night)
  5. Sheet entry (when a row is added, when a cell is filled)
  6. Product list
  7. Instructions given to the AI model
  8. Hour meter group (its sheet entry rules and AI instructions)
"""

from datetime import datetime, time

MODEL = "claude-opus-5-5"

# ── 1. Which photo goes to which sheet ──────────────────────────────────────
# tank_sign has no sheet of its own: it feeds Curing Log (start time, tank) and
# Boiler Temp Log (fuel) once photos are combined in the sheet-writing step.
SHEET_FOR_KIND = {
    "curing_log": "Curing Log",
    "boiler_temp": "Boiler Temp Log",
    "tank_sign": None,
}

# ── 2. Sheet columns ────────────────────────────────────────────────────────
# Columns the system fills. Anything not listed is left blank:
#   - every "(auto)" column (the sheet calculates those)
#   - Curing Log: XLPE Compound, Visual Check, Sent Date, Remarks, MD Remarks
#   - Boiler Temp Log: Operator, Remarks
CURING_COLUMNS = [
    "Lot No",
    "Core Production Date",  # = the date written on the page
    "Product",
    "Core Drum No",
    "Length (m)",
    "Chamber / Tank",
    "Curing Start Date",  # = In time on the page
    "Curing Start Time",
]
# Curing End Date / Time are not read from the page: see section 5.
BOILER_COLUMNS = [
    "Date",  # = when the photo was taken
    "Time",
    "Reading (Morning / Afternoon / Night)",
    "Water Tank 1 Temp °C",
    "Water Tank 2 Temp °C",
    "Water Tank 3 Temp °C",
    "Boiler Running On (Diesel / Wood)",  # only if the photo shows it
    "Operator",  # who sent the photo, see section 5
]

# ── 3. Naming and formats ───────────────────────────────────────────────────
TANK_NAME = "Water Tank {n}"  # "Chamber 1" / "TRANK -1" -> "Water Tank 1"
# If the handwritten chamber and the printed tank sign disagree, the sign wins.
DATE_FORMAT = "%d-%b-%y"  # 20-Nov-26
# Drum number keeps digits only: "914-L" -> "914". One sheet row per drum.
# Length = all lengths written for that drum added up: 2020 + 507 = 2527.


def format_time(t: datetime) -> str:
    return t.strftime("%I:%M %p").lstrip("0").lower()  # 1:53 am


# ── 4. Reading ──────────────────────────────────────────────────────────────
def reading_for(t: time) -> str:
    if time(4, 0) <= t < time(12, 0):
        return "Morning"
    if time(12, 0) <= t < time(19, 0):
        return "Afternoon"
    return "Night"


# ── 5. Sheet entry ──────────────────────────────────────────────────────────
SPREADSHEET_ID = "1GgRE8r_r75vQt4ZZlFMlPCDkkVf1DJZrlfosT0Mc_bI"
# General
#   - A filled cell is never changed. Only empty cells are filled.
#   - If a photo says something different from a filled cell, the cell stays and the
#     difference is logged (photos/results.jsonl).
#   - "(auto)" columns are never written, also not on a new row.
# Boiler Temp Log
#   - Panel photo: a new row, unless a row with the same Date and Time is already there.
#   - Boiler Running On of a new row: copied from the latest row of the same date that has it.
#   - Tank sign photo (WOOD FIRE / diesel): fills every empty Boiler Running On of that date.
#   - Operator: the person who sent the photo. Their WhatsApp number is looked up in the
#     Person Master sheet and that name is written; an unknown number leaves it blank.
# Curing Log
#   - Notebook page: one row per drum, found by Lot No + Core Drum No. Not there: new row.
#     There: only its empty cells are filled.
#   - The page never fills Curing End. The OUT sign photo does: its photo time goes into the
#     latest row with that drum number and an empty Curing End (also a row of an earlier day).
#   - The IN sign photo fills Chamber / Tank and Curing Start of that row if they are empty.
SIGN_MATCH_DAYS = 7  # a sign photo only matches a lot that went in within this many days
PERSON_SHEET = "Person Master"  # column A name, column C WhatsApp number (10 digits)


# ── 6. Product list ─────────────────────────────────────────────────────────
# shortcut: copied from the Product Master sheet, read it live when sheet writing is added
PRODUCTS = [
    "100 SQMM 11KV (N)",
    "100 SQMM 11KV (IS)",
    "55 SQMM 11KV (N)",
    "120 SQMM 11KV (IS)",
    "ACS Dog AL-59 11KV (IS)",
    "ACS Dog AL-59 33KV (IS)",
    "ACS Rabbit AL-59 11KV",
    "ACS Raccoon AL-59 11KV",
    "1C X 150 SQMM 33KV (IS)",
    "1C X 232 SQMM 33KV (IS)",
    "1C X 241 SQMM 33KV (IS)",
    "3C X 300 SQMM 11KV (N)",
    "3C X 300 SQMM 11KV (IS)",
    "3C X 300 SQMM 33KV (N)",
    "3C X 300 SQMM 33KV (IS)",
    "3C X 400 SQMM 11KV (N)",
    "3 X 400 SQMM 33KV (N)",
    "3C X 300 SQMM 11KV (N) strip",
    "1C X 630 SQMM 11 KV (N)",
    "1C X 630 SQMM 11 KV (IS) strip",
    "1C X 630 SQMM 11 KV (N) strip",
    "1C X 630 SQMM 33 KV (N) ",
]

# ── 6b. Dropdown columns ────────────────────────────────────────────────────
# These sheet columns only accept a value from their dropdown. A value read from a
# photo that is not in the list is left blank and reported, never written as-is.
DROPDOWNS = {
    "Product": PRODUCTS,
    "Chamber / Tank": ["Autoclave", "Water Tank 1", "Water Tank 2", "Water Tank 3"],
    "Reading (Morning / Afternoon / Night)": ["Morning", "Afternoon", "Night"],
    "Boiler Running On (Diesel / Wood)": ["Diesel", "Wood"],
    # Not filled by the system, listed so the rule is in one place:
    "XLPE Compound": ["Kalpana", "Laser In-house", "Laser Special"],
    "Visual Check": ["OK", "Damage", "Not checked"],
    # "Operator": names in the Person Master sheet
}
TEMP_RANGE = (0, 150)  # the sheet rejects tank temperatures outside this

# ── 7. Instructions given to the AI model ───────────────────────────────────
PROMPT = f"""This photo comes from a cable factory's XLPE curing area. Read it and fill the fields.

First decide `kind`:
- "curing_log": a handwritten notebook page for one curing lot.
- "boiler_temp": a panel with three red digital temperature displays labelled 1, 2 and 3.
- "tank_sign": a water tank with printed signs in front of it (drum number, tank number, fuel, IN/OUT).
- "unknown": anything else.

Fill only the fields for that kind and leave every other field null.
Never guess: if something is not written, or its heading is there but the value under it is
empty, return null (for a text field, an empty string ""). If you can read a value but are not sure of it, still return your best
reading and add the field name to `uncertain`.
Dates are written day/month/year. Return dates as YYYY-MM-DD and times as 24-hour HH:MM.
A field that holds a date and a time is "YYYY-MM-DD HH:MM", or just "HH:MM" if no date is written.

curing_log:
- page_date: the date at the top of the page.
- lot_no: the number after "LOT".
- tank_no: the number after "Chamber". If it was overwritten, read the final value and list it in `uncertain`.
- product: the page gives size, type and voltage, e.g. "300 sq.mm (N) (33 KV)". Return the one
  name from this list that matches the size, type (N / IS) and voltage. If none
  or more than one fits, return "" and list "product" in `uncertain`.
{chr(10).join("  - " + repr(p) for p in PRODUCTS)}
- in_time: under "In time".
- temp90: date and time under "90°C" (when the tank reached 90°C).
- hours: the planned curing hours.
- off: date and time under "Off" (written "O/F").
- drums: one entry per drum, with every length in metres written for it
  ("Drum 914-L 2020 mtr + 507 mtr" is drum_no "914-L" with lengths [2020, 507]).

boiler_temp:
- temp_1, temp_2, temp_3: the red reading next to the label 1, 2 and 3. Match by label, not by
  position. Ignore the small dot or "R" mark after the digits.
- fuel: only if the photo itself shows Wood or Diesel.

tank_sign:
- drum_no: the drum number sign.
- tank_no: the number on the tank sign (it may be misspelt, e.g. "TRANK -1").
- fuel: "WOOD FIRE" is Wood; a diesel sign is Diesel.
- event: the "IN" or "OUT" sign."""


# ── 8. Hour meter group (LASER HOUR METER UPDATE) ───────────────────────────
# Photos of forklift / hydra / DG-set hour meters go into one sheet: one row per day
# (column A), one column per machine (row 1 name, row 2 equipment ID).
HOURS_SPREADSHEET_ID = "15sZGLWLzASpdcUOXdr98B7x7TmvBzDmyee-hgtRzYGM"
HOURS_SHEET = "LASER EQUIPMENT READING"
# The machine is named in the caption, or in a text the same person sends within this many
# seconds before or after the photo, or written on the machine itself.
TEXT_WINDOW = 60
# Sheet entry
#   - Row: the date the photo was sent (India time). No row for that date yet: a new row is
#     added under the last one.
#   - Only an empty cell is filled. A second photo of the same machine that day is logged,
#     not written (the first reading of the day stays).
#   - A reading lower than that machine's last reading, or more than 24 hours a day above it,
#     is not written (looks misread, e.g. 12044.3 for 1204.3).
#   - If the machine's last values are all whole numbers, the reading is written without its
#     tenths (Hydra 4244.5 -> 4244); otherwise as the meter shows it.
WHOLE_NUMBER_CHECK = 5  # how many of the machine's last values decide "whole numbers"

HOURS_PROMPT = """This photo was posted in a factory WhatsApp group where people send the hour meter
reading of a machine (forklift, hydra crane, DG set, boiler, hired vehicle).

Return:
- equipment_id: the machine, as one ID from the list below. People name it in the message text
  ("FL 22", "F . L . 8", "Forklift No-19", "35 NOF" = forklift 35, "Hydra 5", "Haider 5" = Hydra 5,
  "FOR clip 25" = forklift 25) or write the ID on the machine (e.g. "U1DG000007" in marker).
  Forklift N means the machine named "FORKLIFT NO. N"; its ID number is different from N.
  If you cannot tell which machine it is, return "" and list "equipment_id" in `uncertain`.
- reading: the total hours on the meter, with its decimals: an LCD with a "1/10" box (5469.6), a
  mechanical counter whose last (often red) wheel is tenths (4244.5), or a DG panel "Eng Hrs"
  (640.97). Ignore clocks, dates printed by the camera, fuel and pressure gauges. If the screen is
  unreadable but the message text gives the hours (e.g. "1686.33 hrs"), use the text.
  If there is no reading, return null and list "reading" in `uncertain`.
- uncertain: names of fields you are not sure of.

Machines (ID | name | location):
{equipment}

Message text sent with the photo:
{text}"""
