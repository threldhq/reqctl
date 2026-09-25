#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import plugin_build

faults = []

WHEEL = '[project]\nname = "reqctl"\nversion = "1.2.0"\n'
HERE = {"name": "reqctl", "source": "./plugin"}


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def found(wheel=WHEEL, listed=None, manifest=None):
    with tempfile.TemporaryDirectory() as held:
        root = Path(held)
        (root / "reqctl").mkdir()
        (root / "reqctl" / "pyproject.toml").write_text(wheel)
        if listed is not None:
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "marketplace.json").write_text(
                listed if isinstance(listed, str) else json.dumps(listed))
        if manifest is not None:
            (root / "plugin" / ".claude-plugin").mkdir(parents=True)
            (root / "plugin" / ".claude-plugin" / "plugin.json").write_text(
                json.dumps(manifest))
        return plugin_build.faults(root)


def reading(got):
    return [fault.split(": cannot read it: ")[0] for fault in got]


OUTSIDE = ("{0}: reqctl is sourced from {1!r}, which is not a ./ path within "
           "this repository -- keep its sources here")
AT = ".claude-plugin/marketplace.json"

case("a plugin sourced here at the wheel's version passes",
     found(listed={"plugins": [HERE]}, manifest={"version": "1.2.0"}), [])
case("a plugin at another version than the wheel is refused",
     found(listed={"plugins": [HERE]}, manifest={"version": "1.1.0"}),
     ["plugin/.claude-plugin/plugin.json: the plugin states version 1.1.0, "
      "the reqctl wheel 1.2.0 -- state one version in both"])
elsewhere = {"source": "github", "repo": "someone/plugin"}
case("a plugin sourced from another repository is refused",
     found(listed={"plugins": [{"name": "reqctl", "source": elsewhere}]}),
     [OUTSIDE.format(AT, elsewhere)])
case("a marketplace naming no plugin after the wheel is refused",
     found(listed={"plugins": [{"name": "other", "source": "./plugin"}]}),
     [f"{AT}: lists no plugin named reqctl, the name of the reqctl wheel"])
case("a repository shipping no marketplace is refused",
     reading(found()), [AT])
case("a marketplace that is not a mapping is refused",
     found(listed="[]"), [f"{AT}: cannot read it: it is not a mapping"])
case("a wheel stating no version is refused, whatever the plugin states",
     found(wheel='[project]\nname = "reqctl"\n', listed={"plugins": [HERE]},
           manifest={}),
     ["reqctl/pyproject.toml: states no project name or version for the "
      "plugin to match"])

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("plugin build self-test: 0 fault(s)")
sys.exit(0)
