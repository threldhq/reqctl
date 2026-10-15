#!/usr/bin/env python3
import argparse
import re
import sys
import unicodedata
from pathlib import Path

from reqctl import corpus, write

LISTS = ("unclaimed", "renamed")
NAMES = LISTS + ("quote", "owner", "reason", "statement", "proposal")
# @req> REQ-13591264@tle-mDzkWdnR ybhob6
BOUNDS = {"reason": 300, "owner": 60}
EMPHASIS = re.compile(r"[*`]+")
JOINED = re.compile(r"(?<=\w)[*`]+(?=\w)")


def spoken(text):
    return " ".join(str(text).split())


# @req+ REQ-12032769@1Km3PLqZHCDu n2lx2b
def plain(text):
    straight = "".join("'" if write._quoting(char) else char for char in text)
    return " ".join(EMPHASIS.sub("", JOINED.sub(" ", straight)).split())


def worded(char):
    return char == "_" or unicodedata.category(char)[0] in "LNM"


def quoted(said, needle):
    needle = plain(needle)
    if not any(map(worded, needle)):
        return False
    at = said.find(needle)
    while at != -1:
        end = at + len(needle)
        if not (at and worded(said[at - 1])) and not (
                end < len(said) and worded(said[end])):
            return True
        at = said.find(needle, at + 1)
    return False
# @req- n2lx2b


def keys_in(node):
    if isinstance(node, dict):
        return {str(name) for name in node}.union(*map(keys_in, node.values()))
    if isinstance(node, list):
        return set().union(*map(keys_in, node))
    return set()


def faults(found, words):
    # @req+ REQ-59870599@2h71qdAwEzkC uffga6
    if not isinstance(found, dict):
        return ["the findings are not a mapping"]
    missing = [name for name in LISTS if not isinstance(found.get(name), list)]
    if missing:
        return [f"states no {name} list" for name in missing]
    # @req- uffga6

    # @req> REQ-26693396@t2DC4anz7B5V pdq53a
    said = plain(spoken(words)).casefold()
    # @req+ REQ-86066994@ZdOflpXK5eCb a4gokv
    stated = keys_in(found)
    held = [f"states {name!r}, which is not one of {', '.join(NAMES)}"
            for name in sorted(stated - set(NAMES))]
    # @req- a4gokv
    # @req+ REQ-41361856@4UOkrz1niMIl y4zpw2
    # @req+ REQ-67248754@f8kUPPzaG_-U c3jev7
    # @req+ REQ-26693396@t2DC4anz7B5V czhlcg
    for entry in found["unclaimed"]:
        if not isinstance(entry, dict) or "quote" not in entry:
            held.append(f"an unclaimed entry carries no quote: {entry!r}")
        elif not spoken(entry["quote"]):
            held.append("an unclaimed entry quotes nothing, and every passage "
                        "holds the empty quote")
        elif not quoted(said, spoken(entry["quote"]).casefold()):
            held.append(f"quotes what the owner did not say: {entry['quote']!r}")
    for entry in found["renamed"]:
        if not isinstance(entry, dict) or "owner" not in entry:
            held.append(f"a renamed entry names no owner word: {entry!r}")
        elif not spoken(entry["owner"]):
            held.append("a renamed entry names no word, and every passage "
                        "holds the empty one")
        elif not quoted(said, spoken(entry["owner"]).casefold()):
            held.append(f"names a word the owner did not use: {entry['owner']!r}")
    # @req- czhlcg
    # @req- c3jev7
    # @req- y4zpw2
    # @req> REQ-13591264@tle-mDzkWdnR ieflg7
    held += [f"{one}: an entry's {name} runs to {len(entry[name])} characters, "
             f"past the {bound} the coverage shape allows"
             for one in LISTS for entry in found[one] if isinstance(entry, dict)
             for name, bound in BOUNDS.items()
             if isinstance(entry.get(name), str) and len(entry[name]) > bound]
    return held


def main(argv=None):
    parsed = argparse.ArgumentParser()
    parsed.add_argument("--words", required=True, metavar="FILE")
    parsed.add_argument("--found", required=True, metavar="FILE")
    args = parsed.parse_args(argv)

    where = Path(args.found)
    # @req> REQ-27370034@uYfNuf6k4Q_h ptkgg3
    respawn = ("spawn the coverage agent again from "
               f"{where.parent / 'workflow' / 'coverage.json'}")
    # @req+ REQ-95375719@-TYbW5JhiwAf k26kry
    try:
        found = corpus.loads(corpus.read_text(where), where)
    except corpus.ReqctlError as broken:
        corpus.remove(where, missing_ok=True)
        # @req> REQ-27370034@uYfNuf6k4Q_h way2fx
        raise corpus.ReqctlError(f"{broken} -- {respawn}") from broken
    held = faults(found, corpus.read_text(args.words))
    if held:
        corpus.remove(where)
    # @req- k26kry
    # @req+ REQ-74501429@3K-aFi7yo4Cp rzcign
    for fault in held:
        print(f"{where.name}: {fault}")
    if held:
        # @req> REQ-27370034@uYfNuf6k4Q_h nodcxf
        print(f"\n{len(held)} fault(s): the run does not act on these findings "
              f"-- {respawn}")
        return 1
    print(f"{len(found['unclaimed'])} unclaimed, {len(found['renamed'])} renamed, "
          "every quote the owner's own")
    # @req- rzcign
    return 0


if __name__ == "__main__":
    # @req+ REQ-29234402@b5_8tR6bNR44 ifziur
    try:
        sys.exit(main())
    except (corpus.ReqctlError, OSError, UnicodeError) as unreadable:
        sys.exit(f"{Path(__file__).name}: " + " ".join(str(unreadable).split()))
    except SystemExit as stop:
        if isinstance(stop.code, str):
            sys.exit(f"{Path(__file__).name}: " + " ".join(stop.code.split()))
        raise
    # @req- ifziur
