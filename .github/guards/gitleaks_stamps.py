#!/usr/bin/env python3
import re
import string
import sys
import tomllib
import warnings
from pathlib import Path
from re import _constants as sre
from re import _parser

from reqctl import corpus

CONFIG = Path(".gitleaks.toml")
RULE = "generic-api-key"
INSIDE = str(corpus.folder_for(".", "data") / "object_storage.yml")
ROOT = Path(INSIDE).parts[0] + "/"
DIGITS = frozenset(string.digits)
DIGEST = frozenset(string.ascii_letters + string.digits + "_-")
CATEGORIES = {sre.CATEGORY_DIGIT: DIGITS,
              sre.CATEGORY_WORD: DIGEST - {"-"},
              sre.CATEGORY_SPACE: frozenset(string.whitespace)}
SPELLINGS = 4096


def allowlists(config):
    for rule in config.get("rules") or []:
        if rule.get("id") == RULE:
            return rule.get("allowlists") or []
    return []


def everywhere(config):
    held = list(config.get("allowlists") or [])
    for owner in [config, *(config.get("rules") or [])]:
        if isinstance(owner.get("allowlist"), dict):
            held.append(owner["allowlist"])
    return held + [one for rule in config.get("rules") or []
                   for one in rule.get("allowlists") or []]


def stamping(held):
    regexes = held.get("regexes") or []
    return (not regexes or held.get("regextarget", "secret") != "secret"
            or bool(held.get("stopwords") or held.get("commits"))
            or (held.get("condition") != "AND" and bool(held.get("paths")))
            or any(re.search(one, stamp) for one in regexes for stamp in stamps()))


def admitting(config, sample):
    return [held for held in allowlists(config)
            if any(re.fullmatch(one, sample) for one in held.get("regexes") or [])]


def _class(items):
    held = set()
    for op, av in items:
        if op is sre.LITERAL:
            held.add(chr(av))
        elif op is sre.RANGE:
            held.update(map(chr, range(av[0], av[1] + 1)))
        elif op is sre.CATEGORY and av in CATEGORIES:
            held.update(CATEGORIES[av])
        else:
            return None
    return frozenset(held)


def _spelled(items):
    found = [()]
    for op, av in items:
        if op is sre.LITERAL:
            parts = [(frozenset(chr(av)),)]
        elif op is sre.IN:
            one = _class(av)
            parts = None if one is None else [(one,)]
        elif op is sre.SUBPATTERN:
            parts = None if av[1] & re.IGNORECASE else _spelled(av[3])
        elif op is sre.BRANCH:
            arms = [_spelled(arm) for arm in av[1]]
            parts = None if None in arms else [one for arm in arms for one in arm]
        elif op in (sre.MAX_REPEAT, sre.MIN_REPEAT) and av[1] <= SPELLINGS:
            inner = _spelled(av[2])
            parts = None if inner is None else _repeated(inner, av[0], av[1])
        else:
            parts = None
        if parts is None or len(found) * len(parts) > SPELLINGS:
            return None
        found = [left + right for left in found for right in parts]
    return found


def _repeated(inner, low, high):
    found, run = [], [()]
    for count in range(high + 1):
        if count >= low:
            found += run
        if len(found) + len(run) * len(inner) > SPELLINGS:
            return None
        run = [left + right for left in run for right in inner]
    return found


def spellings(pattern):
    parsed = _parser.parse(pattern)
    items = list(parsed)
    if (parsed.state.flags & (re.IGNORECASE | re.MULTILINE) or len(items) < 2
            or items[0] != (sre.AT, sre.AT_BEGINNING)
            or items[-1] != (sre.AT, sre.AT_END)):
        return None
    return _spelled(items[1:-1])


def confined(pattern):
    parsed = _parser.parse(pattern)
    if parsed.state.flags & (re.IGNORECASE | re.MULTILINE):
        return False
    return list(parsed)[:1 + len(ROOT)] == ([(sre.AT, sre.AT_BEGINNING)]
                                     + [(sre.LITERAL, ord(one)) for one in ROOT])


def wider(pattern, shapes):
    found = spellings(pattern)
    if found is None:
        return "strings this check cannot bound"
    for spelled in found:
        if not any(len(spelled) == len(shape)
                   and all(one <= held for one, held in zip(spelled, shape))
                   for shape in shapes):
            return repr("".join(min(one) for one in spelled))
    return None


def uids():
    return [f"{prefix}84927103" for prefix in corpus.PREFIXES]


def stamps():
    term = {"kind": "term",
            "entries": {"object_body": {"word": "body",
                                        "definition": "The prose it carries."}}}
    parameter = {"kind": "parameter", "text": "How far a path may go.",
                 "value_type": "count", "entries": {"5": {}}}
    return [corpus.stamp_of("REQ-84927103", {"text": "The product shall run."}),
            corpus.stamp_of("hop_limit", parameter),
            corpus.stamp_of("object_body", term),
            corpus.address_stamp_of("hop_limit", parameter, "5"),
            corpus.address_stamp_of("hop_limit", parameter, corpus.MEMBERS)]


def named_faults(config):
    admits = admitting(config, uids()[0])
    if len(admits) != 1:
        return [f"{CONFIG}: {len(admits)} {RULE} allowlist(s) admit the shape "
                "reqctl mints a uid with; one states it, and this check cannot "
                "say which is it"]
    held = admits[0]
    written = held.get("regexes") or []
    if len(written) != 1:
        return [f"{CONFIG}: the {RULE} uid allowlist states {len(written)} "
                "regex(es); one states the uid shape and this check holds it to "
                "what reqctl mints"]
    found = []
    # @req+ REQ-91184727@qgpF6mhsmj-W fllahn
    if held.get("regextarget") != "secret":
        found.append(
            f"{CONFIG}: the {RULE} uid allowlist states regexTarget "
            f"{held.get('regexTarget')!r}. The shape below describes the value "
            "gitleaks captured, not the line it sat on, and against a line it "
            "matches nothing at all; state regexTarget = \"secret\"")
    if held.get("paths"):
        found.append(
            f"{CONFIG}: the {RULE} uid allowlist states paths. A uid is cited "
            "wherever code names one, and gitleaks joins an "
            "allowlist's conditions with OR unless AND is stated, so a path "
            "here would admit every secret in it; drop the paths, or state "
            "condition = \"AND\" and hold this check to the scope")
    shape = re.compile(written[0])
    for uid in uids():
        if not shape.fullmatch(uid):
            found.append(
                f"{CONFIG}: {written[0]} does not match the uid {uid!r} that "
                "reqctl mints, so a citation of one still fails the scan")
    # @req- fllahn
    # @req+ REQ-89759399@H6dJHl49GRYn l43smi
    beyond = wider(written[0], [[frozenset(one) for one in prefix] + [DIGITS] * 8
                                for prefix in corpus.PREFIXES])
    if beyond:
        found.append(
            f"{CONFIG}: {written[0]} admits {beyond}, beyond the uids "
            "reqctl mints; state the minted kinds and eight digits, anchored "
            "with ^ and $")
    # @req- l43smi
    return found


def lowered(node):
    if isinstance(node, dict):
        keys = [str(key).lower() for key in node]
        twice = sorted({key for key in keys if keys.count(key) > 1})
        if twice:
            raise SystemExit(f"::error::{CONFIG}: {', '.join(twice)} is stated "
                             "under two spellings that differ only by case, and "
                             "gitleaks reads one of them; keep one")
        return {str(key).lower(): lowered(value) for key, value in node.items()}
    if isinstance(node, list):
        return [lowered(one) for one in node]
    return node


def faults(config):
    admits = admitting(config, stamps()[0])
    if len(admits) != 1:
        return [f"{CONFIG}: {len(admits)} {RULE} allowlist(s) admit the shape "
                "reqctl stamps with; one states it, and this check cannot say "
                "which is it"]
    held = admits[0]
    found = named_faults(config)
    written = held.get("regexes") or []
    if len(written) != 1:
        return found + [
            f"{CONFIG}: the {RULE} allowlist states {len(written)} regex(es); "
            "one states the stamp shape and this check holds it to what "
            "reqctl writes"]
    # @req> REQ-89759399@H6dJHl49GRYn os2qmc
    if held.get("condition") != "AND":
        found.append(
            f"{CONFIG}: the {RULE} allowlist states condition "
            f"{held.get('condition')!r}. gitleaks joins an allowlist's "
            "conditions with OR unless AND is stated, and under OR the path "
            "admits every secret in the corpus whatever its shape; state "
            "condition = \"AND\"")
    # @req> REQ-90593907@77_4Pvs9T0Oa ugruo2
    if held.get("regextarget") != "secret":
        found.append(
            f"{CONFIG}: the {RULE} allowlist states regexTarget "
            f"{held.get('regexTarget')!r}. The shape below describes the "
            "value gitleaks captured, not the line it sat on, and against a "
            "line it matches nothing at all -- so every real stamp fails the "
            "scan; state regexTarget = \"secret\"")
    scope = [re.compile(one) for one in held.get("paths") or []]
    # @req+ REQ-14101215@QDD9quPR25YJ pzazjf
    if {"path", "url"} & set(config.get("extend") or {}):
        found.append(
            f"{CONFIG}: [extend] path or url names allowlists this check does "
            "not read; state them here")
    if RULE in ((config.get("extend") or {}).get("disabledrules") or []) or any(
            rule.get("id") == RULE and set(rule) - {"id", "allowlist", "allowlists"}
            for rule in config.get("rules") or []):
        found.append(
            f"{CONFIG}: the {RULE} rule is disabled or redefined, so the scan "
            "admits a stamp anywhere; state only its allowlists here")
    # @req> REQ-89759399@H6dJHl49GRYn mx6gxo
    for one in filter(stamping, everywhere(config)):
        if one is not held:
            found.append(
                f"{CONFIG}: {one.get('description') or 'an allowlist'!r} also "
                "admits the stamp shape; state it in the stamp allowlist alone")
    if held.get("stopwords") or held.get("commits"):
        found.append(
            f"{CONFIG}: the {RULE} allowlist states stopwords or commits, "
            "which admit a secret of any shape; drop them")
    if not scope:
        found.append(
            f"{CONFIG}: the {RULE} allowlist states no paths, so the stamp "
            "shape is admitted everywhere rather than where reqctl writes it; "
            "state the paths the corpus occupies")
    for path in held.get("paths") or []:
        if not confined(path):
            found.append(
                f"{CONFIG}: the {RULE} allowlist path {path} can admit a file "
                f"outside {ROOT}; begin it with ^{ROOT}")
    # @req- pzazjf
    # @req> REQ-90593907@77_4Pvs9T0Oa ef2ben
    if scope and not any(one.search(INSIDE) for one in scope):
        found.append(
            f"{CONFIG}: the {RULE} allowlist does not admit {INSIDE}, where "
            "reqctl writes stamps, so every real stamp fails the scan")
    # @req+ REQ-90593907@77_4Pvs9T0Oa waiych
    shape = re.compile(written[0])
    for stamp in stamps():
        if not shape.fullmatch(stamp):
            found.append(
                f"{CONFIG}: {written[0]} does not match the stamp {stamp!r} that "
                "reqctl writes. The allowlist admits a shape reqctl no longer "
                "produces, so a real stamp now fails the secret scan and the "
                "shape it does admit means nothing")
    # @req- waiych
    # @req+ REQ-89759399@H6dJHl49GRYn gyyeey
    width = len(stamps()[0])
    beyond = wider(written[0], [[DIGEST] * width])
    if beyond:
        found.append(
            f"{CONFIG}: {written[0]} admits {beyond}, beyond the stamps "
            f"reqctl writes; state {width} characters of "
            "[A-Za-z0-9_-], anchored with ^ and $")
    # @req- gyyeey
    return found


def main():
    # @req+ GUARD-83168738@zhoOQpGgBd9R sfnyhq
    try:
        config = tomllib.loads(CONFIG.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as broken:
        print(f"::error::cannot read {CONFIG}: {broken}")
        return 1
    # @req- sfnyhq
    # @req+ REQ-89759399@H6dJHl49GRYn lttpvk
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", FutureWarning)
            found = faults(lowered(config))
    except (re.error, FutureWarning) as broken:
        print(f"::error::{CONFIG}: a regex does not read as gitleaks reads it: "
              f"{broken}; state it in syntax Go and Python read alike")
        return 1
    # @req- lttpvk
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
