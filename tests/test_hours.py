from datetime import date

from auto_ocr import hours

ARIJIT = {"participant": "150487198380092@lid"}


def msg(id, t, kind="conversation", text="", caption="", who=ARIJIT):
    body = {"imageMessage": {"caption": caption}} if kind == "imageMessage" else {"conversation": text}
    return {"key": {"id": id, **who}, "messageType": kind, "messageTimestamp": t, "message": body}


def test_each_photo_gets_its_own_text():
    # 23-Nov 09:46: photo, "FL 37" 2 s later, photo, "FL 22" the same second
    p1, p2 = msg("p1", 1000, "imageMessage"), msg("p2", 1018, "imageMessage")
    chat = [p1, msg("t1", 1002, text="FL 37"), p2, msg("t2", 1018, text="FL 22"),
            msg("x", 1001, text="FL 99", who={"participant": "someone-else"})]
    assert hours.text_for(p1, chat) == "FL 37"
    assert hours.text_for(p2, chat) == "FL 22"


def test_caption_and_text_before_photo():
    p = msg("p", 1000, "imageMessage", caption="35 NOF")
    assert hours.text_for(p, [msg("t", 995, text="FL 18"), p, msg("far", 1100, text="FL 1")]) == "35 NOF\nFL 18"
    # caption only on the photo, nothing else sent; webhook copy without the caption still finds it
    assert hours.text_for(p, [p]) == "35 NOF"
    assert hours.text_for(msg("p", 1000, "imageMessage"), [p]) == "35 NOF"


TABLE = [
    [" ", "FORKLIFT NO. 08", "HYDRA NO-5"],
    ["EQUIPMENT ID", "FL000002", "U1HY000005"],
    ["LOCATION", "SHED 6", "KHARAGPUR"],
    ["DATE"],
    *[[f"{d}-Nov-26", f"54{d}.5", f"42{d}"] for d in range(16, 22)],  # 16..21 Nov
    ["22-Nov-26", "", "4230"],
]
DAY22, DAY23 = date(2026, 11, 22), date(2026, 11, 23)


def test_fills_empty_cell_of_the_day():
    cells, notes = hours.changes({"equipment_id": "FL000002", "reading": 5430.6}, TABLE, DAY22)
    assert cells == [{"sheet": "LASER EQUIPMENT READING", "row": 11, "column": "FL000002", "cell": "B11", "value": "5430.6"}]
    assert notes == []


def test_new_day_row_and_whole_number_column():
    cells, _ = hours.changes({"equipment_id": "u1hy000005", "reading": 4244.5}, TABLE, DAY23)
    assert [(c["cell"], c["value"]) for c in cells] == [("A12", "23-Nov-26"), ("C12", "4244")]


def test_filled_cell_is_kept_and_misread_refused():
    assert "already" in hours.changes({"equipment_id": "U1HY000005", "reading": 4252.4}, TABLE, DAY22)[1][0]
    for misread in (999.0, 54210.5):  # lower than 21-Nov, or more than 24 h a day above it
        cells, notes = hours.changes({"equipment_id": "FL000002", "reading": misread}, TABLE, DAY22)
        assert cells == [] and "looks misread" in notes[0]
    assert "not in row 2" in hours.changes({"equipment_id": "FL999", "reading": 1.0}, TABLE, DAY22)[1][0]
