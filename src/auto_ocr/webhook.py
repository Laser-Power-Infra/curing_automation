"""Receives WhatsApp messages from Evolution and reads every photo posted in our group.

Run:       uv run python -m uvicorn auto_ocr.webhook:app --host 0.0.0.0 --port 6027
Register:  uv run python -m auto_ocr.webhook --register   (once: tells Evolution to call us)
Catch up:  uv run python -m auto_ocr.webhook --catch-up 2026-11-23 [--dry-run]
           (enters that day's group photos again; rows already in the sheet are left alone)
"""

import base64
import hmac
import json
import logging
import re
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from . import read_photo, sheet
from .config import setting

IST = timezone(timedelta(hours=5, minutes=30))
PHOTOS = Path("photos")  # every received photo, results.jsonl and auto_ocr.log
PORT = 6027
PHOTOS.mkdir(exist_ok=True)

# Every event is logged twice: to the console (docker logs) and to photos/auto_ocr.log (kept on disk).
log = logging.getLogger("auto_ocr")
if not log.handlers:
    line = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    line.converter = lambda *_: datetime.now(IST).timetuple()  # India time, whatever the server clock says
    for handler in (logging.StreamHandler(), RotatingFileHandler(PHOTOS / "auto_ocr.log", maxBytes=5_000_000, backupCount=5, encoding="utf-8")):
        handler.setFormatter(line)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def _evolution(method: str, path: str, **kwargs) -> httpx.Response:
    url = f"{setting('EVOLUTION_URL', 'http://127.0.0.1:6026').rstrip('/')}/{path}/{quote(setting('EVOLUTION_INSTANCE'), safe='')}"
    return httpx.request(method, url, headers={"apikey": setting("EVOLUTION_API_KEY")}, timeout=30, **kwargs)


def group_photo(event: object) -> dict | None:
    """The Evolution message data if this event is a photo posted in our group, else None."""
    data = event.get("data") if isinstance(event, dict) else None
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, dict) or event.get("event") != "messages.upsert":
        return None
    if key.get("remoteJid") != setting("WHATSAPP_GROUP_ID") or data.get("messageType") != "imageMessage":
        return None
    return data if key.get("id") and str(data.get("messageTimestamp", "")).isdigit() else None


def _log(record: dict) -> None:
    with open(PHOTOS / "results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def handle(data: dict, dry_run: bool = False) -> None:
    """Save the photo, read it, enter it in the sheet, log it. Runs after the webhook has answered."""
    message_id = re.sub(r"\W", "", data["key"]["id"])  # goes into a file name
    taken_at = datetime.fromtimestamp(int(data["messageTimestamp"]), IST).replace(tzinfo=None)
    # participantAlt is the phone-number JID when WhatsApp addresses the sender by a hidden LID.
    sender = {"name": data.get("pushName"), "number": data["key"].get("participantAlt") or data["key"].get("participant")}
    step = "get the photo"
    try:
        image = (data.get("message") or {}).get("base64")
        if not image:  # the webhook was registered without base64: ask Evolution for the file
            log.info("%s: no image in the event, asking Evolution for it", message_id)
            reply = _evolution("POST", "chat/getBase64FromMediaMessage", json={"message": {"key": data["key"]}})
            reply.raise_for_status()
            image = reply.json()["base64"]
        path = PHOTOS / f"{taken_at:%Y-%m-%d_%H%M%S}_{message_id}.jpeg"
        path.write_bytes(base64.b64decode(image))
        log.info("%s: photo saved as %s (%d bytes), sent %s by %s %s",
                 message_id, path.name, path.stat().st_size, taken_at, sender["name"], sender["number"])

        step = "read the photo"
        result = read_photo(path, taken_at)
        log.info("%s: read as %s, rows=%s, uncertain=%s%s", message_id, result["kind"], json.dumps(result.get("rows", []), ensure_ascii=False),
                 result["uncertain"], f", error={result['error']}" if "error" in result else "")

        step = "enter it in the sheet"
        entry = sheet.write(result, sender["number"], dry_run)
        for c in entry["sheet_changes"]:
            log.info("%s: %s %s row %d, %s = %s", message_id, "would fill" if dry_run else "filled", c["sheet"], c["row"], c["column"], c["value"])
        if not entry["sheet_changes"]:
            log.info("%s: nothing to fill in the sheet", message_id)
        for note in entry["notes"]:
            log.warning("%s: %s", message_id, note)
        _log({"sender": sender, "time": taken_at.isoformat(), **result, **entry})
    except Exception as e:  # a failed photo must leave a trace, not vanish
        log.exception("%s: FAILED to %s", message_id, step)
        _log({"sender": sender, "time": taken_at.isoformat(), "message_id": message_id, "error": f"{step}: {type(e).__name__}: {e}"})


# Evolution can deliver the same message twice; ids of saved photos survive a restart.
seen = {p.stem.rsplit("_", 1)[-1] for p in PHOTOS.glob("*.jpeg")}
REQUIRED = ("EVOLUTION_API_KEY", "EVOLUTION_INSTANCE", "WHATSAPP_GROUP_ID", "WEBHOOK_SECRET",
            "GOOGLE_SERVICE_ACCOUNT_EMAIL", "GOOGLE_PRIVATE_KEY")


@asynccontextmanager
async def lifespan(_: FastAPI):
    missing = [name for name in REQUIRED if not setting(name)] + (
        [] if setting("CLAUDE_API_KEY") or setting("ANTHROPIC_API_KEY") else ["CLAUDE_API_KEY"])
    log.info("receiver started: group=%s, evolution=%s, %d photo(s) already handled", setting("WHATSAPP_GROUP_ID"),
             setting("EVOLUTION_URL", "http://127.0.0.1:6026"), len(seen))
    if missing:
        log.error("settings missing in .env: %s", ", ".join(missing))
    yield
    log.info("receiver stopped")


app = FastAPI(title="auto-ocr WhatsApp receiver", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "photos_handled": len(seen)}


@app.post("/whatsapp")
async def whatsapp(request: Request, tasks: BackgroundTasks, x_webhook_secret: str = Header("")) -> dict:
    secret = setting("WEBHOOK_SECRET")
    if not secret or not hmac.compare_digest(x_webhook_secret, secret):
        log.warning("call rejected: wrong or missing webhook secret (from %s)", request.client.host if request.client else "?")
        raise HTTPException(401, "bad webhook secret")
    event = await request.json()
    data = group_photo(event)
    if data is None:
        # Other chats are private: log only that something came, never who or what.
        inner = event.get("data") if isinstance(event, dict) and isinstance(event.get("data"), dict) else {}
        ours = (inner.get("key") or {}).get("remoteJid") == setting("WHATSAPP_GROUP_ID")
        log.info("ignored: event=%s type=%s chat=%s", event.get("event") if isinstance(event, dict) else "?",
                 inner.get("messageType"), "our group" if ours else "other")
        return {"status": "ignored"}
    message_id = re.sub(r"\W", "", data["key"]["id"])
    if message_id in seen:
        log.info("%s: duplicate delivery, skipped", message_id)
        return {"status": "duplicate"}
    seen.add(message_id)
    log.info("%s: photo from our group accepted", message_id)
    tasks.add_task(handle, data)
    return {"status": "accepted"}


def register() -> None:
    """Tell Evolution to call this receiver on every new message, then show what it stored."""
    # host.docker.internal: Evolution runs in Docker, this receiver runs on the PC itself.
    url = setting("WEBHOOK_URL", f"http://host.docker.internal:{PORT}/whatsapp")
    webhook = {
        "enabled": True,
        "url": url,
        "headers": {"x-webhook-secret": setting("WEBHOOK_SECRET")},
        "byEvents": False,
        "base64": True,
        "events": ["MESSAGES_UPSERT"],
    }
    reply = _evolution("POST", "webhook/set", json={"webhook": webhook})
    print("set:", reply.status_code, "url:", url)
    found = _evolution("GET", "webhook/find").json()
    if isinstance(found, dict):
        found.pop("headers", None)  # holds the secret
    print("stored:", json.dumps(found, indent=2))


def catch_up(day: str, dry_run: bool) -> None:
    """Handle every photo Evolution has stored for our group on `day` (YYYY-MM-DD, India time)."""
    where = {"key": {"remoteJid": setting("WHATSAPP_GROUP_ID")},
             "messageTimestamp": {"gte": f"{day}T00:00:00+05:30", "lte": f"{day}T23:59:59+05:30"}}
    records, page, pages = [], 1, 1
    while page <= pages:
        reply = _evolution("POST", "chat/findMessages", json={"where": where, "page": page, "offset": 100})
        reply.raise_for_status()
        found = reply.json()["messages"]
        records += found["records"]
        pages, page = found.get("pages") or 1, page + 1
    photos = sorted((r for r in records if r.get("messageType") == "imageMessage"), key=lambda r: int(r["messageTimestamp"]))
    print(f"{len(photos)} photo(s) on {day}")
    for record in photos:
        handle(record, dry_run)
        print((PHOTOS / "results.jsonl").read_text(encoding="utf-8").splitlines()[-1])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--register"]:
        register()
    elif sys.argv[1:2] == ["--catch-up"] and len(sys.argv) > 2:
        catch_up(sys.argv[2], "--dry-run" in sys.argv)
    else:
        print(__doc__)
