"""Settings come from the environment, else from the .env file in the project folder."""

import os
import re
from pathlib import Path


def setting(name: str, default: str | None = None) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    env = Path(".env")
    m = env.exists() and re.search(rf"^{name}=(.+)$", env.read_text(), re.M)
    return m.group(1).strip().strip("\"'") if m else default
