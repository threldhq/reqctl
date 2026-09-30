import copy
from dataclasses import dataclass

from jsonschema import Draft202012Validator

from . import corpus
from .corpus import ReqctlError

KIND = "kind"
ENTRIES = "entries"


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
    string: bool
    strings: bool
    prose: bool

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
        return None


def _schema(root, kind):
    name = corpus.schema_name_for(kind)
    return corpus.schema(root, name) if root else corpus.packaged_schema(name)


def _pointed(schema, ref):
    if not ref.startswith("#/"):
        return None
    target = schema
    for step in ref[2:].split("/"):
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


def _merged(schema, kind):
    properties = {name: _resolved(schema, stated)
                  for name, stated in schema.get("properties", {}).items()
                  if stated is not False}
    required = set(schema.get("required", ()))
    for branch in schema.get("allOf", ()):
        test = branch.get("if", {}) if isinstance(branch, dict) else {}
        if not isinstance(test, dict) or KIND not in test.get("properties", {}):
            continue
        if not Draft202012Validator(test).is_valid({KIND: kind}):
            continue
        then = branch.get("then", {})
        required.update(then.get("required", ()))
        for name, stated in then.get("properties", {}).items():
            if stated is False:
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
    said = str(stated.get("x-flag", name))
    flag = _flag(said)
    shape = stated.get("type")
    repeated = shape in ("array", "object")
    items = _resolved(schema, stated.get("items", {})) if shape == "array" else {}
    clears, empty = None, None
    if not required:
        clears = _flag("no_" + said)
    elif repeated and not stated.get("minItems") and not stated.get("minProperties"):
        clears, empty = _flag("no_" + said), [] if shape == "array" else {}
    return Field(name=name, flag=flag, choices=tuple(stated.get("enum", ())),
                 repeated=repeated,
                 required=required and "default" not in stated,
                 clears=clears, empty=empty,
                 address=stated.get("x-address") is True, entry=entry,
                 string=shape == "string" and "enum" not in stated,
                 strings=items.get("type") == "string",
                 prose=_prose(stated))


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
                     for key, value in entry.get("properties", {}).items()]
            continue
        held.append(_field(schema, name, stated, name in required, False))
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
                choices = (tuple(dict.fromkeys(stated.choices + choices))
                           if stated.choices and choices else ())
            held[field.flag] = Flag(field.flag, choices, field.repeated, False)
    return list(held.values())


def clears(root):
    held = {}
    for kind in corpus.SCHEMA_NAMES:
        for field in of(root, kind):
            if field.clears:
                held.setdefault(field.clears, Flag(field.clears, (), False, True))
    return list(held.values())
