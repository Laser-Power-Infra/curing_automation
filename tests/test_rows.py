from datetime import datetime

from auto_ocr import rows
from auto_ocr.extract import Drum, Extraction

def photo(**read) -> Extraction:
    """An Extraction with every field the photo did not show left empty."""
    blank = {name: None for name in Extraction.model_fields}
    blank |= dict.fromkeys(["page_date", "lot_no", "product", "in_time", "temp90", "off", "fuel", "drum_no", "event"], "")
    return Extraction(**{**blank, "drums": [], "uncertain": [], **read})


PAGE = dict(
    kind="curing_log",
    page_date="2026-11-20",
    lot_no="477",
    tank_no=1,
    product="3C X 300 SQMM 33KV (N)",
    in_time="01:53",
    hours=32,
    drums=[Drum(drum_no="914-L", lengths_m=[2020, 507])],
)


def test_photo_time_from_whatsapp_name():
    name = "WhatsApp Image 2026-11-20 at 11.24.23 AM.jpeg"
    assert rows.photo_time(name) == datetime(2026, 11, 20, 11, 24, 23)
    assert rows.photo_time("IMG_001.jpg") is None


def test_curing_row_matches_sheet_row_for_lot_477():
    full = photo(**PAGE, temp90="2026-11-20 08:30", off="2026-11-21 16:30")
    assert rows.curing_rows(full) == [
        {
            "Lot No": "477",
            "Core Production Date": "20-Nov-26",
            "Product": "3C X 300 SQMM 33KV (N)",
            "Core Drum No": "914",
            "Length (m)": "2527",
            "Chamber / Tank": "Water Tank 1",
            "Curing Start Date": "20-Nov-26",
            "Curing Start Time": "1:53 am",
            "Curing End Date": "21-Nov-26",
            "Curing End Time": "4:30 pm",
        }
    ]
    # a bare Off time is the first one after the 90°C time: 90°C 22:50, Off 06:50 -> next morning
    bare = rows.curing_rows(photo(**PAGE, temp90="22:50", off="06:50"))[0]
    assert (bare["Curing End Date"], bare["Curing End Time"]) == ("21-Nov-26", "6:50 am")


def test_one_row_per_drum():
    two = photo(**{**PAGE, "drums": [Drum(drum_no="913", lengths_m=[508]), Drum(drum_no="877", lengths_m=[1010])]})
    assert [(r["Core Drum No"], r["Length (m)"]) for r in rows.curing_rows(two)] == [("913", "508"), ("877", "1010")]


def test_boiler_row_matches_sheet():
    x = photo(kind="boiler_temp", temp_1=71, temp_2=91, temp_3=91)
    assert list(rows.boiler_row(x, datetime(2026, 11, 20, 3, 7, 47)).values()) == [
        "20-Nov-26", "3:07 am", "Night", "71", "91", "91", "", "",
    ]
    assert rows.boiler_row(x, datetime(2026, 11, 20, 11, 24))["Reading (Morning / Afternoon / Night)"] == "Morning"
    assert rows.boiler_row(x, datetime(2026, 11, 20, 17, 47))["Reading (Morning / Afternoon / Night)"] == "Afternoon"


def test_tank_sign():
    x = photo(kind="tank_sign", drum_no="914", tank_no=1, fuel="Wood", event="IN")
    assert rows.tank_record(x, datetime(2026, 11, 20, 1, 53, 36)) == {
        "Event": "IN",
        "Date": "20-Nov-26",
        "Time": "1:53 am",
        "Core Drum No": "914",
        "Chamber / Tank": "Water Tank 1",
        "Boiler Running On (Diesel / Wood)": "Wood",
    }


def test_values_outside_the_dropdowns_are_left_blank_and_reported():
    page = photo(**{**PAGE, "product": "300 SQMM 33KV", "tank_no": 4})
    row = rows.curing_rows(page)[0]
    assert (row["Product"], row["Chamber / Tank"]) == ("", "")
    assert len(page.uncertain) == 2

    # the Product Master spelling (with its trailing space) is what gets written
    assert rows.curing_rows(photo(**{**PAGE, "product": "1C X 630 SQMM 33 KV (N)"}))[0]["Product"] == "1C X 630 SQMM 33 KV (N) "

    panel = photo(kind="boiler_temp", temp_1=941, temp_2=95, temp_3=93)
    assert list(rows.boiler_row(panel, datetime(2026, 11, 20, 11, 24)).values())[3:6] == ["", "95", "93"]
    assert len(panel.uncertain) == 1
