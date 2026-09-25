#!/usr/bin/env python3
import re
import sys
import tomllib
from pathlib import Path

from reqctl import corpus

CONFIG = Path(".gitleaks.toml")
RULE = "generic-api-key"
INSIDE = str(corpus.folder_for(".", "data") / "file_store.yml")
OUTSIDE = ".github/workflows/ci.yml"


def allowlists(config):
    for rule in config.get("rules") or []:
        if rule.get("id") == RULE:
            return rule.get("allowlists") or []
    return []


def admitting(config, sample):
    return [held for held in allowlists(config)
            if any(re.fullmatch(one, sample) for one in held.get("regexes") or [])]


def uids():
    return [f"{prefix}84927103" for prefix in corpus.PREFIXES]


def stamps():
    term = {"kind": "term",
            "entries": {"item_body": {"word": "body",
                                        "definition": "The prose it carries."}}}
    parameter = {"kind": "parameter", "text": "How far a path may go.",
                 "value_type": "count", "entries": {"5": {}}}
    return [corpus.stamp_of("REQ-84927103", {"text": "The product shall run."}),
            corpus.stamp_of("hop_limit", parameter),
            corpus.stamp_of("item_body", term),
            corpus.address_stamp_of("hop_limit", parameter, "5"),
            corpus.address_stamp_of("hop_limit", parameter, corpus.MEMBERS)]


def named_faults(config):
    admits = admitting(config, uids()[0])
    if len(admits) != 1:
        return [f"{CONFIG}: {len(admits)} {RULE} allowlist(s) admit the shape "
                "reqctl mints a uid with; one states it, and this test cannot "
                "say which is it"]
    held = admits[0]
    written = held.get("regexes") or []
    if len(written) != 1:
        return [f"{CONFIG}: the {RULE} uid allowlist states {len(written)} "
                "regex(es); one states the uid shape and this test holds it to "
                "what reqctl mints"]
    found = []
    if held.get("regexTarget") != "secret":
        found.append(
            f"{CONFIG}: the {RULE} uid allowlist states regexTarget "
            f"{held.get('regexTarget')!r}. The shape below describes the value "
            "gitleaks captured, not the line it sat on, and against a line it "
            "matches nothing at all; state regexTarget = \"secret\"")
    if held.get("paths"):
        found.append(
            f"{CONFIG}: the {RULE} uid allowlist states paths. A uid is cited "
            "wherever code and tests name one, and gitleaks joins an "
            "allowlist's conditions with OR unless AND is stated, so a path "
            "here would admit every secret in it; drop the paths, or state "
            "condition = \"AND\" and hold this test to the scope")
    shape = re.compile(written[0])
    for uid in uids():
        if not shape.fullmatch(uid):
            found.append(
                f"{CONFIG}: {written[0]} does not match the uid {uid!r} that "
                "reqctl mints, so a citation of one still fails the scan")
    for near in ("REQ-8492710", "REQ-849271034", "req-84927103", "REQX-84927103",
                 "REQ-8492710a", "sk-live-84927103aBcDeFgHiJkLmNoP"):
        if shape.fullmatch(near):
            found.append(
                f"{CONFIG}: {written[0]} also matches {near!r}, which is not a "
                "uid. An allowlist wider than the uid admits a secret of that "
                "shape")
    return found


def faults(config):
    admits = admitting(config, stamps()[0])
    if len(admits) != 1:
        return [f"{CONFIG}: {len(admits)} {RULE} allowlist(s) admit the shape "
                "reqctl stamps with; one states it, and this test cannot say "
                "which is it"]
    held = admits[0]
    found = named_faults(config)
    written = held.get("regexes") or []
    if len(written) != 1:
        return found + [
            f"{CONFIG}: the {RULE} allowlist states {len(written)} regex(es); "
            "one states the stamp shape and this test holds it to what "
            "reqctl writes"]
    if held.get("condition") != "AND":
        found.append(
            f"{CONFIG}: the {RULE} allowlist states condition "
            f"{held.get('condition')!r}. gitleaks joins an allowlist's "
            "conditions with OR unless AND is stated, and under OR the path "
            "admits every secret in the corpus whatever its shape; state "
            "condition = \"AND\"")
    if held.get("regexTarget") != "secret":
        found.append(
            f"{CONFIG}: the {RULE} allowlist states regexTarget "
            f"{held.get('regexTarget')!r}. The shape below describes the "
            "value gitleaks captured, not the line it sat on, and against a "
            "line it matches nothing at all -- so every real stamp fails the "
            "scan; state regexTarget = \"secret\"")
    scope = [re.compile(one) for one in held.get("paths") or []]
    if not scope:
        found.append(
            f"{CONFIG}: the {RULE} allowlist states no paths, so the stamp "
            "shape is admitted everywhere rather than where reqctl writes it; "
            "state the paths the corpus occupies")
    if any(one.search(OUTSIDE) for one in scope):
        found.append(
            f"{CONFIG}: the {RULE} allowlist admits {OUTSIDE}, which is not "
            "the corpus. A stamp is only ever written by reqctl into the "
            "corpus, so a scope reaching past it admits this shape from a "
            "hand that is not reqctl's")
    if scope and not any(one.search(INSIDE) for one in scope):
        found.append(
            f"{CONFIG}: the {RULE} allowlist does not admit {INSIDE}, where "
            "reqctl writes stamps, so every real stamp fails the scan")
    shape = re.compile(written[0])
    for stamp in stamps():
        if not shape.fullmatch(stamp):
            found.append(
                f"{CONFIG}: {written[0]} does not match the stamp {stamp!r} that "
                "reqctl writes. The allowlist admits a shape reqctl no longer "
                "produces, so a real stamp now fails the secret scan and the "
                "shape it does admit means nothing")
    for near in ("A" * 42, "A" * 44, "A" * 42 + "+"):
        if shape.fullmatch(near):
            found.append(
                f"{CONFIG}: {written[0]} also matches {near!r}, which is not a "
                "stamp. An allowlist wider than the digest admits a secret of "
                "that width")
    return found


def main():
    try:
        config = tomllib.loads(CONFIG.read_text())
    except (OSError, tomllib.TOMLDecodeError) as broken:
        print(f"::error::cannot read {CONFIG}: {broken}")
        return 1
    found = faults(config)
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
