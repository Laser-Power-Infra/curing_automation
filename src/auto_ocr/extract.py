"""Reads one photo with Claude and returns the raw fields. No business rules here."""

import base64
import mimetypes
import os
import re
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel

from . import rules


class Drum(BaseModel):
    drum_no: str
    lengths_m: list[float]


# Every field is required (no defaults): optional fields make the API reject the schema as too complex.
class Extraction(BaseModel):
    kind: Literal["curing_log", "boiler_temp", "tank_sign", "unknown"]
    # curing_log
    page_date: str
    lot_no: str
    product: str
    in_time: str
    temp90: str
    hours: float | None
    off: str
    drums: list[Drum]
    # boiler_temp
    temp_1: int | None
    temp_2: int | None
    temp_3: int | None
    # boiler_temp and tank_sign
    fuel: Literal["Wood", "Diesel", ""]
    # curing_log (chamber number) and tank_sign
    tank_no: int | None
    # tank_sign
    drum_no: str
    event: Literal["IN", "OUT", ""]

    uncertain: list[str]


def _api_key() -> str | None:
    """Key from the environment, else from .env (as ANTHROPIC_API_KEY or CLAUDE_API_KEY)."""
    names = ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
    env = Path(".env")
    if env.exists():
        m = re.search(rf"^({'|'.join(names)})=(.+)$", env.read_text(), re.M)
        if m:
            return m.group(2).strip().strip("\"'")
    return None  # the SDK then tries its own login profile


def extract(image: Path) -> Extraction:
    client = anthropic.Anthropic(api_key=_api_key())
    response = client.messages.parse(
        model=rules.MODEL,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mimetypes.guess_type(image.name)[0] or "image/jpeg",
                            "data": base64.standard_b64encode(image.read_bytes()).decode(),
                        },
                    },
                    {"type": "text", "text": rules.PROMPT},
                ],
            }
        ],
        output_format=Extraction,
    )
    if response.parsed_output is None:
        raise RuntimeError(f"{image.name}: no result (stop_reason={response.stop_reason})")
    return response.parsed_output
