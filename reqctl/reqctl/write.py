import math
import random
import re
import unicodedata

from . import baseline as _baseline
from . import corpus
from . import validate as _validate
from .corpus import ReqctlError

REQUIREMENT_FIELDS = ("type", "status", "verification", "priority", "rationale")
GUARD_FIELDS = ("status", "rationale")
PARAMETER_FIELDS = ("status", "name", "unit", "value_type", "rationale")
TERM_FIELDS = ("status", "term", "aliases", "definition", "unclaimed")
RELATIONS = ("derives_from", "depends_on", "constrains", "supersedes",
             "conflicts_with")
STATEMENTS = frozenset(corpus.PREFIXES[prefix]
                       for prefix in _validate.SUBJECTS)
SETTABLE = (set(REQUIREMENT_FIELDS) | set(PARAMETER_FIELDS) | set(TERM_FIELDS)
            | {"value"})
REVISABLE = SETTABLE | {"kind", "text", "criteria", "no_criteria", "ack", "entry",
                        "new_entry", "set", "append", "unset", "default", "drop_entry",
                        "reword", "handle"}
FLAGS = {"aliases": "--alias"}

CLEARABLE = {
    "no_rationale": ("--no-rationale", ("requirement", "parameter", "data")),
    "no_unit": ("--no-unit", ("parameter",)),
    "no_default": ("--no-default", ("parameter", "data")),
    "no_aliases": ("--no-alias", ("term",)),
}
REVISABLE |= set(CLEARABLE)
SWITCHES = {"no_criteria"} | set(CLEARABLE)

KINDS = {kind: prefix.rstrip("-")
         for prefix, kind in corpus.PREFIXES.items()}
FIELDS = {
    "requirement": REQUIREMENT_FIELDS,
    "guard": GUARD_FIELDS,
    "parameter": PARAMETER_FIELDS + ("value",),
    "term": TERM_FIELDS,
    "data": ("status", "name", "rationale", "text"),
}
REQUIRED = {
    "requirement": ("text",),
    "guard": ("text",),
    "parameter": ("text", "name", "value", "value_type"),
    "term": ("term", "definition"),
    "data": ("name",),
}
REFILED = ("value_type", "unit")

MINT_ATTEMPTS = 10

GIVEN_UID = re.compile(rf"\A({corpus.KINDS})-[0-9]{{8}}\Z")

SEPARATED = re.compile(r"\d,\d")
BETWEEN_DIGITS = re.compile(r"\d\s*(\D)\s*\d")

ARTICLED_LINK = re.compile(r"(?:\b([Aa]n?)(\s+))?" + corpus.CONCEPT_LINK.pattern)

PARAMETER_DEFAULTS = {"kind": "parameter", "status": "draft", "assessed": {}}
TERM_DEFAULTS = {"kind": "term", "status": "draft", "assessed": {}}
REQUIREMENT_DEFAULTS = {
    "type": "functional",
    "status": "draft",
    "verification": "automated_test",
    "priority": "medium",
    "acceptance_criteria": [],
    "relations": {},
    "assessed": {},
}
GUARD_DEFAULTS = {
    "status": "draft",
    "acceptance_criteria": [],
    "relations": {},
    "assessed": {},
}
DATA_DEFAULTS = {"kind": "data", "status": "draft", "assessed": {}}
DEFAULTS = {"requirement": REQUIREMENT_DEFAULTS,
            "guard": GUARD_DEFAULTS,
            "parameter": PARAMETER_DEFAULTS,
            "term": TERM_DEFAULTS,
            "data": DATA_DEFAULTS}


def _quoting(char):
    return bool({"QUOTATION", "APOSTROPHE"} & set(unicodedata.name(char, "").split()))


def _listing(text):
    return next((c for c in text
                 if unicodedata.category(c) == "Po"
                 and "COMMA" in unicodedata.name(c, "").split()), None)


def _hidden(text):
    return next((c for i, c in enumerate(text)
                 if not c.isprintable() or (i == 0 and unicodedata.category(c) == "Mn")),
                None)


def _hidden_fault(char):
    if len(f"a{char}b".splitlines()) > 1:
        return f"holds U+{ord(char):04X}, a line break -- write it as one line"
    if char.isspace():
        return (f"holds U+{ord(char):04X}, which prints as a plain space but "
                "is not one -- respace it with ordinary spaces")
    return (f"holds U+{ord(char):04X}, which prints as nothing -- retype it "
            "rather than pasting it")


def scalar(text):
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        if SEPARATED.search(stripped):
            raise ReqctlError(
                f"{stripped!r}: a comma between digits is ambiguous -- write a "
                "number without digit separators (10000), and space set members "
                "apart ([10, 20])"
            )
        inner = stripped[1:-1]
        members = []
        for part in inner.split(",") if inner.strip() else []:
            hidden = _hidden(part.strip(" "))
            if hidden is not None:
                raise ReqctlError(f"{part.strip()!r}: {_hidden_fault(hidden)}")
            members.append(part.strip())
        for member in members:
            if not member:
                raise ReqctlError(
                    f"{text!r}: a set member is empty -- a doubled or trailing "
                    "comma leaves nothing between the separators"
                )
            if "[" in member or "]" in member:
                raise ReqctlError(
                    f"{text!r}: a set is flat, as in [json, markdown]"
                )
            if member and (_quoting(member[0]) or _quoting(member[-1])):
                raise ReqctlError(
                    f"{member!r}: a set member is unquoted -- the quotes would be "
                    "stored as part of the value"
                )
            grouped = {found.start(1) for found in BETWEEN_DIGITS.finditer(member)}
            separator = next((c for i, c in enumerate(member)
                              if i not in grouped and _listing(c)), None)
            if separator is not None:
                raise ReqctlError(
                    f"{member!r}: holds U+{ord(separator):04X}, a comma the set "
                    "is not split on -- separate members with an ordinary comma"
                )
        # @req> REQ-64256114@LGtxztCW6SK0 wfslro
        if inner and len(members) == 1:
            raise ReqctlError(
                f"{stripped!r}: a set separates members with a comma, as in "
                "[json, markdown]"
            )
        return [scalar(member) for member in members]
    separator = next((c for c in BETWEEN_DIGITS.findall(stripped)
                      if unicodedata.category(c) == "Zs"
                      or {"COMMA", "SEPARATOR", "APOSTROPHE", "QUOTATION"}
                      & set(unicodedata.name(c, "").split())), None)
    if separator:
        raise ReqctlError(
            f"{stripped!r}: U+{ord(separator):04X} between digits is a digit "
            "separator, and which digits it groups is ambiguous -- write the "
            "number whole (10000)"
        )
    hidden = _hidden(text)
    if hidden is not None:
        raise ReqctlError(f"{stripped!r}: {_hidden_fault(hidden)}")
    if stripped.lower() in ("true", "false"):
        return stripped.lower() == "true"
    digits = stripped.lstrip("+-")
    if digits.isdigit() and digits.startswith("0") and digits != "0":
        return stripped
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        number = float(stripped)
    except ValueError:
        return stripped
    return number if math.isfinite(number) else stripped


# @req> REQ-79956352@k55ltaUh0RIF 7g4u3w
def _refuse_hidden(label, value):
    hidden = _hidden(str(value))
    if hidden is not None:
        raise ReqctlError(f"{label} {_hidden_fault(hidden)}")


def _refuse_blank_text(fields):
    for key in ("text", "definition", "term", "rationale", "name", "unit"):
        value = fields.get(key)
        if value is None:
            continue
        if not str(value).strip():
            raise ReqctlError(f"--{key} must not be blank")
        _refuse_hidden(f"--{key}", value)
    for alias in fields.get("aliases") or []:
        if not str(alias).strip():
            raise ReqctlError("--alias must not be blank")
        _refuse_hidden("--alias", alias)


def _unclaimed(pairs):
    held = {}
    for pair in pairs:
        phrase, split, reason = str(pair).partition("=")
        if not phrase.strip() or not split:
            raise ReqctlError(f"--unclaimed {pair!r}: the form is phrase=reason")
        held[" ".join(phrase.split())] = reason.strip()
    return held


def criteria(given):
    if not given:
        return None
    parsed = []
    for raw in given:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ReqctlError(
                f"--criterion {raw!r}: expected 'given | when | then' -- three "
                "non-empty parts separated by |"
            )
        for part in parts:
            _refuse_hidden("--criterion", part)
        parsed.append(dict(zip(("given", "when", "then"), parts)))
    return parsed


def _assessed_map(uid, data):
    pins = data.get("assessed")
    if pins is None:
        return {}
    if not isinstance(pins, dict):
        raise ReqctlError(
            f"{uid}: assessed is not a mapping, so this item's pins "
            "cannot be changed without discarding them -- `reqctl validate` "
            "names the fault"
        )
    return dict(pins)


def _prune_assessed(store, uid, data):
    wanted = set(corpus.pin_addresses(corpus.data_lookup(store), data))
    parents = {corpus.split_address(address)[0]
               for address in corpus.dependencies(data)}
    pins = _assessed_map(uid, data)
    data["assessed"] = {
        address: pin for address, pin in pins.items()
        if address in wanted or corpus.split_address(address)[0] in parents
    }
    return wanted


def _refuse_unknown_references(store, data):
    # @req+ REQ-44791607@jSOQJ6WGpg_l mtmaxs
    known = corpus.addressable(
        {item.uid: item.data for item in corpus.items(store)})
    unknown = sorted({corpus.split_address(address)[0]
                      for address in corpus.references(data)} - known)
    if unknown:
        raise ReqctlError(
            f"text references {', '.join(unknown)}, which does not exist -- "
            "the parameter or data item must exist before the statement can "
            "reference it"
        )
    absent = sorted({corpus.split_address(address)[0]
                     for address in corpus.concept_references(data)} - known)
    if absent:
        raise ReqctlError(
            f"text links {', '.join(absent)}, which does not exist -- "
            "it must exist before the statement can link it"
        )
    # @req- mtmaxs
    for near in corpus.PARAM_NEAR.finditer(corpus.prose(data)):
        if not corpus.PARAM_REF.fullmatch(near.group()):
            raise ReqctlError(
                f"text contains {near.group()}, which is not a parameter "
                f"reference -- the form is {corpus.NAME_FORM}"
            )
    for near in corpus.TERM_NEAR.finditer(corpus.unlinked_prose(data)):
        raise ReqctlError(
            f"text contains {near.group()} outside a link -- a term is "
            f"written {corpus.LINK_FORM}"
        )


WIKI_LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
ANY_LINK = re.compile(r"\[([^\]\n]+)\]\(([^()\n]+)\)")


def _name_index(store):
    terms, params, claimed = {}, {}, {}
    for item in corpus.items(store):
        held = corpus.name_of(item.uid, item.data)
        if held is None:
            continue
        if corpus.kind_of(item.uid, item.data) == "term":
            for word in _validate._term_words(item.data):
                key = word.casefold()
                first = claimed.setdefault(("word", key), item.uid)
                terms[key] = held if first == item.uid else None
            continue
        first = claimed.setdefault(("name", held), item.uid)
        params[held] = held if first == item.uid else None
    return terms, params


def _addresses_match(store, address, ack):
    held, rest = corpus.split_address(address)
    wanted, wanted_rest = corpus.split_address(ack)
    if held != wanted:
        try:
            if corpus.find(store, held) is not corpus.find(store, wanted):
                return False
        except ReqctlError:
            return False
    if wanted_rest is None:
        return True
    if "." in wanted_rest:
        return wanted_rest == rest
    lookup = corpus.data_lookup(store)
    asked = corpus.expand_address(lookup, f"{held}.{wanted_rest}") - {held}
    return bool(asked) and asked <= corpus.expand_address(lookup, address)


def resolve_names(store, text, index=None):
    terms, params = index or _name_index(store)
    identities = {held for held in (*terms.values(), *params.values()) if held}

    def wiki(match):
        word = match.group(1).strip().casefold()
        uid = terms.get(word)
        if word in terms and uid is None:
            raise ReqctlError(
                f"[[{match.group(1)}]]: more than one term claims it -- "
                "`reqctl validate` names them; resolve that first"
            )
        if uid is None:
            raise ReqctlError(
                f"[[{match.group(1)}]]: no term defines it -- mint the term "
                "first, or write the word without brackets"
            )
        return f"[{match.group(1)}]({uid})"

    def link(match):
        target = match.group(2).strip()
        addressed = corpus.ADDRESS.match(target)
        held = addressed.group(1) if addressed else target
        if target in identities or params.get(held):
            return match.group(0)
        if addressed and corpus.kind_for_uid(held):
            if held.startswith(("TERM-", "PARAM-", "DATA-")):
                raise ReqctlError(
                    f"[{match.group(1)}]({target}): a term, a parameter and a "
                    "data item are each addressed by the name they carry"
                )
            noun = "requirement" if held.startswith("REQ-") else "guard"
            raise ReqctlError(
                f"[{match.group(1)}]({target}): a link names a concept; a "
                + noun + " is wired with `reqctl relate`, not linked"
            )
        word = target.casefold()
        uid = terms.get(word)
        # @req> REQ-57369684@hCyj1HdrHTr5 kijh3h
        if word in terms and uid is None:
            raise ReqctlError(
                f"[{match.group(1)}]({target}): more than one term claims "
                f"{target!r} -- `reqctl validate` names them; resolve that first"
            )
        if uid is None:
            raise ReqctlError(
                f"[{match.group(1)}]({target}): no term defines {target!r}"
            )
        return f"[{match.group(1)}]({uid})"

    def reference(match):
        name = match.group(1)
        uid = params.get(name)
        if name in params and uid is None:
            raise ReqctlError(
                f"${{{name}}}: more than one item claims the name -- "
                "`reqctl validate` names them; resolve that first"
            )
        if uid is None:
            raise ReqctlError(
                f"${{{name}}}: no parameter or data item named {name!r}"
            )
        return f"${{{uid}{match.group(2) or ''}}}"

    resolved = corpus.PARAM_REF.sub(
        reference, ANY_LINK.sub(link, WIKI_LINK.sub(wiki, text)))
    if "[[" in resolved or "]]" in resolved:
        raise ReqctlError(
            "text holds [[ or ]] outside a resolved link -- a nested or "
            "unmatched bracket"
        )
    for token in re.finditer(r"\$\{[^}]*\}?", resolved):
        if not corpus.PARAM_REF.fullmatch(token.group()):
            raise ReqctlError(
                f"text contains {token.group()}, which is not a parameter "
                f"reference -- the form is {corpus.NAME_FORM}"
            )
    return resolved


# @req> REQ-76604940@HbN3En3lfKzD 25cppk
def _resolved_prose(store, uid, data):
    paths = set(_validate.prose_paths(store.root, uid, data))
    index = _name_index(store)
    return corpus.prosed(data, paths,
                         lambda text: resolve_names(store, text, index))


def entry_key(member):
    if isinstance(member, bool):
        return "true" if member else "false"
    return str(member)


# @req> REQ-76604940@HbN3En3lfKzD cd7owj
def _set_fields(entry, pairs, uid):
    for pair in pairs:
        name, split, value = str(pair).partition("=")
        if not name.strip() or not split:
            raise ReqctlError(
                f"--set {pair!r}: the form is field=value; {uid} was not changed"
            )
        steps = [step.strip() for step in name.strip().split(".")]
        if not all(steps):
            raise ReqctlError(
                f"--set {name.strip()!r}: a dotted field names the entries a "
                f"field holds, as properties.date.name; {uid} was not changed"
            )
        where = entry
        for step in steps[:-1]:
            nested = where.get(step, {})
            if not isinstance(nested, dict):
                raise ReqctlError(
                    f"--set {name.strip()}: {step} holds a value, not entries; "
                    f"{uid} was not changed"
                )
            where[step] = nested = dict(nested)
            where = nested
        held = scalar(value)
        where[steps[-1]] = held
    return entry


def _appended(where, steps, uid):
    for step in steps[:-1]:
        nested = where.get(step, {})
        if not isinstance(nested, dict):
            raise ReqctlError(
                f"--append {'.'.join(steps)}: {step} holds a value, not "
                f"entries; {uid} was not changed"
            )
        where[step] = nested = dict(nested)
        where = nested
    held = where.get(steps[-1])
    if held is not None and not isinstance(held, list):
        raise ReqctlError(
            f"--append {'.'.join(steps)}: {steps[-1]} holds a value, not a "
            f"set; {uid} was not changed"
        )
    return where, list(held or [])


# @req> REQ-76604940@HbN3En3lfKzD zijwjm
def _append_fields(entry, pairs, uid):
    for pair in pairs:
        name, split, value = str(pair).partition("=")
        if not name.strip() or not split:
            raise ReqctlError(
                f"--append {pair!r}: the form is field=value; {uid} was not "
                "changed"
            )
        steps = [step.strip() for step in name.strip().split(".")]
        if not all(steps):
            raise ReqctlError(
                f"--append {name.strip()!r}: a dotted field names the entries a "
                f"field holds, as properties.date.name; {uid} was not changed"
            )
        member = scalar(value)
        if isinstance(member, list):
            raise ReqctlError(
                f"--append {name.strip()}: a set is appended a member at a "
                f"time; repeat --append; {uid} was not changed"
            )
        where, held = _appended(entry, steps, uid)
        where[steps[-1]] = held + [member]
    return entry


def _unset_fields(entry, names, key, uid):
    for name in names:
        gone = str(name).strip()
        steps = [step.strip() for step in gone.split(".")]
        if not all(steps):
            raise ReqctlError(
                f"--unset {gone!r}: a dotted field names the entries a field "
                f"holds, as properties.date.name; {uid} was not changed"
            )
        where = entry
        for step in steps[:-1]:
            nested = where.get(step)
            if not isinstance(nested, dict):
                raise ReqctlError(
                    f"--unset {gone}: {step} holds no entries; "
                    f"{uid} was not changed"
                )
            where[step] = nested = dict(nested)
            where = nested
        if steps[-1] not in where:
            raise ReqctlError(
                f"--unset {gone}: not a field of "
                f"{'.'.join([key, *steps[:-1]])}; {uid} was not changed"
            )
        where.pop(steps[-1])
    return entry


def _article_for(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def _rename_map(before, fields):
    words = {}
    if fields.get("term") is not None:
        was = corpus.term_word(before)
        now = str(fields["term"]).strip()
        if was and was != now:
            words[was] = now
    for pair in fields.get("reword") or []:
        old, _, new = str(pair).partition("=")
        old, new = old.strip(), new.strip()
        if not old or not new:
            raise ReqctlError(f"--reword {pair!r}: the form is old=new")
        words[old] = new
    for new in words.values():
        stray = next((c for c in new if c in "]\n"), None)
        if stray is not None:
            raise ReqctlError(
                f"{new!r} holds U+{ord(stray):04X}, which a link's visible text "
                f"cannot carry -- {corpus.LINK_FORM} ends at the first "
                f"of it"
            )
    return words


def _reworded(text, addresses, words, seen):
    def swap(match):
        article, gap, shown, target = match.groups()
        if target not in addresses:
            return match.group(0)
        new = words.get(shown)
        asked = shown
        if new is None and shown[:1].isupper():
            asked = shown[:1].lower() + shown[1:]
            held = words.get(asked)
            new = held and held[:1].upper() + held[1:]
        if new is None:
            seen["left"].add(shown)
            return match.group(0)
        seen["placed"].add(asked)
        seen["done"] += 1
        if not article:
            return f"[{new}]({target})"
        want = _article_for(new)
        if want == article.lower():
            want = article
        else:
            if article[:1].isupper():
                want = want[:1].upper() + want[1:]
            seen["articles"].append(f"{article} {shown} -> {want} {new}")
        return f"{want}{gap}[{new}]({target})"

    return ARTICLED_LINK.sub(swap, str(text))


def _reword_fields(fields, addresses, words, seen):
    held = {}
    for name, value in fields.items():
        if name == "aliases" or not isinstance(value, (str, list)):
            held[name] = value
        elif isinstance(value, list):
            held[name] = [_reworded(each, addresses, words, seen)
                          if isinstance(each, str) else each for each in value]
        else:
            held[name] = _reworded(value, addresses, words, seen)
    return held


def _reword_data(data, addresses, words, seen):
    held = dict(data)
    for name in ("text", "rationale"):
        if isinstance(held.get(name), str):
            held[name] = _reworded(held[name], addresses, words, seen)
    criteria = held.get("acceptance_criteria")
    if isinstance(criteria, list):
        held["acceptance_criteria"] = [
            {key: _reworded(value, addresses, words, seen)
             if isinstance(value, str) else value
             for key, value in criterion.items()}
            if isinstance(criterion, dict) else criterion
            for criterion in criteria
        ]
    entries = corpus.entries(held)
    if entries:
        held["entries"] = {
            key: _reword_fields(fields, addresses, words, seen)
            if isinstance(fields, dict) else fields
            for key, fields in entries.items()
        }
    return held


def _repin(after, touched):
    moved = {}
    for uid, data in after.items():
        pins = data.get("assessed")
        if not isinstance(pins, dict):
            continue
        held = dict(pins)
        for address, pin in pins.items():
            target, rest = corpus.split_address(address)
            if target not in touched or target not in after:
                continue
            fresh = corpus.address_stamp_of(target, after[target], rest)
            if fresh is not None and fresh != pin:
                held[address] = fresh
        if held != pins:
            moved[uid] = dict(data, assessed=held)
    return moved


def _propagate(store, uid, prospective, words):
    before = {item.uid: item.data for item in corpus.items(store)}
    addresses = {uid, corpus.name_of(uid, prospective)} - {None}
    seen = {"done": 0, "left": set(), "placed": set(), "articles": [],
            "moved": [], "repinned": 0}
    after = dict(before)
    touched = set()
    for held_uid, data in before.items():
        was = prospective if held_uid == uid else data
        held = _reword_data(was, addresses, words, seen)
        if held != was:
            after[held_uid] = held
            touched.add(held_uid)
    after[uid] = prospective if uid not in touched else after[uid]
    repinned = _repin(after, touched)
    after.update(repinned)
    seen["repinned"] = len(repinned)
    found = (_validate.coherence(after, store.root)
             + _validate._unlinked_terms(after, store.root))
    stood = (_validate.coherence(before, store.root)
             + _validate._unlinked_terms(before, store.root)) if found else []
    faults = [fault for fault in found if fault not in stood]
    if faults:
        raise ReqctlError("\n".join(faults) + f"\n{uid} was not changed")
    fields = corpus.term_fields(after[uid])
    seen["left"] -= {corpus.term_word(after[uid]), *(fields.get("aliases") or [])}
    seen["moved"] = [
        corpus.Item(held_uid, corpus.find(store, held_uid).path, after[held_uid])
        for held_uid in sorted(touched | set(repinned)) if held_uid != uid
    ]
    return after[uid], seen


def _readdressed(value, olds, new):
    if isinstance(value, str):
        def link(match):
            held, _, rest = match.group(2).partition(".")
            if held not in olds:
                return match.group(0)
            return f"[{match.group(1)}]({new}{'.' + rest if rest else ''})"

        def reference(match):
            if match.group(1) not in olds:
                return match.group(0)
            return "${" + new + (match.group(2) or "") + "}"

        return corpus.PARAM_REF.sub(
            reference, corpus.CONCEPT_LINK.sub(link, value))
    if isinstance(value, list):
        return [_readdressed(each, olds, new) for each in value]
    if isinstance(value, dict):
        return {key: _readdressed(each, olds, new) for key, each in value.items()}
    return value


def _readdressed_item(data, olds, new):
    held = {key: value if key in ("assessed", "relations")
            else _readdressed(value, olds, new)
            for key, value in data.items()}
    pins = data.get("assessed")
    if isinstance(pins, dict):
        moved = {}
        for address, pin in pins.items():
            target, _, rest = str(address).partition(".")
            key = (f"{new}.{rest}" if rest else new) if target in olds else address
            moved[key] = pin
        held["assessed"] = moved
    return held


def _carrying(uid, data, old_name, new_name):
    held = [one for one in corpus.carried_of(uid, data) if one != new_name]
    if old_name is not None and old_name not in held:
        held.append(old_name)
    return dict(data, carried=held)


def _named(data, kind, new_name):
    if kind != "term":
        return dict(data, name=new_name)
    held = corpus.entries(data) or {}
    word = next(iter(held), None)
    return dict(data, entries={new_name: held[word]})


# @req> REQ-53177302@2yk3BbuA8YqV 7bhax4
def _refuse_unusable_name(store, name, held=None):
    if not corpus.DATA_KEY.match(name):
        raise ReqctlError(f"{name}: a name is snake_case")
    for other in corpus.items(store):
        if other.uid == held or corpus.name_of(other.uid, other.data) != name:
            continue
        kind = corpus.kind_of(other.uid, other.data)
        unchanged = f"; {held} was not changed" if held else ""
        raise ReqctlError(
            f"{name}: the {kind} {other.uid} already answers to it; rename "
            f"that one first{unchanged}")


def rename(store, uid, new_name):
    item = corpus.find(store, uid)
    kind = corpus.kind_of(item.uid, item.data)
    if kind not in ("term", "parameter", "data"):
        raise ReqctlError(
            f"{item.uid}: a {kind} carries no name; a term, a parameter or a "
            "data item is renamed")
    _refuse_unusable_name(store, new_name, item.uid)
    old_name = corpus.name_of(item.uid, item.data)
    olds = {item.uid} | ({old_name} if old_name is not None else set())
    if old_name == new_name and item.path.stem == new_name:
        raise ReqctlError(f"{item.uid} already answers to {new_name}")

    # @req+ REQ-97543346@PsO_rDObX2nf jjk7ud
    before = {held.uid: held.data for held in corpus.items(store)}
    after = {held_uid: _readdressed_item(data, olds, new_name)
             for held_uid, data in before.items()}
    # @req- jjk7ud
    # @req> REQ-94917590@UDuLOE8d-fQZ 7xvisp
    after[item.uid] = _named(
        _carrying(item.uid, after[item.uid], old_name, new_name),
        kind, new_name)
    after[new_name] = after.pop(item.uid)
    after.update(_repin(after, {new_name}))

    found = _validate.coherence(after, store.root)
    stood = _validate.coherence(before, store.root) if found else []
    faults = [fault for fault in found if fault not in stood]
    if faults:
        raise ReqctlError("\n".join(faults) + f"\n{item.uid} was not changed")

    moved = corpus.folder_for(store.root, kind) / f"{new_name}.yml"
    corpus.save(store, corpus.Item(new_name, moved, after[new_name]))
    if item.path != moved:
        item.path.unlink()
    for held_uid, data in after.items():
        if held_uid == new_name or data == before.get(held_uid):
            continue
        corpus.save(store, corpus.Item(
            held_uid, corpus.find(store, held_uid).path, data))
    corpus.invalidate(store)
    return sorted(held_uid for held_uid, data in after.items()
                  if held_uid != new_name and data != before.get(held_uid))


def refile(store, uid):
    item = corpus.find(store, uid)
    held = corpus.kind_of(item.uid, item.data)
    if held != "parameter":
        raise ReqctlError(
            f"{item.uid} is a {held}; refile files a parameter as a data item")

    before = {found.uid: found.data for found in corpus.items(store)}
    after = dict(before)
    after[item.uid] = dict(
        {key: value for key, value in item.data.items()
         if key not in REFILED}, kind="data")
    after.update(_repin(after, {item.uid}))

    problems = _validate.dictionary_rules(item.uid, after[item.uid])
    found = _validate.coherence(after, store.root)
    stood = _validate.coherence(before, store.root) if found else []
    problems += [fault for fault in found if fault not in stood]
    if problems:
        raise ReqctlError("\n".join(problems) + f"\n{item.uid} was not changed")

    moved = corpus.folder_for(store.root, "data") / f"{item.uid}.yml"
    corpus.save(store, corpus.Item(item.uid, moved, after[item.uid]))
    if item.path != moved:
        item.path.unlink()
    for held_uid, data in after.items():
        if held_uid == item.uid or data == before.get(held_uid):
            continue
        corpus.save(store, corpus.Item(
            held_uid, corpus.find(store, held_uid).path, data))
    corpus.invalidate(store)
    return sorted(held_uid for held_uid, data in after.items()
                  if held_uid != item.uid and data != before.get(held_uid))


def _entered(value):
    if not isinstance(value, list):
        separator = _listing(entry_key(value))
        if separator is not None:
            raise ReqctlError(
                f"{value!r}: a set needs its brackets, as in [json, markdown] -- "
                f"without them U+{ord(separator):04X} is not a separator but part "
                "of the one member's name"
            )
    # @req+ REQ-42544082@SSo3dr8vJpX3 ghvzto
    members = value if isinstance(value, list) else [value]
    if len(set(members)) != len(members):
        raise ReqctlError("a set member is duplicated")
    keys = [entry_key(member) for member in members]
    if len(set(keys)) != len(keys):
        raise ReqctlError("a set member is duplicated")
    # @req- ghvzto
    return {key: {} for key in keys}


def _taken(folder, uid):
    return any((folder / f"{uid}{suffix}").exists() for suffix in (".yml", ".yaml"))


# @req> REQ-57781505@JeDsR_YIG2Wd cmxvxt
def _placeholder_for(kind, uid):
    prefix = KINDS[kind]
    given = GIVEN_UID.match(uid)
    if given is None or given.group(1) != prefix:
        raise ReqctlError(
            f"{uid}: a {kind} is minted under {prefix}- and eight digits")
    return uid.removeprefix(f"{prefix}-")


def mint(store, kind, name=None, placeholder=None):
    folder = corpus.folder_for(store.root, kind)
    if name is not None:
        _refuse_unusable_name(store, name)
        return name, folder / f"{name}.yml"
    prefix = KINDS[kind]
    # @req+ REQ-73115701@e51Qp8vDbDXd j3ijco
    if placeholder is not None:
        uid = f"{prefix}-{placeholder}"
        # @req> REQ-64236823@peysRQtlkC57 5xsesf
        if _taken(folder, uid):
            raise ReqctlError(f"{uid}: the corpus already holds an item under it")
        return uid, folder / f"{uid}.yml"
    # @req- j3ijco
    rng = random.SystemRandom()
    for _ in range(MINT_ATTEMPTS):
        uid = f"{prefix}-{rng.randrange(10_000_000, 100_000_000)}"
        if not _taken(folder, uid):
            return uid, folder / f"{uid}.yml"
    raise ReqctlError(f"could not mint a free UID in {MINT_ATTEMPTS} attempts")


def prepare(store, kind, fields, placeholder=None):
    missing = [f"--{f.replace('_', '-')}" for f in REQUIRED[kind]
               if fields.get(f) is None]
    if missing:
        raise ReqctlError(
            f"a {kind} needs {', '.join(missing)} to be valid the moment it exists"
        )

    allowed = FIELDS[kind]
    stray = sorted(
        FLAGS.get(key, f"--{key.replace('_', '-')}")
        for key in SETTABLE - set(allowed)
        if fields.get(key) is not None
    )
    if stray:
        raise ReqctlError(f"{', '.join(stray)} does not apply to a {kind}")
    if fields.get("criteria") and kind not in ("requirement", "guard"):
        raise ReqctlError("only a requirement or a guard carries acceptance "
                          "criteria")
    if fields.get("uid") is not None and kind not in ("requirement", "guard"):
        raise ReqctlError(f"--uid does not apply to a {kind}; it is minted "
                          "under the name it carries")
    if fields.get("text") is not None and kind == "term":
        raise ReqctlError("--text does not apply to a term; it carries --definition")
    if fields.get("default") is not None and kind not in ("parameter", "data"):
        raise ReqctlError(f"--default does not apply to a {kind}")
    if fields.get("entry") and kind != "data":
        raise ReqctlError(f"--entry does not apply to a {kind}")
    _refuse_blank_text(fields)
    if fields.get("value") is not None:
        fields = dict(fields, value=scalar(fields["value"]))

    named = None
    data = {key: (dict(value) if isinstance(value, dict)
                  else list(value) if isinstance(value, list) else value)
            for key, value in DEFAULTS[kind].items()}
    if kind in ("requirement", "guard"):
        data["text"] = fields["text"]
        for key in allowed:
            if fields.get(key) is not None:
                data[key] = fields[key]
        given = criteria(fields.get("criteria"))
        if given is not None:
            data["acceptance_criteria"] = given
    elif kind == "term":
        word = str(fields["term"]).strip()
        handle = corpus.handle_for(word)
        if not corpus.DATA_KEY.match(handle):
            raise ReqctlError(
                f"--term {word!r}: no snake_case handle falls out of it, and a "
                "term is addressed by one")
        entry = {"word": word, "definition": fields["definition"]}
        if fields.get("aliases"):
            entry["aliases"] = [str(alias).strip() for alias in fields["aliases"]]
        if fields.get("unclaimed"):
            # @req> REQ-24481048@ZhiYUpKwnPlA 3zljbn
            entry["unclaimed"] = _unclaimed(fields["unclaimed"])
        if fields.get("status") is not None:
            data["status"] = fields["status"]
        data["entries"] = {handle: entry}
        named = handle
    elif kind == "parameter":
        data["text"] = fields["text"]
        for key in ("status", "name", "unit", "value_type", "rationale"):
            if fields.get(key) is not None:
                data[key] = fields[key]
        data["entries"] = _entered(fields["value"])
        named = fields["name"]
        if fields.get("default") is not None:
            chosen = entry_key(scalar(str(fields["default"])))
            if chosen not in data["entries"]:
                raise ReqctlError(f"--default {fields['default']}: not a member "
                                  "of the set")
            data["default"] = chosen
    else:
        for key in allowed:
            if fields.get(key) is not None:
                data[key] = fields[key]
        if not fields.get("entry"):
            raise ReqctlError("a data item needs at least one --entry")
        keys = [str(key).strip() for key in fields["entry"]]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            raise ReqctlError(
                f"--entry {', '.join(repeated)}: given more than once"
            )
        data["entries"] = {key: {} for key in keys}
        if fields.get("default") is not None:
            chosen = str(fields["default"]).strip()
            if chosen not in data["entries"]:
                raise ReqctlError(f"--default {fields['default']}: not an entry")
            data["default"] = chosen
        named = fields["name"]

    # @req+ REQ-73115701@e51Qp8vDbDXd yorgmf
    if placeholder is None and fields.get("uid") is not None:
        placeholder = _placeholder_for(kind, fields["uid"])
    uid, path = mint(store, kind, named, placeholder)
    # @req- yorgmf
    data = _resolved_prose(store, uid, data)
    _refuse_unknown_references(store, data)
    problems = _validate.schema_problems(store.root, uid, data)
    problems += _validate.ears(uid, data)
    problems += _validate.text_values(uid, data)
    problems += _validate.dictionary_rules(uid, data)
    problems += _new_corpus_faults(store, uid, data)
    return uid, path, data, problems


def create(store, kind, fields):
    # @req+ REQ-25589226@gN1zcZG8pbON fqpvnt
    # @req+ REQ-67914848@CoWJ0QyQOZsG ytoyxl
    # @req+ REQ-42544082@SSo3dr8vJpX3 4cg2e4
    uid, path, data, problems = prepare(store, kind, fields)
    if problems:
        raise ReqctlError("\n".join(problems))
    # @req- 4cg2e4
    # @req- ytoyxl
    # @req- fqpvnt
    item = corpus.Item(uid, path, data)
    corpus.save(store, item)
    return item


def _new_corpus_faults(store, uid, prospective):
    records = {item.uid: item.data for item in corpus.items(store)}
    joined = {**records, uid: prospective}
    found = (_validate.coherence(joined, store.root)
             + _validate.shared_quantities(joined, store.root)
             + _validate.approved_relations(joined)
             + _validate.conflicts(joined)
             + _validate.supersedes(joined)
             + _validate.unlinked_terms(uid, prospective, records, store.root))
    if not found:
        return []
    held = records.get(uid) or {}
    stood = (_validate.coherence(records, store.root)
             + _validate.shared_quantities(records, store.root)
             + _validate.approved_relations(records)
             + _validate.conflicts(records)
             + _validate.supersedes(records)
             + _validate.unlinked_terms(uid, held, records, store.root))
    return [problem for problem in found if problem not in stood]


def _new_cycles(store, uid, prospective):
    records = {item.uid: item.data for item in corpus.items(store)}
    existing = _validate.cycles(records)
    return [problem
            for problem in _validate.cycles({**records, uid: prospective})
            if problem not in existing]


def _refuse_new_schema_faults(store, uid, before, prospective):
    existing = (_validate.schema_problems(store.root, uid, before)
                + _validate.text_values(uid, before)
                + _validate.dictionary_rules(uid, before))
    introduced = [
        problem
        for problem in _validate.schema_problems(store.root, uid, prospective)
        + _validate.text_values(uid, prospective)
        + _validate.dictionary_rules(uid, prospective)
        if problem not in existing
    ]
    if introduced:
        raise ReqctlError("\n".join(introduced) + f"\n{uid} was not changed")


# @req+ REQ-98666936@8CkDXfV6m3Ir eo3nl5
def revise(store, uid, fields):
    item = corpus.find(store, uid)
    kind = corpus.kind_of(uid, item.data)
    if kind not in FIELDS:
        raise ReqctlError(
            f"{uid}: names no kind; `reqctl validate` names the fault; "
            f"{uid} was not changed")
    allowed = FIELDS[kind]

    stray = sorted(
        FLAGS.get(key, f"--{key.replace('_', '-')}")
        for key in SETTABLE - set(allowed)
        if fields.get(key) is not None
    )
    if stray:
        raise ReqctlError(
            f"{', '.join(stray)} does not apply to a {kind}; {uid} was not changed"
        )
    if fields.get("text") is not None and kind == "term":
        raise ReqctlError(
            f"--text does not apply to a term; it carries --definition; "
            f"{uid} was not changed"
        )
    # @req+ REQ-61755382@oWxB5-1lwQ9G 7pv66p
    if fields.get("handle") is not None:
        if kind != "term":
            raise ReqctlError(
                f"--handle does not apply to a {kind}; only a term wears its "
                f"word as a key; {uid} was not changed"
            )
        raise ReqctlError(
            f"--handle: a term's handle is the address the corpus reaches it "
            f"by; `reqctl rename {uid} HANDLE` moves the file with it; "
            f"{uid} was not changed"
        )
    if fields.get("name") is not None and kind in ("parameter", "data"):
        noun = "a parameter" if kind == "parameter" else "a data item"
        raise ReqctlError(
            f"--name: {noun}'s name is the address the corpus reaches it by; "
            f"`reqctl rename {uid} NAME` moves the file with it; {uid} was "
            "not changed"
        )
    # @req- 7pv66p
    if fields.get("reword") and kind != "term":
        raise ReqctlError(
            f"--reword does not apply to a {kind}; only a term's links show a "
            f"word a statement can outgrow; {uid} was not changed"
        )

    if kind in ("term", "parameter") and corpus.entries(item.data) is None:
        raise ReqctlError(
            f"{uid}: has no entries -- `reqctl validate` names the fault; "
            f"{uid} was not changed"
        )
    try:
        _refuse_blank_text(fields)
    except ReqctlError as error:
        raise ReqctlError(f"{error}; {uid} was not changed") from None
    # @req> REQ-25589226@gN1zcZG8pbON 6mn4qt
    if fields.get("default") is not None and kind not in ("parameter", "data"):
        raise ReqctlError(
            f"--default does not apply to a {kind}; {uid} was not changed"
        )
    if fields.get("entry") is not None and kind not in ("data", "parameter"):
        raise ReqctlError(
            f"--entry does not apply to a {kind}; {uid} was not changed"
        )
    if fields.get("new_entry") is not None and kind != "data":
        raise ReqctlError(
            f"--new-entry does not apply to a {kind}; {uid} was not changed"
        )
    if fields.get("drop_entry") is not None and kind != "data":
        raise ReqctlError(
            f"--drop-entry does not apply to a {kind}; {uid} was not changed"
        )
    if fields.get("entry") is not None and fields.get("new_entry") is not None:
        raise ReqctlError(
            f"--entry and --new-entry are one write each; pass one; "
            f"{uid} was not changed"
        )
    if (fields.get("set") and fields.get("entry") is None
            and fields.get("new_entry") is None):
        raise ReqctlError(f"--set needs --entry; {uid} was not changed")
    if (fields.get("append") and fields.get("entry") is None
            and fields.get("new_entry") is None):
        raise ReqctlError(f"--append needs --entry; {uid} was not changed")
    if fields.get("unset") and fields.get("entry") is None:
        raise ReqctlError(
            f"--unset needs --entry; a new entry has no field to drop, and "
            f"--drop-entry takes the whole one; {uid} was not changed"
        )
    both = ({str(name).strip() for name in fields.get("unset") or []}
            & {str(pair).partition("=")[0].strip()
               for pair in fields.get("set") or []})
    if both:
        raise ReqctlError(
            f"--unset {', '.join(sorted(both))} contradicts --set; pass one; "
            f"{uid} was not changed"
        )
    for flag, (spelt, kinds) in CLEARABLE.items():
        if fields.get(flag) in (None, False):
            continue
        if kind not in kinds:
            raise ReqctlError(
                f"{spelt} does not apply to a {kind}; {uid} was not changed"
            )
        clash = flag[3:]
        if fields.get(clash) is not None:
            raise ReqctlError(
                f"{spelt} contradicts {FLAGS.get(clash, '--' + clash.replace('_', '-'))}"
                f"; pass one; {uid} was not changed"
            )
    try:
        if fields.get("value") is not None:
            fields = dict(fields, value=scalar(fields["value"]))
        given = ([] if fields.get("no_criteria")
                 else criteria(fields.get("criteria")))
    except ReqctlError as error:
        raise ReqctlError(f"{error}; {uid} was not changed") from None
    if given is not None and not uid.startswith(("REQ-", "GUARD-")):
        raise ReqctlError(
            f"only a requirement or a guard carries acceptance criteria; "
            f"{uid} was not changed"
        )
    acks = fields.get("ack") or []

    before = dict(item.data)
    words = _rename_map(before, fields)
    prospective = dict(before)
    # @req> REQ-34694183@iiEJLoDQUuRu i7ubge
    prospective["assessed"] = _assessed_map(uid, before)
    if fields.get("kind") is not None:
        if kind in ("requirement", "guard"):
            raise ReqctlError(
                f"--kind does not apply to a {kind}; {uid} was not changed")
        if fields["kind"] != kind:
            raise ReqctlError(
                f"--kind {fields['kind']}: {uid} is a {kind}; mint the item "
                f"you meant; {uid} was not changed")
        prospective["kind"] = kind
    if fields.get("text") is not None:
        prospective["text"] = fields["text"]
    if given is not None:
        prospective["acceptance_criteria"] = given
    if kind == "term":
        held = dict(corpus.entries(before))
        word = next(iter(held), None)
        entry = dict(held.get(word) or {})
        if fields.get("definition") is not None:
            entry["definition"] = fields["definition"]
        if fields.get("aliases") is not None:
            entry["aliases"] = [str(alias).strip() for alias in fields["aliases"]]
        elif fields.get("no_aliases"):
            entry.pop("aliases", None)
        if fields.get("unclaimed"):
            # @req> REQ-24481048@ZhiYUpKwnPlA apdsw2
            entry["unclaimed"] = {**(entry.get("unclaimed") or {}),
                                  **_unclaimed(fields["unclaimed"])}
        if fields.get("term") is not None:
            entry["word"] = str(fields["term"]).strip()
        prospective["entries"] = {word: entry}
        if fields.get("status") is not None:
            prospective["status"] = fields["status"]
    elif kind == "parameter":
        for key in ("status", "name", "unit", "value_type", "rationale"):
            if fields.get(key) is not None:
                prospective[key] = fields[key]
        if fields.get("value") is not None:
            try:
                prospective["entries"] = _entered(fields["value"])
            except ReqctlError as error:
                raise ReqctlError(f"{error}; {uid} was not changed") from None
            prospective.pop("default", None)
            held = before.get("default")
            if held in prospective["entries"]:
                prospective["default"] = held
        if fields.get("no_unit"):
            prospective.pop("unit", None)
        if fields.get("no_default"):
            prospective.pop("default", None)
        if fields.get("default") is not None:
            chosen = entry_key(scalar(str(fields["default"])))
            if chosen not in corpus.entries(prospective):
                raise ReqctlError(
                    f"--default {fields['default']}: not a member of the set; "
                    f"{uid} was not changed"
                )
            prospective["default"] = chosen
        if fields.get("entry") is not None:
            held = dict(corpus.entries(prospective))
            key = str(fields["entry"]).strip()
            if key not in held:
                raise ReqctlError(
                    f"--entry {key}: not a member of the set; "
                    f"{uid} was not changed"
                )
            held[key] = _unset_fields(
                _append_fields(
                    _set_fields(dict(held[key] or {}),
                                fields.get("set") or [], uid),
                    fields.get("append") or [], uid),
                fields.get("unset") or [], key, uid)
            prospective["entries"] = held
    elif kind == "data":
        for key in allowed:
            if fields.get(key) is not None:
                prospective[key] = fields[key]
        held = dict(corpus.entries(before) or {})
        if fields.get("new_entry") is not None:
            key = str(fields["new_entry"]).strip()
            if key in held:
                raise ReqctlError(
                    f"--new-entry {key}: already an entry; use --entry {key}; "
                    f"{uid} was not changed"
                )
            held[key] = _append_fields(
                _set_fields({}, fields.get("set") or [], uid),
                fields.get("append") or [], uid)
            prospective["entries"] = held
        if fields.get("entry") is not None:
            key = str(fields["entry"]).strip()
            if key not in held:
                raise ReqctlError(
                    f"--entry {key}: not an entry of {uid}; to add one, pass "
                    f"--new-entry {key}; {uid} was not changed"
                )
            held[key] = _unset_fields(
                _append_fields(
                    _set_fields(dict(held[key] or {}),
                                fields.get("set") or [], uid),
                    fields.get("append") or [], uid),
                fields.get("unset") or [], key, uid)
            prospective["entries"] = held
        if fields.get("drop_entry") is not None:
            held = dict(corpus.entries(prospective) or {})
            key = str(fields["drop_entry"]).strip()
            if key not in held:
                raise ReqctlError(
                    f"--drop-entry {key}: no such entry; {uid} was not changed"
                )
            held.pop(key)
            prospective["entries"] = held
        if fields.get("no_default"):
            prospective.pop("default", None)
        if fields.get("default") is not None:
            chosen = str(fields["default"]).strip()
            if chosen not in (corpus.entries(prospective) or {}):
                raise ReqctlError(
                    f"--default {fields['default']}: not an entry; "
                    f"{uid} was not changed"
                )
            prospective["default"] = chosen
    else:
        for key in allowed:
            if fields.get(key) is not None:
                prospective[key] = fields[key]

    if fields.get("no_rationale"):
        prospective.pop("rationale", None)

    try:
        prospective = _resolved_prose(store, uid, prospective)
    except ReqctlError as error:
        raise ReqctlError(f"{error}; {uid} was not changed") from None

    if fields.get("text") is not None:
        faults = _validate.ears(uid, {"text": prospective["text"]})
        if faults:
            raise ReqctlError("\n".join(faults) + f"\n{uid} was not changed")
    if (fields.get("text") is not None or fields.get("definition") is not None
            or fields.get("rationale") is not None
            or fields.get("set") or fields.get("append")
            or given is not None):
        try:
            _refuse_unknown_references(store, prospective)
        except ReqctlError as error:
            raise ReqctlError(f"{error}; {uid} was not changed") from None
    _refuse_new_schema_faults(store, uid, before, prospective)
    # @req+ REQ-53480164@R-Vze1T10x-h xpj5go
    # @req+ REQ-62819035@LB2IzcLq4nTI qgjwmq
    stranded = _new_corpus_faults(store, uid, prospective)
    if stranded:
        raise ReqctlError("\n".join(stranded) + f"\n{uid} was not changed")
    # @req- qgjwmq
    # @req- xpj5go

    referenced = corpus.references(prospective) + corpus.concept_references(prospective)
    ack_written = {}
    for ack in acks:
        written = [address for address in referenced
                   if _addresses_match(store, address, ack)]
        if not written:
            raise ReqctlError(
                f"--ack {ack}: the statement does not reference it; "
                f"{uid} was not changed"
            )
        ack_written[ack] = written

    changed = {key: prospective[key] for key in prospective
               if key != "assessed"
               and not corpus.same(prospective[key], before.get(key))}
    for key in [key for key in before
                if key not in prospective and key != "assessed"]:
        changed[key] = None
    wanted = set()
    if changed or acks:
        wanted = _prune_assessed(store, uid, prospective)
    lookup = corpus.data_lookup(store)
    for ack in acks:
        expanded = set()
        for written in ack_written[ack]:
            expanded |= corpus.expand_address(lookup, written)
        for address in sorted(expanded):
            target_uid, rest = corpus.split_address(address)
            pin = corpus.stamp_at(corpus.find(store, target_uid), rest)
            if pin is None:
                raise ReqctlError(
                    f"--ack {ack}: {address} names no entry to pin; "
                    f"{uid} was not changed"
                )
            if prospective["assessed"].get(address) != pin:
                prospective["assessed"][address] = pin
                changed.setdefault("assessed", []).append(address)
        target = corpus.split_address(ack)[0]
        for address in [held for held in prospective["assessed"]
                        if corpus.split_address(held)[0] == target
                        and held not in wanted]:
            del prospective["assessed"][address]
            changed.setdefault("assessed", []).append(address)

    _refuse_new_schema_faults(store, uid, before, prospective)
    spread = None
    if words:
        prospective, spread = _propagate(store, uid, prospective, words)
        # @req> REQ-42658093@fcEx9NJMNikS gainxj
        for pair in fields.get("reword") or []:
            asked = str(pair).partition("=")[0].strip()
            if asked not in spread["placed"]:
                raise ReqctlError(
                    f"--reword {pair}: no link shows {asked!r}, so the reword "
                    f"placed no word; {uid} was not changed"
                )
    # @req> REQ-96926927@HugEvFR4Eh82 q2ou3q
    if not changed and not (spread and spread["done"]):
        asked = [key for key in sorted(REVISABLE)
                 if fields.get(key) is not None and fields.get(key) != []
                 and (key not in SWITCHES or fields.get(key))]
        if not asked:
            raise ReqctlError(
                f"nothing to change; pass at least one field; "
                f"{uid} was not changed"
            )
        return {}
    corpus.save(store, corpus.Item(uid, item.path, prospective))
    if spread:
        written = [uid]
        try:
            for held in spread["moved"]:
                corpus.save(store, held)
                written.append(held.uid)
        except OSError as broken:
            waiting = [held.uid for held in spread["moved"]
                       if held.uid not in written]
            raise ReqctlError(
                f"{broken}\nwritten: {', '.join(written)}\nnot written: "
                f"{', '.join(waiting)}\nthe rename is part-written and reads "
                f"as though it holds; restore requirements/ and run it again"
            ) from broken
        changed["reworded"] = {
            "links": spread["done"],
            "items": sorted(held.uid for held in spread["moved"]),
            "articles": spread["articles"],
            "left": sorted(spread["left"]),
            "repinned": spread["repinned"],
        }
    item.data = prospective
    return changed
# @req- eo3nl5


def _relations_map(item):
    kinds = item.data.get("relations")
    if kinds is None:
        return {}
    if not isinstance(kinds, dict):
        raise ReqctlError(
            f"{item.uid}: relations is not a mapping, so this item's relations "
            "cannot be changed without discarding it -- `reqctl validate` "
            "names the fault"
        )
    return dict(kinds)


def relate(store, source_uid, relation, target_uid):
    if source_uid == target_uid:
        raise ReqctlError("an item cannot link to itself")
    source = corpus.find(store, source_uid)
    # @req> REQ-35877465@UZWrwK_xKhBH r2xftu
    target = corpus.find(store, target_uid)
    stating = corpus.kind_of(source.uid, source.data)
    if stating not in STATEMENTS:
        raise ReqctlError("only a requirement or a guard carries relations")
    kind = corpus.kind_of(target.uid, target.data)
    address = corpus.name_of(target.uid, target.data) or target_uid
    pin = f" -- pin it with `reqctl revise {source_uid} --ack {target_uid}`"
    # @req> REQ-10503329@WLWOt9-DSU1S nso2i7
    if kind in ("parameter", "data"):
        noun = "a parameter" if kind == "parameter" else "a data item"
        raise ReqctlError(
            f"{noun} is bound by referencing it in the statement, written "
            "${" + address + "}" + pin
        )
    # @req> REQ-35606788@1D-PoBeeDGqr kezsvo
    if kind == "term":
        raise ReqctlError(
            "a term is bound by linking it in the statement, written "
            f"[the words]({address}){pin}"
        )
    if kind != stating:
        raise ReqctlError(f"a {stating} relates only to a {stating}")

    kinds = _relations_map(source)
    repinned = target_uid in kinds
    kinds[target_uid] = relation
    prospective = dict(source.data)
    prospective["assessed"] = _assessed_map(source_uid, source.data)
    prospective["relations"] = kinds
    _prune_assessed(store, source_uid, prospective)
    # @req+ REQ-44520277@sKFaJ_af6JS6 6sepga
    closed = _new_cycles(store, source_uid, prospective)
    if closed:
        raise ReqctlError("\n".join(closed) + f"\n{source_uid} was not changed")
    # @req- 6sepga
    # @req+ REQ-53480164@R-Vze1T10x-h ssmh6o
    stranded = _new_corpus_faults(store, source_uid, prospective)
    if stranded:
        raise ReqctlError("\n".join(stranded) + f"\n{source_uid} was not changed")
    # @req- ssmh6o
    if repinned:
        prospective["assessed"][target_uid] = corpus.stamp(
            corpus.find(store, target_uid)
        )
    corpus.save(store, corpus.Item(source_uid, source.path, prospective))
    source.data = prospective
    return repinned


def _stated(root):
    where = _baseline.path(root)
    if not where.is_file():
        return set()
    held = corpus.read(where)
    recorded = held.get("items") if isinstance(held, dict) else None
    return set(recorded) if isinstance(recorded, dict) else set()


def delete(tree, uid):
    item = corpus.find(tree, uid)
    status = corpus.raw(item).get("status")
    # @req> REQ-43821318@fwDcRRhE6tEQ qhlga3
    if status == "approved":
        raise ReqctlError(
            f"{uid} is approved -- what the corpus promises is deprecated, "
            f"not removed: `reqctl revise {uid} --status deprecated`"
        )
    # @req+ REQ-80226740@PZjI5BrUS5hq d223dk
    # @req+ REQ-13861816@banV6DgxKI1S nmlqee
    name = corpus.name_of(item.uid, item.data)
    identity = {item.uid} | ({name} if name is not None else set())
    wore = set(corpus.carried_of(item.uid, item.data))
    if (identity | wore) & _stated(tree.root):
        raise ReqctlError(
            f"{uid} is {status}, but the baseline still states it -- it was "
            "approved when that cut was taken. Generate a baseline that no "
            "longer names it, then delete"
        )
    # @req- nmlqee
    # @req- d223dk
    # @req+ REQ-60430571@hgaKmodLJQdG ebwpu6
    holders = sorted(
        other.uid
        for other in corpus.items(tree)
        if other.uid != item.uid
        and identity & {corpus.split_address(address)[0]
                        for address in (list(corpus.dependencies(other.data))
                                        + list(corpus.mapping(other.data,
                                                              "assessed")))}
    )
    if holders:
        raise ReqctlError(
            f"{uid} is still reached by {', '.join(holders)} -- removing it "
            "would leave them pointing at nothing; unlink first"
        )
    # @req- ebwpu6
    # @req+ REQ-42065260@f4qBCU4zNhSm s7iyuc
    item.path.unlink()
    corpus.invalidate(tree)
    return item.path
    # @req- s7iyuc


def unrelate(store, source_uid, target_uid):
    source = corpus.find(store, source_uid)
    corpus.find(store, target_uid)
    kinds = _relations_map(source)
    if target_uid not in kinds:
        return False
    kinds.pop(target_uid)
    prospective = dict(source.data)
    prospective["assessed"] = _assessed_map(source_uid, source.data)
    prospective["relations"] = kinds
    _prune_assessed(store, source_uid, prospective)
    corpus.save(store, corpus.Item(source_uid, source.path, prospective))
    source.data = prospective
    return True
