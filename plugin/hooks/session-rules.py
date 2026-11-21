#!/usr/bin/env python3
import json
import shutil
import subprocess
import sys
from pathlib import Path

RULES = Path(__file__).with_name("session-rules.md")
MANIFEST = Path(__file__).parents[1] / ".claude-plugin" / "plugin.json"


# @req> REQ-66969682@V-YxKtbF_YLG ijl5lw
def releases():
    found = shutil.which("reqctl")
    # @req> REQ-72360623@aPs9FUqC9zb4 pylefz
    if found is None:
        return "This session finds no reqctl.\n"
    try:
        loaded = str(json.loads(MANIFEST.read_text(encoding="utf-8"))["version"])
    except (OSError, ValueError, KeyError, TypeError) as broken:
        loaded = f"unreadable ({broken!r})"
    try:
        done = subprocess.run([found, "--version"], capture_output=True, text=True,
                              timeout=20, check=False)
        reported = done.stdout.strip() or f"unreported (exit {done.returncode})"
    except (OSError, subprocess.SubprocessError) as broken:
        reported = f"unreported ({broken!r})"
    if loaded == reported:
        return ""
    return (f"The reqctl plugin this session loaded is release {loaded} and the "
            f"reqctl it finds is release {reported}: they are different releases.\n")


def main():
    # @req+ REQ-90700416@AGFmCuLqPUC4 reo737
    try:
        said = RULES.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as broken:
        said = ("reqctl's rules for working a corpus could not be read: "
                f"{broken}\n")
    sys.stdout.write(said)
    # @req- reo737
    # @req> REQ-66969682@V-YxKtbF_YLG crcpyo
    # @req> REQ-72360623@aPs9FUqC9zb4 eyhgli
    sys.stdout.write(releases())
    sys.exit(0)


# @req> REQ-38288492@4l6tMNjp19tH myhqkt
if __name__ == "__main__":
    # @req> REQ-38288492@4l6tMNjp19tH 46mvef
    main()
