#!/usr/bin/env python3
import sys
from pathlib import Path

RULES = Path(__file__).with_name("session-rules.md")


def main():
    # @req+ REQ-90700416@AGFmCuLqPUC4 reo737
    try:
        said = RULES.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as broken:
        said = ("reqctl's rules for working a corpus could not be read: "
                f"{broken}\n")
    sys.stdout.write(said)
    # @req- reo737
    sys.exit(0)


if __name__ == "__main__":
    # @req> REQ-38288492@1yCh_1wG8N-l 46mvef
    main()
