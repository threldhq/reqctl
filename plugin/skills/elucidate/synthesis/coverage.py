#!/usr/bin/env python3
import argparse
import re
import sys
from pathlib import Path

from reqctl import corpus, write

LISTS = ("unclaimed", "renamed")
NAMES = LISTS + ("quote", "owner", "reason", "statement", "proposal")


def spoken(text):
    return " ".join(str(text).split())


# @req+ REQ-12032769@1Km3PLqZHCDu n2lx2b
def plain(text):
    return "".join("'" if write._quoting(char) else char for char in text)


def quoted(said, needle):
    return re.search(rf"(?<!\w){re.escape(plain(needle))}(?!\w)",
                     said) is not None
# @req- n2lx2b


def faults(found, words):
    # @req+ REQ-59870599@2h71qdAwEzkC uffga6
    if not isinstance(found, dict):
        return ["the findings are not a mapping"]
    missing = [name for name in LISTS if not isinstance(found.get(name), list)]
    if missing:
        return [f"states no {name} list" for name in missing]
    # @req- uffga6

    said = plain(spoken(words))
    # @req+ REQ-86066994@ZdOflpXK5eCb a4gokv
    stated = {str(name) for name in found}
    for one in LISTS:
        for entry in found[one]:
            if isinstance(entry, dict):
                stated |= {str(name) for name in entry}
    held = [f"states {name!r}, which is not one of {', '.join(NAMES)}"
            for name in sorted(stated - set(NAMES))]
    # @req- a4gokv
    # @req+ REQ-41361856@4UOkrz1niMIl y4zpw2
    # @req+ REQ-67248754@f8kUPPzaG_-U c3jev7
    for entry in found["unclaimed"]:
        if not isinstance(entry, dict) or "quote" not in entry:
            held.append(f"an unclaimed entry carries no quote: {entry!r}")
        elif not spoken(entry["quote"]):
            held.append("an unclaimed entry quotes nothing, and every passage "
                        "holds the empty quote")
        elif not quoted(said, spoken(entry["quote"])):
            held.append(f"quotes what the owner did not say: {entry['quote']!r}")
    for entry in found["renamed"]:
        if not isinstance(entry, dict) or "owner" not in entry:
            held.append(f"a renamed entry names no owner word: {entry!r}")
        elif not spoken(entry["owner"]):
            held.append("a renamed entry names no word, and every passage "
                        "holds the empty one")
        elif not quoted(said, spoken(entry["owner"])):
            held.append(f"names a word the owner did not use: {entry['owner']!r}")
    # @req- c3jev7
    # @req- y4zpw2
    return held


def main(argv=None):
    parsed = argparse.ArgumentParser()
    parsed.add_argument("--words", required=True, metavar="FILE")
    parsed.add_argument("--found", required=True, metavar="FILE")
    args = parsed.parse_args(argv)

    where = Path(args.found)
    found = corpus.loads(corpus.read_text(where), where)
    held = faults(found, corpus.read_text(args.words))
    # @req+ REQ-74501429@3K-aFi7yo4Cp rzcign
    for fault in held:
        print(f"{where.name}: {fault}")
    if held:
        print(f"\n{len(held)} fault(s): the run does not act on these findings")
        return 1
    print(f"{len(found['unclaimed'])} unclaimed, {len(found['renamed'])} renamed, "
          "every quote the owner's own")
    # @req- rzcign
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except corpus.ReqctlError as unreadable:
        sys.exit(f"{Path(__file__).name}: {unreadable}")
