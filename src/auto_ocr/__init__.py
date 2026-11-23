import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import rows, rules
from .extract import extract


def read_photo(image: Path, taken_at: datetime | None = None) -> dict:
    x = extract(image)
    taken_at = taken_at or rows.photo_time(image.name)
    out = {"file": image.name, "kind": x.kind, "sheet": rules.SHEET_FOR_KIND.get(x.kind)}
    if x.kind == "curing_log":
        out["rows"] = rows.curing_rows(x)
    elif x.kind in ("boiler_temp", "tank_sign"):
        if not taken_at:
            out["error"] = "photo time unknown: not in the file name, pass --time"
        elif x.kind == "boiler_temp":
            out["rows"] = [rows.boiler_row(x, taken_at)]
        else:
            out["rows"] = [rows.tank_record(x, taken_at)]
    out["uncertain"] = x.uncertain
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Read curing / boiler photos into sheet rows.")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument(
        "--time",
        type=datetime.fromisoformat,
        help="when the photo was taken, e.g. 2026-11-20T11:24 (default: from the WhatsApp file name)",
    )
    parser.add_argument("--write", action="store_true", help="enter the rows in the Google Sheet")
    parser.add_argument("--dry-run", action="store_true", help="show the cells that would be filled, write nothing")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # column names contain °
    for image in args.images:
        result = read_photo(image, args.time)
        if args.write or args.dry_run:
            from . import sheet  # only needed (and only needs Google access) when entering rows

            result |= sheet.write(result, dry_run=not args.write)
        print(json.dumps(result, indent=2, ensure_ascii=False))
