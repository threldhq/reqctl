#!/usr/bin/env python3
import sys
from pathlib import Path

from reqctl import corpus


def faults(root):
    # @req+ REQ-21699310@_tcVfQG_ywGM 64pj5j
    nominated = set(corpus.binding_dimensions(root))
    if not nominated:
        return []
    store, _ = corpus.load(root)
    held = {str(item.uid): corpus.raw(item) for item in corpus.items(store)}
    found = []
    for uid, data in held.items():
        if corpus.kind_of(uid, data) != "guard":
            continue
        for address in (corpus.references(data)
                        + corpus.concept_references(data)):
            name = corpus.split_address(address)[0]
            if name in nominated:
                found.append(
                    f"{uid}: references {address}, which binds the guard to "
                    f"{name} -- reword the guard without the reference, or "
                    "state the rule as a requirement")
    return sorted(found)
# @req- 64pj5j


def main():
    found = faults(Path("."))
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except corpus.ReqctlError as unreadable:
        sys.exit(f"{Path(__file__).name}: {unreadable}")
