import copy
import re
from dataclasses import dataclass

from . import corpus
from .corpus import ReqctlError

KIND = "kind"
ENTRIES = "entries"


def boolean(text):
    if text not in ("true", "false"):
        raise ValueError(text)
    return text == "true"


CONVERTED = {"integer": int, "number": float, "boolean": boolean}


def _dest(flag):
    return flag[2:].replace("-", "_")


def _flag(word):
    return "--" + word.replace("_", "-")


@dataclass(frozen=True)
class Flag:
    flag: str
    choices: tuple
    repeated: bool
    switch: bool
    convert: object
    metavar: str | None
    entries: bool

    @property
    def dest(self):
        return _dest(self.flag)


@dataclass(frozen=True)
class Field:
    name: str
    flag: str
    choices: tuple
    repeated: bool
    required: bool
    clears: str | None
    empty: object
    address: bool
    entry: bool
    textual: bool
    prose: bool
    convert: object
    parts: tuple

    @property
    def dest(self):
        return _dest(self.flag)

    @property
    def cleared(self):
        return _dest(self.clears) if self.clears else None


def root():
    try:
        return corpus.find_root()
    except ReqctlError:
        return "."


def _schema(root, kind):
    held = corpus.schema_for(root, kind)
    return held if isinstance(held, dict) else {}


def _pointed(schema, ref):
    if not ref.startswith("#/"):
        return None
    target = schema
    for step in ref[2:].split("/"):
        step = step.replace("~1", "/").replace("~0", "~")
        if isinstance(target, list) and step.isdecimal() and int(step) < len(target):
            target = target[int(step)]
        else:
            target = target.get(step) if isinstance(target, dict) else None
    return target


def _resolved(schema, node):
    if not isinstance(node, dict):
        return {}
    named = schema.get("$id", "a kind schema")
    seen = set()
    while "$ref" in node:
        ref = node["$ref"]
        if ref in seen:
            raise ReqctlError(f"{named}: {ref} refers back to itself")
        target = _pointed(schema, ref)
        if isinstance(target, bool):
            target = {} if target else {"not": {}}
        if not isinstance(target, dict):
            raise ReqctlError(f"{named}: {ref} names nothing within the schema")
        seen.add(ref)
        node = {**target, **{key: value for key, value in node.items()
                             if key != "$ref"}}
    return node


def _forbidden(schema, stated):
    return stated is False or _resolved(schema, stated).get("not") in ({}, True)


def _selects(schema, test, kind):
    if set(test) - {"properties", "required"}:
        return False
    if set(test.get("required", ())) - {KIND}:
        return False
    tested = test.get("properties")
    if not isinstance(tested, dict) or set(tested) != {KIND}:
        return False
    said = _resolved(schema, tested[KIND])
    return said.get("const") == kind or kind in said.get("enum", ())


def _merged(schema, kind):
    properties, required, barred = {}, set(), set()
    branches = [_resolved(schema, item) for item in schema.get("allOf", ())]
    chosen = [_resolved(schema, branch.get("then")) for branch in branches
              if _selects(schema, _resolved(schema, branch.get("if")), kind)]
    for block in [schema] + branches + chosen:
        required.update(block.get("required", ()))
        for name, stated in (block.get("properties") or {}).items():
            if _forbidden(schema, stated):
                barred.add(name)
            else:
                properties[name] = {**properties.get(name, {}),
                                    **_resolved(schema, stated)}
    return {name: stated for name, stated in properties.items()
            if name not in barred}, required


def _prose(node):
    if isinstance(node, dict):
        return node.get("x-prose") is True or any(map(_prose, node.values()))
    if isinstance(node, list):
        return any(map(_prose, node))
    return False


def _field(schema, name, stated, required, entry):
    said = stated.get("x-flag", name)
    if not isinstance(said, str) or not corpus.DATA_KEY.fullmatch(said):
        raise ReqctlError(f"{schema.get('$id', 'a kind schema')}: {name} would "
                          f"take the flag {said!r}, which is not a snake_case word")
    shape = stated.get("type")
    repeated = shape in ("array", "object")
    items = _resolved(schema, stated.get("items", {})) if shape == "array" else {}
    typed = items.get("type") if shape == "array" else shape
    convert = CONVERTED.get(typed) if isinstance(typed, str) else None
    parts = tuple(items.get("required", ())) if items.get("type") == "object" else ()
    enum = stated.get("enum", ())
    choices = tuple(enum) if all(isinstance(one, str) for one in enum) else ()
    clears, empty = None, None
    if not required:
        clears = _flag("no_" + said)
    elif repeated and not stated.get("minItems") and not stated.get("minProperties"):
        clears, empty = _flag("no_" + said), list if shape == "array" else dict
    return Field(name=name, flag=_flag(said), choices=choices,
                 repeated=repeated,
                 required=required and (entry or "default" not in stated),
                 clears=clears, empty=empty,
                 address=stated.get("x-address") is True, entry=entry,
                 textual=(convert is None and "enum" not in stated
                          and shape != "object" and not parts),
                 prose=_prose(stated), convert=convert, parts=parts)


def of(root, kind):
    schema = _schema(root, kind)
    properties, required = _merged(schema, kind)
    held = []
    for name, stated in properties.items():
        if stated.get("readOnly") is True:
            continue
        if name == ENTRIES and stated.get("maxProperties") == 1:
            entry = _resolved(schema, stated.get("additionalProperties", {}))
            wanted = set(entry.get("required", ()))
            held += [_field(schema, key, _resolved(schema, value), key in wanted, True)
                     for key, value in (entry.get("properties") or {}).items()
                     if not _forbidden(schema, value)
                     and _resolved(schema, value).get("readOnly") is not True]
            continue
        held.append(_field(schema, name, stated, name in required, False))
    taken = {}
    for field in held:
        for flag in filter(None, (field.flag, field.clears)):
            if flag in taken:
                raise ReqctlError(f"{kind}: {taken[flag]} and {field.name} would "
                                  f"both take {flag}; give one an x-flag")
            taken[flag] = field.name
    return held


def names(root, kind):
    return set(_merged(_schema(root, kind), kind)[0])


def defaults(root, kind):
    properties, _ = _merged(_schema(root, kind), kind)
    held = {name: copy.deepcopy(stated["default"])
            for name, stated in properties.items() if "default" in stated}
    if KIND in properties:
        held[KIND] = kind
    return held


def flags(root):
    held = {}
    for kind in corpus.SCHEMA_NAMES:
        for field in of(root, kind):
            stated = held.get(field.flag, field)
            if (stated.repeated, stated.convert) != (field.repeated, field.convert):
                raise ReqctlError(f"{field.flag} takes a different kind of value "
                                  f"for a {kind}; give one field an x-flag")
            choices = (tuple(dict.fromkeys(stated.choices + field.choices))
                       if stated.choices and field.choices else ())
            metavar = f"'{' | '.join(field.parts).upper()}'" if field.parts else None
            held[field.flag] = Flag(field.flag, choices, field.repeated, False,
                                    field.convert, metavar, field.name == ENTRIES)
    return list(held.values())


def clears(root):
    return list({field.clears: Flag(field.clears, (), False, True, None, None, False)
                 for kind in corpus.SCHEMA_NAMES for field in of(root, kind)
                 if field.clears}.values())


# @req+ REQ-14895892@JjrTwHoJqTRe aepkss
def _expanded(schema, nodes, kind):
    seen = set()

    def facets(node, read, sure):
        if (id(node), read, sure) in seen or not isinstance(node, dict):
            return
        seen.add((id(node), read, sure))
        if "$ref" in node:
            yield from facets(_resolved(schema, {"$ref": node["$ref"]}), read, sure)
        yield node, read, sure
        for key in ("allOf", "anyOf", "oneOf"):
            for member in node.get(key, ()):
                yield from facets(member, read and key == "allOf", sure and key == "allOf")
        if "if" in node:
            kinds = {one for one in corpus.SCHEMA_NAMES
                     if _selects(schema, _resolved(schema, node["if"]), one)}
            for branch, applies in (("then", not kinds or kind in kinds),
                                    ("else", kind not in kinds)):
                if applies:
                    yield from facets(node.get(branch), read, sure and bool(kinds))

    return [one for node, read, sure in nodes for one in facets(node, read, sure)]


def _children(schema, facets, name):
    found = []
    for node, read, sure in facets:
        named = node.get("properties") or {}
        if name in named:
            found.append((named[name], read, sure))
        found += [(value, read, sure) for pattern, value in
                  (node.get("patternProperties") or {}).items()
                  if isinstance(pattern, str) and re.search(pattern, name)]
    return [] if any(sure and _forbidden(schema, value) for value, _, sure in found) else found


def _lacking(shipped, copy, held, stated, at, kind, seen=frozenset()):
    pair = tuple(frozenset((id(node), read, sure) for node, read, sure in nodes)
                 for nodes in (held, stated))
    if pair in seen or not (held and stated):
        return
    seen |= {pair}
    carried = {marker for node, read, _ in stated if read for marker in _resolved(copy, node)}
    yield from (f"{marker} on {at}" for node, read, _ in held if read
                for marker in _resolved(shipped, node).keys() - carried
                if marker.startswith("x-") or marker in ("default", "readOnly"))
    held, stated = _expanded(shipped, held, kind), _expanded(copy, stated, kind)
    for name in {name for node, _, _ in held for name in node.get("properties") or {}}:
        yield from _lacking(shipped, copy, _children(shipped, held, name),
                            _children(copy, stated, name),
                            f"{at}.{name}" if at else name, kind, seen)
    for step in ("items", "additionalProperties"):
        yield from _lacking(shipped, copy, *([(node[step], read, sure) for node, read, sure in facets
                                              if isinstance(node.get(step), dict)]
                                             + [(value, read, False) for node, read, _ in facets
                                                if step == "additionalProperties"
                                                for value in
                                                (node.get("patternProperties") or {}).values()]
                                             for facets in (held, stated)), at, kind, seen)


def _lacking_plain(shipped, copy, held, stated, at, seen=frozenset()):
    pair = (id(held), id(stated))
    if pair in seen:
        return
    seen |= {pair}
    held, stated = _resolved(shipped, held), _resolved(copy, stated)
    yield from (f"{marker} on {at}" for marker in held.keys() - stated.keys()
                if marker.startswith("x-") or marker in ("default", "readOnly"))
    inner = stated.get("properties") or {}
    for name, value in (held.get("properties") or {}).items():
        if name in inner and not _forbidden(copy, inner[name]):
            yield from _lacking_plain(shipped, copy, value, inner[name], f"{at}.{name}", seen)
    for step in ("items", "additionalProperties"):
        if isinstance(held.get(step), dict) and isinstance(stated.get(step), dict):
            yield from _lacking_plain(shipped, copy, held[step], stated[step], at, seen)


def unmarked(shipped, copy, kinds):
    found = set()
    for kind in kinds:
        found.update(_lacking(shipped, copy, [(shipped, True, True)], [(copy, True, True)],
                              "", kind))
        held = _merged(shipped, kind)[0]
        stated = _merged(copy if isinstance(copy, dict) else {}, kind)[0]
        for name in held.keys() & stated.keys():
            found.update(_lacking_plain(shipped, copy, held[name], stated[name], name))
    return ", ".join(sorted(found))
# @req- aepkss
