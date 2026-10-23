import math
import random
import re
import unicodedata

from . import baseline as _baseline
from . import corpus
from . import fields as _fields
from . import validate as _validate
from .corpus import ReqctlError

RELATIONS = ("derives_from", "depends_on", "constrains", "supersedes",
             "conflicts_with")
STATEMENTS = frozenset(corpus.PREFIXES[prefix]
                       for prefix in _validate.SUBJECTS)
OPERATIONS = ("ack", "handle", "kind", "entry", "new_entry", "set", "append",
              "unset", "drop_entry", "reword")
# @req> REQ-40281745@Ifnq5GBzdwaj vbv3ir
FORMS = {"unclaimed": "phrase=reason"}

KINDS = {kind: prefix.rstrip("-")
         for prefix, kind in corpus.PREFIXES.items()}

MINT_ATTEMPTS = 10

GIVEN_UID = re.compile(rf"\A({corpus.KINDS})-[0-9]{{8}}\Z")

SEPARATED = re.compile(r"\d,\d")
BETWEEN_DIGITS = re.compile(r"\d\s*(\D)\s*\d")

ARTICLED_LINK = re.compile(r"(?:\b([Aa]n?)(\s+))?" + corpus.CONCEPT_LINK.pattern)


def _quoting(char):
    return bool({"QUOTATION", "APOSTROPHE"} & set(unicodedata.name(char, "").split()))


def _listing(text):
    return next((c for c in text
                 if unicodedata.category(c) == "Po"
                 and "COMMA" in unicodedata.name(c, "").split()), None)


def scalar(text, carried=frozenset()):
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        if SEPARATED.search(stripped):
            # @req> REQ-30898926@Vu28eWaG_1mE fbreuh
            raise ReqctlError(
                f"{stripped!r}: a comma between digits is ambiguous -- write a "
                "number without digit separators (10000), and space set members "
                "apart ([10, 20])"
            )
        inner = stripped[1:-1]
        members = []
        for part in inner.split(",") if inner.strip() else []:
            # @req> REQ-79956352@OsoTGRd6D5CZ gdh2ib
            _refuse_hidden(f"{part.strip()!r}:", part.strip(" "), carried)
            members.append(part.strip())
        for member in members:
            if not member:
                # @req> REQ-30898926@Vu28eWaG_1mE skicnd
                raise ReqctlError(
                    f"{text!r}: a set member is empty, as a doubled or trailing "
                    "comma leaves nothing between the separators -- remove the "
                    "extra comma"
                )
            if "[" in member or "]" in member:
                # @req> REQ-30898926@Vu28eWaG_1mE zqqx5c
                raise ReqctlError(
                    f"{text!r}: a set is flat -- write its members inside one "
                    "pair of brackets, as in [json, markdown]"
                )
            if member and (_quoting(member[0]) or _quoting(member[-1])):
                # @req> REQ-30898926@Vu28eWaG_1mE esggiu
                raise ReqctlError(
                    f"{member!r}: a set member is unquoted, as the quotes would "
                    "be stored as part of the value -- drop the quotes"
                )
            grouped = {found.start(1) for found in BETWEEN_DIGITS.finditer(member)}
            separator = next((c for i, c in enumerate(member)
                              if i not in grouped and _listing(c)), None)
            if separator is not None:
                # @req> REQ-30898926@Vu28eWaG_1mE 6yewzg
                raise ReqctlError(
                    f"{member!r}: holds U+{ord(separator):04X}, a comma the set "
                    "is not split on -- separate members with an ordinary comma"
                )
        # @req> REQ-64256114@T4kJ-fI_AXrq wfslro
        if inner and len(members) == 1:
            # @req> REQ-30898926@Vu28eWaG_1mE ottxok
            raise ReqctlError(
                f"{stripped!r}: a set separates members with a comma -- "
                "separate them as in [json, markdown], or drop the brackets "
                "to state one value"
            )
        return [scalar(member, carried) for member in members]
    separator = next((c for c in BETWEEN_DIGITS.findall(stripped)
                      if unicodedata.category(c) == "Zs"
                      or {"COMMA", "SEPARATOR", "APOSTROPHE", "QUOTATION"}
                      & set(unicodedata.name(c, "").split())), None)
    if separator:
        # @req> REQ-30898926@Vu28eWaG_1mE agkisl
        raise ReqctlError(
            f"{stripped!r}: U+{ord(separator):04X} between digits is a digit "
            "separator, and which digits it groups is ambiguous -- write the "
            "number whole (10000)"
        )
    # @req> REQ-79956352@OsoTGRd6D5CZ 6dcbid
    _refuse_hidden(f"{stripped!r}:", text, carried)
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


# @req> REQ-79956352@OsoTGRd6D5CZ 7g4u3w
def _refuse_hidden(label, value, carried=frozenset()):
    hidden = _validate.hidden(str(value))
    if hidden is not None and str(value).strip(" ") not in carried:
        # @req> REQ-30898926@Vu28eWaG_1mE asmpgw
        raise ReqctlError(f"{label} {_validate.hidden_fault(hidden)}")


def _restated(field, text, carried):
    pieces = (text.split("|") if field.parts
              else text.partition("=")[::2] if field.name == "unclaimed" else [text])
    return all(piece.strip(" ") in carried for piece in pieces
               if _validate.hidden(piece) is not None)


def _blank_or_hidden(fields, own, kind, carried=frozenset()):
    entries = next((field for field in own if field.name == "entries"), None)
    hidden = []
    for field in own:
        value = fields.get(field.dest)
        if value is None or _keyed(field, entries) or not (
                field.textual or field.parts or field.name == "unclaimed"):
            continue
        for member in value if field.repeated else [value]:
            # @req> REQ-18950462@TJVbxYWG6Dcw 6ed4w7
            if field.textual and not str(member).strip() and not (
                    field.name == "text" and kind in STATEMENTS):
                # @req> REQ-30898926@Vu28eWaG_1mE 3vca72
                raise ReqctlError(f"{field.flag} must not be blank -- give it "
                                  "a value, or leave it out; on revise, its "
                                  "--no- flag clears the field")
            # @req+ REQ-79956352@OsoTGRd6D5CZ i24q67
            found = _validate.hidden(str(member))
            if found is not None and not _restated(field, str(member), carried):
                hidden.append(f"{field.flag} {_validate.hidden_fault(found)}")
            # @req- i24q67
    return hidden


def _stray(root, own, fields, operations=()):
    mine = set(operations) | {dest for field in own
                              for dest in (field.dest, field.cleared, field.dropped)}
    return sorted(flag.flag for flag in _fields.flags(root) + _fields.clears(root)
                  if flag.dest not in mine and fields.get(flag.dest) is not None)


def _converted(field, value):
    if field.parts:
        return criteria(value, field)
    # @req> REQ-24481048@ZhiYUpKwnPlA 2k7l5j
    if field.name == "unclaimed":
        return _unclaimed(value)
    if field.name == "word":
        return str(value).strip()
    if field.textual and field.repeated:
        return [str(member).strip() for member in value]
    return value


def _keyed(field, entries):
    return entries is not None and (field is entries or field.name == "default")


def _one(values, flag, carried=frozenset()):
    if len(values) > 1:
        # @req> REQ-30898926@Vu28eWaG_1mE byxyqp
        raise ReqctlError(f"{flag} states the whole set once -- pass {flag} "
                          "once, with every member inside one pair of brackets, "
                          "as in [json, markdown]")
    return scalar(values[0], carried)


def _unclaimed(pairs):
    held = {}
    for pair in pairs:
        phrase, split, reason = str(pair).partition("=")
        if not phrase.strip() or not split:
            # @req> REQ-30898926@Vu28eWaG_1mE zdqcku
            raise ReqctlError(f"--unclaimed {pair!r}: the form is {FORMS['unclaimed']} "
                              "-- write the phrase, then =, then the reason")
        held[" ".join(phrase.split())] = reason.strip()
    return held


def criteria(given, field):
    parsed = []
    for raw in given:
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) != len(field.parts) or not all(parts):
            # @req> REQ-30898926@Vu28eWaG_1mE i4fgd4
            raise ReqctlError(
                f"{field.flag} {raw!r}: expected '{' | '.join(field.parts)}' -- "
                f"write {len(field.parts)} non-empty parts separated by |"
            )
        parsed.append(dict(zip(field.parts, parts)))
    return parsed


def _assessed_map(uid, data):
    pins = data.get("assessed")
    if pins is None:
        return {}
    if not isinstance(pins, dict):
        # @req> REQ-30898926@Vu28eWaG_1mE 73c76c
        raise ReqctlError(
            f"{uid}: assessed is not a mapping, so this item's pins "
            "cannot be changed without discarding them -- `reqctl validate` "
            f"names the fault; edit {uid}'s file by hand so assessed maps each "
            "address to its pin, or remove assessed"
        )
    return dict(pins)


def _prune_assessed(lookup, uid, data):
    # @req+ REQ-54697016@Ch9-SdvPj8vq ncotff
    wanted = set(corpus.pin_addresses(lookup, data))
    data["assessed"] = {address: pin
                        for address, pin in _assessed_map(uid, data).items()
                        if address in wanted}
    # @req- ncotff
    return wanted


def _pruned(after, uids):
    canonical = corpus.reachable(after)
    for uid in uids:
        held = dict(after[uid])
        if isinstance(held.get("assessed"), dict):
            _prune_assessed(lambda name: after.get(canonical.get(name, name)),
                            uid, held)
            after[uid] = held


def _targets(data):
    return set(corpus.concept_references(data)), set(corpus.references(data))


def _unknown_references(store, uid, data, carried):
    faults = []
    # @req+ REQ-44791607@6FX5SSp9MG3B mtmaxs
    known = corpus.addressable(
        {item.uid: item.data for item in corpus.items(store)})
    linked, referenced = _targets(data)
    held_links, held_references = carried
    unknown = sorted({corpus.split_address(address)[0]
                      for address in referenced - held_references} - known)
    if unknown:
        # @req> REQ-30898926@Vu28eWaG_1mE dk5xj7
        faults.append(
            f"text references {', '.join(unknown)}, which does not exist -- "
            "the parameter or data item must exist before the statement can "
            "reference it; mint it with `reqctl new parameter --name NAME` or "
            "`reqctl new data --name NAME`, or drop the reference"
        )
    absent = sorted({corpus.split_address(address)[0]
                     for address in linked - held_links} - known)
    if absent:
        # @req> REQ-30898926@Vu28eWaG_1mE rlcdi5
        faults.append(
            f"text links {', '.join(absent)}, which does not exist -- "
            "it must exist before the statement can link it; mint it with "
            "`reqctl new term --term WORD`, or write the words without the link"
        )
    # @req- mtmaxs
    # @req> REQ-30898926@Vu28eWaG_1mE ff2nft
    faults += [f"text contains {near.group()}, which is not a parameter "
               f"reference -- write it in the form {corpus.NAME_FORM}"
               for near in corpus.PARAM_NEAR.finditer(corpus.prose(data))
               if not corpus.PARAM_REF.fullmatch(near.group())]
    # @req> REQ-48500355@rnstkLKM48vN pctgzd
    # @req> REQ-30898926@Vu28eWaG_1mE w52idy
    faults += [f"text contains {near.group()} outside a link -- write a term "
               f"as {corpus.LINK_FORM}"
               for near in corpus.TERM_NEAR.finditer(corpus.unlinked_prose(
                   _validate.own_words(store.root, uid, data)))]
    return faults


WIKI_LINK = re.compile(r"\[\[([^\[\]\n]+)\]\]")
ANY_LINK = re.compile(r"\[([^\]\n]+)\]\(([^()\n]+)\)")


def _name_index(store):
    claimants, params, claimed = {}, {}, {}
    for item in corpus.items(store):
        held = corpus.name_of(item.uid, item.data)
        if held is None:
            continue
        if corpus.kind_of(item.uid, item.data) == "term":
            for word in _validate._term_words(item.data):
                claimants.setdefault(word.casefold(), {})[held] = None
            continue
        first = claimed.setdefault(held, item.uid)
        params[held] = held if first == item.uid else None
    # @req+ REQ-57369684@hCyj1HdrHTr5 tbhiwa
    terms = {word: next(iter(held)) if len(held) == 1 else None
             for word, held in claimants.items()}
    # @req- tbhiwa
    return terms, params, claimants


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
    # @req+ REQ-11930677@zW9EYrOae8-u wgpma6
    lookup = corpus.data_lookup(store)
    asked = corpus.expand_address(lookup, f"{held}.{wanted_rest}") - {held}
    if "." in wanted_rest and f"{held}.{wanted_rest}" not in asked:
        return wanted_rest == rest
    return bool(asked) and asked <= corpus.expand_address(lookup, address)
    # @req- wgpma6


def resolve_names(store, text, index=None, carried=(frozenset(), frozenset())):
    terms, params, claimants = index or _name_index(store)
    identities = {held for held in (*terms.values(), *params.values()) if held}
    linked, referenced = carried

    def wiki(match):
        word = match.group(1).strip().casefold()
        uid = terms.get(word)
        # @req> REQ-57369684@hCyj1HdrHTr5 oiqyws
        if word in terms and uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE 373yog
            raise ReqctlError(
                f"[[{match.group(1)}]]: the terms {' and '.join(claimants[word])} "
                f"each claim it -- link the one you mean, as [{match.group(1)}]"
                "(handle), or revise one term so it no longer claims the word"
            )
        if uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE jlaqcl
            raise ReqctlError(
                f"[[{match.group(1)}]]: no term defines it -- mint the term "
                "first with `reqctl new term --term WORD`, or write the word "
                "without brackets"
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
                # @req> REQ-30898926@Vu28eWaG_1mE ntc6a4
                raise ReqctlError(
                    f"[{match.group(1)}]({target}): a term, a parameter and a "
                    "data item are each addressed by the name they carry -- link "
                    "a term by its handle, or reference a parameter or data item "
                    f"as {corpus.NAME_FORM}; `reqctl list` names them"
                )
            noun = "requirement" if held.startswith("REQ-") else "guard"
            # @req> REQ-30898926@Vu28eWaG_1mE u4gv5e
            raise ReqctlError(
                f"[{match.group(1)}]({target}): a link names a concept; a "
                + noun + " is wired with `reqctl relate`, not linked -- write "
                "the words without the link, and run `reqctl relate UID "
                f"RELATION {held}`"
            )
        word = target.casefold()
        uid = terms.get(word)
        # @req> REQ-57369684@hCyj1HdrHTr5 kijh3h
        if word in terms and uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE 6m2au2
            raise ReqctlError(
                f"[{match.group(1)}]({target}): the terms "
                f"{' and '.join(claimants[word])} each claim {target!r} -- "
                "link the one you mean by its handle, or revise one term so it "
                "no longer claims the word"
            )
        # @req> REQ-44791607@6FX5SSp9MG3B h2zt3s
        if uid is None and target in linked:
            return match.group(0)
        if uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE 2fwuyi
            raise ReqctlError(
                f"[{match.group(1)}]({target}): no term defines {target!r} -- "
                "mint the term with `reqctl new term --term WORD`, or write the "
                "words without the link"
            )
        return f"[{match.group(1)}]({uid})"

    def reference(match):
        name = match.group(1)
        uid = params.get(name)
        if name in params and uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE flt4qg
            raise ReqctlError(
                f"${{{name}}}: more than one item claims the name -- "
                "`reqctl validate` names them; give one another name with "
                "`reqctl rename UID NAME`"
            )
        # @req> REQ-44791607@6FX5SSp9MG3B nadc6z
        if uid is None and name + (match.group(2) or "") in referenced:
            return match.group(0)
        if uid is None:
            # @req> REQ-30898926@Vu28eWaG_1mE zejpjo
            raise ReqctlError(
                f"${{{name}}}: no parameter or data item named {name!r} -- "
                f"mint it with `reqctl new parameter --name {name}` or `reqctl "
                f"new data --name {name}`, or drop the reference"
            )
        return f"${{{uid}{match.group(2) or ''}}}"

    resolved = corpus.PARAM_REF.sub(
        reference, ANY_LINK.sub(link, WIKI_LINK.sub(wiki, text)))
    if "[[" in resolved or "]]" in resolved:
        # @req> REQ-30898926@Vu28eWaG_1mE ehjjod
        raise ReqctlError(
            "text holds [[ or ]] outside a resolved link, a nested or "
            "unmatched bracket -- close or remove the stray bracket"
        )
    for token in re.finditer(r"\$\{[^}]*\}?", resolved):
        if not corpus.PARAM_REF.fullmatch(token.group()):
            # @req> REQ-30898926@Vu28eWaG_1mE otgqko
            raise ReqctlError(
                f"text contains {token.group()}, which is not a parameter "
                f"reference -- write it in the form {corpus.NAME_FORM}"
            )
    return resolved


# @req> REQ-76604940@SEVyiDrbH-Ez 25cppk
def _resolved_prose(store, uid, data, carried=(frozenset(), frozenset())):
    paths = set(_validate.prose_paths(store.root, uid, data))
    index = _name_index(store)
    return corpus.prosed(data, paths,
                         lambda text: resolve_names(store, text, index, carried))


def entry_key(member):
    if isinstance(member, bool):
        return "true" if member else "false"
    return str(member)


def _set_fields(entry, pairs, carried):
    for pair in pairs:
        name, split, value = str(pair).partition("=")
        if not name.strip() or not split:
            # @req> REQ-30898926@Vu28eWaG_1mE idy5kb
            raise ReqctlError(f"--set {pair!r}: the form is field=value -- "
                              "write the field, then =, then the value")
        steps = [step.strip() for step in name.strip().split(".")]
        if not all(steps):
            # @req> REQ-30898926@Vu28eWaG_1mE geao3l
            raise ReqctlError(
                f"--set {name.strip()!r}: a dotted field names the entries a "
                "field holds -- name a step between every pair of dots, as "
                "properties.date.name"
            )
        # @req> REQ-79956352@OsoTGRd6D5CZ qldnjy
        for said in name.split("."):
            _refuse_hidden(f"--set {name.strip()!r}:", said.strip(" "), carried)
        where = entry
        for step in steps[:-1]:
            nested = where.get(step, {})
            if not isinstance(nested, dict):
                # @req> REQ-30898926@Vu28eWaG_1mE 6hmnnw
                raise ReqctlError(
                    f"--set {name.strip()}: {step} holds a value, not entries -- "
                    f"set {step} itself rather than a field under it"
                )
            where[step] = nested = dict(nested)
            where = nested
        held = scalar(value, carried)
        where[steps[-1]] = held
    return entry


def _appended(where, steps):
    for step in steps[:-1]:
        nested = where.get(step, {})
        if not isinstance(nested, dict):
            # @req> REQ-30898926@Vu28eWaG_1mE qumxgk
            raise ReqctlError(
                f"--append {'.'.join(steps)}: {step} holds a value, not entries "
                f"-- name {step} itself rather than a field under it"
            )
        where[step] = nested = dict(nested)
        where = nested
    held = where.get(steps[-1])
    if held is not None and not isinstance(held, list):
        # @req> REQ-30898926@Vu28eWaG_1mE li7im2
        raise ReqctlError(
            f"--append {'.'.join(steps)}: {steps[-1]} holds a value, not a set "
            f"-- replace the value with --set {'.'.join(steps)}=VALUE"
        )
    return where, list(held or [])


def _append_fields(entry, pairs, carried):
    for pair in pairs:
        name, split, value = str(pair).partition("=")
        if not name.strip() or not split:
            # @req> REQ-30898926@Vu28eWaG_1mE tqbymt
            raise ReqctlError(f"--append {pair!r}: the form is field=value -- "
                              "write the field, then =, then the value")
        steps = [step.strip() for step in name.strip().split(".")]
        if not all(steps):
            # @req> REQ-30898926@Vu28eWaG_1mE hmdsjr
            raise ReqctlError(
                f"--append {name.strip()!r}: a dotted field names the entries a "
                "field holds -- name a step between every pair of dots, as "
                "properties.date.name"
            )
        # @req> REQ-79956352@OsoTGRd6D5CZ gey5jb
        for said in name.split("."):
            _refuse_hidden(f"--append {name.strip()!r}:", said.strip(" "), carried)
        member = scalar(value, carried)
        if isinstance(member, list):
            # @req> REQ-30898926@Vu28eWaG_1mE b4xdt6
            raise ReqctlError(
                f"--append {name.strip()}: a set is appended a member at a "
                "time; repeat --append"
            )
        where, held = _appended(entry, steps)
        # @req+ REQ-55564856@yOTVGvtwjD3l ej4esr
        held = [member if str(kept).strip() == str(member) else kept for kept in held]
        where[steps[-1]] = held if any(corpus.same(kept, member) for kept in held) else held + [member]
        # @req- ej4esr
    return entry


def _unset_fields(entry, names, key):
    for name in names:
        gone = str(name).strip()
        steps = [step.strip() for step in gone.split(".")]
        if not all(steps):
            # @req> REQ-30898926@Vu28eWaG_1mE vzhjts
            raise ReqctlError(
                f"--unset {gone!r}: a dotted field names the entries a field "
                "holds -- name a step between every pair of dots, as "
                "properties.date.name"
            )
        where = entry
        for step in steps[:-1]:
            nested = where.get(step)
            if not isinstance(nested, dict):
                # @req> REQ-30898926@Vu28eWaG_1mE ocglhp
                raise ReqctlError(f"--unset {gone}: {step} holds no entries -- "
                                  "name a field the entry records, as `reqctl "
                                  "context` shows them")
            where[step] = nested = dict(nested)
            where = nested
        if steps[-1] not in where:
            # @req> REQ-30898926@Vu28eWaG_1mE 3nzrtm
            raise ReqctlError(
                f"--unset {gone}: not a field of {'.'.join([key, *steps[:-1]])} "
                "-- name a field it records, as `reqctl context` shows them"
            )
        where.pop(steps[-1])
    return entry


def _article_for(word):
    return "an" if word[:1].lower() in "aeiou" else "a"


def _rename_map(before, fields, now):
    was = corpus.term_word(before)
    words = {was: now} if was and now and was != now else {}
    for pair in fields.get("reword") or []:
        old, _, new = str(pair).partition("=")
        old, new = old.strip(), new.strip()
        if not old or not new:
            # @req> REQ-30898926@Vu28eWaG_1mE tbiwhv
            raise ReqctlError(f"--reword {pair!r}: the form is old=new -- "
                              "write the words a link shows, then =, then the new words")
        # @req> REQ-79956352@OsoTGRd6D5CZ uafjgl
        _refuse_hidden("--reword", pair)
        words[old] = new
    for new in words.values():
        stray = next((c for c in new if c in "]\n"), None)
        if stray is not None:
            # @req> REQ-30898926@Vu28eWaG_1mE clek7u
            raise ReqctlError(
                f"{new!r} holds U+{ord(stray):04X}, which a link's visible text "
                f"cannot carry, as {corpus.LINK_FORM} ends at the first of it -- "
                "choose words without it"
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


# @req+ REQ-67358511@6v5ZhXIOqAkD b3ts36
def _reword_data(root, uid, data, addresses, words, seen):
    return corpus.prosed(data, set(_validate.prose_paths(root, uid, data)),
                         lambda text: _reworded(text, addresses, words, seen))
# @req- b3ts36


def _repin(after, touched, keep=frozenset()):
    moved = {}
    for uid, data in after.items():
        pins = data.get("assessed")
        if not isinstance(pins, dict):
            continue
        held = dict(pins)
        for address, pin in pins.items():
            target, rest = corpus.split_address(address)
            if target not in touched or target not in after or (uid, address) in keep:
                continue
            fresh = corpus.address_stamp_of(target, after[target], rest)
            if fresh is not None and fresh != pin:
                held[address] = fresh
        if held != pins:
            moved[uid] = dict(data, assessed=held)
    return moved


def _awaiting(before, uid, olds, new):
    return {(holder, f"{new}.{rest}" if rest else new)
            for holder, data in before.items()
            for address, pin in corpus.mapping(data, "assessed").items()
            for target, rest in [corpus.split_address(address)]
            if target in olds
            and pin != corpus.address_stamp_of(uid, before[uid], rest)}


def _propagate(store, uid, prospective, words):
    before = {item.uid: item.data for item in corpus.items(store)}
    addresses = {uid, corpus.name_of(uid, prospective)} - {None}
    seen = {"done": 0, "left": set(), "placed": set(), "articles": [],
            "moved": []}
    after = dict(before)
    touched = set()
    for held_uid, data in before.items():
        was = prospective if held_uid == uid else data
        if not any(f"]({address})" in str(was) for address in addresses):
            continue
        held = _reword_data(store.root, held_uid, was, addresses, words, seen)
        if held != was:
            after[held_uid] = held
            touched.add(held_uid)
    after[uid] = prospective if uid not in touched else after[uid]
    # @req> REQ-54697016@Ch9-SdvPj8vq mzmppv
    _pruned(after, touched)
    found = (_validate.coherence(after, store.root)
             + _validate._unlinked_terms(after, store.root))
    stood = (_validate.coherence(before, store.root)
             + _validate._unlinked_terms(before, store.root)) if found else []
    faults = [fault for fault in found if fault not in stood]
    if faults:
        raise ReqctlError("\n".join(faults))
    fields = corpus.term_fields(after[uid])
    seen["left"] -= {corpus.term_word(after[uid]), *(fields.get("aliases") or [])}
    seen["moved"] = [
        corpus.Item(held_uid, corpus.find(store, held_uid).path, after[held_uid])
        for held_uid in sorted(touched) if held_uid != uid
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


# @req> REQ-53177302@oSukBFyA3jXq 7bhax4
def _refuse_unusable_name(store, name, held=None):
    if not corpus.DATA_KEY.match(name):
        # @req> REQ-30898926@Vu28eWaG_1mE 4x2722
        raise ReqctlError(f"{name}: a name is snake_case -- write it in "
                          "lowercase words joined by _, as stated_name")
    for other in corpus.items(store):
        if other.uid == held or corpus.name_of(other.uid, other.data) != name:
            continue
        kind = corpus.kind_of(other.uid, other.data)
        unchanged = f"; {held} was not changed" if held else ""
        # @req> REQ-30898926@Vu28eWaG_1mE dbxarp
        raise ReqctlError(
            f"{name}: the {kind} {other.uid} already answers to it -- choose "
            f"another name, or rename that one first with `reqctl rename "
            f"{other.uid} NAME`{unchanged}")


def rename(store, uid, new_name):
    item = corpus.find(store, uid)
    kind = corpus.kind_of(item.uid, item.data)
    if kind not in ("term", "parameter", "data"):
        # @req> REQ-30898926@Vu28eWaG_1mE olyxh6
        raise ReqctlError(
            f"{item.uid}: a {kind} carries no name; a term, a parameter or a "
            "data item is renamed -- name one of those instead")
    # @req> REQ-79956352@OsoTGRd6D5CZ 75mdrs
    _refuse_hidden("name", new_name)
    _refuse_unusable_name(store, new_name, item.uid)
    # @req+ REQ-99037710@COBChae3SzWZ mbvtpn
    wore = [held for held in sorted(corpus.carriers(store).get(new_name, []))
            if held != item.uid]
    if wore:
        # @req> REQ-30898926@Vu28eWaG_1mE n6hriu
        raise ReqctlError(
            f"{new_name}: {', '.join(wore)} has carried that name, so a "
            f"reference to it would be ambiguous -- choose another; {item.uid} "
            "was not changed")
    # @req- mbvtpn
    old_name = corpus.name_of(item.uid, item.data)
    olds = {item.uid} | ({old_name} if old_name is not None else set())
    if old_name == new_name and item.path.stem == new_name:
        # @req> REQ-30898926@Vu28eWaG_1mE egtnqu
        raise ReqctlError(f"{item.uid} already answers to {new_name} -- "
                          "name a different name")

    # @req+ REQ-97543346@Yc-UcdtSPtB3 jjk7ud
    before = {held.uid: held.data for held in corpus.items(store)}
    after = {held_uid: _readdressed_item(data, olds, new_name)
             for held_uid, data in before.items()}
    # @req- jjk7ud
    # @req> REQ-94917590@2yP1VjEjzn4- 7xvisp
    after[item.uid] = _named(
        _carrying(item.uid, after[item.uid], old_name, new_name),
        kind, new_name)
    after[new_name] = after.pop(item.uid)
    # @req> REQ-54697016@Ch9-SdvPj8vq rvmjri
    _pruned(after, [held_uid for held_uid, data in after.items()
                    if data != before.get(held_uid)])
    # @req> REQ-14368186@0pLRg6eJoadP mgzb3c
    after.update(_repin(after, {new_name}, _awaiting(before, item.uid, olds, new_name)))

    # @req> REQ-81815730@fForAOZqtxKN k27etl
    faults = [fault for fault in _validate.dictionary_rules(new_name, after[new_name])
              if fault not in _validate.dictionary_rules(new_name, item.data)]
    found = _validate.coherence(after, store.root)
    stood = _validate.coherence(before, store.root) if found else []
    faults += [fault for fault in found if fault not in stood]
    if faults:
        raise ReqctlError("\n".join(faults) + f"\n{item.uid} was not changed")

    paths = {held.uid: held.path for held in corpus.items(store)}
    moved = corpus.folder_for(store.root, kind) / f"{new_name}.yml"
    corpus.save(store, corpus.Item(new_name, moved, after[new_name]))
    if item.path != moved:
        corpus.remove(item.path)
    for held_uid, data in after.items():
        if held_uid == new_name or data == before.get(held_uid):
            continue
        corpus.save(store, corpus.Item(held_uid, paths[held_uid], data))
    corpus.invalidate(store)
    return sorted(held_uid for held_uid, data in after.items()
                  if held_uid != new_name and data != before.get(held_uid))


def refile(store, uid):
    item = corpus.find(store, uid)
    held = corpus.kind_of(item.uid, item.data)
    if held != "parameter":
        # @req> REQ-30898926@Vu28eWaG_1mE xuf4dj
        raise ReqctlError(
            f"{item.uid} is a {held}; refile files a parameter as a data item -- "
            "name a parameter; `reqctl list parameter` names them")

    before = {found.uid: found.data for found in corpus.items(store)}
    after = dict(before)
    dropped = (_fields.names(store.root, "parameter")
               - _fields.names(store.root, "data"))
    after[item.uid] = dict(
        {key: value for key, value in item.data.items()
         if key not in dropped}, kind="data")
    # @req> REQ-14368186@0pLRg6eJoadP p2igyc
    after.update(_repin(after, {item.uid},
                        _awaiting(before, item.uid, {item.uid}, item.uid)))

    problems = _validate.dictionary_rules(item.uid, after[item.uid])
    found = _validate.coherence(after, store.root)
    stood = _validate.coherence(before, store.root) if found else []
    problems += [fault for fault in found if fault not in stood]
    if problems:
        raise ReqctlError("\n".join(problems) + f"\n{item.uid} was not changed")

    moved = corpus.folder_for(store.root, "data") / f"{item.uid}.yml"
    corpus.save(store, corpus.Item(item.uid, moved, after[item.uid]))
    if item.path != moved:
        corpus.remove(item.path)
    for held_uid, data in after.items():
        if held_uid == item.uid or data == before.get(held_uid):
            continue
        corpus.save(store, corpus.Item(
            held_uid, corpus.find(store, held_uid).path, data))
    corpus.invalidate(store)
    return sorted(held_uid for held_uid, data in after.items()
                  if held_uid != item.uid and data != before.get(held_uid))


def typed(store):
    try:
        held = corpus.find(store, _validate.VALUE_TYPES)
    except ReqctlError:
        return False
    return corpus.kind_of(held.uid, held.data) == "data"


def _filed(value, olds, address, values):
    if isinstance(value, str):
        def reference(match):
            head, _, tail = (match.group(2) or ".")[1:].partition(".")
            if match.group(1) not in olds or head not in ("", "default", *map(str, values)):
                return match.group(0)
            return "${" + address + ("." + tail if tail else "") + "}"

        return corpus.PARAM_REF.sub(reference, value)
    if isinstance(value, list):
        return [_filed(each, olds, address, values) for each in value]
    if isinstance(value, dict):
        return {key: _filed(each, olds, address, values) for key, each in value.items()}
    return value


def _filed_item(data, olds, address, values):
    held = _filed(data, olds, address, values)
    pins = data.get("assessed")
    if isinstance(pins, dict):
        held["assessed"] = {}
        for pinned, pin in pins.items():
            if str(pinned).partition(".")[0] not in olds:
                held["assessed"][pinned] = pin
                continue
            held["assessed"][address] = pin
            held["assessed"].setdefault(address.partition(".")[0], pin)
    return held


def refile_into(store, uid, into, key):
    item = corpus.find(store, uid)
    held = corpus.kind_of(item.uid, item.data)
    if held != "parameter":
        # @req> REQ-30898926@Vu28eWaG_1mE aplnce
        raise ReqctlError(
            f"{item.uid} is a {held}; refile files a parameter as a data item -- "
            "name a parameter; `reqctl list parameter` names them")
    # @req> REQ-47334951@68J7gRTY6uvK yw2ky4
    if not typed(store):
        # @req> REQ-30898926@Vu28eWaG_1mE 7s76xc
        raise ReqctlError(
            f"the corpus holds no data item named {_validate.VALUE_TYPES} -- "
            f"mint it with `reqctl new data --name {_validate.VALUE_TYPES}`, or "
            f"file {item.uid} as a data item of its own with `reqctl refile "
            f"{item.uid}`; {item.uid} was not changed")
    # @req+ REQ-32527326@JhrCBejivbr9 44gp2u
    target = corpus.find(store, into)
    held = corpus.kind_of(target.uid, target.data)
    if held != "data":
        # @req> REQ-30898926@Vu28eWaG_1mE juki7h
        raise ReqctlError(
            f"{target.uid} is a {held}; a parameter is filed into a data item -- "
            "name a data item after --into; `reqctl list data` names them; "
            f"{item.uid} was not changed")
    stated = item.data.get("entries")
    values = list(stated) if isinstance(stated, (dict, list)) else [stated] * (stated is not None)
    if len(values) > 1:
        # @req> REQ-30898926@Vu28eWaG_1mE 2pcwe7
        raise ReqctlError(
            f"{item.uid} holds {', '.join(map(str, values))}; only a parameter "
            f"holding one value is filed as an entry -- file it as a data item of "
            f"its own with `reqctl refile {item.uid}`; {item.uid} was not changed")
    if item.data.get("default") is not None:
        # @req> REQ-30898926@Vu28eWaG_1mE ploxif
        raise ReqctlError(
            f"{item.uid} states a default, which an entry cannot carry -- "
            f"drop it with `reqctl revise {item.uid} --no-default`, or file it "
            f"as a data item of its own with `reqctl refile {item.uid}`; "
            f"{item.uid} was not changed")
    entries = target.data.get("entries", {})
    if not isinstance(entries, dict):
        # @req> REQ-30898926@Vu28eWaG_1mE pue73u
        raise ReqctlError(
            f"{target.uid} does not hold its entries under keys -- name a data "
            "item that keys its entries after --into, or edit "
            f"{target.uid}'s file by hand to key them; {item.uid} was not changed")
    if key in map(str, entries):
        # @req> REQ-30898926@Vu28eWaG_1mE h3nhv2
        raise ReqctlError(
            f"{target.uid} already holds {key} -- choose another key; "
            f"{item.uid} was not changed")

    address = f"{target.uid}.{key}"
    if not corpus.PARAM_REF.fullmatch("${" + address + "}"):
        # @req> REQ-30898926@Vu28eWaG_1mE d5msl2
        raise ReqctlError(
            f"{address} is not an address a reference can carry -- choose a "
            f"snake_case key; {item.uid} was not changed")
    olds = {item.uid, corpus.name_of(item.uid, item.data)}
    paths = {found.uid: found.path for found in corpus.items(store)}
    before = {found.uid: found.data for found in corpus.items(store)}
    after = {held_uid: _filed_item(data, olds, address, values)
             for held_uid, data in before.items()}
    carried = corpus.mapping(after[item.uid], "assessed")
    after[target.uid] = dict(
        after[target.uid],
        **({"assessed": {**carried, **corpus.mapping(after[target.uid], "assessed")}}
           if carried else {}),
        entries={**(corpus.entries(after[target.uid]) or {}), key: {
            "definition": after[item.uid].get("text"),
            "value_type": item.data.get("value_type"),
            **({"quantity": values[0]} if values else {}),
            **({"unit": item.data["unit"]} if item.data.get("unit") is not None else {})}})
    after[item.uid] = dict(after[item.uid], status="deprecated")
    moved = {held_uid for held_uid, data in after.items() if data != before[held_uid]}
    after.update(_repin(after, moved - {target.uid, item.uid}))
    # @req+ REQ-14368186@0pLRg6eJoadP yrfrdz
    awaiting = {holder for holder, _ in _awaiting(before, item.uid, olds, address)}
    after.update({held_uid: data for held_uid, data in _repin(after, {target.uid}, {
        (holder, pinned) for holder in awaiting for pinned in (address, target.uid)
        if pinned not in corpus.mapping(before[holder], "assessed")}
        | _awaiting(before, target.uid, {target.uid}, target.uid)).items()
                  if held_uid in moved})
    # @req- yrfrdz

    # @req+ REQ-42390302@QOC4GhS7SkFg aev5ks
    written = [corpus.Item(held_uid, paths[held_uid], data)
               for held_uid, data in sorted(after.items()) if data != before[held_uid]]
    found = _validate.coherence(after, store.root)
    stood = _validate.coherence(before, store.root) if found else []
    problems = _new_item_faults(store, written) + [
        fault for fault in found if fault not in stood]
    if problems:
        raise ReqctlError("\n".join(problems) + f"\n{item.uid} was not changed")
    # @req- aev5ks

    for filed in written:
        corpus.save(store, filed)
    corpus.invalidate(store)
    return address, sorted(moved - {item.uid, target.uid})
    # @req- 44gp2u


def _entered(value):
    if not isinstance(value, list):
        separator = _listing(entry_key(value))
        if separator is not None:
            # @req> REQ-30898926@Vu28eWaG_1mE mv6opl
            raise ReqctlError(
                f"{value!r}: a set needs its brackets, as without them "
                f"U+{ord(separator):04X} is not a separator but part of the one "
                "member's name -- write it inside brackets, as in [json, markdown]"
            )
    # @req+ REQ-42544082@VRPSEgM9tJWs ghvzto
    members = value if isinstance(value, list) else [value]
    if len(set(members)) != len(members):
        # @req> REQ-30898926@Vu28eWaG_1mE x7dnbk
        raise ReqctlError("a set member is duplicated -- name each member once")
    keys = [entry_key(member) for member in members]
    if len(set(keys)) != len(keys):
        # @req> REQ-30898926@Vu28eWaG_1mE olur2z
        raise ReqctlError("a set member is duplicated -- name each member once")
    # @req- ghvzto
    return {key: {} for key in keys}


def _taken(folder, uid):
    return any((folder / f"{uid}{suffix}").exists() for suffix in (".yml", ".yaml"))


# @req> REQ-57781505@5YGB5n_NZmnc cmxvxt
def _placeholder_for(kind, uid):
    prefix = KINDS[kind]
    given = GIVEN_UID.match(uid)
    if given is None or given.group(1) != prefix:
        # @req> REQ-30898926@Vu28eWaG_1mE qnl3yk
        raise ReqctlError(
            f"{uid}: a {kind} is minted under {prefix}- and eight digits -- "
            f"pass --uid {prefix}-NNNNNNNN, or leave --uid out to mint a free one")
    return uid.removeprefix(f"{prefix}-")


def mint(store, kind, name=None, placeholder=None):
    folder = corpus.folder_for(store.root, kind)
    if name is not None:
        _refuse_unusable_name(store, name)
        return name, folder / f"{name}.yml"
    prefix = KINDS[kind]
    # @req+ REQ-73115701@_3WJxxfhIo7L j3ijco
    if placeholder is not None:
        uid = f"{prefix}-{placeholder}"
        # @req> REQ-64236823@S--_1RHFn9pW 5xsesf
        if _taken(folder, uid):
            # @req> REQ-30898926@Vu28eWaG_1mE ohel7y
            raise ReqctlError(f"{uid}: the corpus already holds an item under it "
                              "-- pass another --uid, or leave --uid out to "
                              "mint a free one")
        return uid, folder / f"{uid}.yml"
    # @req- j3ijco
    rng = random.SystemRandom()
    for _ in range(MINT_ATTEMPTS):
        uid = f"{prefix}-{rng.randrange(10_000_000, 100_000_000)}"
        if not _taken(folder, uid):
            return uid, folder / f"{uid}.yml"
    # @req> REQ-30898926@Vu28eWaG_1mE pk7vas
    raise ReqctlError(f"could not mint a free UID in {MINT_ATTEMPTS} attempts "
                      "-- run the command again")


def prepare(store, kind, fields, placeholder=None):
    own = _fields.of(store.root, kind)
    # @req+ REQ-48998966@TUTQjlZtGDUP 4zgzmu
    missing = [field.flag for field in own
               if field.required and fields.get(field.dest) is None]
    if missing:
        # @req> REQ-30898926@Vu28eWaG_1mE tljg2g
        raise ReqctlError(
            f"a {kind} needs {', '.join(missing)} to be valid the moment it exists "
            f"-- pass {', '.join(missing)}"
        )
    # @req- 4zgzmu
    # @req+ REQ-25589226@gN1zcZG8pbON nk637k
    stray = _stray(store.root, own, fields)
    if stray:
        # @req> REQ-30898926@Vu28eWaG_1mE m547p4
        raise ReqctlError(f"{', '.join(stray)} does not apply to a {kind} -- "
                          f"drop {', '.join(stray)}")
    # @req- nk637k
    if fields.get("uid") is not None and kind not in ("requirement", "guard"):
        # @req> REQ-30898926@Vu28eWaG_1mE xhixmr
        raise ReqctlError(f"--uid does not apply to a {kind}; it is minted "
                          "under the name it carries -- drop --uid")
    hidden = _blank_or_hidden(fields, own, kind)

    data = _fields.defaults(store.root, kind)
    entries = next((field for field in own if field.name == "entries"), None)
    default = {field.name: fields.get(field.dest) for field in own}.get("default")
    entry = {}
    for field in own:
        value = fields.get(field.dest)
        if value is not None and not _keyed(field, entries):
            (entry if field.entry else data)[field.name] = _converted(field, value)
    named = next((data.get(field.name) for field in own if field.address), None)
    if kind == "term":
        word = entry.get("word")
        if not isinstance(word, str):
            # @req> REQ-30898926@Vu28eWaG_1mE k4sb36
            raise ReqctlError("a term needs a word: its handle falls out of the "
                              "word it states -- pass --term WORD")
        handle = corpus.handle_for(word)
        if not corpus.DATA_KEY.match(handle):
            # @req> REQ-30898926@Vu28eWaG_1mE ju2fda
            raise ReqctlError(
                f"--term {word!r}: no snake_case handle falls out of it, and a "
                "term is addressed by one -- state a word that holds a letter "
                "or digit from a to z or 0 to 9")
        data["entries"] = {handle: entry}
        named = handle
    elif kind == "parameter" and entries and fields.get(entries.dest) is not None:
        data["entries"] = _entered(_one(fields[entries.dest], entries.flag))
        if default is not None:
            chosen = entry_key(scalar(str(default)))
            # @req> REQ-67914848@cRb9rHls6z6c b4izbx
            if chosen not in data["entries"]:
                # @req> REQ-30898926@Vu28eWaG_1mE 64xone
                raise ReqctlError(f"--default {default}: not a member of the set "
                                  "-- name one of its members")
            data["default"] = chosen
    elif kind == "data" and entries and fields.get(entries.dest) is not None:
        # @req+ REQ-42544082@VRPSEgM9tJWs 3nahao
        keys = [str(key).strip() for key in fields[entries.dest]]
        repeated = sorted({key for key in keys if keys.count(key) > 1})
        if repeated:
            # @req> REQ-30898926@Vu28eWaG_1mE qeu3k2
            raise ReqctlError(
                f"{entries.flag} {', '.join(repeated)}: given more than once -- "
                "give each once"
            )
        # @req- 3nahao
        data["entries"] = {key: {} for key in keys}
        if default is not None:
            chosen = str(default).strip()
            # @req> REQ-67914848@cRb9rHls6z6c wzvf5m
            if chosen not in data["entries"]:
                # @req> REQ-30898926@Vu28eWaG_1mE h2cq5l
                raise ReqctlError(f"--default {default}: not an entry -- name one "
                                  "of its entries")
            data["default"] = chosen

    # @req+ REQ-73115701@_3WJxxfhIo7L yorgmf
    if placeholder is None and fields.get("uid") is not None:
        placeholder = _placeholder_for(kind, fields["uid"])
    uid, path = mint(store, kind, named, placeholder)
    # @req- yorgmf
    data = _resolved_prose(store, uid, data)
    # @req+ REQ-85308584@4lLbQIsexIid lmav5l
    site = path if corpus.UID.match(uid) or named is not None else mint(store, kind)[1]
    # @req> REQ-42390302@QOC4GhS7SkFg r5sgzy
    problems = hidden + _new_item_faults(store, [corpus.Item(uid, site, data)])
    # @req- lmav5l
    problems += _joined_faults(store, uid, data)
    return uid, path, data, problems


def _joined_faults(store, uid, prospective):
    records = {item.uid: item.data for item in corpus.items(store)}
    paths = corpus.item_files(store.root)
    # @req+ REQ-85308584@4lLbQIsexIid td4i2r
    found = _validate.corpus_checks({**records, uid: prospective}, store.root, paths)
    if all(problem.startswith(f"{uid}: ") for problem in found):
        return found
    stood = set(_validate.corpus_checks(records, store.root, paths))
    return [problem for problem in found
            if problem not in stood or _validate.UNFINISHED in problem]
    # @req- td4i2r


def create(store, kind, fields):
    uid, path, data, problems = prepare(store, kind, fields)
    if problems:
        raise ReqctlError("\n".join(problems))
    item = corpus.Item(uid, path, data)
    corpus.save(store, item)
    return item


def _checked(check, *args):
    try:
        return check(*args)
    except ReqctlError:
        raise
    except Exception as fault:
        raise ReqctlError(f"corpus: reqctl could not finish {check.__name__} -- "
                          f"{type(fault).__name__}: {fault}") from fault


def _corpus_faults(store, checked, written, records):
    return (_validate.coherence(checked, store.root, _checked)
            + _checked(_validate.shared_quantities, checked, store.root)
            + _checked(_validate.approved_relations, checked)
            + _checked(_validate.conflicts, checked)
            + _checked(_validate.supersedes, checked)
            + _checked(_validate._bound_guards, checked, store.root)
            + [fault for uid in sorted(written)
               for fault in _checked(_validate.unlinked_terms, uid,
                                     checked.get(uid) or {}, records, store.root)])


def _new_corpus_faults(store, written):
    records = {item.uid: item.data for item in corpus.items(store)}
    found = _corpus_faults(store, {**records, **written}, written, records)
    if not found:
        return []
    stood = _corpus_faults(store, records, written, records)
    return [problem for problem in found if problem not in stood]


def _pins_only(before, prospective):
    return all(corpus.same(prospective.get(key), before.get(key))
               for key in {*before, *prospective} - {"assessed"})


def _new_cycles(store, uid, prospective):
    records = {item.uid: item.data for item in corpus.items(store)}
    existing = _validate.cycles(records)
    return [problem
            for problem in _validate.cycles({**records, uid: prospective})
            if problem not in existing]


def _new_item_faults(store, written):
    # @req+ REQ-42390302@QOC4GhS7SkFg vbwcqp
    # @req+ REQ-79956352@OsoTGRd6D5CZ m2sskk
    # @req+ REQ-44791607@6FX5SSp9MG3B norsxb
    records = {item.uid: item.data for item in corpus.items(store)}
    joined = {**records, **{item.uid: item.data for item in written}}
    standing, reach = corpus.reachable(records), corpus.reachable(joined)
    faults = []
    for item in written:
        # @req> REQ-85308584@4lLbQIsexIid sz4ty3
        found = _validate.item_problems(store.root, item.uid, item.path, item.data,
                                        joined, reach, reach, suspect=False)
        stood = [] if not found or item.uid not in records else _validate.item_problems(
            store.root, item.uid, item.path, records[item.uid], records, standing,
            standing, suspect=False)
        faults += [fault for fault in found if fault not in stood]
    return faults
    # @req- norsxb
    # @req- m2sskk
    # @req- vbwcqp


# @req> REQ-15211173@2tindbOlAUEJ krbgcj
def _placed(uid, blocks, prospective, flag, named):
    block, dot, key = named.partition(".")
    if dot and not (block in blocks and key and "." not in key):
        # @req> REQ-30898926@Vu28eWaG_1mE 5lbsgd
        raise ReqctlError(f"{flag} {named}: names no block member of {uid} -- name "
                          "it as block.key, where block is one the schema marks "
                          "addressable")
    place = block if dot else "entries"
    held = prospective.get(place)
    prospective[place] = held = dict(held) if isinstance(held, dict) else {}
    return held, key if dot else named


def revisable_fields(own, kind):
    return [field for field in own if field.name != "entries"
            or kind == "parameter" and field.dest not in OPERATIONS]


def _revision(store, uid, fields):
    item = corpus.find(store, uid)
    kind = corpus.kind_of(uid, item.data)
    if kind not in KINDS:
        # @req> REQ-30898926@Vu28eWaG_1mE cvizke
        raise ReqctlError(f"{uid}: names no kind; `reqctl validate` names the fault "
                          f"-- edit {uid}'s file by hand so it states a kind the "
                          "corpus knows")
    own = _fields.of(store.root, kind)
    revisable = revisable_fields(own, kind)

    # @req+ REQ-25589226@gN1zcZG8pbON 5apnio
    stray = _stray(store.root, revisable, fields, OPERATIONS)
    if stray:
        # @req> REQ-30898926@Vu28eWaG_1mE betlcx
        raise ReqctlError(f"{', '.join(stray)} does not apply to a {kind} -- "
                          f"drop {', '.join(stray)}")
    # @req- 5apnio
    # @req+ REQ-61755382@LGJAUmpv4utG 7pv66p
    if fields.get("handle") is not None:
        if kind != "term":
            # @req> REQ-30898926@Vu28eWaG_1mE 7cecle
            raise ReqctlError(
                f"--handle does not apply to a {kind}; only a term wears its "
                "word as a key -- drop --handle"
            )
        # @req> REQ-30898926@Vu28eWaG_1mE 2uvdy5
        raise ReqctlError(
            "--handle: a term's handle is the address the corpus reaches it "
            f"by; `reqctl rename {uid} HANDLE` moves the file with it"
        )
    # @req> REQ-91205530@FiUaykViw6dQ hc64tl
    for field in own:
        if field.address and fields.get(field.dest) is not None:
            noun = "a data item" if kind == "data" else f"a {kind}"
            # @req> REQ-30898926@Vu28eWaG_1mE e5c7hi
            raise ReqctlError(
                f"{field.flag}: {noun}'s {field.name} is the address the corpus "
                f"reaches it by; `reqctl rename {uid} {field.name.upper()}` "
                "moves the file with it"
            )
    # @req- 7pv66p
    if fields.get("reword") and kind != "term":
        # @req> REQ-30898926@Vu28eWaG_1mE lnrgyk
        raise ReqctlError(
            f"--reword does not apply to a {kind}; only a term's links show a "
            "word a statement can outgrow -- drop --reword"
        )

    if kind in ("term", "parameter") and corpus.entries(item.data) is None:
        # @req> REQ-30898926@Vu28eWaG_1mE sbazfq
        raise ReqctlError(f"{uid}: has no entries -- `reqctl validate` names the "
                          f"fault; edit {uid}'s file by hand to give it entries")
    carried = {said for _, said in _validate._strings(item.data)}
    hidden = _blank_or_hidden(fields, own, kind, carried)
    if hidden:
        raise ReqctlError("\n".join(hidden))
    if fields.get("entry") is not None and kind not in ("data", "parameter"):
        # @req> REQ-30898926@Vu28eWaG_1mE r7lubu
        raise ReqctlError(f"--entry does not apply to a {kind} -- drop --entry")
    if fields.get("new_entry") is not None and kind != "data":
        # @req> REQ-30898926@Vu28eWaG_1mE loe7wp
        raise ReqctlError(f"--new-entry does not apply to a {kind} -- drop "
                          "--new-entry")
    if fields.get("drop_entry") is not None and kind != "data":
        # @req> REQ-30898926@Vu28eWaG_1mE mlejhf
        raise ReqctlError(f"--drop-entry does not apply to a {kind} -- drop "
                          "--drop-entry")
    if fields.get("entry") is not None and fields.get("new_entry") is not None:
        # @req> REQ-30898926@Vu28eWaG_1mE olxiz7
        raise ReqctlError("--entry and --new-entry are one write each; pass one")
    if (fields.get("set") and fields.get("entry") is None
            and fields.get("new_entry") is None):
        # @req> REQ-30898926@Vu28eWaG_1mE ygfwfy
        raise ReqctlError("--set needs --entry -- name the entry with --entry "
                          "KEY; a data item also takes a new one with --new-entry KEY")
    if (fields.get("append") and fields.get("entry") is None
            and fields.get("new_entry") is None):
        # @req> REQ-30898926@Vu28eWaG_1mE yearku
        raise ReqctlError("--append needs --entry -- name the entry with "
                          "--entry KEY; a data item also takes a new one with "
                          "--new-entry KEY")
    if fields.get("unset") and fields.get("entry") is None:
        # @req> REQ-30898926@Vu28eWaG_1mE oblxrc
        raise ReqctlError(
            "--unset needs --entry; a new entry has no field to drop, and "
            "--drop-entry takes the whole one -- name the entry with --entry KEY"
        )
    both = ({str(name).strip() for name in fields.get("unset") or []}
            & {str(pair).partition("=")[0].strip()
               for pair in fields.get("set") or []})
    if both:
        # @req> REQ-30898926@Vu28eWaG_1mE 6gqwtd
        raise ReqctlError(
            f"--unset {', '.join(sorted(both))} contradicts --set; pass one"
        )
    for field in own:
        if (field.clears and fields.get(field.cleared)
                and fields.get(field.dest) is not None):
            # @req> REQ-30898926@Vu28eWaG_1mE sqvc5f
            raise ReqctlError(f"{field.clears} contradicts {field.flag}; pass one")
    entries = next((field for field in own if field.name == "entries"), None)
    default = {field.name: fields.get(field.dest) for field in own}.get("default")
    before = dict(item.data)
    stated = {field.name: _converted(field, fields[field.dest])
              for field in own if fields.get(field.dest) is not None
              and not _keyed(field, entries)}
    words = _rename_map(before, fields, stated.get("word"))
    acks = fields.get("ack") or []

    prospective = dict(before)
    # @req> REQ-34694183@DRvdPekHL7hR i7ubge
    prospective["assessed"] = _assessed_map(uid, before)
    if fields.get("kind") is not None:
        if kind in ("requirement", "guard"):
            # @req> REQ-30898926@Vu28eWaG_1mE dmhzd4
            raise ReqctlError(f"--kind does not apply to a {kind} -- drop --kind")
        if fields["kind"] != kind:
            # @req> REQ-30898926@Vu28eWaG_1mE ucv7hm
            raise ReqctlError(
                f"--kind {fields['kind']}: {uid} is a {kind} -- drop --kind, or "
                f"mint the item you meant with `reqctl new {fields['kind']}`")
        prospective["kind"] = kind
    sole = next(iter(corpus.entries(before) or {}), None)
    entry = dict(corpus.term_fields(before))
    for field in own:
        target = entry if field.entry else prospective
        # @req> REQ-20206793@HmbOOqLkGGec xna7hd
        if field.drops and fields.get(field.dropped):
            recorded = target.pop(field.name, None) or {}
            if not isinstance(recorded, dict):
                # @req> REQ-30898926@Vu28eWaG_1mE hvsi7q
                raise ReqctlError(f"{uid}: {field.name} is not a mapping -- "
                                  "`reqctl validate` names the fault; edit "
                                  f"{uid}'s file by hand so {field.name} is a "
                                  "mapping, or remove it")
            named = [" ".join(str(key).split()) for key in fields[field.dropped]]
            absent = [key for key in named if key not in recorded]
            # @req> REQ-78673239@6YprF1By2TZv hszdda
            if absent:
                # @req> REQ-30898926@Vu28eWaG_1mE ketz2v
                raise ReqctlError(f"{field.drops} {', '.join(map(repr, absent))}: "
                                  f"not recorded on {uid} -- name what it records; "
                                  f"`reqctl context {uid}` shows it")
            kept = {key: value for key, value in recorded.items() if key not in named}
            if kept:
                target[field.name] = kept
        if field.name in stated:
            said = stated[field.name]
            # @req+ REQ-55564856@yOTVGvtwjD3l gl6li3
            was = target.get(field.name)
            if isinstance(said, dict):
                said = {**{key: value for key, value in (was or {}).items()
                           if " ".join(str(key).split()) not in said}, **said}
            elif isinstance(said, str) and isinstance(was, str) and said.strip() == was.strip():
                said = said.strip()
            target[field.name] = said
            # @req- gl6li3
        elif field.clears and fields.get(field.cleared):
            if field.empty is None:
                target.pop(field.name, None)
            else:
                target[field.name] = field.empty()
    if any(field.entry for field in own):
        prospective["entries"] = {sole: entry}
    if kind == "parameter":
        if entries in revisable and fields.get(entries.dest) is not None:
            prospective["entries"] = _entered(
                _one(fields[entries.dest], entries.flag, carried))
            held = prospective.pop("default", None)
            if held in prospective["entries"]:
                prospective["default"] = held
        if default is not None:
            chosen = entry_key(scalar(str(default), carried))
            # @req> REQ-67914848@cRb9rHls6z6c 6xxjkf
            if chosen not in corpus.entries(prospective):
                # @req> REQ-30898926@Vu28eWaG_1mE xghyrm
                raise ReqctlError(f"--default {default}: not a member of the set "
                                  "-- name one of its members")
            prospective["default"] = chosen
        if fields.get("entry") is not None:
            held = dict(corpus.entries(prospective))
            key = str(fields["entry"]).strip()
            if key not in held:
                # @req> REQ-30898926@Vu28eWaG_1mE 4lhyjr
                raise ReqctlError(f"--entry {key}: not a member of the set -- "
                                  "name one of its members")
            held[key] = _unset_fields(
                _append_fields(
                    _set_fields(dict(held[key] or {}), fields.get("set") or [], carried),
                    fields.get("append") or [], carried),
                fields.get("unset") or [], key)
            prospective["entries"] = held
    elif kind == "data":
        # @req+ REQ-11930677@zW9EYrOae8-u ra2sb2
        blocks = corpus.addressable_blocks(store.root, uid, before)
        if fields.get("new_entry") is not None:
            named = str(fields["new_entry"]).strip()
            held, key = _placed(uid, blocks, prospective, "--new-entry", named)
            if key in held:
                # @req> REQ-30898926@Vu28eWaG_1mE mvjy5b
                raise ReqctlError(
                    f"--new-entry {named}: already an entry; use --entry {named}"
                )
            held[key] = _append_fields(
                _set_fields({}, fields.get("set") or [], carried),
                fields.get("append") or [], carried)
        if fields.get("entry") is not None:
            named = str(fields["entry"]).strip()
            held, key = _placed(uid, blocks, prospective, "--entry", named)
            if key not in held:
                # @req> REQ-30898926@Vu28eWaG_1mE 3p7tpq
                raise ReqctlError(
                    f"--entry {named}: not an entry of {uid}; to add one, pass "
                    f"--new-entry {named}"
                )
            held[key] = _unset_fields(
                _append_fields(
                    _set_fields(dict(held[key] or {}), fields.get("set") or [], carried),
                    fields.get("append") or [], carried),
                fields.get("unset") or [], named)
        if fields.get("drop_entry") is not None:
            named = str(fields["drop_entry"]).strip()
            held, key = _placed(uid, blocks, prospective, "--drop-entry", named)
            if key not in held:
                # @req> REQ-30898926@Vu28eWaG_1mE dkt6jv
                raise ReqctlError(f"--drop-entry {named}: no such entry -- name "
                                  f"an entry {uid} holds")
            held.pop(key)
        # @req- ra2sb2
        if default is not None:
            chosen = str(default).strip()
            # @req> REQ-67914848@cRb9rHls6z6c znrmhw
            if chosen not in (corpus.entries(prospective) or {}):
                # @req> REQ-30898926@Vu28eWaG_1mE tukwii
                raise ReqctlError(f"--default {default}: not an entry -- name one "
                                  "of its entries")
            prospective["default"] = chosen

    targets = _targets(before)
    prospective = _resolved_prose(store, uid, prospective, targets)

    if (any(field.prose and fields.get(field.dest) is not None for field in own)
            or fields.get("set") or fields.get("append")):
        faults = _unknown_references(store, uid, prospective, targets)
        if faults:
            raise ReqctlError("\n".join(faults))
    # @req> REQ-15079061@DGcuZTEeq7ZL s4egdj
    pinning = not words and _pins_only(before, prospective)
    # @req+ REQ-53480164@5yFhCLJmuTBt xpj5go
    # @req+ REQ-62819035@SRb6tL8xEERF qgjwmq
    stranded = [] if pinning else _new_corpus_faults(store, {uid: prospective})
    if stranded:
        raise ReqctlError("\n".join(stranded))
    # @req- qgjwmq
    # @req- xpj5go

    referenced = corpus.references(prospective) + corpus.concept_references(prospective)
    ack_written = {}
    for ack in acks:
        written = [address for address in referenced
                   if _addresses_match(store, address, ack)]
        if not written:
            # @req> REQ-30898926@Vu28eWaG_1mE khjl2i
            raise ReqctlError(f"--ack {ack}: the statement does not reference it "
                              "-- name an item the statement links or references")
        ack_written[ack] = written

    changed = {key: prospective[key] for key in prospective
               if key != "assessed"
               and not corpus.same(prospective[key], before.get(key))}
    for key in [key for key in before
                if key not in prospective and key != "assessed"]:
        changed[key] = None
    wanted = set()
    lookup = corpus.data_lookup(store)
    if changed or acks:
        wanted = _prune_assessed(lookup, uid, prospective)
    for ack in acks:
        expanded = set()
        for written in ack_written[ack]:
            expanded |= corpus.expand_address(lookup, written)
        for address in sorted(expanded):
            target_uid, rest = corpus.split_address(address)
            pin = corpus.stamp_at(corpus.find(store, target_uid), rest)
            if pin is None:
                # @req> REQ-30898926@Vu28eWaG_1mE waymau
                raise ReqctlError(f"--ack {ack}: {address} names no entry to pin "
                                  "-- name an entry the item holds")
            if prospective["assessed"].get(address) != pin:
                prospective["assessed"][address] = pin
                changed.setdefault("assessed", []).append(address)
        target = corpus.split_address(ack)[0]
        for address in [held for held in prospective["assessed"]
                        if corpus.split_address(held)[0] == target
                        and held not in wanted]:
            del prospective["assessed"][address]
            changed.setdefault("assessed", []).append(address)

    spread = None
    if words:
        prospective, spread = _propagate(store, uid, prospective, words)
        # @req> REQ-42658093@fcEx9NJMNikS gainxj
        for pair in fields.get("reword") or []:
            asked = str(pair).partition("=")[0].strip()
            if asked not in spread["placed"]:
                # @req> REQ-30898926@Vu28eWaG_1mE tfhoq7
                raise ReqctlError(
                    f"--reword {pair}: no link shows {asked!r}, so the reword "
                    "placed no word -- name the words a link shows"
                )
    # @req> REQ-96926927@JrkNpeQqNUl0 q2ou3q
    if not changed and not (spread and spread["done"]):
        asked = [key for key in OPERATIONS
                 + tuple(field.dest for field in own)
                 + tuple(field.cleared for field in own if field.clears)
                 if fields.get(key) is not None]
        if not asked:
            # @req> REQ-30898926@Vu28eWaG_1mE 7blfrs
            raise ReqctlError("nothing to change; pass at least one field")
        return {}, []
    if spread:
        changed["reworded"] = {
            "links": spread["done"],
            "items": sorted(held.uid for held in spread["moved"]),
            "articles": spread["articles"],
            "left": sorted(spread["left"]),
        }
    # @req+ REQ-42390302@QOC4GhS7SkFg vge6ux
    writing = [corpus.Item(item.uid, item.path, prospective),
               *(spread["moved"] if spread else [])]
    faults = _new_item_faults(store, writing)
    # @req+ REQ-53864992@bIpK1ribjvtb 7a2e6t
    carried_ways = {fault.partition("\n")[0] for one in writing
                    for fault in _validate.ears(one.uid, corpus.find(store, one.uid).data)}
    faults = [fault for fault in faults if fault.partition("\n")[0] not in carried_ways]
    # @req- 7a2e6t
    if faults:
        raise ReqctlError("\n".join(faults))
    # @req- vge6ux
    return changed, writing


def revise(store, uid, fields):
    # @req+ REQ-98666936@TeGjonYXb0EM 4k5e4z
    try:
        changed, written = _revision(store, uid, fields)
    except ReqctlError as error:
        joint = "\n" if "\n" in str(error) else "; "
        raise ReqctlError(f"{error}{joint}{uid} was not changed") from None
    # @req- 4k5e4z
    for held in written:
        corpus.save(store, held)
    return changed


def _relations_map(item):
    kinds = item.data.get("relations")
    if kinds is None:
        return {}
    if not isinstance(kinds, dict):
        # @req> REQ-30898926@Vu28eWaG_1mE uvsmta
        raise ReqctlError(
            f"{item.uid}: relations is not a mapping, so this item's relations "
            "cannot be changed without discarding it -- `reqctl validate` "
            f"names the fault; edit {item.uid}'s file by hand so relations maps "
            "each item to its relation, or remove relations"
        )
    return dict(kinds)


def relate(store, source_uid, relation, target_uid):
    if source_uid == target_uid:
        # @req> REQ-30898926@Vu28eWaG_1mE fodj5o
        raise ReqctlError("an item cannot link to itself -- name two different "
                          "items")
    source = corpus.find(store, source_uid)
    # @req> REQ-35877465@zMIttKgLLwy- r2xftu
    target = corpus.find(store, target_uid)
    stating = corpus.kind_of(source.uid, source.data)
    if stating not in STATEMENTS:
        # @req> REQ-30898926@Vu28eWaG_1mE xuui2r
        raise ReqctlError("only a requirement or a guard carries relations -- "
                          "name a requirement or a guard first")
    kind = corpus.kind_of(target.uid, target.data)
    address = corpus.name_of(target.uid, target.data) or target_uid
    pin = f" -- pin it with `reqctl revise {source_uid} --ack {target_uid}`"
    # @req> REQ-10503329@rcywmd_10OQY nso2i7
    if kind in ("parameter", "data"):
        noun = "a parameter" if kind == "parameter" else "a data item"
        # @req> REQ-30898926@Vu28eWaG_1mE snowg4
        raise ReqctlError(
            f"{noun} is bound by referencing it in the statement, written "
            "${" + address + "}" + pin
        )
    # @req> REQ-35606788@1D-PoBeeDGqr kezsvo
    if kind == "term":
        # @req> REQ-30898926@Vu28eWaG_1mE cnwij4
        raise ReqctlError(
            "a term is bound by linking it in the statement, written "
            f"[the words]({address}){pin}"
        )
    if kind != stating:
        # @req> REQ-30898926@Vu28eWaG_1mE 3sf4er
        raise ReqctlError(f"a {stating} relates only to a {stating} -- name a "
                          f"{stating} as the target")

    kinds = _relations_map(source)
    repinned = target_uid in kinds
    # @req> REQ-77808874@o0P_SIB1tzP6 l7oe6k
    if repinned and kinds[target_uid] != relation:
        # @req> REQ-30898926@Vu28eWaG_1mE dpxzka
        raise ReqctlError(
            f"{source_uid} already records {kinds[target_uid]} toward "
            f"{target_uid} -- to record {relation} instead, run "
            f"`reqctl unrelate {source_uid} {target_uid}`, then relate it again"
            f"\n{source_uid} was not changed")
    kinds[target_uid] = relation
    prospective = dict(source.data)
    prospective["assessed"] = _assessed_map(source_uid, source.data)
    prospective["relations"] = kinds
    _prune_assessed(corpus.data_lookup(store), source_uid, prospective)
    # @req> REQ-15079061@DGcuZTEeq7ZL acmucb
    pinning = repinned and _pins_only(source.data, prospective)
    # @req+ REQ-44520277@w92ngdeF87Mm 6sepga
    closed = [] if pinning else _new_cycles(store, source_uid, prospective)
    if closed:
        raise ReqctlError("\n".join(closed) + f"\n{source_uid} was not changed")
    # @req- 6sepga
    # @req+ REQ-53480164@5yFhCLJmuTBt ssmh6o
    stranded = [] if pinning else _new_corpus_faults(store, {source_uid: prospective})
    if stranded:
        raise ReqctlError("\n".join(stranded) + f"\n{source_uid} was not changed")
    # @req- ssmh6o
    if repinned:
        prospective["assessed"][target_uid] = corpus.stamp(
            corpus.find(store, target_uid)
        )
    # @req+ REQ-15079061@DGcuZTEeq7ZL gtdcql
    written = corpus.Item(source_uid, source.path, prospective)
    faults = _new_item_faults(store, [written]) if pinning else []
    if faults:
        raise ReqctlError("\n".join(faults) + f"\n{source_uid} was not changed")
    # @req- gtdcql
    corpus.save(store, written)
    source.data = prospective
    return repinned


# @req> REQ-59707978@txCcQRCbn81h ipk7bd
def _awaiting_pins(item, records, canonical):
    def held(address):
        return records.get(canonical.get(address, address))

    pins = corpus.mapping(item.data, "assessed")
    moved = {}
    for target in corpus.pin_addresses(held, item.data):
        target_uid, rest = corpus.split_address(target)
        stamped = canonical.get(target_uid, target_uid)
        if stamped not in records:
            continue
        stamp = corpus.address_stamp_of(stamped, records[stamped], rest)
        if stamp is not None and pins.get(target) != stamp:
            moved[target] = stamp
    return moved


def repin_links(store, uids, everything):
    # @req> REQ-27825753@2D8M3t-t1BG1 cyo2du
    if bool(uids) == bool(everything):
        # @req> REQ-30898926@Vu28eWaG_1mE f64oxx
        raise ReqctlError("repin-links names the items to re-pin or takes --all, "
                          "not both and not neither -- run `reqctl repin-links "
                          "UID [UID ...]` or `reqctl repin-links --all`")
    held = list(corpus.items(store))
    records = {item.uid: item.data for item in held}
    canonical = corpus.reachable(records)
    # @req+ REQ-59707978@txCcQRCbn81h 5usm7z
    chosen = held if everything else [corpus.find(store, uid) for uid in uids]
    written, repinned = {}, {}
    for item in chosen:
        if item.uid in written or item.data.get("status") in _validate.RETIRED:
            continue
        moved = _awaiting_pins(item, records, canonical)
        # @req> REQ-27564818@6ED2a9SQcZSQ trkw5f
        if moved:
            pins = {**_assessed_map(item.uid, item.data), **moved}
            written[item.uid] = corpus.Item(item.uid, item.path,
                                            {**item.data, "assessed": pins})
            repinned[item.uid] = sorted(moved)
    # @req- 5usm7z
    if not written:
        return repinned
    # @req> REQ-74985073@u--jP_zHM8wW k3f324
    faults = _new_corpus_faults(store, {uid: one.data for uid, one in written.items()})
    # @req+ REQ-82159833@XT-Vyx7SgeW0 u4gac2
    if faults:
        raise ReqctlError("\n".join(faults) + "\nno item was written")
    for one in written.values():
        corpus.save(store, one)
    # @req- u4gac2
    return repinned


def _stated(root):
    # @req+ REQ-80226740@xdXflfkWkveF m6jqza
    where = _baseline.path(root)
    ref = _baseline._default_ref(root)
    if ref is None:
        if not where.is_file():
            return set(), None
        held = corpus.read(where)
        where = where.relative_to(root)
    else:
        named = where.relative_to(root).as_posix()
        listed = _baseline._git(root, "ls-tree", ref, "--", named)
        if listed.returncode:
            # @req> REQ-30898926@Vu28eWaG_1mE 7hhrbq
            raise ReqctlError(
                f"cannot read the tree {ref} names, so whether it states a "
                f"baseline cannot be told: {listed.stderr.strip()} -- fetch it "
                "with `git fetch origin`, then run the command again")
        if not listed.stdout.strip():
            return set(), None
        found = _baseline._git(root, "show", f"{ref}:{named}")
        if found.returncode:
            # @req> REQ-30898926@Vu28eWaG_1mE iwplaf
            raise ReqctlError(
                f"{ref} states a baseline that cannot be read: "
                f"{found.stderr.strip()} -- fetch it again with `git fetch "
                "origin`, then run the command again")
        held = corpus.loads(found.stdout, ref)
        where = f"{named} on {ref.removeprefix('refs/remotes/')}"
    held = held if isinstance(held, dict) else {}
    recorded = held.get("items")
    return (set(recorded) if isinstance(recorded, dict) else set(),
            f"baseline {held.get('baseline')} in {where}")
    # @req- m6jqza


def delete(tree, uid):
    item = corpus.find(tree, uid)
    status = corpus.raw(item).get("status")
    # @req> REQ-43821318@iOP6I3zudijr qhlga3
    if status == "approved":
        # @req> REQ-30898926@Vu28eWaG_1mE svmcig
        raise ReqctlError(
            f"{uid} is approved -- what the corpus promises is deprecated, "
            f"not removed: `reqctl revise {uid} --status deprecated`"
        )
    # @req+ REQ-80226740@xdXflfkWkveF d223dk
    # @req+ REQ-13861816@OGhn1Q-Xs0__ nmlqee
    name = corpus.name_of(item.uid, item.data)
    identity = {item.uid} | ({name} if name is not None else set())
    wore = set(corpus.carried_of(item.uid, item.data))
    stated, cut = _stated(tree.root)
    if (identity | wore) & stated:
        # @req> REQ-30898926@Vu28eWaG_1mE vu6cxf
        raise ReqctlError(
            f"{uid} is {status}, but {cut} still states it -- it was "
            "approved when that cut was taken. Delete it once a baseline that "
            "no longer names it stands there"
        )
    # @req- nmlqee
    # @req- d223dk
    # @req+ REQ-60430571@Whq2LW6rLEyb ebwpu6
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
        # @req> REQ-30898926@Vu28eWaG_1mE 7toybx
        raise ReqctlError(
            f"{', '.join(holders)} still record a link, a reference or a pin "
            f"toward {uid} -- removing it would leave them pointing at "
            f"nothing; unlink first: `reqctl unrelate HOLDER {uid}` for a "
            "relation, `reqctl revise HOLDER` to drop a link or reference"
        )
    # @req- ebwpu6
    # @req+ REQ-42065260@tSlWvFBjE0qf s7iyuc
    corpus.remove(item.path)
    corpus.invalidate(tree)
    return item.path
    # @req- s7iyuc


def unrelate(store, source_uid, target_uid):
    source = corpus.find(store, source_uid)
    # @req+ REQ-94696919@Nf39VeBeXq9K fvstef
    kinds = _relations_map(source)
    if target_uid not in kinds:
        corpus.find(store, target_uid)
        return False
    kinds.pop(target_uid)
    # @req- fvstef
    prospective = dict(source.data)
    prospective["assessed"] = _assessed_map(source_uid, source.data)
    prospective["relations"] = kinds
    _prune_assessed(corpus.data_lookup(store), source_uid, prospective)
    corpus.save(store, corpus.Item(source_uid, source.path, prospective))
    source.data = prospective
    return True
