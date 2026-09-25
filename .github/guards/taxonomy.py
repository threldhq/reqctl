#!/usr/bin/env python3
import sys
from pathlib import Path

import yaml

from reqctl import corpus

VOCABULARY = "text"
SETTING = 1


def faults(root):
    found = []
    try:
        listed = corpus.item_files(root)
    except corpus.ReqctlError as broken:
        sys.exit(str(broken))
    for path in listed:
        try:
            text = corpus.read_text(path)
        except corpus.ReqctlError as broken:
            sys.exit(str(broken))
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as broken:
            sys.exit(f"{path}: not YAML: {broken}")
        if not isinstance(data, dict):
            sys.exit(f"{path}: item file is not a mapping")
        uid = path.stem
        if corpus.kind_of(uid, data) != "parameter":
            continue
        if data.get("value_type") != VOCABULARY:
            continue
        if len(corpus.entries(data) or {}) <= SETTING:
            continue
        found.append(
            f"{uid}: a parameter of {VOCABULARY} holding more than one member "
            f"is a data item -- `reqctl refile {uid}`")
    return sorted(found)


def main():
    found = faults(Path("."))
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
