#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import guard_binding

faults = []

MARKED = ('$schema: "https://json-schema.org/draft/2020-12/schema"\n'
          "x-binding: true\ntype: object\n")

PLATFORM = "requirements/data/platform.yml"
REGISTER = ("name: platform\nkind: data\nstatus: approved\n"
            "entries:\n  android: {}\n  ios: {}\n  web: {}\n")
TIER = "requirements/data/tier.yml"
TIERS = ("name: tier\nkind: data\nstatus: approved\n"
         "entries:\n  free: {}\n  paid: {}\n")

BOUND = "requirements/guards/GUARD-10000001.yml"
WHOLE = "requirements/guards/GUARD-10000002.yml"
IN_CRITERION = "requirements/guards/GUARD-10000003.yml"
IN_RATIONALE = "requirements/guards/GUARD-10000004.yml"
PLAIN = "requirements/guards/GUARD-10000005.yml"
OTHER = "requirements/guards/GUARD-10000006.yml"
STATEMENT = "requirements/reqs/REQ-20000001.yml"


def guard(text, criterion=None, rationale=None):
    held = f"kind: guard\nstatus: approved\ntext: {text!r}\n"
    if criterion:
        held += ("acceptance_criteria:\n  - given: 'a build'\n"
                 f"    when: 'the corpus is validated'\n    then: {criterion!r}\n")
    if rationale:
        held += f"rationale: {rationale!r}\n"
    return held


A_MEMBER = guard("Where the build runs on ${platform.android}, the build "
                 "shall refuse an install.")
THE_WHOLE = guard("The build shall refuse an install on ${platform}.")
BY_CRITERION = guard("The build shall refuse an install.",
                     criterion="the ${platform.ios} build is refused")
BY_RATIONALE = guard("The build shall refuse an install.",
                     rationale="It matters on ${platform.web}.")
PLAIN_WORD = guard("The build shall refuse a guard that binds to a platform.")
ANOTHER = guard("The build shall refuse an entry keyed by an "
                "${retry_limit}.")
A_TIER = guard("Where the build runs for the ${tier.paid} plan, the build "
               "shall refuse an install.")
A_REQUIREMENT = ("kind: requirement\nstatus: approved\n"
                 "text: 'Where the product runs on ${platform.android}, the "
                 "product shall offer a share target.'\n")


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def held(corpse, *nominated):
    with tempfile.TemporaryDirectory() as room:
        root = Path(room)
        for where, text in corpse.items():
            path = root / where
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        schemas = root / "requirements" / "schemas"
        schemas.mkdir(parents=True, exist_ok=True)
        for name in nominated:
            (schemas / f"{name}.schema.yaml").write_text(MARKED)
        return guard_binding.faults(root)


def refusal(uid, address, name):
    return (f"{uid}: references {address}, which binds the guard to {name} -- "
            "reword the guard without the reference, or state the rule as a "
            "requirement")


# @req+ REQ-21699310@_tcVfQG_ywGM svkeqh
case("a corpus nominating no dimension names no guard, there being nothing to "
     "bind to",
     held({PLATFORM: REGISTER, BOUND: A_MEMBER}), [])
case("an empty corpus nominates nothing and names nothing", held({}), [])
case("a register with no guard states nothing",
     held({PLATFORM: REGISTER}, "platform"), [])
case("a guard bound to a member is refused",
     held({PLATFORM: REGISTER, BOUND: A_MEMBER}, "platform"),
     [refusal("GUARD-10000001", "platform.android", "platform")])
case("a guard bound to the register whole is refused",
     held({PLATFORM: REGISTER, WHOLE: THE_WHOLE}, "platform"),
     [refusal("GUARD-10000002", "platform", "platform")])
case("a guard bound by a criterion is refused",
     held({PLATFORM: REGISTER, IN_CRITERION: BY_CRITERION}, "platform"),
     [refusal("GUARD-10000003", "platform.ios", "platform")])
case("a guard bound by its rationale is refused",
     held({PLATFORM: REGISTER, IN_RATIONALE: BY_RATIONALE}, "platform"),
     [refusal("GUARD-10000004", "platform.web", "platform")])
BY_LINK = OTHER.replace("10000006", "10000007")
BY_LINK_RATIONALE = OTHER.replace("10000006", "10000008")
A_LINK = guard("Where the build runs on [the android build](platform.android)"
               ", the build shall refuse an install.")
LINK_RATIONALE = guard("The build shall refuse an install.",
                       rationale="It matters on [the web build](platform.web).")

case("a guard bound by a concept link is refused, which binds exactly as a "
     "reference does and is how six existing guards reach a data item",
     held({PLATFORM: REGISTER, BY_LINK: A_LINK}, "platform"),
     [refusal("GUARD-10000007", "platform.android", "platform")])
case("a guard bound by a concept link in its rationale is refused",
     held({PLATFORM: REGISTER, BY_LINK_RATIONALE: LINK_RATIONALE}, "platform"),
     [refusal("GUARD-10000008", "platform.web", "platform")])
case("a guard naming the word without referencing it stands",
     held({PLATFORM: REGISTER, PLAIN: PLAIN_WORD}, "platform"), [])
case("a guard referencing another item stands",
     held({PLATFORM: REGISTER, OTHER: ANOTHER}, "platform"), [])
case("a requirement bound to a member stands",
     held({PLATFORM: REGISTER, STATEMENT: A_REQUIREMENT}, "platform"), [])
case("a guard bound to a dimension the corpus does not nominate stands",
     held({PLATFORM: REGISTER, TIER: TIERS, BOUND: A_MEMBER}, "tier"), [])
case("a guard bound to the second of two nominated dimensions is refused",
     held({PLATFORM: REGISTER, TIER: TIERS, OTHER: A_TIER}, "platform", "tier"),
     [refusal("GUARD-10000006", "tier.paid", "tier")])
case("every bound guard is named, not only the first",
     held({PLATFORM: REGISTER, BOUND: A_MEMBER, WHOLE: THE_WHOLE}, "platform"),
     [refusal("GUARD-10000001", "platform.android", "platform"),
      refusal("GUARD-10000002", "platform", "platform")])
# @req- svkeqh

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("guard binding self-test: 0 fault(s)")
sys.exit(0)
