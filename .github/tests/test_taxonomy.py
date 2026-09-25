#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import taxonomy

faults = []

SETTINGS = "requirements/params/max_export_size.yml"
VOCABULARY = "requirements/params/review_roles.yml"
FILED = "requirements/data/review_roles.yml"

A_SETTING = ("name: max_export_size\nkind: parameter\nstatus: approved\n"
             "value_type: size\nunit: MB\nentries:\n  100: {}\n")
ONE_WORD = ("name: fallback_locale\nkind: parameter\nstatus: approved\n"
            "value_type: text\nentries:\n  utc: {}\n")
A_VOCABULARY = ("name: review_roles\nkind: parameter\nstatus: approved\n"
                "value_type: text\nentries:\n  owner: {}\n  editor: {}\n")
REFILED = ("name: review_roles\nkind: data\nstatus: approved\n"
           "entries:\n  owner: {}\n  editor: {}\n")
A_COUNTED_SET = ("name: retry_ceiling\nkind: parameter\nstatus: approved\n"
                 "value_type: count\nentries:\n  '3': {}\n  '5': {}\n")
MISTYPED = ("name: review_roles\nkind: data\nstatus: approved\n"
            "value_type: text\nentries:\n  owner: {}\n  editor: {}\n")


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def held(corpse):
    with tempfile.TemporaryDirectory() as room:
        root = Path(room)
        for where, text in corpse.items():
            path = root / where
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        return taxonomy.faults(root)


def refused(corpse):
    with tempfile.TemporaryDirectory() as room:
        root = Path(room)
        for where, text in corpse.items():
            path = root / where
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(text, bytes):
                path.write_bytes(text)
            else:
                path.write_text(text)
        try:
            taxonomy.faults(root)
        except SystemExit as clean:
            return str(clean)
        return ""


case("an empty corpus states nothing to refile", held({}), [])
case("a sized setting is a parameter", held({SETTINGS: A_SETTING}), [])
case("a text parameter of one member is a setting",
     held({"requirements/params/fallback_locale.yml": ONE_WORD}), [])
case("a text parameter of several members is a data item",
     held({VOCABULARY: A_VOCABULARY}),
     ["review_roles: a parameter of text holding more than one member is a "
      "data item -- `reqctl refile review_roles`"])
case("a set of counts is a parameter however many members it holds",
     held({"requirements/params/retry_ceiling.yml": A_COUNTED_SET}), [])
case("the same vocabulary filed as data is left alone",
     held({FILED: REFILED}), [])
case("a data item that states a value_type is left to reqctl validate",
     held({FILED: MISTYPED}), [])
case("a setting beside a vocabulary is not swept up with it",
     held({SETTINGS: A_SETTING, VOCABULARY: A_VOCABULARY}),
     ["review_roles: a parameter of text holding more than one member is a "
      "data item -- `reqctl refile review_roles`"])

case("a stem claimed by two kinds is refused cleanly, not crashed on",
     "two files claim this uid" in
     refused({VOCABULARY: A_VOCABULARY, FILED: REFILED}), True)
case("a non-utf-8 item file is refused cleanly, not crashed on",
     refused({VOCABULARY: b"name: review_roles\nkind: parameter\n\xff\xfe\n"}
             ).startswith("cannot read"), True)

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
