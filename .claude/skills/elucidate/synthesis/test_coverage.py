#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import coverage

faults = []
WORDS = ("I want to pin a statement to the top of a corpus. Items should have a word\n"
         "count somewhere. And when I share a corpus I should be able to set\n"
         "whether the people I share it with can comment or just read.")


def check(name, held, wanted):
    if held != wanted:
        faults.append(f"{name}: expected {wanted!r}, got {held!r}")


def found(**over):
    held = {"unclaimed": [], "renamed": []}
    held.update(over)
    return held


check("findings that quote the owner pass",
      coverage.faults(found(unclaimed=[
          {"quote": "Items should have a word count somewhere.",
           "reason": "no statement obliges it"}]), WORDS),
      [])
check("a quote wrapped at another column is still the owner's",
      coverage.faults(found(unclaimed=[
          {"quote": "Items should have a word count somewhere. And when I "
                    "share a corpus", "reason": "spans the wrap"}]), WORDS),
      [])
check("a quote the owner did not say is refused",
      [line.split(":")[0] for line in coverage.faults(found(unclaimed=[
          {"quote": "Items should be encrypted at rest.", "reason": "invented"}]),
          WORDS)],
      ["quotes what the owner did not say"])
check("an unclaimed entry with no quote is refused",
      len(coverage.faults(found(unclaimed=[{"reason": "no quote"}]), WORDS)), 1)
check("an entry quoting nothing is refused: the empty quote is a substring of "
      "everything, so it would pass as the owner's own",
      len(coverage.faults(found(unclaimed=[
          {"quote": "   ", "reason": "quotes nothing"}]), WORDS)), 1)
check("and a renaming naming no word is refused for the same reason",
      len(coverage.faults(found(renamed=[
          {"owner": "", "statement": "document", "proposal": 1}]), WORDS)), 1)
check("a renaming naming a word the owner used passes",
      coverage.faults(found(renamed=[
          {"owner": "corpus", "statement": "document", "proposal": 1}]), WORDS),
      [])
check("a renaming naming a word the owner never used is refused",
      len(coverage.faults(found(renamed=[
          {"owner": "widget", "statement": "gadget", "proposal": 1}]), WORDS)), 1)
check("findings that are not a mapping are refused",
      coverage.faults(["unclaimed"], WORDS), ["the findings are not a mapping"])
check("findings missing a list are refused",
      coverage.faults({"unclaimed": []}, WORDS), ["states no renamed list"])
# @req> REQ-12032769@1Km3PLqZHCDu uiykqd
check("a quote falling inside one of the owner's words is refused: a "
      "substring is not a passage",
      [line.split(":")[0] for line in coverage.faults(found(unclaimed=[
          {"quote": "tem", "reason": "a fragment of Items"}]), WORDS)],
      ["quotes what the owner did not say"])
# @req> REQ-12032769@1Km3PLqZHCDu z35jpg
check("and a word the owner did use passes at its own boundaries",
      coverage.faults(found(unclaimed=[
          {"quote": "word\ncount", "reason": "spans the wrap"}]), WORDS),
      [])
# @req> REQ-12032769@1Km3PLqZHCDu kfbefn
check("a renamed entry naming a fragment of the owner's word is refused too",
      len(coverage.faults(found(renamed=[
          {"owner": "tem", "statement": "document", "proposal": 1}]), WORDS)),
      1)

TYPED = ("I'd like undo, and the people I share with shouldn't lose it. "
         'The "pinned" statement stays pinned.')
# @req> REQ-12032769@1Km3PLqZHCDu s6gtgu
check("a quote curling the apostrophe the owner typed straight is accepted, "
      "and one straightening the owner's curl with it",
      (coverage.faults(found(unclaimed=[
          {"quote": "I\u2019d like undo", "reason": "curled"}]), TYPED),
       coverage.faults(found(renamed=[
           {"owner": "shouldn\u2019t", "statement": "may not", "proposal": 1}]),
           TYPED),
       coverage.faults(found(unclaimed=[
           {"quote": "The \u201cpinned\u201d statement", "reason": "curled"}]),
           TYPED)),
      ([], [], []))
# @req> REQ-12032769@1Km3PLqZHCDu 7bn4q7
check("and normalising the quotes does not admit a word the owner never used",
      len(coverage.faults(found(unclaimed=[
          {"quote": "I\u2019d like redo", "reason": "invented"}]), TYPED)), 1)

# @req> REQ-86066994@ZdOflpXK5eCb x2ldv3
check("a top-level name the check does not read fails the document",
      coverage.faults(dict(found(), summary="a statement nobody asked for"), WORDS),
      ["states 'summary', which is not one of unclaimed, renamed, quote, "
       "owner, reason, statement, proposal"])
# @req> REQ-86066994@ZdOflpXK5eCb velvjr
check("an entry name it does not read fails the document too",
      [line.split(",")[0] for line in coverage.faults(found(unclaimed=[
          {"quote": "Items should have a word count somewhere.",
           "severity": "high"}]), WORDS)],
      ["states 'severity'"])
# @req> REQ-86066994@ZdOflpXK5eCb vzyygi
check("a document stating no other name is accepted, every name it carries "
      "being one of the seven",
      coverage.faults(found(
          unclaimed=[{"quote": "Items should have a word count somewhere.",
                      "reason": "no statement obliges it"}],
          renamed=[{"owner": "corpus", "statement": "document",
                    "proposal": 1}]), WORDS),
      [])

check("an invented quote is reported alongside a sound one, not instead of it",
      len(coverage.faults(found(unclaimed=[
          {"quote": "Items should have a word count somewhere.", "reason": "a"},
          {"quote": "Items should be encrypted at rest.", "reason": "b"}]),
          WORDS)),
      1)

with tempfile.TemporaryDirectory() as room:
    where = Path(room)
    (where / "words.md").write_text(WORDS)
    (where / "sound.yml").write_text(yaml.safe_dump(found(unclaimed=[
        {"quote": "Items should have a word count somewhere.", "reason": "a"}])))
    (where / "invented.yml").write_text(yaml.safe_dump(found(unclaimed=[
        {"quote": "Items should be encrypted at rest.", "reason": "b"}])))
    check("a sound run passes",
          coverage.main(["--words", str(where / "words.md"),
                         "--found", str(where / "sound.yml")]), 0)
    check("a run quoting what was never said does not pass",
          coverage.main(["--words", str(where / "words.md"),
                         "--found", str(where / "invented.yml")]), 1)

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("coverage check self-test: 0 fault(s)")
sys.exit(0)
