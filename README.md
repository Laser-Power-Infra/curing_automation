# auto-ocr

Reads curing-area photos (handwritten curing page, boiler temperature panel, tank sign)
and prints the Google Sheet row each one should become.

    uv run python -m auto_ocr "WhatsApp Image 2026-11-20 at 11.24.23 AM.jpeg"
    uv run python -m pytest

- Business rules: `src/auto_ocr/rules.py` (the only place rules live).
- API key: `.env` in this folder, as `CLAUDE_API_KEY=...` or `ANTHROPIC_API_KEY=...`.
- Photo time comes from the WhatsApp file name; use `--time 2026-11-20T11:24` otherwise.
- `pydantic` is pinned below 2.12 because Windows Application Control on this PC blocks the newer build.

## WhatsApp receiver

Evolution (on the server, `192.168.1.190:6026`) calls this receiver on every new WhatsApp
message. Photos posted in the group `WHATSAPP_GROUP_ID` are saved to `photos/`, read, and the
result is entered in the Google Sheet by the "Sheet entry" rules in `rules.py` (only empty
cells are filled). Everything read and every cell filled is logged in `photos/results.jsonl`.

Photos in the hour meter group `HOURS_GROUP_ID` (LASER HOUR METER UPDATE) go to the
LASER EQUIPMENT READING tab of the FUEL CONSUMPTION sheet: the receiver waits 60 s for the text
the sender types with the photo ("FL 22", "Hydra 5"), finds the machine's column by its
equipment ID (row 2) and fills that day's row (rules.py section 8).

    uv run python -m uvicorn auto_ocr.webhook:app --host 0.0.0.0 --port 6027
    uv run python -m auto_ocr.webhook --register    # once, or after WEBHOOK_URL changes
    uv run python -m auto_ocr.webhook --catch-up 2026-11-23 [--dry-run] [--group curing|hours]   # photos missed while it was off
    uv run python -m auto_ocr --dry-run photo.jpeg   # show the cells a photo would fill (--write to fill them)

Settings in `.env`: `EVOLUTION_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`,
`WHATSAPP_GROUP_ID`, `HOURS_GROUP_ID`, `WEBHOOK_SECRET`, `GOOGLE_SERVICE_ACCOUNT_EMAIL`, `GOOGLE_PRIVATE_KEY`, `WEBHOOK_URL` (the address Evolution uses to reach
this receiver).

If Application Control blocks `uv run` ("blocked this file"), run with the base Python:

    set PYTHONPATH=.venv\Lib\site-packages;src
    "%APPDATA%\uv\python\cpython-3.12-windows-x86_64-none\python.exe" -m uvicorn auto_ocr.webhook:app --host 0.0.0.0 --port 6027

## Run on the server (Docker)

Copy this folder to the server (with `.env`; the photos and `.venv` are not needed), then:

    docker compose up -d --build
    docker compose exec auto-ocr python -m auto_ocr.webhook --register   # points Evolution at the server
    curl http://127.0.0.1:6027/health

`docker-compose.yml` assumes the server is `192.168.1.190` (Evolution on 6026, this receiver
on 6027). Stop the receiver on the PC once the server one is registered: only one should run.

## Logs

Every event is logged with the WhatsApp message id, in India time:

    docker compose logs -f auto-ocr      # live
    photos/auto_ocr.log                  # the same lines on disk (5 files of 5 MB are kept)
    photos/results.jsonl                 # one line per photo: what was read, which cells were filled

What a photo's lines look like: `accepted` → `photo saved` → `read as ...` → `filled <sheet> row
N, <column> = <value>` (or `nothing to fill`). A `WARNING` is a value left alone (cell already
filled with something else, sender not in Person Master). `FAILED to <step>` comes with the
full error. `ignored: ... chat=other` lines are messages from other chats; they show the
webhook is alive.
