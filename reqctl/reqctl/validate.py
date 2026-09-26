import copy
import math
import re
import unicodedata
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from . import baseline as _baseline
from . import corpus

SCHEMAS = ("requirement", "guard", "dictionary", "baseline")


def _schemas_are_schemas(root):
    problems, broken = [], set()
    for name in sorted(set(SCHEMAS) | set(corpus.schema_names(root))):
        try:
            corpus.schema(root, name)
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
            problems.append(f"{uid}: filename is not PREFIX-NNNNNNNN")
    elif not corpus.UID.match(uid) and uid != corpus.name_of(uid, data or {}):
        problems.append(
            f"{uid}: filename is not the name the item carries")
    # @req> REQ-48186295@whKUIi0BRp9f yvekz4
    if corpus.UID.match(uid) or kind is not None:
        expected = corpus.folder_for(root, corpus.kind_of(uid, data))
        if path.parent != expected:
            problems.append(
                f"{uid}: file is in {path.parent.name}/, not {expected.name}/"
            )
    if path.suffix != ".yml":
        problems.append(f"{uid}: item file is named {path.name}; items are .yml")
    return problems


def schema_problems(root, uid, data):
    try:
        declared = corpus.schema_for(root, corpus.kind_of(uid, data),
                                     corpus.name_of(uid, data))
    except corpus.ReqctlError as absent:
        return [f"{uid}: {absent}"]
    validator = Draft202012Validator(declared)
    problems = []
    for error in sorted(validator.iter_errors(data), key=str):
        error = best_match([error])
        where = ".".join(str(p) for p in error.absolute_path) or "(item)"
        problems.append(f"{uid}: schema: {where}: {error.message}")
    # @req> REQ-35443917@7V3GXXoqruBl znhrrb
    if data.get("verification") == "automated_test" and not any(
            problem.startswith(f"{uid}: schema: verification:")
            for problem in problems):
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
    if not text:
        return []

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
    return [
        f"{uid}: EARS: {'; '.join(faults)}\n"
        f"  statement: {text[:100]}{'...' if len(text) > 100 else ''}\n"
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


NESTING = 100


def _nesting(uid, held, path=(), seen=()):
    if len(seen) >= NESTING:
        return [f"{uid}: entry {'.'.join(path)} nests deeper than {NESTING} "
                "levels -- flatten it"]
    problems = []
    seen = seen + (id(held),)
    for key, fields in (held or {}).items():
        if not isinstance(fields, dict):
            continue
        where = path + (str(key),)
        for name, value in fields.items():
            if isinstance(value, dict) and id(value) not in seen:
                problems += _nesting(uid, value, where + (str(name),), seen)
    return problems


def dictionary_rules(uid, data):
    problems = []
    item_kind = corpus.kind_of(uid, data)
    declared = data.get("kind")
    if declared is not None and declared != item_kind:
        problems.append(
            f"{uid}: states kind {declared} -- state {item_kind} or mint the "
            f"item you meant")
    held = corpus.entries(data)
    if held is None or uid.startswith("REQ-"):
        return problems
    # @req> REQ-67450031@Ltb3K5bINBgP 5qg2a5
    for key in ("default", "pinned", "text", "name"):
        if key in held:
            problems.append(f"{uid}: an entry may not be keyed {key} -- it "
                            "would shadow an item field of that name; rename "
                            "the entry")
    # @req> REQ-22887335@phmPbBePOAku idfqw5
    if corpus.MEMBERS in held:
        problems.append(f"{uid}: an entry may not be keyed {corpus.MEMBERS} -- "
                        "that address pins the item's membership; rename the "
                        "entry")
    problems += _nesting(uid, held)
    if item_kind == "term":
        # @req> REQ-79013939@bHJwWtA0cgeG wcl7vt
        if len(held) != 1:
            problems.append(f"{uid}: a term holds exactly one entry -- its word")
        # @req+ REQ-47317077@ROG7ulJ6WVMa iwiit6
        stated = corpus.term_fields(data).get("word")
        if not (isinstance(stated, str) and stated.strip()):
            problems.append(f"{uid}: word is {stated!r} -- a term states the "
                            "word it is known by, as text; the entry key is a "
                            "handle and addresses it")
        # @req- iwiit6
        # @req> REQ-15469759@ETBwvNW6rbpC b6qizb
        for phrase, reason in corpus.unclaimed(data).items():
            if not reason.strip():
                problems.append(
                    f"{uid}: records \"{phrase}\" as not the term but gives no "
                    f"reason -- write --unclaimed \"{phrase}=the reason\"")
        for key in ("name", "value_type", "unit", "default", "text"):
            if data.get(key) is not None:
                problems.append(f"{uid}: {key} does not apply to a term")
        return problems
    if not isinstance(data.get("name"), str):
        noun = "parameter" if item_kind == "parameter" else "data item"
        problems.append(f"{uid}: a {noun} carries a name")
    # @req+ REQ-67914848@CoWJ0QyQOZsG fnsqos
    default = data.get("default")
    if default is not None and default not in held:
        problems.append(f"{uid}: default names {default!r}, which is not an "
                        "entry")
    # @req- fnsqos
    if item_kind == "data":
        for key in ("value_type", "unit"):
            if data.get(key) is not None:
                problems.append(f"{uid}: {key} does not apply to a data item")
        for key in held:
            if not corpus.DATA_KEY.match(str(key)):
                problems.append(f"{uid}: entry key {key!r} is not a snake_case "
                                "handle")
        return problems
    value_type = data.get("value_type")
    shape = KEY_SHAPES.get(value_type)
    if shape is None:
        problems.append(f"{uid}: a parameter carries a value_type")
    else:
        # @req> REQ-41697188@oclky4jsxJDW da5737
        for key in held:
            if not isinstance(key, str) or not shape.match(key):
                problems.append(f"{uid}: entry key {key!r} does not parse as "
                                f"{value_type}")
    # @req+ REQ-57061306@KwSVtwHyHRCj clnvsb
    if value_type in UNITLESS and data.get("unit") is not None:
        problems.append(f"{uid}: unit does not apply to {value_type}")
    if (value_type is not None and value_type not in UNITLESS
            and data.get("unit") is None):
        problems.append(f"{uid}: {value_type} carries a unit")
    # @req- clnvsb
    return problems


def text_values(uid, data):
    if corpus.kind_of(uid, data) != "parameter" or data.get("value_type") != "text":
        return []
    problems = []
    # @req> REQ-83091747@3cl5T4OOlk-t q5fj2f
    for member in corpus.entries(data) or {}:
        if not isinstance(member, str):
            continue
        found = QUANTITY.fullmatch(member.strip())
        if found and not isinstance(_quantity(found.group(1)), str):
            problems.append(
                f"{uid}: text value {member!r} is shaped like a quantity -- "
                "give it a numeric value_type, or reword the name"
            )
    return problems


def _relations(uid, data, records, canonical, known):
    stated = data.get("relations")
    problems = [
        f"{uid}: relates {target!r}, which is not a {corpus.NAMED} uid"
        for target in sorted(stated if isinstance(stated, dict) else {}, key=str)
        if not isinstance(target, str)
    ]
    requirement = uid.startswith("REQ-")
    for target in sorted(corpus.mapping(data, "relations")):
        if requirement:
            held = canonical.get(target)
            kind = (corpus.kind_of(held, records[held]) if held in records
                    else corpus.kind_for_uid(target))
            # @req> REQ-26911169@CRy8IY3aHxkB v3b5cc
            if target == uid:
                problems.append(f"{uid}: links to itself")
                continue
            if kind in ("parameter", "data"):
                noun = "a parameter" if kind == "parameter" else "a data item"
                problems.append(
                    f"{uid}: relates {target}; {noun} is bound by referencing "
                    "it in the statement, not by a relation"
                )
                continue
            if kind == "term":
                problems.append(
                    f"{uid}: relates {target}; a term is bound by linking it in "
                    "the statement, written [the words](" + target + ")"
                )
                continue
        # @req> REQ-35877465@UZWrwK_xKhBH cx6r6x
        if target not in known:
            problems.append(f"{uid}: links to {target}, which does not exist")
    return problems


def _references(uid, data, known, root):
    problems = []
    # @req+ REQ-44791607@jSOQJ6WGpg_l e5vzf6
    for address in corpus.references(data):
        target, _ = corpus.split_address(address)
        if target not in known:
            problems.append(f"{uid}: references {target}, which does not exist")
    for near in corpus.PARAM_NEAR.finditer(corpus.prose(data)):
        token = near.group()
        if not corpus.PARAM_REF.fullmatch(token):
            problems.append(
                f"{uid}: text contains {token}, which is not a parameter "
                f"reference -- the form is {corpus.NAME_FORM}"
            )
    for address in corpus.concept_references(data):
        target, _ = corpus.split_address(address)
        if target not in known:
            problems.append(f"{uid}: links to {target}, which does not exist")
    # @req- e5vzf6
    for near in corpus.CONCEPT_NEAR.finditer(
            corpus.CONCEPT_LINK.sub(" ", corpus.prose(data))):
        problems.append(
            f"{uid}: {' '.join(near.group(1).split())} does not read as a "
            "link -- an item is addressed by the name it carries, the words "
            "and the address each sit on one line, a term is linked whole"
        )
    # @req> REQ-48500355@L2q7dNX5i86u f7binw
    for near in corpus.TERM_NEAR.finditer(
            corpus.unlinked_prose(own_words(root, uid, data))):
        problems.append(
            f"{uid}: text contains {near.group()} outside a link -- a term is "
            f"written {corpus.LINK_FORM}"
        )
    return problems


PRONOUNS = (
    "it its itself they them their theirs themselves this these those "
    "he him his she her hers someone something anyone anything everyone "
    "everything somebody anybody everybody nobody nothing none"
).split()

PRONOUN = re.compile(r"(?<![A-Za-z0-9-])(" + "|".join(PRONOUNS)
                     + r")(?![A-Za-z0-9-])", re.IGNORECASE)


def pronouns(text):
    return [(found.start(), found.group()) for found in PRONOUN.finditer(text)]


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
    # @req+ REQ-83702299@IgLtX0BfZTks tmczgb
    bare = corpus.unlinked_prose(data)
    # @req> REQ-24481048@ZhiYUpKwnPlA bapzey
    return [
        f"{uid}: uses \"{word}\" without linking it -- write "
        f"[{word}]({term_uid}), or reword so the statement does not "
        "claim the term"
        for term_uid, word, pattern, phrases in defined
        if term_uid != uid and pattern.search(_outside(bare, phrases))
    ]
    # @req- tmczgb


def exempted(records, root):
    # @req> REQ-88221320@tXvROEk2-d6r 5gpgix
    return sorted({
        f"{uid}: \"{' '.join(found.group().split())}\" is not {term_uid} -- {reason}"
        for term_uid, _, _, phrases in term_index(_approved(records))
        for uid, data in records.items() if uid != term_uid
        for phrase, reason in phrases
        for found in phrase.finditer(
            corpus.unlinked_prose(own_words(root, uid, data)))
    })


def unlinked_terms(uid, data, records, root):
    return _bare_terms(uid, own_words(root, uid, data),
                       term_index(_approved(records)))


def _unlinked_terms(records, root):
    defined = term_index(_approved(records))
    return [problem
            for uid, data in sorted(records.items())
            for problem in _bare_terms(uid, own_words(root, uid, data), defined)]


def occurring(records, text):
    folded = " ".join(re.sub(r"-\n[ \t]*", "-", text).split())
    found = {}
    for uid, word, pattern, _ in term_index(records):
        if pattern.search(folded):
            found.setdefault(uid, []).append(word)
    return found


def unlinked_elsewhere(uid, data, records, root):
    index = term_index({uid: data})
    return sorted(other for other, held in records.items()
                  if _bare_terms(other, own_words(root, other, held), index))


QUANTITY = re.compile(
    r"(?<!\w)(?<!\d\.)(?<![^\W\d_]-)"
    r"(\.?\d[\d,_]*(?:\.\d+)*(?:[eE][+-]?\d+)?)[\s-]*"
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
UNITS = frozenset(ISO_UNITS.values())

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


def quantities(text):
    held = _ungrouped(corpus.UID_IN_PROSE.sub(" ", text))
    return {(_quantity(found.group(1)), _unit(found.group(2)))
            for found in QUANTITY.finditer(held)}


def _quantities(data):
    return quantities(
        corpus.PARAM_REF.sub(" ", corpus.CONCEPT_LINK.sub(r"\1", corpus.prose(data))))


def _states(stated, value, unit):
    if unit:
        return (value, unit) in stated
    return any(value == held and spelling not in UNITS
               for held, spelling in stated)


def occurring_values(records, text):
    stated = quantities(text)
    found = {}
    for uid, data in sorted(records.items()):
        if corpus.kind_of(uid, data) != "parameter":
            continue
        unit = data.get("unit")
        for key in corpus.entries(data) or {}:
            if _states(stated, _quantity(key), _unit(str(unit or ""))):
                found.setdefault(uid, []).append(
                    f"{key} {unit}" if unit else str(key))
    return found


def _unit(written):
    spelling = written.lower()
    return ISO_UNITS.get(spelling, spelling)


def shared_quantities(records, root):
    where = {}
    for uid, data in records.items():
        for quantity in _quantities(own_quantities(root, uid, data)):
            where.setdefault(quantity, []).append(uid)
    problems = []
    # @req> REQ-31827606@1tyZUHjYl_sV 4h2aan
    for (value, unit), uids in sorted(where.items(), key=lambda pair: str(pair[0])):
        if len(uids) > 1:
            problems.append(
                f"{', '.join(sorted(uids))} each state {value} {unit}".rstrip()
                + " -- a quantity more than one statement makes belongs in a "
                f"single parameter, referenced {corpus.NAME_FORM}"
            )
    return problems


def _assessed(uid, data, records, canonical, known):
    def held_data(address):
        return records.get(canonical.get(address, address))

    # @req+ REQ-50160324@7XJSw7absDkA gxi4g4
    unreadable = set()
    for address in corpus.dependencies(data):
        found = corpus.ADDRESS.match(str(address))
        if found and found.group(1) in known and held_data(found.group(1)) is None:
            unreadable.add(found.group(1))
    problems = [f"{uid}: depends on {target}, which could not be read -- "
                f"fix {target} first" for target in sorted(unreadable)]
    # @req- gxi4g4
    wanted = set(corpus.pin_addresses(held_data, data))
    pins = corpus.mapping(data, "assessed")
    stated = data.get("assessed")
    held = set(stated) if isinstance(stated, dict) else set()
    # @req> REQ-67539399@u2d_QLbO8m8G pcswfe
    for target in sorted(held - wanted, key=str):
        found = corpus.ADDRESS.match(str(target))
        if found and found.group(1) in unreadable:
            continue
        problems.append(
            f"{uid}: pins {target}, which is neither related nor referenced"
        )
    for target in sorted(wanted):
        item_uid, rest = corpus.split_address(target)
        stamped = canonical.get(item_uid, item_uid)
        if stamped not in records:
            continue
        held = corpus.address_stamp_of(stamped, records[stamped], rest)
        pinned = pins.get(target)
        if not isinstance(pinned, str) or pinned != held:
            problems.append(
                f"{uid}: suspect link: {target} -- reread both, then "
                "`reqctl relate` a requirement or `reqctl revise "
                f"{uid} --ack` the rest to pin it"
            )
    return problems


def _approved(records):
    return {uid: data for uid, data in records.items()
            if data.get("status") == "approved"}


def conflicts(records):
    approved = _approved(records)
    declared = []
    # @req+ REQ-77022154@Nc0Pd8y2fd1Q loruif
    for uid, data in approved.items():
        for target, relation in sorted(corpus.mapping(data, "relations").items()):
            if relation == "conflicts_with" and target in approved:
                declared.append(tuple(sorted((uid, target))))
    return [
        f"{left} and {right} are both approved and declare conflicts_with -- "
        "resolve it by deprecating one, superseding both, or rewriting them"
        for left, right in sorted(set(declared))
    ]
    # @req- loruif


def supersedes(records):
    approved = _approved(records)
    # @req> REQ-53480164@R-Vze1T10x-h qxi4hb
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
        # @req> REQ-18059226@MYj9BvF9QPy1 2troxr
        if len(set(uids)) > 1:
            problems.append(
                f"{', '.join(sorted(set(uids)))} each claim \"{word}\" -- a "
                "reader cannot tell which definition governs; merge them or "
                "reword one"
            )
        elif len(uids) > 1:
            problems.append(f"{uids[0]}: claims \"{word}\" more than once")
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


def _cycle_problems(edges, noun, tail):
    return [
        f"{_caught(edges, group)}: circular {noun} -- {tail}"
        for group in _components(edges)
        if len(group) > 1 or group[0] in edges.get(group[0], ())
    ]


def _circular_definitions(records):
    # @req+ REQ-49321694@sgj-Dt7t_niN ijccb5
    edges = {uid: sorted(corpus.concept_references(data))
             for uid, data in records.items()
             if corpus.kind_of(uid, data) == "term"}
    return _cycle_problems(edges, "definition",
                           "none of these means anything before the others")
    # @req- ijccb5


def _entry_selection(records):
    canonical = corpus.reachable(records)
    problems = []
    for uid, data in sorted(records.items()):
        for address in corpus.references(data) + corpus.concept_references(data):
            target, rest = corpus.split_address(address)
            if rest is None:
                continue
            held = records.get(canonical.get(target, target))
            if held is None:
                continue
            existing = corpus.entries(held)
            key = rest.split(".")[0]
            if existing is None:
                problems.append(
                    f"{uid}: selects {address} but {target} has no entries"
                )
            elif rest == "default":
                if held.get("default") is None:
                    problems.append(
                        f"{uid}: selects ${{{target}.default}} but {target} "
                        "names no default"
                    )
            # @req> REQ-93367131@fuSPMaKz6PeP vye4xb
            elif rest == key and key in existing and any(
                    isinstance(fields, dict) and rest in fields
                    for fields in existing.values()):
                problems.append(
                    f"{uid}: selects {address}, which names both an entry of "
                    f"{target} and a field its entries carry -- rename one"
                )
            elif corpus.flagged(held, rest) is not None:
                stated = [fields[rest] for fields in existing.values()
                          if isinstance(fields, dict) and rest in fields
                          and not isinstance(fields[rest], bool)]
                # @req> REQ-28975717@KzAN9P4wu6R7 p5hfxl
                if stated:
                    problems.append(
                        f"{uid}: selects {address} but {target} states {rest} "
                        f"{stated[0]!r} -- true or false"
                    )
                # @req> REQ-10000795@SpPvQo8n4Djw bg3tyu
                elif not corpus.flagged(held, rest):
                    problems.append(
                        f"{uid}: selects {address} but no entry of {target} "
                        f"is {rest}"
                    )
            elif key not in existing:
                problems.append(
                    f"{uid}: selects {address} but {target} has no entry "
                    f"{key!r}"
                )
            elif "." in rest:
                field = rest.split(".", 1)[1]
                fields = existing[key] if isinstance(existing[key], dict) else {}
                if field not in fields:
                    problems.append(
                        f"{uid}: selects {address} but entry {key!r} of "
                        f"{target} has no field {field!r}"
                    )
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
        validator = Draft202012Validator(schema)
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
UNMARKED = "\0not marked\0"


def _unmarked(node, marks):
    if isinstance(node, dict):
        if marks(node):
            return {"const": UNMARKED}
        return {key: _unmarked(value, marks) for key, value in node.items()}
    if isinstance(node, list):
        return [_unmarked(one, marks) for one in node]
    return node


def _marked_paths(root, uid, data, marks):
    schema = corpus.schema_for(root, corpus.kind_of(uid, data),
                               corpus.name_of(uid, data))
    return [tuple(str(step) for step in fault.absolute_path)
            for fault in Draft202012Validator(
                _unmarked(schema, marks)).iter_errors(data)
            if fault.validator == "const" and fault.validator_value == UNMARKED]


def prose_paths(root, uid, data):
    return _marked_paths(root, uid, data, lambda node: node.get(PROSE) is True)


def observed_paths(root, uid, data):
    # @req> REQ-48500355@L2q7dNX5i86u t3fuqq
    return _marked_paths(root, uid, data, lambda node: node.get(OBSERVED) is True)


def dated_paths(root, uid, data):
    # @req> REQ-62072712@041OLjKleuri npwa4k
    return _marked_paths(root, uid, data, lambda node: node.get("format") == DATE)


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
    except corpus.ReqctlError:
        return data
    return _dropped(data, paths) if paths else data


def own_words(root, uid, data):
    # @req> REQ-48500355@L2q7dNX5i86u rwffnk
    return _without(root, uid, data, observed_paths)


def own_quantities(root, uid, data):
    # @req> REQ-62072712@041OLjKleuri hlxm3m
    return _without(root, uid, data, observed_paths, dated_paths)


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
            # @req> REQ-31592505@BljBbPHrGGbg vtxlpz
            if named and not linked & _addresses(records, named[0]):
                term_uid, word = named
                held_by = corpus.name_of(term_uid, records[term_uid]) or term_uid
                link = f"[{word}]({held_by})"
                if _admits_link(root, uid, data, where, field, link, judged):
                    problems.append(
                        f"{uid}: entry {'.'.join(where)} field {field} is "
                        f'named for "{word}" but its value does not link '
                        f"{held_by} -- write the value with {link}, or "
                        "rename the field"
                    )
            # @req> REQ-51326810@s0ZUNLc4g3Ek xx2sp7
            if not _declares_prose(root, uid, data, where, field,
                                   refused):
                for target in sorted(linked):
                    if spelled not in words_of.get(target, ()):
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


def coherence(records, root):
    return (_approved_bindings(records) + _shared_words(records)
            + _circular_definitions(records) + _entry_selection(records)
            + _duplicate_names(records) + _entry_term_fields(records, root))


def _duplicate_names(records):
    # @req+ REQ-53177302@2yk3BbuA8YqV uay7dt
    named = {}
    for uid, data in records.items():
        name = corpus.name_of(uid, data)
        if name is not None:
            named.setdefault(name, []).append(uid)
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
    # @req> REQ-44520277@sKFaJ_af6JS6 2pebps
    for relation, tail in ONE_WAY:
        edges = {
            uid: sorted(
                target
                for target, stated in corpus.mapping(data, "relations").items()
                if stated == relation
            )
            for uid, data in records.items()
        }
        problems += _cycle_problems(edges, relation, tail)
    return problems


def _strays(root, paths):
    corpus_dir = Path(root) / "requirements"
    claimed = set(paths)
    skipped = (corpus_dir / "schemas", corpus_dir / "baselines")
    problems = []
    # @req> REQ-69003763@V8Kam1_6cnnC 4ljfwh
    for held in sorted(corpus_dir.rglob("*.yml")) + sorted(corpus_dir.rglob("*.yaml")):
        if held in claimed or held == _baseline.path(root):
            continue
        if any(skip in held.parents for skip in skipped):
            continue
        problems.append(
            f"{held.relative_to(root)}: not where an item lives -- an item is "
            "requirements/(reqs|params|terms|data)/UID.yml; move or delete it"
        )
    return problems


def _guarded(where, check, *args):
    # @req+ REQ-23691260@3s5Nt8Pn1BXA kgrg4l
    try:
        return check(*args)
    except corpus.ReqctlError as fault:
        return [f"{where}: {fault}"]
    # @req> REQ-55939360@qvRmeRuBl0T9 yi53ne
    except Exception as fault:
        return [f"{where}: reqctl could not finish {check.__name__} -- "
                f"{type(fault).__name__}: {fault}"]
    # @req- kgrg4l


def _settled(path):
    text = corpus.read_text(path)
    # @req> REQ-98359235@dyL4jJOUQB1r 5wu7pz
    if corpus.CONFLICTED.search(text):
        raise corpus.ReqctlError(
            f"holds an unresolved merge -- `reqctl resolve {path.stem}` "
            "settles one that falls within its pins"
        )
    return corpus.loads(text, path)


def _named_schemas(records, root):
    # @req+ REQ-48136849@06uQ0leCcA29 wljy47
    held = {corpus.name_of(uid, data) for uid, data in records.items()}
    return [f"corpus: {name}.schema.yaml governs an item named {name}, and "
            "the corpus holds none -- mint it, or remove the schema"
            for name in corpus.named_schemas(root) if name not in held]
    # @req- wljy47


def run(root, exempt=None):
    paths = corpus.item_files(root)
    problems, broken_schemas = _schemas_are_schemas(root)
    records, unreadable = {}, {}
    for path in paths:
        try:
            data = _settled(path)
        except corpus.ReqctlError as error:
            unreadable[path.stem] = str(error).replace(f"{root}/", "")
            continue
        if isinstance(data, dict):
            records[path.stem] = data
    reachable = corpus.reachable(records)
    known = {path.stem for path in paths} | set(reachable)

    for path in paths:
        uid = path.stem
        problems += _guarded(uid, _identity, root, path, records.get(path.stem))
        if uid in unreadable:
            problems.append(f"{uid}: {unreadable[uid]}")
            continue
        if uid not in records:
            problems.append(f"{uid}: item file is not a mapping")
            continue
        data = records[uid]
        try:
            needs = corpus.schema_name_at(root, corpus.kind_of(uid, data),
                                          corpus.name_of(uid, data))
        except corpus.ReqctlError:
            needs = None
        if needs not in broken_schemas:
            problems += _guarded(uid, schema_problems, root, uid, data)
        problems += _guarded(uid, ears, uid, data)
        problems += _guarded(uid, text_values, uid, data)
        problems += _guarded(uid, dictionary_rules, uid, data)
        problems += _guarded(uid, _relations, uid, data, records,
                             reachable, known)
        problems += _guarded(uid, _references, uid, data, known, root)
        problems += _guarded(uid, _assessed, uid, data, records, reachable, known)

    problems += _guarded("corpus", _strays, root, paths)
    problems += _guarded("corpus", _named_schemas, records, root)
    problems += _guarded("corpus", _unlinked_terms, records, root)
    problems += _guarded("corpus", shared_quantities, records, root)
    problems += _guarded("corpus", approved_relations, records)
    problems += _guarded("corpus", conflicts, records)
    problems += _guarded("corpus", supersedes, records)
    problems += _guarded("corpus", coherence, records, root)
    problems += _guarded("corpus", cycles, records)
    if exempt is not None:
        exempt += exempted(records, root)
    return problems
