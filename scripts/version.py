"""Read the release version and generate the core's version header."""
from datetime import date
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read_version():
    value = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]{4}\.[0-9]{2}\.[0-9]{2}", value):
        raise ValueError("VERSION must be YYYY.MM.DD")
    date(*map(int, value.split(".")[:3]))
    return value


def version_header():
    template = (ROOT / "scripts/version.h.in").read_text(encoding="utf-8")
    return template.replace("@XEMU_LIBRETRO_VERSION@", read_version()).encode("utf-8")
