import copy
import datetime
import functools
import math
import re
import unicodedata
from pathlib import Path

from jsonschema import FormatChecker
from jsonschema.exceptions import best_match

from . import baseline as _baseline
from . import corpus
from . import fields as _fields
from . import history
from . import settings as _settings

SCHEMAS = ("requirement", "guard", "dictionary", "baseline")
# @req> REQ-20325022@eJ3lXlumh7tY m2dmcp
ALIAS_SEPARATOR = ","


def _schemas_are_schemas(root):
    problems, broken = [], set()
    for name in sorted(set(SCHEMAS) | set(corpus.schema_names(root))):
        try:
            corpus.schema(root, name)
        # @req> REQ-14895892@JjrTwHoJqTRe 22v4gm
        except corpus.RefusedCopy:
            raise
        except corpus.ReqctlError as unreadable:
            problems.append(str(unreadable))
            broken.add(name)
    return problems, broken


NAMED_FOLDERS = frozenset(
    corpus.FOLDERS[kind] for kind in ("parameter", "term", "data"))


def _identity(root, path, data):
    uid = path.stem
    problems = []
    kind = corpus.kind_of(uid, data or {})
    if kind in (None, "requirement", "guard"):
        unreadable_named = (data is None and kind is None
                           and path.parent.name in NAMED_FOLDERS)
        if not unreadable_named and not corpus.UID.match(uid):
            # @req> REQ-30898926@Vu28eWaG_1mE awdccf
            problems.append(f"{uid}: filename is not PREFIX-NNNNNNNN -- rename "
                            "the file by hand to a uid of that form")
    elif not corpus.UID.match(uid) and uid != corpus.name_of(uid, data or {}):
        # @req> REQ-30898926@Vu28eWaG_1mE 5uybod
        problems.append(
            f"{uid}: filename is not the name the item carries -- rename the "
            "file by hand to that name, or give both one name with `reqctl "
            f"rename {uid} NAME`")
    # @req> REQ-48186295@E_K39S9hbhEz yvekz4
    if corpus.UID.match(uid) or kind is not None:
        expected = corpus.folder_for(root, corpus.kind_of(uid, data))
        if path.parent != expected:
            # @req> REQ-30898926@Vu28eWaG_1mE 7vh2hf
            problems.append(
                f"{uid}: file is in {path.parent.name}/, not {expected.name}/ "
                f"-- move it into {expected.name}/ by hand"
            )
    if path.suffix != ".yml":
        # @req> REQ-30898926@Vu28eWaG_1mE 52fz5f
        problems.append(f"{uid}: item file is named {path.name}; items are .yml "
                        f"-- rename it by hand to {uid}.yml")
    return problems


def schema_problems(root, uid, data):
    try:
        declared = corpus.schema_for(root, corpus.kind_of(uid, data),
                                     corpus.name_of(uid, data))
    # @req> REQ-14895892@JjrTwHoJqTRe r2dbx6
    except corpus.RefusedCopy:
        raise
    except corpus.ReqctlError as absent:
        return [f"{uid}: {absent}"]
    # @req+ REQ-33359142@u8vbxFMjrV6Z p3hzqn
    # @req> REQ-62072712@m81ZZqYdquaS qvzmoq
    problems = []
    for error in sorted(corpus.validator(declared, DATED).iter_errors(data), key=str):
        error = best_match([error])
        where = ".".join(str(p) for p in error.absolute_path) or "(item)"
        said = error.message
        if error.validator == "not" and error.validator_value in ({}, True):
            kind = corpus.kind_of(uid, data)
            said = ("does not apply to a data item" if kind == "data"
                    else f"does not apply to a {kind}")
        # @req> REQ-30898926@Vu28eWaG_1mE cgpecz
        problems.append(f"{uid}: schema: {where}: {said} -- correct {where} "
                        "through the flag that writes it, or by hand in "
                        f"{uid}'s file where none does")
    # @req- p3hzqn
    # @req> REQ-35443917@I_xqd07AsRI5 znhrrb
    if data.get("verification") == "automated_test" and not any(
            problem.startswith(f"{uid}: schema: verification:")
            for problem in problems):
        # @req> REQ-30898926@Vu28eWaG_1mE pz3h7r
        problems.append(f"{uid}: verification: automated_test is not a "
                        "verification method; state inspection, analysis or "
                        "demonstration")
    return problems


def ears_forms(noun):
    return (f"  The {noun} shall <response>.\n"
            f"  When <trigger>, the {noun} shall <response>.\n"
            f"  While <state>, the {noun} shall <response>.\n"
            f"  If <condition>, then the {noun} shall <response>.\n"
            f"  Where <feature>, the {noun} shall <response>.")
CONDITIONAL = ("When ", "While ", "Where ", "If ")
OPENERS = CONDITIONAL + ("The ",)
SHALL = re.compile(r"\bshall\b")
SUBJECTS = {
    "REQ-": ("product",
             "a requirement governs what the product ships to its users; a rule "
             "about what makes or checks it is a guard"),
    "GUARD-": ("build",
               "a guard governs what makes, checks and governs the product; "
               "a statement about what a user can do is a requirement"),
}
SUBJECT = {noun: re.compile(rf"\bthe\s+{noun}\s+shall\b", re.IGNORECASE)
           for noun, _ in SUBJECTS.values()}


def ears(uid, data):
    stated = next((v for k, v in SUBJECTS.items() if uid.startswith(k)), None)
    if stated is None:
        return []
    noun, because = stated
    text = " ".join(str(data.get("text") or "").split())

    faults = []
    # @req+ REQ-18950462@TJVbxYWG6Dcw ey43wr
    obligations = list(SHALL.finditer(text))
    if not obligations:
        faults.append("no 'shall' -- a requirement states an obligation")
    elif len(obligations) > 1:
        faults.append("more than one 'shall' -- one requirement states one "
                      "obligation; split the statement")
    elif not re.search(r"\w", text[obligations[0].end():]):
        faults.append("nothing follows 'shall' -- the response is the obligation")
    # @req> REQ-35156546@fPsYxachw_U9 nam7kw
    if obligations and not SUBJECT[noun].search(text):
        faults.append(f'the subject must be "the {noun}" -- {because}')
    if not text.startswith(OPENERS):
        faults.append("must open with When, While, Where, If, or The")
    elif text.startswith(CONDITIONAL):
        opener = next(o for o in CONDITIONAL if text.startswith(o))
        comma = text.find(",")
        if comma == -1:
            faults.append("the precondition must be closed with a comma")
        elif not text[len(opener):comma].strip():
            faults.append(f"the precondition between '{opener.strip()}' and "
                          "the comma is empty")
        elif obligations and obligations[0].start() < comma:
            faults.append("'shall' sits in the precondition -- the obligation "
                          "follows the comma")
        if text.startswith("If ") and ", then " not in text:
            faults.append("'If ...' must continue ', then the ... shall ...'")
    # @req- ey43wr

    if not faults:
        return []
    # @req> REQ-30898926@Vu28eWaG_1mE ew3q5h
    return [
        f"{uid}: EARS: {'; '.join(faults)}\n"
        f"  statement: {text[:100]}{'...' if len(text) > 100 else ''}\n"
        "  restate it with --text in one of these forms:\n"
        f"{ears_forms(noun)}"
    ]


KEY_SHAPES = {
    "count": re.compile(r"^(0|[1-9][0-9]*)$"),
    "duration": re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    "size": re.compile(r"^(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    "ratio": re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    "percentage": re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    "currency": re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$"),
    "boolean": re.compile(r"^(true|false)$"),
    "text": re.compile(r"^.+$"),
}
UNITLESS = ("count", "ratio", "boolean", "text")
VALUE_TYPES = "value_types"
# @req> REQ-74163593@shkbFgp8gpvT iiu22k
RETIRED = ("superseded", "deprecated")


NESTING = 100


def _nesting(uid, held):
    # @req> REQ-30898926@Vu28eWaG_1mE r3hsm2
    return [f"{uid}: entry {'.'.join(path)} nests deeper than {NESTING} "
            "levels -- flatten it"
            for path, fields in _entries_within(held) if fields is None]


def _entries_within(held, path=(), seen=()):
    if not isinstance(held, dict) or id(held) in seen:
        return
    if len(seen) >= NESTING:
        yield path, None
        return
    seen = seen + (id(held),)
    for key, fields in held.items():
        if isinstance(fields, dict):
            where = path + (str(key),)
            yield where, fields
            for name, value in fields.items():
                yield from _entries_within(value, where + (str(name),), seen)


def _written(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return format(value, "f")
    return str(value) if isinstance(value, (int, str)) else ""


def _typed(where, value_type, stated, unit):
    problems = []
    shape = KEY_SHAPES.get(value_type)
    if shape is None and isinstance(value_type, str):
        # @req> REQ-30898926@Vu28eWaG_1mE sza2az
        problems.append(f"{where}: value_type {value_type} is not a type "
                        "reqctl reads an entry key as -- state one with "
                        "--value-type")
    if shape is not None:
        # @req> REQ-41697188@IRR8A-_NbYw4 fv4qpq
        for named, written in stated:
            if not shape.match(written):
                # @req> REQ-30898926@Vu28eWaG_1mE mhsloy
                problems.append(f"{where}: {named} does not parse as "
                                f"{value_type} -- write it as a {value_type}, "
                                "or change value_type to the type it is")
    # @req+ REQ-57061306@grhOhf7rpAJV gf75aj
    if value_type in UNITLESS and unit is not None:
        # @req> REQ-30898926@Vu28eWaG_1mE gwseiw
        problems.append(f"{where}: unit does not apply to {value_type} -- "
                        "drop it with --no-unit on a parameter, or --unset "
                        "unit on a data entry")
    if (value_type is not None and value_type not in UNITLESS
            and unit is None):
        # @req> REQ-30898926@Vu28eWaG_1mE o447gk
        problems.append(f"{where}: {value_type} carries a unit -- state it "
                        "with --unit on a parameter, or --set unit=UNIT on a "
                        "data entry")
    # @req- gf75aj
    return problems


def dictionary_rules(uid, data):
    problems = []
    item_kind = corpus.kind_of(uid, data)
    declared = data.get("kind")
    if declared is not None and declared != item_kind:
        # @req> REQ-30898926@Vu28eWaG_1mE wvfq3z
        problems.append(
            f"{uid}: states kind {declared} -- state {item_kind} or mint the "
            f"item you meant")
    held = corpus.entries(data)
    if held is None or uid.startswith("REQ-"):
        return problems
    # @req> REQ-67450031@dHzdY0EyKyJ3 5qg2a5
    for key in ("default", "pinned", "text", "name"):
        if key in held and (item_kind, corpus.name_of(uid, data)) != ("data", VALUE_TYPES):
            # @req> REQ-30898926@Vu28eWaG_1mE iuktgn
            problems.append(f"{uid}: an entry may not be keyed {key} -- it "
                            "would shadow an item field of that name; rename "
                            "the entry")
    # @req> REQ-22887335@Tt3HpjzWuiU6 idfqw5
    if corpus.MEMBERS in held:
        # @req> REQ-30898926@Vu28eWaG_1mE 35cjyj
        problems.append(f"{uid}: an entry may not be keyed {corpus.MEMBERS} -- "
                        "that address pins the item's membership; rename the "
                        "entry")
    problems += _nesting(uid, held)
    if item_kind == "term":
        # @req> REQ-79013939@LHWesLk8a6d7 wcl7vt
        if len(held) != 1:
            # @req> REQ-30898926@Vu28eWaG_1mE hckx4k
            problems.append(f"{uid}: a term holds exactly one entry, its word "
                            f"-- edit {uid}'s file by hand so it holds that "
                            "one entry")
        # @req+ REQ-47317077@nmlbp2InoWXJ iwiit6
        stated = corpus.term_fields(data).get("word")
        if not (isinstance(stated, str) and stated.strip()):
            # @req> REQ-30898926@Vu28eWaG_1mE 3kpufa
            problems.append(f"{uid}: word is {stated!r} -- a term states the "
                            "word it is known by, as text; the entry key is a "
                            "handle and addresses it -- state the word with "
                            "--term")
        # @req- iwiit6
        # @req+ REQ-20325022@eJ3lXlumh7tY smwuev
        aliases = corpus.term_fields(data).get("aliases")
        for alias in aliases if isinstance(aliases, list) else []:
            if ALIAS_SEPARATOR in str(alias):
                # @req> REQ-30898926@Vu28eWaG_1mE y3z2hn
                problems.append(
                    f"{uid}: alias {alias!r} holds {ALIAS_SEPARATOR!r}, which "
                    "separates an alias list -- give each wording an alias of "
                    "its own")
        # @req- smwuev
        # @req> REQ-15469759@ETBwvNW6rbpC b6qizb
        for phrase, reason in corpus.unclaimed(data).items():
            if not reason.strip():
                # @req> REQ-30898926@Vu28eWaG_1mE coceck
                problems.append(
                    f"{uid}: records \"{phrase}\" as not the term but gives no "
                    f"reason -- write --unclaimed \"{phrase}=the reason\"")
        # @req+ REQ-23885960@rwNen-FIWBND 5n63fi
        words = [_worded(word) for word in _term_words(data)]
        for phrase in corpus.unclaimed(data):
            if not any(word.search(phrase) for word in words):
                # @req> REQ-30898926@Vu28eWaG_1mE gnjmvl
                problems.append(
                    f"{uid}: records \"{phrase}\" as not the term, but it holds "
                    "neither the word nor an alias -- record a phrase that holds "
                    f"one, or drop it with --drop-unclaimed \"{phrase}\"")
        # @req- 5n63fi
        return problems
    # @req+ REQ-67914848@cRb9rHls6z6c fnsqos
    default = data.get("default")
    if default is not None and default not in held:
        # @req> REQ-30898926@Vu28eWaG_1mE weapt5
        problems.append(f"{uid}: default names {default!r}, which is not an "
                        "entry -- name an entry with --default, or clear it "
                        "with --no-default")
    # @req- fnsqos
    if item_kind == "data":
        for key in held:
            if not corpus.DATA_KEY.match(str(key)):
                # @req> REQ-30898926@Vu28eWaG_1mE qgxblp
                problems.append(f"{uid}: entry key {key!r} is not a snake_case "
                                "handle -- add the entry again under a "
                                "snake_case key with --new-entry and remove "
                                "this one with --drop-entry, or rekey it by hand")
        return problems
    return problems + _typed(
        uid, data.get("value_type"),
        [(f"entry key {key!r}", key if isinstance(key, str) else "")
         for key in held],
        data.get("unit"))


def text_values(uid, data):
    if corpus.kind_of(uid, data) != "parameter" or data.get("value_type") != "text":
        return []
    problems = []
    # @req> REQ-83091747@onYntcqXXhk7 q5fj2f
    for member in corpus.entries(data) or {}:
        if not isinstance(member, str):
            continue
        found = QUANTITY.fullmatch(re.sub(r"\A[+-](?=\.?\d)", "", member.strip()))
        if found and not isinstance(_quantity(found.group(1)), str):
            # @req> REQ-30898926@Vu28eWaG_1mE btxjsu
            problems.append(
                f"{uid}: text value {member!r} is shaped like a quantity -- "
                "give it a numeric value_type, or reword the name"
            )
    # @req> REQ-40026456@tmXkAn-osOnn 6qstia
    if len(corpus.entries(data) or {}) > 1:
        # @req> REQ-30898926@Vu28eWaG_1mE 23iaaz
        problems.append(f"{uid}: a parameter of text holding more than one "
                        f"member is a data item -- `reqctl refile {uid}`")
    return problems


# @req> REQ-98653444@_BYrN0hH1mzV gvf6gm
def repeated_labels(uid, data):
    criteria = data.get("acceptance_criteria")
    if not isinstance(criteria, list):
        return []
    problems = []
    for at, criterion in enumerate(criteria, 1):
        for part, said in (criterion.items() if isinstance(criterion, dict) else ()):
            found = (re.match(rf"{re.escape(part)}\b",
                              "".join(filter(str.isprintable,
                                             re.sub(r"\s", " ", said))).lstrip(),
                              re.IGNORECASE)
                     if isinstance(part, str) and isinstance(said, str) else None)
            if found:
                # @req> REQ-30898926@Vu28eWaG_1mE jpevge
                problems.append(f"{uid}: criterion {at}'s {part} {said!r} begins "
                                f"with {found.group()!r}, which reqctl writes "
                                f"before it -- drop the word from the {part}")
    return problems


def hidden(text):
    return next((c for i, c in enumerate(text)
                 if not c.isprintable() or (i == 0 and unicodedata.category(c) == "Mn")),
                None)


def hidden_fault(char):
    if len(f"a{char}b".splitlines()) > 1:
        return f"holds U+{ord(char):04X}, a line break -- write it as one line"
    if char.isspace():
        return (f"holds U+{ord(char):04X}, which prints as a plain space but "
                "is not one -- respace it with ordinary spaces")
    return (f"holds U+{ord(char):04X}, which prints as nothing -- retype it "
            "rather than pasting it")


def _strings(node, at=()):
    if isinstance(node, set):
        node = dict.fromkeys(node)
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                yield at, key
            yield from _strings(value, at + (str(key),))
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from _strings(value, at + (str(index),))
    elif isinstance(node, str):
        yield at, node


# @req> REQ-22682482@F_OIMxlkifKy ijkpsx
def listed_fields(root, uid, data):
    if corpus.kind_of(uid, data) != "data":
        return []
    name = corpus.name_of(uid, data)
    schema = corpus.schema_for(root, "data", name)
    own = corpus.schema_name_at(root, "data", name) != corpus.schema_name_for("data")
    held = _fields._merged(schema, "data")[0].get("entries", {})
    listed = data.get("fields") if isinstance(data.get("fields"), list) else []
    problems = []
    for key, entry in sorted((corpus.entries(data) or {}).items(),
                             key=lambda item: str(item[0])):
        if not isinstance(entry, dict):
            continue
        applied = _fields._resolved(schema, corpus.mapping(held, "properties").get(
            str(key), held.get("additionalProperties")))
        others = applied.get("additionalProperties")
        if own and (others is False or isinstance(others, dict)):
            continue
        # @req> REQ-30898926@Vu28eWaG_1mE yee54k
        problems += [f"{uid}: entry {key} holds the field {field}, which its schema does "
                     f"not declare and the data item does not list -- it lists "
                     f"{', '.join(map(str, listed)) or 'no fields'}; correct the field, "
                     "or add it to fields"
                     for field in sorted(map(str, entry))
                     if field not in corpus.mapping(applied, "properties")
                     and field not in listed]
    return problems


# @req> REQ-20342497@XOTP8seel4tN sm5nxf
def _shadowed_blocks(records, root):
    # @req> REQ-30898926@Vu28eWaG_1mE azzv2t
    return [f"{uid}: an entry may not be keyed {key} -- the schema marks {key} as "
            "an addressable block, so an address naming it would name both; "
            "rename the entry"
            for uid, data in sorted(records.items())
            for blocks in [corpus.addressable_blocks(root, uid, data)]
            for key in sorted(map(str, corpus.entries(data) or {})) if key in blocks]


# @req> REQ-79956352@OsoTGRd6D5CZ 5uqc7i
def hidden_values(uid, data):
    problems = []
    for at, said in _strings(data):
        char = hidden(said)
        if char is not None:
            # @req> REQ-30898926@Vu28eWaG_1mE gpeu6h
            problems.append(f"{uid}: {'.'.join(at) or '(item)'} {said!r} "
                            f"{hidden_fault(char)}")
    return problems


def _relations(uid, data, records, canonical, known):
    stated = data.get("relations")
    # @req> REQ-30898926@Vu28eWaG_1mE cyqvl3
    problems = [
        f"{uid}: relates {target!r}, which is not a {corpus.NAMED} uid -- "
        f"remove it from {uid}'s relations by hand"
        for target in sorted(stated if isinstance(stated, dict) else {}, key=str)
        if not isinstance(target, str)
    ]
    requirement = uid.startswith("REQ-")
    for target in sorted(corpus.mapping(data, "relations")):
        # @req> REQ-26911169@Ty70WfMx9YfH p2wcdn
        if target == uid:
            # @req> REQ-30898926@Vu28eWaG_1mE 5usqw3
            problems.append(f"{uid}: links to itself -- `reqctl unrelate "
                            f"{uid} {uid}`")
            continue
        if requirement:
            held = canonical.get(target)
            kind = (corpus.kind_of(held, records[held]) if held in records
                    else corpus.kind_for_uid(target))
            if kind in ("parameter", "data"):
                noun = "a parameter" if kind == "parameter" else "a data item"
                # @req> REQ-30898926@Vu28eWaG_1mE 3bxk3t
                problems.append(
                    f"{uid}: relates {target}; {noun} is bound by referencing "
                    "it in the statement, not by a relation -- `reqctl "
                    f"unrelate {uid} {target}`"
                )
                continue
            if kind == "term":
                # @req> REQ-30898926@Vu28eWaG_1mE iyunoa
                problems.append(
                    f"{uid}: relates {target}; a term is bound by linking it in "
                    "the statement, written [the words](" + target + ") -- "
                    f"`reqctl unrelate {uid} {target}`"
                )
                continue
        # @req> REQ-35877465@zMIttKgLLwy- cx6r6x
        if target not in known:
            # @req> REQ-30898926@Vu28eWaG_1mE 22tyzi
            problems.append(f"{uid}: links to {target}, which does not exist "
                            f"-- `reqctl unrelate {uid} {target}`, or mint "
                            f"{target} with `reqctl new`")
    return problems


def _references(uid, data, known, root):
    problems = []
    # @req+ REQ-44791607@6FX5SSp9MG3B e5vzf6
    for address in corpus.references(data):
        target, _ = corpus.split_address(address)
        if target not in known:
            # @req> REQ-30898926@Vu28eWaG_1mE wpeyzk
            problems.append(f"{uid}: references {target}, which does not "
                            f"exist -- mint {target} with `reqctl new`, or "
                            f"reword {uid} without the reference")
    for near in corpus.PARAM_NEAR.finditer(corpus.prose(data)):
        token = near.group()
        if not corpus.PARAM_REF.fullmatch(token):
            # @req> REQ-30898926@Vu28eWaG_1mE vin7kb
            problems.append(
                f"{uid}: text contains {token}, which is not a parameter "
                f"reference -- the form is {corpus.NAME_FORM}"
            )
    for address in corpus.concept_references(data):
        target, _ = corpus.split_address(address)
        if target not in known:
            # @req> REQ-30898926@Vu28eWaG_1mE 7dubyp
            problems.append(f"{uid}: links to {target}, which does not exist "
                            f"-- mint {target} with `reqctl new`, or reword "
                            f"{uid} without the link")
    # @req- e5vzf6
    for near in corpus.CONCEPT_NEAR.finditer(
            corpus.CONCEPT_LINK.sub(" ", corpus.prose(data))):
        # @req> REQ-30898926@Vu28eWaG_1mE b35ssj
        problems.append(
            f"{uid}: {' '.join(near.group(1).split())} does not read as a "
            "link -- an item is addressed by the name it carries, the words "
            "and the address each sit on one line, a term is linked whole"
        )
    # @req> REQ-48500355@rnstkLKM48vN f7binw
    for near in corpus.TERM_NEAR.finditer(
            corpus.unlinked_prose(own_words(root, uid, data))):
        # @req> REQ-30898926@Vu28eWaG_1mE j74ncb
        problems.append(
            f"{uid}: text contains {near.group()} outside a link -- a term is "
            f"written {corpus.LINK_FORM}"
        )
    return problems


def _term_words(data):
    fields = corpus.term_fields(data)
    aliases = fields.get("aliases")
    words = [corpus.term_word(data),
             *(aliases if isinstance(aliases, list) else [])]
    return [word.strip() for word in words
            if isinstance(word, str) and word.strip()]


def _worded(text):
    return re.compile(r"(?<![\w-])" + r"\s+".join(map(re.escape, text.split()))
                      + r"(?![\w-])", re.IGNORECASE)


def term_index(records):
    return [
        (uid, word, pattern,
         [(_worded(phrase), reason)
          for phrase, reason in corpus.unclaimed(data).items()
          if pattern.search(phrase)])
        for uid, data in sorted(records.items())
        if corpus.kind_of(uid, data) == "term"
        for word in _term_words(data)
        for pattern in [re.compile(r"(?<![\w-])" + re.escape(word) + r"(?![\w-])",
                                   re.IGNORECASE)]
    ]


def _outside(text, phrases):
    for phrase, _ in phrases:
        text = phrase.sub(" ", text)
    return text


def _bare_terms(uid, data, defined):
    # @req+ REQ-83702299@kBGzIwAyKDHL tmczgb
    bare = corpus.unlinked_prose(data)
    # @req> REQ-24481048@ZhiYUpKwnPlA bapzey
    # @req> REQ-30898926@Vu28eWaG_1mE db25wj
    return [
        f"{uid}: uses \"{word}\" without linking it -- write "
        f"[{word}]({term_uid}), or reword so the statement does not "
        "claim the term"
        for term_uid, word, pattern, phrases in defined
        if term_uid != uid and pattern.search(_outside(bare, phrases))
    ]
    # @req- tmczgb


def exempted(records, root, exempt):
    prose = {uid: corpus.unlinked_prose(own_words(root, uid, data))
             for uid, data in records.items()}
    # @req> REQ-88221320@vIuzLHP0hHUo 5gpgix
    # @req> REQ-46373547@54MxhOaz3t8O 3lh7ij
    exempt += sorted(
        f"{uid}: \"{' '.join(found.group().split())}\" accepted unlinked, a phrase recorded on term {term_uid} -- {reason}"
        for term_uid, _, _, phrases in term_index(_approved(records))
        for uid, text in prose.items() if uid != term_uid
        for phrase, reason in phrases
        for found in phrase.finditer(text)
    )
    return []


def unlinked_terms(uid, data, records, root):
    return _bare_terms(uid, own_words(root, uid, data),
                       term_index(_approved(records)))


def _unlinked_terms(records, root):
    defined = term_index(_approved(records))
    return [problem
            for uid, data in sorted(records.items())
            for problem in _bare_terms(uid, own_words(root, uid, data), defined)]


QUANTITY = re.compile(
    r"(?<!\w)(?<!\d\.)(?<![^\W\d_]-)"
    r"(\.?\d[\d,_]*(?:\.\d+)*(?:[eE][+-]?\d+)?)(?:(?!\n)[\s-])*"
    r"((?:[^\W\d_]|[%\u00b0])*)"
)

ISO_UNITS = {
    "s": "s", "sec": "s", "secs": "s", "second": "s", "seconds": "s",
    "ms": "ms", "msec": "ms", "msecs": "ms",
    "millisecond": "ms", "milliseconds": "ms",
    "us": "\u00b5s", "\u00b5s": "\u00b5s",
    "microsecond": "\u00b5s", "microseconds": "\u00b5s",
    "ns": "ns", "nanosecond": "ns", "nanoseconds": "ns",
    "min": "min", "mins": "min", "minute": "min", "minutes": "min",
    "h": "h", "hr": "h", "hrs": "h", "hour": "h", "hours": "h",
    "d": "d", "day": "d", "days": "d",
    "bit": "bit", "bits": "bit",
    "b": "B", "byte": "B", "bytes": "B",
    "kb": "kB", "kilobyte": "kB", "kilobytes": "kB",
    "mb": "MB", "megabyte": "MB", "megabytes": "MB",
    "gb": "GB", "gigabyte": "GB", "gigabytes": "GB",
    "tb": "TB", "terabyte": "TB", "terabytes": "TB",
    "kib": "KiB", "kibibyte": "KiB", "kibibytes": "KiB",
    "mib": "MiB", "mebibyte": "MiB", "mebibytes": "MiB",
    "gib": "GiB", "gibibyte": "GiB", "gibibytes": "GiB",
    "%": "%", "percent": "%", "pct": "%",
}

HYPHENATED = re.compile(r"(?<![\w.-])[^\W\d_][\w.]*(?:-[\w.]*)+")

RADIX = "."
GROUPED_DIGITS = {"Zs", "Pc", "Pi", "Pf", "Po"}
SPLIT_DIGITS = re.compile(r"(?<=\d)(\D)(?=\d{3}(?!\d))")


def _ungrouped(text):
    def joined(found):
        mark = found.group(1)
        if mark != RADIX and unicodedata.category(mark) in GROUPED_DIGITS:
            return ""
        return mark
    return SPLIT_DIGITS.sub(joined, text)


def _quantity(written):
    text = str(written)
    plain = text.replace(",", "").replace("_", "")
    try:
        return int(plain)
    except ValueError:
        pass
    try:
        number = float(plain)
    except ValueError:
        return text
    if not math.isfinite(number):
        return number
    return int(number) if number.is_integer() else number


def quantities(text, units=ISO_UNITS):
    held = _ungrouped(HYPHENATED.sub(" ", corpus.UID_IN_PROSE.sub(" ", text)))
    return {(_quantity(found.group(1)), _unit(found.group(2), units))
            for found in QUANTITY.finditer(held)}


def _quantities(data, units=ISO_UNITS):
    data = dict(data, entries={
        key: {**fields, "quantity": f"{fields['quantity']} {fields['unit']}"}
        if isinstance(fields, dict) and "quantity" in fields and fields.get("unit")
        else fields
        for key, fields in (corpus.entries(data) or {}).items()})
    return quantities(
        corpus.PARAM_REF.sub(" ", corpus.CONCEPT_LINK.sub(r"\1", corpus.prose(data))),
        units)


def _unit(written, units=ISO_UNITS):
    spelling = written.lower()
    return units.get(spelling, spelling)


def _units(records):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    # @req> REQ-36436662@AUcYocp2yrFS qrxqss
    if corpus.kind_of(held, records.get(held)) != "data":
        return ISO_UNITS
    # @req> REQ-57721566@kHs1aOC7uW84 udbc2z
    return {spelling.lower(): symbol for _, symbol, spelling in _spellings(records[held])}


def _spellings(held):
    return [(str(key), str(symbol), str(spelling))
            for key, stated in (corpus.entries(held) or {}).items()
            if isinstance(stated, dict) and isinstance(stated.get("units"), dict)
            for symbol, unit in stated["units"].items()
            for spelling in [symbol, *(unit.get("spellings")
                                       if isinstance(unit, dict)
                                       and isinstance(unit.get("spellings"), list)
                                       else [])]
            if str(spelling).strip()]


def shared_quantities(records, root):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    typed = corpus.kind_of(held, records.get(held)) == "data"
    units = _units(records)
    where = {}
    for uid, data in records.items():
        # @req> REQ-71775839@o0Rw6sW3xCGB 2afre5
        if typed and uid == held:
            continue
        # @req> REQ-74163593@shkbFgp8gpvT bzkfod
        if data.get("status") in RETIRED:
            continue
        own = own_quantities(root, uid, data)
        # @req> REQ-30792942@jO6e3Cn6To-1 ozipy3
        if typed:
            own = _dropped(own, {("entries", *at, "quantity")
                                 for at, fields in _entries_within(corpus.entries(own))
                                 if fields is not None and "value_type" in fields})
        for quantity in _quantities(own, units):
            where.setdefault(quantity, []).append(uid)
    problems = []
    # @req> REQ-31827606@LqXaOXp6DLBG 4h2aan
    for (value, unit), uids in sorted(where.items(), key=lambda pair: str(pair[0])):
        if len(uids) > 1:
            # @req> REQ-30898926@Vu28eWaG_1mE nn2awc
            problems.append(
                f"{', '.join(sorted(uids))} each state {value} {unit}".rstrip()
                + " -- a quantity more than one statement makes belongs in a "
                f"single parameter, referenced {corpus.NAME_FORM}"
            )
    return problems


def _assessed(uid, data, records, canonical, known, past):
    def held_data(address):
        return records.get(canonical.get(address, address))

    # @req+ REQ-50160324@rCxgTJz0CeZX gxi4g4
    unreadable = set()
    for address in corpus.dependencies(data):
        found = corpus.ADDRESS.match(str(address))
        if found and found.group(1) in known and held_data(found.group(1)) is None:
            unreadable.add(found.group(1))
    # @req> REQ-30898926@Vu28eWaG_1mE xe6om6
    problems = [f"{uid}: depends on {target}, which could not be read -- "
                f"fix {target} first" for target in sorted(unreadable)]
    # @req- gxi4g4
    wanted = set(corpus.pin_addresses(held_data, data))
    pins = corpus.mapping(data, "assessed")
    stated = data.get("assessed")
    held = set(stated) if isinstance(stated, dict) else set()
    # @req> REQ-67539399@tuMwHXTE6ACx pcswfe
    for target in sorted(held - wanted, key=str):
        found = corpus.ADDRESS.match(str(target))
        if found and found.group(1) in unreadable:
            continue
        # @req> REQ-30898926@Vu28eWaG_1mE phxt2t
        problems.append(
            f"{uid}: pins {target}, which is neither related nor referenced "
            f"-- relate or reference {target} again, or remove the pin from "
            f"{uid}'s assessed by hand"
        )
    # @req> REQ-81493991@71cbxqAtqZTk w5qzvp
    if data.get("status") in RETIRED:
        return problems
    for target in sorted(wanted):
        item_uid, rest = corpus.split_address(target)
        stamped = canonical.get(item_uid, item_uid)
        if stamped not in records:
            continue
        held = corpus.address_stamp_of(stamped, records[stamped], rest)
        pinned = pins.get(target)
        # @req> REQ-42390302@QOC4GhS7SkFg w3y4p3
        if past and (not isinstance(pinned, str) or pinned != held):
            # @req> REQ-24608716@rrTjNN2Ay0D0 bzyf37
            # @req> REQ-30898926@Vu28eWaG_1mE utkrv6
            problems.append(
                f"{uid}: suspect link: {target} -- reread both, then "
                "`reqctl relate` a requirement or `reqctl revise "
                f"{uid} --ack` the rest to pin it"
                + history.lines(past.pinned(stamped, records[stamped], rest, pinned)))
    return problems


def _approved(records):
    return {uid: data for uid, data in records.items()
            if data.get("status") == "approved"}


def conflicts(records):
    approved = _approved(records)
    declared = []
    # @req+ REQ-77022154@-t-5C3fYQMS3 loruif
    for uid, data in approved.items():
        for target, relation in sorted(corpus.mapping(data, "relations").items()):
            if relation == "conflicts_with" and target in approved:
                declared.append(tuple(sorted((uid, target))))
    # @req> REQ-30898926@Vu28eWaG_1mE ssnfls
    return [
        f"{left} and {right} are both approved and declare conflicts_with -- "
        "resolve it by deprecating one, superseding both, or rewriting them"
        for left, right in sorted(set(declared))
    ]
    # @req- loruif


def supersedes(records):
    approved = _approved(records)
    # @req> REQ-53480164@5yFhCLJmuTBt qxi4hb
    # @req> REQ-30898926@Vu28eWaG_1mE 2evdh5
    return [
        f"{uid} supersedes {target}, which is still approved -- "
        "revise it to superseded or deprecated in this same change"
        for uid, data in approved.items()
        for target, relation in sorted(corpus.mapping(data, "relations").items())
        if relation == "supersedes" and target in approved
    ]


LEANS_ON = ("derives_from", "depends_on", "constrains")


def approved_relations(records):
    approved = _approved(records)
    problems = []
    # @req> REQ-42068162@TlRyGA-UJLlq hbpm4t
    for uid, data in sorted(approved.items()):
        for target, relation in sorted(corpus.mapping(data, "relations").items()):
            if relation not in LEANS_ON:
                continue
            held = records.get(target)
            if held is None or target in approved:
                continue
            # @req> REQ-30898926@Vu28eWaG_1mE bcyrxr
            problems.append(
                f"{uid} is approved but {relation} {target}, which is "
                f"{held.get('status')} -- approve {target}, or revise {uid} "
                "in this same change"
            )
    return problems


def _approved_bindings(records):
    canonical = corpus.reachable(records)
    approved = _approved(records)
    problems = []
    for uid, data in sorted(approved.items()):
        for address in corpus.references(data) + corpus.concept_references(data):
            target, _ = corpus.split_address(address)
            stated = canonical.get(target, target)
            held = records.get(stated)
            if held is None or stated in approved:
                continue
            # @req> REQ-30898926@Vu28eWaG_1mE p5bokx
            problems.append(
                f"{uid} is approved but stated against {target}, which is "
                f"{held.get('status')} -- approve {target}, or revise {uid}"
            )
    return problems


def _shared_words(records):
    claims = {}
    for uid, data in sorted(records.items()):
        if corpus.kind_of(uid, data) == "term":
            for word in _term_words(data):
                claims.setdefault(word.strip().casefold(), ([], word))[0].append(uid)
    problems = []
    for _, (uids, word) in sorted(claims.items()):
        # @req> REQ-18059226@M_Z00FMwux9p 2troxr
        if len(set(uids)) > 1:
            # @req> REQ-30898926@Vu28eWaG_1mE yrx3ss
            problems.append(
                f"{', '.join(sorted(set(uids)))} each claim \"{word}\" -- a "
                "reader cannot tell which definition governs; merge them or "
                "reword one"
            )
        elif len(uids) > 1:
            # @req> REQ-30898926@Vu28eWaG_1mE 3jvhux
            problems.append(f"{uids[0]}: claims \"{word}\" more than once -- "
                            "restate its aliases with --alias, leaving out the "
                            "repeat, or clear them with --no-alias")
    return problems


def _components(edges):
    order, low, live, stack, found = {}, {}, set(), [], []
    reached = 0
    for root in sorted(edges):
        if root in order:
            continue
        work = [(root, iter(edges.get(root, ())))]
        order[root] = low[root] = reached
        reached += 1
        stack.append(root)
        live.add(root)
        while work:
            uid, targets = work[-1]
            for target in targets:
                if target not in order:
                    order[target] = low[target] = reached
                    reached += 1
                    stack.append(target)
                    live.add(target)
                    work.append((target, iter(edges.get(target, ()))))
                    break
                if target in live:
                    low[uid] = min(low[uid], order[target])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[uid])
                if low[uid] == order[uid]:
                    group = []
                    while True:
                        held = stack.pop()
                        live.discard(held)
                        group.append(held)
                        if held == uid:
                            break
                    found.append(tuple(sorted(group)))
    return sorted(found)


def _round_trip(edges, group):
    held, trail = set(group), []
    uid = group[0]
    while uid not in trail:
        trail.append(uid)
        uid = min(target for target in edges[uid] if target in held)
    return trail[trail.index(uid):] + [uid]


def _caught(edges, group):
    round_trip = _round_trip(edges, group)
    others = sorted(set(group) - set(round_trip))
    return " -> ".join(round_trip) + (f", and {', '.join(others)}" if others else "")


def _cycle_problems(edges, noun, tail, step):
    # @req> REQ-30898926@Vu28eWaG_1mE vd7u6s
    return [
        f"{_caught(edges, group)}: circular {noun}, so {tail} -- {step}"
        for group in _components(edges)
        if len(group) > 1 or group[0] in edges.get(group[0], ())
    ]


def _circular_definitions(records):
    # @req+ REQ-49321694@sgj-Dt7t_niN ijccb5
    canonical = corpus.reachable(records)
    edges = {uid: sorted({canonical.get(found.partition(".")[0], found)
                          for _, found in corpus.CONCEPT_LINK.findall(
                              str(corpus.term_fields(data).get("definition")))})
             for uid, data in records.items()
             if corpus.kind_of(uid, data) == "term"}
    # @req> REQ-30898926@Vu28eWaG_1mE 46diyb
    return _cycle_problems(edges, "definition",
                           "none of these means anything before the others",
                           "reword one definition with --definition so it no "
                           "longer links the next")
    # @req- ijccb5


def _entry_selection(records, root):
    canonical = corpus.reachable(records)
    problems = []
    for uid, data in sorted(records.items()):
        links = corpus.concept_references(data)
        for address in corpus.references(data) + links:
            target, rest = corpus.split_address(address)
            if rest is None:
                continue
            held = records.get(canonical.get(target, target))
            if held is None:
                continue
            existing = corpus.entries(held)
            key, *steps = rest.split(".")
            # @req+ REQ-15211173@2tindbOlAUEJ sggzwh
            # @req+ REQ-11930677@zW9EYrOae8-u xxvuas
            block = corpus.held_blocks(root, canonical.get(target, target), held).get(key)
            if block is not None:
                if not steps:
                    # @req> REQ-30898926@Vu28eWaG_1mE k6ab75
                    problems.append(f"{uid}: selects {address}, which names {key} of "
                                    f"{target} and none of its block members -- "
                                    f"reword {uid} to select one of its members")
                elif not isinstance(block.get(steps[0], {}), dict):
                    # @req> REQ-30898926@Vu28eWaG_1mE kssexg
                    problems.append(f"{uid}: selects {address} but {steps[0]} of {key} of "
                                    f"{target} holds no fields of its own -- "
                                    f"reword {uid} to select a member of {key} "
                                    "that holds fields")
                    continue
                fields = block
                for step in steps:
                    if not isinstance(fields, dict) or step not in fields:
                        # @req> REQ-30898926@Vu28eWaG_1mE kijt3f
                        problems.append(f"{uid}: selects {address} but {key} of "
                                        f"{target} holds no {step!r} -- reword "
                                        f"{uid} to select what {key} holds, or "
                                        f"add {step!r} to it")
                        break
                    fields = fields[step]
                continue
            # @req- xxvuas
            if address in links and "." in rest:
                # @req> REQ-30898926@Vu28eWaG_1mE xeqgyv
                problems.append(f"{uid}: links {address}, which names neither an "
                                f"entry nor a block member of {target} -- reword "
                                f"{uid} to link {target} or one of its entries")
                continue
            # @req- sggzwh
            # @req+ REQ-62329029@wjRs5FRIhJ3C rc5mmy
            if existing is None:
                # @req> REQ-30898926@Vu28eWaG_1mE hagaom
                problems.append(
                    f"{uid}: selects {address} but {target} has no entries -- "
                    f"reword {uid} to reference {target} whole, or give "
                    f"{target} entries"
                )
            elif rest == "default":
                if held.get("default") is None:
                    # @req> REQ-30898926@Vu28eWaG_1mE 6lxfme
                    problems.append(
                        f"{uid}: selects ${{{target}.default}} but {target} "
                        f"names no default -- name one with `reqctl revise "
                        f"{target} --default`, or reword {uid} to select an "
                        "entry"
                    )
            # @req> REQ-93367131@liYuAavoXSA4 vye4xb
            elif rest == key and key in existing and any(
                    isinstance(fields, dict) and rest in fields
                    for fields in existing.values()):
                # @req> REQ-30898926@Vu28eWaG_1mE bcq3ce
                problems.append(
                    f"{uid}: selects {address}, which names both an entry of "
                    f"{target} and a field its entries carry -- rename one"
                )
            elif corpus.flagged(held, rest) is not None:
                stated = [fields[rest] for fields in existing.values()
                          if isinstance(fields, dict) and rest in fields
                          and not isinstance(fields[rest], bool)]
                # @req> REQ-28975717@sXPovM6T9HGc p5hfxl
                if stated:
                    # @req> REQ-30898926@Vu28eWaG_1mE burvbt
                    problems.append(
                        f"{uid}: selects {address} but {target} states {rest} "
                        f"{stated[0]!r} -- set {rest} to true or false on each "
                        f"entry of {target} with --set"
                    )
                # @req> REQ-10000795@VNUKO0iJNjTj bg3tyu
                elif not corpus.flagged(held, rest):
                    # @req> REQ-30898926@Vu28eWaG_1mE 5t4oer
                    problems.append(
                        f"{uid}: selects {address} but no entry of {target} "
                        f"is {rest} -- set {rest}=true on an entry of "
                        f"{target} with --set, or reword {uid}"
                    )
            elif key not in existing:
                # @req> REQ-30898926@Vu28eWaG_1mE i3ezb4
                problems.append(
                    f"{uid}: selects {address} but {target} has no entry "
                    f"{key!r} -- reword {uid} to select an entry {target} "
                    f"holds, or add {key!r} to {target}"
                )
            elif "." in rest:
                fields = existing[key]
                for field in rest.split(".")[1:]:
                    if not isinstance(fields, dict) or field not in fields:
                        # @req> REQ-30898926@Vu28eWaG_1mE jo2xia
                        problems.append(
                            f"{uid}: selects {address} but entry {key!r} of "
                            f"{target} has no field {field!r} -- reword {uid} "
                            f"to select a field it holds, or set {field!r} on "
                            "it with --set"
                        )
                        break
                    fields = fields[field]
            # @req- rc5mmy
    return problems


def _addresses(records, uid):
    return {found for found in (uid, corpus.name_of(uid, records.get(uid) or {}))
            if found}


def _fault_paths(validator, item):
    return (tuple(str(step) for step in fault.absolute_path)
            for fault in validator.iter_errors(item))


def _refused_at(paths, at):
    return any(path[:len(at)] == at for path in paths)


def _judgement(root, uid, data, judged):
    if uid not in judged:
        schema = corpus.schema_for(root, corpus.kind_of(uid, data),
                                   corpus.name_of(uid, data))
        validator = corpus.validator(schema)
        judged[uid] = (validator, tuple(_fault_paths(validator, data)),
                       (str(root), uid, corpus.digest(repr(schema)),
                        corpus.digest(repr(data))))
    return judged[uid]


_ADMITTED: dict[tuple, bool] = {}


def _admits_link(root, uid, data, where, field, link, judged):
    validator, faults, identity = _judgement(root, uid, data, judged)
    at = ("entries", *where, str(field))
    if _refused_at(faults, at):
        return False
    key = (*identity, where, str(field), link)
    if key not in _ADMITTED:
        candidate = copy.deepcopy(data)
        held = corpus.entries(candidate)
        for step in where:
            held = held[step]
        held[field] = [link] if isinstance(held.get(field), list) else link
        _ADMITTED[key] = not _refused_at(_fault_paths(validator, candidate), at)
    return _ADMITTED[key]


PROSE = "x-prose"
OBSERVED = "x-observed"
DATE = "date"
# @req+ REQ-62072712@m81ZZqYdquaS 5ii662
DATED = FormatChecker(formats=())


@DATED.checks(DATE, raises=ValueError)
def _dated(value):
    return isinstance(value, datetime.date) or (
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        and datetime.date.fromisoformat(value))
# @req- 5ii662


UNMARKED = "\0not marked\0"


def _unmarked(node, marks):
    if isinstance(node, dict):
        if marks(node):
            return {"const": UNMARKED}
        return {key: _unmarked(value, marks) for key, value in node.items()}
    if isinstance(node, list):
        return [_unmarked(one, marks) for one in node]
    return node


_DERIVED: dict[tuple[int, object], tuple[object, object]] = {}


def _marked_paths(root, uid, data, marks):
    schema = corpus.schema_for(root, corpus.kind_of(uid, data),
                               corpus.name_of(uid, data))
    held = _DERIVED.get((id(schema), marks))
    if held is None or held[0] is not schema:
        held = _DERIVED[id(schema), marks] = (schema, _unmarked(schema, marks))
    return [tuple(str(step) for step in fault.absolute_path)
            for fault in corpus.validator(held[1]).iter_errors(data)
            if fault.validator == "const" and fault.validator_value == UNMARKED]


def _prose(node):
    return node.get(PROSE) is True


def _observed(node):
    return node.get(OBSERVED) is True


def _date(node):
    return node.get("format") == DATE


@functools.cache
def _entry_of(target):
    return lambda node: node.get(corpus.ENTRY_OF) == target


def prose_paths(root, uid, data):
    return _marked_paths(root, uid, data, _prose)


def observed_paths(root, uid, data):
    # @req> REQ-48500355@rnstkLKM48vN t3fuqq
    return _marked_paths(root, uid, data, _observed)


def dated_paths(root, uid, data):
    # @req> REQ-62072712@m81ZZqYdquaS npwa4k
    return _marked_paths(root, uid, data, _date)


def _dropped(node, paths, at=()):
    if isinstance(node, dict):
        return {key: _dropped(value, paths, at + (str(key),))
                for key, value in node.items()
                if at + (str(key),) not in paths}
    if isinstance(node, list):
        return [_dropped(one, paths, at + (str(index),))
                for index, one in enumerate(node)
                if at + (str(index),) not in paths]
    return node


def _without(root, uid, data, *finders):
    try:
        paths = frozenset(one for find in finders for one in find(root, uid, data))
    # @req> REQ-14895892@JjrTwHoJqTRe in6ljr
    except corpus.RefusedCopy:
        raise
    except corpus.ReqctlError:
        return data
    return _dropped(data, paths) if paths else data


_OWN: dict[tuple, object] = {}


def _own(root, uid, data, *finders):
    try:
        schema = corpus.schema_for(root, corpus.kind_of(uid, data),
                                   corpus.name_of(uid, data))
    except corpus.ReqctlError:
        return _without(root, uid, data, *finders)
    key = (finders, str(root), uid, id(schema), repr(data))
    if key not in _OWN:
        held = _without(root, uid, data, *finders)
        _OWN[key] = None if held is data else held
    return data if _OWN[key] is None else _OWN[key]


def own_words(root, uid, data):
    # @req> REQ-48500355@rnstkLKM48vN rwffnk
    return _own(root, uid, data, observed_paths)


def own_quantities(root, uid, data):
    # @req> REQ-62072712@m81ZZqYdquaS hlxm3m
    return _own(root, uid, data, observed_paths, dated_paths)


def _declares_prose(root, uid, data, where, field, refused):
    if uid not in refused:
        refused[uid] = prose_paths(root, uid, data)
    return _refused_at(refused[uid], ("entries", *where, str(field)))


def _entry_term_fields(records, root):
    refused, judged = {}, {}
    worded = {found for held_uid, held in records.items()
              if corpus.kind_of(held_uid, held) == "term"
              for found in (held_uid, corpus.name_of(held_uid, held)) if found}
    claimed, words_of = {}, {}
    for uid, data in sorted(records.items()):
        if corpus.kind_of(uid, data) == "term":
            for word in _term_words(data):
                spelled = word.replace("_", " ").casefold()
                for address in _addresses(records, uid):
                    words_of.setdefault(address, set()).add(spelled)
                if data.get("status") == "approved":
                    claimed.setdefault(spelled, (uid, word))

    def walk(uid, data, where, fields, seen):
        if len(seen) >= NESTING:
            return []
        problems = []
        seen = seen + (id(fields),)
        for field, value in sorted(fields.items(),
                                   key=lambda item: str(item[0])):
            pieces = value if isinstance(value, list) else [value]
            linked = {found for piece in pieces if isinstance(piece, str)
                      for _, found in corpus.CONCEPT_LINK.findall(piece)
                      if found in worded}
            spelled = str(field).replace("_", " ").casefold()
            named = claimed.get(spelled)
            # @req> REQ-31592505@2C7Za06pRzA2 vtxlpz
            if named and not linked & _addresses(records, named[0]):
                term_uid, word = named
                held_by = corpus.name_of(term_uid, records[term_uid]) or term_uid
                link = f"[{word}]({held_by})"
                if _admits_link(root, uid, data, where, field, link, judged):
                    # @req> REQ-30898926@Vu28eWaG_1mE vl4u63
                    problems.append(
                        f"{uid}: entry {'.'.join(where)} field {field} is "
                        f'named for "{word}" but its value does not link '
                        f"{held_by} -- write the value with {link}, or "
                        "rename the field"
                    )
            # @req> REQ-51326810@tZsTSo6pwmwE xx2sp7
            if not _declares_prose(root, uid, data, where, field,
                                   refused):
                for target in sorted(linked):
                    if spelled not in words_of.get(target, ()):
                        # @req> REQ-30898926@Vu28eWaG_1mE dzkfxs
                        problems.append(
                            f"{uid}: entry {'.'.join(where)} field "
                            f"{field} links {target} but is not named "
                            "for it -- rename the field to the term's "
                            "words, or unlink the term"
                        )
            if isinstance(value, dict) and id(value) not in seen:
                problems += walk(uid, data, where + (str(field),), value, seen)
        return problems

    problems = []
    for uid, data in sorted(records.items()):
        for entry_key, fields in sorted((corpus.entries(data) or {}).items(),
                                        key=lambda item: str(item[0])):
            if isinstance(fields, dict):
                problems += walk(uid, data, (str(entry_key),), fields, ())
    return problems


def coherence(records, root, run=lambda check, *args: check(*args)):
    return (run(_approved_bindings, records) + run(_shared_words, records)
            + run(_circular_definitions, records) + run(_entry_selection, records, root)
            + run(_duplicate_names, records) + run(_entry_term_fields, records, root)
            + run(_typed_entries, records) + run(_entry_of_values, records, root)
            + run(_value_types, records, root) + run(_unit_quantities, records, root)
            + run(_listed_units, records) + run(_bounds, records)
            + run(_shadowed_blocks, records, root))


# @req> REQ-41697188@IRR8A-_NbYw4 pkvemf
# @req> REQ-57061306@grhOhf7rpAJV 23uhdj
# @req> REQ-77903352@LFt7c94PeLFp leh3qs
def _typed_entries(records):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    if corpus.kind_of(held, records.get(held)) != "data":
        return []
    return [problem
            for uid, data in sorted(records.items())
            if corpus.kind_of(uid, data) == "data"
            for where, fields in _entries_within(corpus.entries(data))
            if fields is not None
            and str(fields.get("value_type")) in KEY_SHAPES
            for problem in _typed(
                f"{uid}: entry {'.'.join(where)}", fields["value_type"],
                [(f"quantity {fields['quantity']!r}",
                  _written(fields["quantity"]))] if "quantity" in fields else [],
                fields.get("unit") or None)]


def _marker_targets(node):
    if isinstance(node, dict):
        return ({node[corpus.ENTRY_OF]} if isinstance(node.get(corpus.ENTRY_OF), str)
                else set()).union(
            *map(_marker_targets, node.values()))
    if isinstance(node, list):
        return set().union(*map(_marker_targets, node))
    return set()


def _at(node, path):
    for step in path:
        node = (node[int(step)] if isinstance(node, list)
                else next(value for key, value in node.items() if str(key) == step))
    return node


# @req> REQ-93210750@EGkfkA3YBorC zrp6x7
def _entry_of_values(records, root):
    reachable = corpus.reachable(records)
    held = {address: {str(key) for key in corpus.entries(records[uid]) or {}}
            for address, uid in reachable.items()
            if corpus.kind_of(uid, records[uid]) == "data"}
    problems = []
    for uid, data in sorted(records.items()):
        schema = corpus.schema_for(root, corpus.kind_of(uid, data),
                                   corpus.name_of(uid, data))
        for target in sorted(_marker_targets(schema) & held.keys()):
            for path in sorted(_marked_paths(root, uid, data, _entry_of(target))):
                value = _at(data, path)
                # @req> REQ-30898926@Vu28eWaG_1mE ip7mux
                problems += [f"{uid}: {'.'.join(path)} {member!r} names no entry "
                             f"of {target} -- name one of its entries, or add "
                             f"{member!r} to {target}"
                             for member in (value if isinstance(value, list) else [value])
                             if str(member) not in held[target]]
    return problems


# @req> REQ-28551871@5A5ZA4_Y3ePJ jnnngp
def _listed_units(records):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    if corpus.kind_of(held, records.get(held)) != "data":
        return []
    listed: dict[str, set[str]] = {
        str(key): set() for key in corpus.entries(records[held]) or {}
        if str(key) not in UNITLESS}
    for key, _, spelling in _spellings(records[held]):
        listed.setdefault(key, set()).add(spelling)
    stating = [(uid, "", data) for uid, data in sorted(records.items())
               if corpus.kind_of(uid, data) == "parameter"]
    stating += [(uid, f" entry {'.'.join(where)}", fields)
                for uid, data in sorted(records.items())
                if corpus.kind_of(uid, data) == "data"
                for where, fields in _entries_within(corpus.entries(data))
                if fields is not None]
    # @req> REQ-30898926@Vu28eWaG_1mE ncsger
    return [f"{uid}:{where} unit {stated['unit']!r} is no unit of {stated['value_type']} "
            f"-- state a unit {held} lists for it, or add the unit to that entry "
            f"of {held}"
            for uid, where, stated in stating
            if str(stated.get("value_type")) in listed and stated.get("unit") is not None
            and str(stated["unit"]) not in listed[str(stated["value_type"])]]


# @req+ REQ-20469423@IrHZJUp5R992 bplqvo
def _number(value):
    value = value if isinstance(value, (int, float)) else _quantity(_written(value))
    return (None if isinstance(value, bool) or not isinstance(value, (int, float))
            or isinstance(value, float) and not math.isfinite(value) else value)


def _span(value_types, spellings, fields):
    quantity = _number(fields.get("quantity"))
    if quantity is None:
        return None
    stated = value_types.get(str(fields.get("value_type")))
    units = stated.get("units") if isinstance(stated, dict) else None
    units = {str(symbol): unit for symbol, unit in units.items()} if isinstance(units, dict) else {}
    if fields.get("unit") is None:
        return None if units else ("", quantity, quantity, quantity)
    for key, symbol, spelling in spellings:
        if (key, spelling) == (str(fields.get("value_type")), str(fields["unit"])):
            unit = units[symbol] if isinstance(units[symbol], dict) else {}
            low, high = map(_number, (unit.get("factor"), unit.get("factor"))
                            if unit.get("factor") is not None
                            else (unit.get("least"), unit.get("most")))
            if low is None or high is None:
                return None
            try:
                sizes = sorted((quantity * low, quantity * high))
            except OverflowError:
                return None
            if all(not isinstance(one, float) or math.isfinite(one) for one in sizes):
                return (symbol, quantity, *sizes)
    return None


def _less(one, other):
    return one[1] < other[1] if one[0] == other[0] else one[2] < other[3]
# @req- bplqvo


def _bounds(records):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    if corpus.kind_of(held, records.get(held)) != "data":
        return []
    value_types = {str(key): stated
                   for key, stated in (corpus.entries(records[held]) or {}).items()}
    spellings = _spellings(records[held])
    problems = []
    for uid, data in sorted(records.items()):
        if corpus.kind_of(uid, data) != "data":
            continue
        held_entries = corpus.entries(data) or {}
        for where, fields in _entries_within(held_entries):
            if fields is None:
                continue
            siblings = _at(held_entries, where[:-1])
            for bound, words in (("at_least", "less"), ("at_most", "more")):
                if bound not in fields:
                    continue
                at = f"{uid}: entry {'.'.join(where)} {bound} {fields[bound]!r}"
                target = next((value for key, value in siblings.items()
                               if str(key) == str(fields[bound])), None)
                # @req+ REQ-75293842@Une663jQ8uUZ l7qntp
                if not isinstance(target, dict) or "quantity" not in target:
                    # @req> REQ-30898926@Vu28eWaG_1mE hvhx2p
                    problems.append(f"{at} names no entry of {uid} stating a quantity "
                                    f"-- name a sibling entry that states one, or "
                                    f"give {fields[bound]!r} a quantity")
                    continue
                mine, theirs = fields.get("value_type"), target.get("value_type")
                if mine is None or str(theirs) != str(mine):
                    # @req> REQ-30898926@Vu28eWaG_1mE be5qdp
                    problems.append(f"{at} states {theirs or 'no value type'}, entry "
                                    f"{'.'.join(where)} states {mine or 'no value type'} "
                                    f"and the two cannot be compared -- give both "
                                    "the same value type")
                    continue
                # @req- l7qntp
                # @req+ REQ-58100850@NgW3efYeVw1k p3q7no
                spans = _span(value_types, spellings, fields), _span(value_types, spellings, target)
                if None not in spans and _less(*(spans if bound == "at_least" else spans[::-1])):
                    # @req> REQ-30898926@Vu28eWaG_1mE ovhbsq
                    problems.append(f"{at}: quantity {fields.get('quantity')} "
                                    f"{fields.get('unit') or ''}".rstrip()
                                    + f" is {words} than {target['quantity']} "
                                    f"{target.get('unit') or ''}".rstrip()
                                    + " -- correct this quantity, or the one "
                                    f"{bound} names")
                # @req- p3q7no
        if "ceiling" not in data:
            continue
        ceiling = next((value for key, value in held_entries.items()
                        if str(key) == str(data["ceiling"])), None)
        # @req> REQ-36099384@oqIHWa_e7CDN uhu3bz
        if not isinstance(ceiling, dict) or "quantity" not in ceiling:
            # @req> REQ-30898926@Vu28eWaG_1mE 6vqmrg
            problems.append(f"{uid}: ceiling {data['ceiling']!r} names no entry of "
                            f"{uid} stating a quantity -- name one with "
                            "--ceiling, or clear it with --no-ceiling")
            continue
        # @req+ REQ-27382610@9np_bpPH3xzx 4unc6n
        top = _span(value_types, spellings, ceiling)
        # @req> REQ-30898926@Vu28eWaG_1mE hsw6rh
        problems += [f"{uid}: ceiling {data['ceiling']!r} states "
                     + f"{ceiling['quantity']} {ceiling.get('unit') or ''}".rstrip()
                     + f", less than entry {'.'.join(where)} at "
                     + f"{fields['quantity']} {fields.get('unit') or ''}".rstrip()
                     + " -- raise the ceiling's quantity, name a higher entry "
                     "with --ceiling, or lower that entry's quantity"
                     for where, fields in _entries_within(held_entries)
                     if fields is not None and ceiling.get("value_type") is not None
                     and str(fields.get("value_type")) == str(ceiling.get("value_type"))
                     and top is not None
                     and (other := _span(value_types, spellings, fields)) is not None
                     and _less(top, other)]
        # @req- 4unc6n
    return problems


NUMBER_WORDS = ("zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
                "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
                "hundred|thousand|million|billion")
WORDED = re.compile(
    rf"(?<![\w-])((?:{NUMBER_WORDS})(?:(?:[\s-]+|\s+and\s+)(?:{NUMBER_WORDS}))*)"
    r"(?:(?!\n)[\s-])+((?:[^\W\d_]|[%\u00b0])+)", re.IGNORECASE)


# @req> REQ-10839190@o1M0SkcZ_uZg sjs5bc
def _unit_quantities(records, root):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    if corpus.kind_of(held, records.get(held)) != "data":
        return []
    units = _units(records)
    problems = []
    for uid, data in sorted(records.items()):
        if corpus.kind_of(uid, data) not in ("requirement", "guard"):
            continue
        # @req> REQ-74163593@shkbFgp8gpvT dzwaj3
        if data.get("status") in RETIRED:
            continue
        own = own_quantities(root, uid, data)
        criteria = own.get("acceptance_criteria")
        text = "\n".join([str(own.get("text") or "")] + [
            str(criterion.get(part) or "")
            for criterion in (criteria if isinstance(criteria, list) else [])
            if isinstance(criterion, dict) for part in ("given", "when", "then")])
        text = corpus.UID_IN_PROSE.sub(" ", corpus.PARAM_REF.sub(
            " ", corpus.CONCEPT_LINK.sub(r"\1", text)))
        written = sorted({f"{found.group(1)} {found.group(2)}"
                          for pattern, prose in ((QUANTITY, _ungrouped(text)), (WORDED, text))
                          for found in pattern.finditer(prose)
                          if found.group(2).lower() in units})
        # @req> REQ-30898926@Vu28eWaG_1mE p4sy2b
        problems += [f"{uid}: writes {quantity} -- reference the parameter or "
                     f"entry holding it, {corpus.NAME_FORM}" for quantity in written]
    return problems


def _value_types(records, root):
    held = corpus.reachable(records).get(VALUE_TYPES, VALUE_TYPES)
    if corpus.kind_of(held, records.get(held)) != "data":
        return []
    listed = next((field.choices for field in _fields.of(root, "parameter")
                   if field.name == "value_type"), ())
    # @req> REQ-34134685@7WjKv7L7yONz tr5vto
    # @req> REQ-30898926@Vu28eWaG_1mE bti7u2
    problems = [f"{uid}: entry {'.'.join(where)}: value_type "
                f"{fields['value_type']!r} is a "
                f"{'list' if isinstance(fields['value_type'], list) else 'mapping'} "
                "-- state one value type"
                for uid, data in sorted(records.items())
                if corpus.kind_of(uid, data) == "data"
                for where, fields in _entries_within(corpus.entries(data))
                if fields is not None
                and isinstance(fields.get("value_type"), (list, dict))]
    for key, stated in (corpus.entries(records[held]) or {}).items():
        # @req> REQ-50607767@HUHiB9K0Vm5f zfnoqs
        if str(key) not in listed:
            # @req> REQ-30898926@Vu28eWaG_1mE b3icej
            problems.append(f"{held}: entry {key} is no value type the kind schema "
                            "for parameters lists -- remove it with --drop-entry, "
                            "or add it to that schema's value_type by hand")
        # @req+ REQ-39867440@lNag_-a2yKhi jbq26t
        units = stated.get("units") if isinstance(stated, dict) else None
        units = (dict.fromkeys(map(str, units if isinstance(units, list) else [units]))
                 if units is not None and not isinstance(units, dict) else units)
        for symbol, unit in (units.items() if isinstance(units, dict) else ()):
            bounds = ({key for key in ("factor", "least", "most") if unit.get(key) is not None}
                      if isinstance(unit, dict) else set())
            if bounds not in ({"factor"}, {"least", "most"}):
                # @req> REQ-30898926@Vu28eWaG_1mE nq4wli
                problems.append(f"{held}: entry {key} unit {symbol} states "
                                f"{', '.join(sorted(bounds)) or 'no bound'} -- state "
                                "a factor, or a least with a most")
        # @req- jbq26t
    return problems


def _duplicate_names(records):
    # @req+ REQ-53177302@oSukBFyA3jXq uay7dt
    named = {}
    for uid, data in records.items():
        name = corpus.name_of(uid, data)
        if name is not None:
            named.setdefault(name, []).append(uid)
    # @req> REQ-30898926@Vu28eWaG_1mE 2emtrk
    return [
        f"{' and '.join(sorted(uids))} share the name `{name}` -- "
        "a name addresses one item; rename all but one"
        for name, uids in sorted(named.items())
        if len(uids) > 1
    ]
    # @req- uay7dt


ONE_WAY = (
    ("derives_from", "none of these can be the one the others derive from"),
    ("depends_on", "none of these can be built before the others"),
    ("supersedes", "none of these can be the one the others replace"),
)


def cycles(records):
    problems = []
    # @req> REQ-44520277@w92ngdeF87Mm 2pebps
    for relation, tail in ONE_WAY:
        edges = {
            uid: sorted(
                target
                for target, stated in corpus.mapping(data, "relations").items()
                if stated == relation
            )
            for uid, data in records.items()
        }
        # @req> REQ-30898926@Vu28eWaG_1mE frqcqo
        problems += _cycle_problems(edges, relation, tail,
                                    "`reqctl unrelate` one link of the cycle")
    return problems


def _strays(root, paths):
    corpus_dir = Path(root) / "requirements"
    claimed = set(paths)
    skipped = (corpus_dir / "schemas", corpus_dir / "baselines")
    problems = []
    # @req> REQ-69003763@oacx0bF0kxdV 4ljfwh
    for held in sorted(corpus_dir.rglob("*.yml")) + sorted(corpus_dir.rglob("*.yaml")):
        # @req> REQ-61926693@GZyk9i4NErF6 snr2ig
        if held in claimed or held in (_baseline.path(root),
                                       _settings.path(root)):
            continue
        if any(skip in held.parents for skip in skipped):
            continue
        # @req> REQ-30898926@Vu28eWaG_1mE a7qobc
        problems.append(
            f"{held.relative_to(root)}: not where an item lives -- an item is "
            "requirements/(reqs|params|terms|data)/UID.yml; move or delete it"
        )
    return problems


# @req> REQ-61926693@GZyk9i4NErF6 cf76cn
def _stated(root):
    where = _settings.path(root)
    if not where.is_file():
        return []
    held = corpus.loads(corpus.read_text(where), _settings.SETTINGS)
    return [f"{_settings.SETTINGS}: {fault}" for fault in _settings.faults(held)]


UNFINISHED = "reqctl could not finish"


def _guarded(where, check, *args):
    # @req+ REQ-23691260@3s5Nt8Pn1BXA kgrg4l
    try:
        return check(*args)
    except corpus.ReqctlError as fault:
        return [f"{where}: {fault}"]
    # @req> REQ-55939360@qvRmeRuBl0T9 yi53ne
    except Exception as fault:
        return [f"{where}: {UNFINISHED} {check.__name__} -- "
                f"{type(fault).__name__}: {fault}"]
    # @req- kgrg4l


def _settled(path):
    text = corpus.read_text(path)
    # @req> REQ-98359235@ZY1HJ0hcSyAZ 5wu7pz
    if corpus.CONFLICTED.search(text):
        # @req> REQ-30898926@Vu28eWaG_1mE kriku5
        raise corpus.ReqctlError(
            f"holds an unresolved merge -- `reqctl resolve {path.stem}` "
            "settles one that falls within its pins"
        )
    # @req> REQ-49870454@KKNV-vdY6oM1 ogeofb
    data = corpus.loads(text, path, aliases=False)
    if isinstance(data, dict):
        corpus.refuse_misshapen(path, data)
    return data


# @req> REQ-21699310@HJWvkB2QKjez uv4bc5
def _bound_guards(records, root):
    nominated = corpus.binding_dimensions(root)
    # @req> REQ-30898926@Vu28eWaG_1mE iccei7
    return [
        f"{uid}: references {address}, which binds the guard to {name} -- "
        "reword the guard without the reference, or state the rule as a "
        "requirement"
        for uid, data in sorted(records.items())
        if corpus.kind_of(uid, data) == "guard"
        for address in corpus.references(data) + corpus.concept_references(data)
        for name in [corpus.split_address(address)[0]]
        if name in nominated]


def _named_schemas(records, root):
    # @req+ REQ-48136849@EXeydTy0CfsX wljy47
    held = {corpus.name_of(uid, data) for uid, data in records.items()}
    # @req> REQ-30898926@Vu28eWaG_1mE klvbx7
    return [f"corpus: {name}.schema.yaml governs an item named {name}, and "
            "the corpus holds none -- mint it, or remove the schema"
            for name in corpus.named_schemas(root) if name not in held]
    # @req- wljy47


def run(root, exempt=None):
    paths = corpus.item_files(root)
    problems, broken_schemas = _schemas_are_schemas(root)
    records, unreadable = {}, {}
    for path in paths:
        # @req+ REQ-69525887@WpuY4yv5NYDo d3uvus
        try:
            data = _settled(path)
        except corpus.ReqctlError as error:
            unreadable[path.stem] = str(error).replace(f"{root}/", "")
            continue
        # @req- d3uvus
        if isinstance(data, dict):
            records[path.stem] = data
    reachable = corpus.reachable(records)
    known = {path.stem for path in paths} | set(reachable)
    past = history.History(root)

    for path in paths:
        uid = path.stem
        if uid not in records:
            problems += _guarded(uid, _identity, root, path, None)
            # @req> REQ-30898926@Vu28eWaG_1mE haoc6o
            problems.append(f"{uid}: " + unreadable.get(
                uid, "item file is not a mapping -- edit it by hand into a "
                     "mapping of the item's fields"))
            continue
        problems += item_problems(root, uid, path, records[uid], records,
                                  reachable, known, broken_schemas, suspect=past)
    return problems + corpus_checks(records, root, paths, exempt)


def item_problems(root, uid, path, data, records, reachable, known, broken=(), *,
                  suspect):
    # @req+ REQ-42390302@QOC4GhS7SkFg igyueu
    problems = _guarded(uid, _identity, root, path, data)
    try:
        needs = corpus.schema_name_at(root, corpus.kind_of(uid, data),
                                      corpus.name_of(uid, data))
    except (corpus.ReqctlError, TypeError):
        needs = None
    if needs not in broken:
        problems += _guarded(uid, schema_problems, root, uid, data)
    problems += _guarded(uid, ears, uid, data)
    problems += _guarded(uid, text_values, uid, data)
    problems += _guarded(uid, repeated_labels, uid, data)
    problems += _guarded(uid, hidden_values, uid, data)
    problems += _guarded(uid, dictionary_rules, uid, data)
    problems += _guarded(uid, listed_fields, root, uid, data)
    problems += _guarded(uid, _relations, uid, data, records, reachable, known)
    problems += _guarded(uid, _references, uid, data, known, root)
    problems += _guarded(uid, _assessed, uid, data, records, reachable, known, suspect)
    return problems
    # @req- igyueu


def corpus_checks(records, root, paths, exempt=None):
    problems = _guarded("corpus", _strays, root, paths)
    problems += _guarded("corpus", _stated, root)
    problems += _guarded("corpus", _named_schemas, records, root)
    problems += _guarded("corpus", _bound_guards, records, root)
    problems += _guarded("corpus", _unlinked_terms, records, root)
    problems += _guarded("corpus", shared_quantities, records, root)
    problems += _guarded("corpus", approved_relations, records)
    problems += _guarded("corpus", conflicts, records)
    problems += _guarded("corpus", supersedes, records)
    # @req> REQ-23691260@3s5Nt8Pn1BXA oan2d2
    problems += coherence(records, root,
                          lambda check, *args: _guarded("corpus", check, *args))
    problems += _guarded("corpus", cycles, records)
    if exempt is not None:
        problems += _guarded("corpus", exempted, records, root, exempt)
    return problems
