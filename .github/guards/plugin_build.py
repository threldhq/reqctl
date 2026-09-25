#!/usr/bin/env python3
import json
import sys
import tomllib
from pathlib import Path

WHEEL = Path("reqctl/pyproject.toml")
MARKETPLACE = Path(".claude-plugin/marketplace.json")
MANIFEST = Path(".claude-plugin/plugin.json")


def read(root, path, parse):
    try:
        held = parse((root / path).read_text())
    except (OSError, UnicodeDecodeError, ValueError) as broken:
        return None, f"{path}: cannot read it: {broken}"
    if not isinstance(held, dict):
        return None, f"{path}: cannot read it: it is not a mapping"
    return held, None


def faults(root):
    root = Path(root).resolve()
    wheel, fault = read(root, WHEEL, tomllib.loads)
    if fault:
        return [fault]
    project = wheel.get("project") or {}
    name, version = project.get("name"), project.get("version")
    # @req> GUARD-56838909@thIjmFd7Wvy9 zznuqt
    if not name or not version:
        return [f"{WHEEL}: states no project name or version for the plugin to "
                "match"]
    listed, fault = read(root, MARKETPLACE, json.loads)
    if fault:
        return [fault]
    entry = next((one for one in listed.get("plugins") or []
                  if isinstance(one, dict) and one.get("name") == name), None)
    if entry is None:
        return [f"{MARKETPLACE}: lists no plugin named {name}, the name of the "
                "reqctl wheel"]
    # @req+ GUARD-65225392@myxez9Yz6SOi ziceo7
    source = entry.get("source")
    held = (root / source).resolve() if isinstance(source, str) else None
    if (held is None or not source.startswith("./")
            or not held.is_relative_to(root)):
        return [f"{MARKETPLACE}: {name} is sourced from {source!r}, which is not "
                "a ./ path within this repository -- keep its sources here"]
    # @req- ziceo7
    where = held.relative_to(root) / MANIFEST
    manifest, fault = read(root, where, json.loads)
    if fault:
        return [fault]
    # @req> GUARD-56838909@thIjmFd7Wvy9 5442zm
    if manifest.get("version") != version:
        return [f"{where}: the plugin states version {manifest.get('version')}, "
                f"the reqctl wheel {version} -- state one version in both"]
    return []


def main():
    found = faults(Path("."))
    for fault in found:
        print(f"::error::{fault}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
