import copy
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
        if not isinstance(target, dict):
            raise ReqctlError(f"{named}: {ref} names nothing within the schema")
        seen.add(ref)
        node = {**target, **{key: value for key, value in node.items()
                             if key != "$ref"}}
    return node


def _forbidden(stated):
    return stated is False or (isinstance(stated, dict)
                               and stated.get("not") in ({}, True))


def _selects(schema, test, kind):
    if not isinstance(test, dict) or set(test) - {"properties", "required"}:
        return False
    if set(test.get("required", ())) - {KIND}:
        return False
    tested = test.get("properties")
    if not isinstance(tested, dict) or set(tested) != {KIND}:
        return False
    said = _resolved(schema, tested[KIND])
    return said.get("const") == kind or kind in said.get("enum", ())


def _merged(schema, kind):
    properties, required = {}, set()
    branches = [_resolved(schema, item) for item in schema.get("allOf", ())]
    chosen = [_resolved(schema, branch.get("then")) for branch in branches
              if _selects(schema, _resolved(schema, branch.get("if")), kind)]
    for block in [schema] + chosen:
        required.update(block.get("required", ()))
        for name, stated in (block.get("properties") or {}).items():
            if _forbidden(stated):
                properties.pop(name, None)
            else:
                properties[name] = {**properties.get(name, {}),
                                    **_resolved(schema, stated)}
    return properties, required


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
                     if not _forbidden(value)
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
            stated = held.get(field.flag)
            choices = field.choices
            if stated is not None:
                if (stated.repeated, stated.convert) != (field.repeated, field.convert):
                    raise ReqctlError(f"{field.flag} takes a different kind of value "
                                      f"for a {kind}; give one field an x-flag")
                choices = (tuple(dict.fromkeys(stated.choices + choices))
                           if stated.choices and choices else ())
            metavar = f"'{' | '.join(field.parts).upper()}'" if field.parts else None
            held[field.flag] = Flag(field.flag, choices, field.repeated, False,
                                    field.convert, metavar, field.name == ENTRIES)
    return list(held.values())


def clears(root):
    return list({field.clears: Flag(field.clears, (), False, True, None, None, False)
                 for kind in corpus.SCHEMA_NAMES for field in of(root, kind)
                 if field.clears}.values())
