from auto_ocr import rules, sheet

FUEL = sheet.FUEL
CURING_HEAD = ["Lot No", "Core Production Date", "Product", "Voltage (auto)", "Core Drum No", "Length (m)",
               "Chamber / Tank", "Curing Start Date", "Curing Start Time", "Curing End Date", "Curing End Time"]
BOILER_HEAD = ["Date", "Time", "Reading (Morning / Afternoon / Night)", "Water Tank 1 Temp °C",
               "Water Tank 2 Temp °C", "Water Tank 3 Temp °C", FUEL, "Operator", "Remarks"]


def tables(curing=(), boiler=()):
    return {
        "Curing Log": [CURING_HEAD, *curing],
        "Boiler Temp Log": [BOILER_HEAD, *boiler],
        rules.PERSON_SHEET: [["Name", "Role", "WhatsApp No."], ["Pravas", "Operator", "9933773265"]],
    }


def cells(found):
    return {(c["sheet"], c["row"], c["column"]): c["value"] for c in found[0]}


PANEL = {"kind": "boiler_temp",
         "rows": [dict(zip(rules.BOILER_COLUMNS, ["23-Nov-26", "8:29 am", "Morning", "95", "95", "95", "", ""]))]}
LOT_479 = ["479", "21-Nov-26", "3C X 300 SQMM 33KV (N)", "33KV", "887", "3047", "Water Tank 2", "21-Nov-26", "7:00 am"]
PAGE = {"kind": "curing_log",
        "rows": [{"Lot No": "479", "Core Production Date": "21-Nov-26", "Product": "3C X 300 SQMM 33KV (N)",
                  "Core Drum No": "887", "Length (m)": "3047", "Chamber / Tank": "Water Tank 3",
                  "Curing Start Date": "21-Nov-26", "Curing Start Time": "7:00 am"}]}


def sign(event, date, time, drum="887", fuel="Wood"):
    return {"kind": "tank_sign", "rows": [{"Event": event, "Date": date, "Time": time, "Core Drum No": drum,
                                           "Chamber / Tank": "Water Tank 2", FUEL: fuel}]}


def test_panel_photo_adds_a_row_once_with_the_sender_as_operator():
    earlier = ["23-Nov-26", "6:00 am", "Morning", "90", "90", "90", "Wood", "Pravas"]
    new = cells(sheet.changes(PANEL, tables(boiler=[earlier]), "919933773265@s.whatsapp.net"))
    assert new[("Boiler Temp Log", 3, "Water Tank 1 Temp °C")] == "95"
    assert new[("Boiler Temp Log", 3, "Operator")] == "Pravas"
    assert new[("Boiler Temp Log", 3, FUEL)] == "Wood"  # copied from the same day's earlier row

    already = ["23-Nov-26", "8:29 am", "Morning", "95", "95", "95", "", "Pravas"]
    assert sheet.changes(PANEL, tables(boiler=[already]), "919933773265@s.whatsapp.net") == ([], [])

    unknown = sheet.changes(PANEL, tables(), "911111111111@s.whatsapp.net")
    assert ("Boiler Temp Log", 2, "Operator") not in cells(unknown) and "not in Person Master" in unknown[1][0]


def test_fuel_sign_fills_only_that_days_empty_cells():
    boiler = [["22-Nov-26", "6:04 pm", "Afternoon", "95", "95", "92", "", ""],
              ["23-Nov-26", "8:29 am", "Morning", "95", "95", "95", "", ""],
              ["23-Nov-26", "9:00 am", "Morning", "95", "95", "95", "Diesel", ""]]
    found = sheet.changes(sign("IN", "23-Nov-26", "9:30 am", drum="999"), tables(boiler=boiler))
    assert cells(found) == {("Boiler Temp Log", 3, FUEL): "Wood"}


def test_page_adds_a_lot_once_and_never_changes_a_filled_cell():
    assert len(sheet.changes(PAGE, tables())[0]) == 8  # new row 2, no Curing End
    found = sheet.changes(PAGE, tables(curing=[LOT_479]))
    assert found[0] == [] and "Water Tank 3" in found[1][0]  # sheet says Tank 2: reported, not written

    missing_length = LOT_479[:5] + [""] + LOT_479[6:]
    assert cells(sheet.changes(PAGE, tables(curing=[missing_length]))) == {("Curing Log", 2, "Length (m)"): "3047"}


def test_out_sign_fills_the_end_of_the_open_lot_from_an_earlier_day():
    old_lot = ["300", "01-Sep-26", "x", "", "887", "1", "Water Tank 2", "01-Sep-26", "7:00 am"]  # same drum, long ago
    found = sheet.changes(sign("OUT", "22-Nov-26", "3:10 pm", fuel=""), tables(curing=[old_lot, LOT_479]))
    assert cells(found) == {("Curing Log", 3, "Curing End Date"): "22-Nov-26",
                            ("Curing Log", 3, "Curing End Time"): "3:10 pm"}

    closed = LOT_479 + ["22-Nov-26", "3:10 pm"]
    assert sheet.changes(sign("OUT", "22-Nov-26", "3:10 pm", fuel=""), tables(curing=[closed]))[0] == []

