import importlib.metadata
import json
import sys
from pathlib import Path

# @req> REQ-66969682@cz1F6um1nDLN dpptld
MANIFEST = Path(__file__).resolve().parents[3] / ".claude-plugin" / "plugin.json"


def compare():
    try:
        stated = str(json.loads(MANIFEST.read_text(encoding="utf-8"))["version"])
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
