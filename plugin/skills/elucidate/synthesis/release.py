import importlib.metadata
import json
import sys
from pathlib import Path


def compare():
    try:
        stated = str(json.loads(Path(__file__).resolve().parents[3].joinpath(
            ".claude-plugin", "plugin.json").read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError, TypeError) as broken:
        stated = f"unreadable ({broken!r})"
    try:
        reported = importlib.metadata.version("reqctl")
    except importlib.metadata.PackageNotFoundError as broken:
        reported = f"unreported ({broken!r})"
    if stated != reported:
        print(f"The reqctl plugin this script belongs to is release {stated} and the "
              f"reqctl it uses is release {reported}: they are different releases.",
              file=sys.stderr)
