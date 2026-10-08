import base64
import contextlib
import functools
import hashlib
import json
import os
import re
import secrets
import shutil
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for
from referencing import Registry
from referencing.jsonschema import DRAFT202012, specification_with

Loader = yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader
NEST_LIMIT = 64

CONFLICTED = re.compile(r"^<{7}", re.M)

PREFIXES = {"REQ-": "requirement", "GUARD-": "guard",
            "PARAM-": "parameter", "TERM-": "term", "DATA-": "data"}
FOLDERS = {"requirement": "reqs", "guard": "guards", "parameter": "params",
           "term": "terms", "data": "data"}
KINDS = "|".join(prefix.rstrip("-") for prefix in PREFIXES)
NAMED = ", ".join(prefix.rstrip("-") for prefix in PREFIXES)
KINDS_NAMED = ", ".join(FOLDERS)

NAME = r"[a-z][a-z0-9_]*"
UID = re.compile(rf"^({KINDS})-\d{{8}}$")
UID_IN_PROSE = re.compile(rf"\b(?:{KINDS})-\d{{8}}\b")
PARAM_REF = re.compile(rf"\$\{{({NAME})((?:\.[^}}\s]+)?)\}}")
PARAM_NEAR = re.compile(r"\$\{?(?:param|data)[-_]\d+(?:\.[\w.-]+)?\}?", re.IGNORECASE)
NAME_FORM = "${name}"
CONCEPT_TARGET = re.compile(rf"{NAME}(?:\.{NAME})?")
CONCEPT_LINK = re.compile(rf"\[([^\]\n]+)\]\(({CONCEPT_TARGET.pattern})\)")
TERM_NEAR = re.compile(r"\bterm[-_]\d+\b", re.IGNORECASE)
LINK_FORM = "[the words](handle)"
CONCEPT_NEAR = re.compile(r"\]\(((?:TERM|PARAM|DATA)-\d+[^)]*)\)")
TAG_STAMP = 12
TEST_PATH = re.compile(r"(^|/)tests?/|(^|/)test_[^/]+$|[._](test|spec)\.[A-Za-z]+$")

STATEMENT_STAMPED = ("text", "acceptance_criteria")
ITEM_STAMPED = ("text", "value_type", "unit", "default")
DATA_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
STATED_SKIP = ("aliases",)
POLICED_SKIP = ("aliases", "word", "name", "carried")
# @req> REQ-68407569@9WdKt66SbMuQ bzk766
POLICED_ITEM_SKIP = POLICED_SKIP + ("default", "unit")
CITATION_LIST = "citations"
# @req> REQ-88203622@QLXb8abUOMT3 otmh6w
CITABLE = ("requirement", "guard", "parameter", "data")
ITEM_SKIP = ("entries", "acceptance_criteria", "text",
             "assessed", "relations", "status", CITATION_LIST)
MEMBERS = "*"
ADDRESS = re.compile(rf"^((?:{KINDS})-\d{{8}}|{NAME})(?:\.(.+))?$")

# @req> REQ-10966072@RC1_0V_R-34U zikuq2
SCAN_SKIP = {
    ".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".elucidate", ".reqctl",
}


class ReqctlError(Exception):
    pass


class Item:
    def __init__(self, uid, path, data):
        self.uid = uid
        self.path = path
        self.data = data


class Store:
    def __init__(self, root):
        self.root = root
        self._items = None
        self._index = None


def find_root(start=None):
    here = Path(start or Path.cwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "requirements").is_dir() and (candidate / ".git").exists():
            return candidate
    # @req> REQ-61212158@EISsRx_ntdvz pdpnj6
    for candidate in [here, *here.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise ReqctlError("not inside a git repository (no .git here or above)")


def load(root=None):
    root = Path(root) if root else find_root()
    return Store(root), root


def _for_prefix(uid, table):
    for prefix, value in table.items():
        if uid.startswith(prefix):
            return value
    raise ReqctlError(f"{uid}: not a {NAMED} uid")


def kind_of(uid, data):
    return kind_for_uid(uid) or (data or {}).get("kind")


def folder_for(root, kind):
    if kind not in FOLDERS:
        raise ReqctlError(f"{kind}: not a {KINDS_NAMED} kind")
    return Path(root) / "requirements" / FOLDERS[kind]


def item_files(root):
    found = []
    for folder in FOLDERS.values():
        directory = Path(root) / "requirements" / folder
        found += sorted(
            path
            for pattern in ("*.yml", "*.yaml")
            for path in directory.glob(pattern)
            if not path.name.startswith(".")
        )
    seen = {}
    for path in found:
        first = seen.setdefault(path.stem, path)
        if first is not path:
            raise ReqctlError(
                f"{path.stem}: two files claim this uid: "
                f"{first.relative_to(root)} and {path.relative_to(root)}"
            )
    return found


def _repeated(node):
    if not isinstance(node, yaml.MappingNode):
        return []
    stated = [key.value for key, _ in node.value
              if isinstance(key, yaml.ScalarNode)]
    return sorted(set(key for key in stated if stated.count(key) > 1))


def loads(text, where):
    loader = Loader(text)
    try:
        node = loader.get_single_node()
        twice = _repeated(node)
        # @req> REQ-84465433@Ci_xHI8aFBMN pkvikc
        if twice:
            raise ReqctlError(
                f"{where} states {', '.join(twice)} more than once -- YAML "
                "keeps the last, so drop the one that does not govern"
            )
        # @req+ REQ-19913588@Pbi1CR5jtivz 3222m4
        try:
            document = loader.construct_document(node) if node is not None else None
        except (yaml.YAMLError, RecursionError):
            raise
        except Exception as error:
            raise ReqctlError(f"{where} holds a value YAML cannot build -- "
                              f"{type(error).__name__}: {error}") from error
        # @req- 3222m4
        # @req> REQ-39368456@fHW3SvGcMIr_ 2zx2qh
        for field, value in (document.items() if isinstance(document, dict) else ()):
            fault = _unreadable(value)
            if fault:
                raise ReqctlError(f"{where}: {field} {fault}")
        return document
    except yaml.YAMLError as error:
        raise ReqctlError(f"{where} is not YAML: {error}") from error
    except RecursionError as error:
        raise ReqctlError(f"{where} nests too deeply to read") from error
    finally:
        loader.dispose()


def _unreadable(value):
    height, open_ = {}, set()
    stack = [(value, False)]
    while stack:
        node, closing = stack.pop()
        if not isinstance(node, (dict, list, tuple)):
            continue
        children = list(node.values() if isinstance(node, dict) else node)
        if closing:
            open_.discard(id(node))
            height[id(node)] = 1 + max((height.get(id(child), 0) for child in children),
                                       default=0)
            if height[id(node)] > NEST_LIMIT:
                return (f"nests deeper than {NEST_LIMIT} levels, so it cannot be read "
                        "as text -- state it flatter")
        elif id(node) in open_:
            return ("forms a cycle, so it cannot be read as text -- state it "
                    "without an alias to itself")
        elif id(node) not in height:
            open_.add(id(node))
            stack.append((node, True))
            stack.extend((child, False) for child in children)
    return None


def read_text(path):
    try:
        return Path(path).read_text()
    except UnicodeDecodeError as error:
        raise ReqctlError(f"cannot read {path}: not valid UTF-8") from error
    except OSError as error:
        raise ReqctlError(f"cannot read {path}: {error.strerror}") from error
    except ValueError as error:
        raise ReqctlError(f"cannot read {path}: {error}") from error


def read(path):
    return loads(read_text(path), path)


def sides(text):
    ours, theirs, taking = [], [], "both"
    for line in text.splitlines(keepends=True):
        if line.startswith("<<<<<<<"):
            taking = "ours"
        elif line.startswith("|||||||"):
            taking = "base"
        elif line.startswith("======="):
            taking = "theirs"
        elif line.startswith(">>>>>>>"):
            taking = "both"
        else:
            if taking in ("both", "ours"):
                ours.append(line)
            if taking in ("both", "theirs"):
                theirs.append(line)
    return "".join(ours), "".join(theirs)


def same(value, prior):
    if type(value) is not type(prior):
        return False
    if isinstance(value, list):
        return len(value) == len(prior) and all(
            same(v, p) for v, p in zip(value, prior)
        )
    if isinstance(value, dict):
        return value.keys() == prior.keys() and all(
            same(v, prior[k]) for k, v in value.items()
        )
    return value == prior


def path_for(root, uid):
    for path in item_files(root):
        if path.stem == uid:
            return path
    raise ReqctlError(f"no such item: {uid}")


def items(store):
    if store._items is None:
        loaded = []
        for path in item_files(store.root):
            data = read(path)
            if not isinstance(data, dict):
                raise ReqctlError(f"{path.stem}: item file is not a mapping")
            loaded.append(Item(path.stem, path, data))
        store._items = loaded
    return store._items


def invalidate(store):
    store._items = None
    store._index = None


def find(store, uid):
    if store._index is None:
        index = {item.uid: item for item in items(store)}
        for item in items(store):
            name = name_of(item.uid, item.data)
            if name is not None:
                index.setdefault(name, item)
        store._index = index
    try:
        return store._index[uid]
    except KeyError:
        raise ReqctlError(f"no such item: {uid}") from None


def raw(item):
    return item.data


# @req> REQ-79557189@9se-A9aoBjZx np3ttn
def atomic_write(path, content):
    target = Path(path).resolve()
    temp = target.with_name(f"{target.name}.{secrets.token_hex(8)}.tmp")
    staged = False
    try:
        # @req> REQ-24406170@M08jCONzg-4u ig234p
        _hold(target)
        # @req> REQ-81667762@82D0B66GuW3u lkbxat
        make_folder(target.parent)
        with open(temp, "xb" if isinstance(content, bytes) else "x") as sink:
            staged = True
            sink.write(content)
            sink.flush()
            os.fsync(sink.fileno())
        if target.exists():
            shutil.copymode(target, temp)
        os.replace(temp, target)
        staged = False
    except OSError as error:
        raise ReqctlError(
            f"cannot write {path}: {error.strerror or error}"
        ) from error
    finally:
        if staged:
            with contextlib.suppress(OSError):
                temp.unlink()


# @req> REQ-65668011@6eXnj2-53DtA l5i6id
def write_all(changes):
    with all_or_nothing():
        for path, content in changes:
            atomic_write(path, content)


# @req+ REQ-24406170@M08jCONzg-4u u5qcba
_held = None
_made = None


@contextlib.contextmanager
def all_or_nothing():
    global _held, _made
    if _held is not None:
        yield
        return
    _held, _made = {}, []
    try:
        yield
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code in (None, 0):
            raise
        held, _held = _held, None
        kept = [str(path) for path, before in reversed(held.items())
                if not _put_back(path, before)]
        # @req> REQ-81667762@82D0B66GuW3u cdcyzh
        for folder in reversed(_made):
            with contextlib.suppress(OSError):
                folder.rmdir()
        # @req+ REQ-83236530@f_SrFVNH8QSC v2zljr
        kept += [f"{folder}{os.sep}" for folder in reversed(_made)
                 if _stands(folder)]
        if kept:
            left = f"not put back: {', '.join(kept)}"
            if isinstance(error, SystemExit):
                raise SystemExit(f"{error}; {left}") from error
            if isinstance(error, (ReqctlError, OSError, UnicodeError)):
                raise ReqctlError(f"{error}; {left}") from error
            error.add_note(left)
        # @req- v2zljr
        raise
    finally:
        _held = None


def atomically(command):
    with all_or_nothing():
        return command()


def _hold(path):
    if _held is not None and path not in _held:
        _held[path] = path.read_bytes() if path.exists() else None


def _put_back(path, before):
    try:
        if before is None:
            if path.exists():
                path.unlink()
        elif not path.is_file() or path.read_bytes() != before:
            atomic_write(path, before)
    except (OSError, ReqctlError):
        return False
    return True


def remove(path, missing_ok=False):
    held = Path(path).absolute()
    _hold(held)
    held.unlink(missing_ok=missing_ok)
# @req- u5qcba


# @req> REQ-81667762@82D0B66GuW3u 3rsgq3
def make_folder(path):
    folder = Path(path).absolute()
    if _held is not None:
        _made.extend(one for one in (*reversed(folder.parents), folder)
                     if not one.exists())
    folder.mkdir(parents=True, exist_ok=True)


# @req> REQ-83236530@f_SrFVNH8QSC 3j7lib
def _stands(folder):
    try:
        return folder.is_dir()
    except OSError:
        return True


def dump(data):
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=True,
                          allow_unicode=True)


def save(store, item):
    atomic_write(item.path, dump(item.data))
    invalidate(store)


def _lexical(value):
    return f"!{type(value).__name__}:{value}"


def digest(payload):
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         default=_lexical)
    hashed = hashlib.sha256(content.encode()).digest()
    return base64.urlsafe_b64encode(hashed).decode().rstrip("=")


def entries(data):
    held = data.get("entries")
    return held if isinstance(held, dict) else None


def split_address(address):
    found = ADDRESS.match(str(address))
    if not found:
        raise ReqctlError(f"{address}: not a UID or UID.entry address")
    return found.group(1), found.group(2)


def kind_for_uid(uid):
    try:
        return _for_prefix(uid, PREFIXES)
    except ReqctlError:
        return None


def name_of(uid, data):
    kind = kind_of(uid, data)
    if kind == "term":
        return next(iter(entries(data) or {}), None)
    if kind in ("parameter", "data"):
        name = data.get("name")
        return name if isinstance(name, str) and name else None
    return None


def carried_of(uid, data):
    held = data.get("carried")
    if held is None:
        return []
    if not isinstance(held, list) or not all(
            isinstance(one, str) for one in held):
        raise ReqctlError(
            f"{uid}: carried is not a list of names, so what this item has "
            "answered to cannot be read -- `reqctl validate` names the fault"
        )
    return held


def carriers(tree):
    held = {}
    for item in items(tree):
        for name in set(carried_of(item.uid, raw(item))):
            held.setdefault(name, []).append(item.uid)
    return held


def reachable(records):
    held = {uid: uid for uid in records}
    for uid, data in records.items():
        name = name_of(uid, data)
        if name is not None:
            held.setdefault(name, uid)
    return held


def addressable(records):
    return set(reachable(records))


def stamp_of(uid, data):
    # @req> REQ-54851939@Iw_Sa4bHHJhi 4jhey4
    if uid.startswith(("REQ-", "GUARD-")):
        return digest([uid, {k: data.get(k) for k in STATEMENT_STAMPED}])
    # @req+ REQ-56581795@IfY71qSXm5yz s7alzx
    if kind_of(uid, data) == "term":
        return _term_digest(uid, term_fields(data))
    return digest([uid, {k: data.get(k) for k in ITEM_STAMPED}])
    # @req- s7alzx


def _term_digest(uid, fields):
    return digest([uid, {"definition": fields.get("definition")}])


def flagged(data, flag):
    held = entries(data) or {}
    if not isinstance(flag, str) or flag in held:
        return None
    carried = [fields.get(flag) for fields in held.values()
               if isinstance(fields, dict) and flag in fields]
    if not carried:
        return None
    # @req> REQ-79222815@kx_jWO6UU-11 3wyszr
    return {key: fields for key, fields in held.items()
            if isinstance(fields, dict) and fields.get(flag) is True}


def entry_at(data, key):
    held = entries(data) or {}
    if key in held:
        fields = held[key]
        return fields if isinstance(fields, dict) else None
    if not isinstance(key, str):
        return None
    steps = key.split(".")
    while steps:
        name = steps.pop(0)
        if not isinstance(held, dict) or name not in held:
            return None
        fields = held[name]
        if not isinstance(fields, dict):
            return None
        if not steps:
            return fields
        field = steps.pop(0)
        if not isinstance(fields.get(field), dict):
            return None
        held = fields[field]
    return None


def entry_stamp_of(uid, data, key):
    # @req+ REQ-23898341@cjkAewZpMCHU nvrect
    fields = entry_at(data, key)
    if fields is None:
        return None
    if kind_of(uid, data) == "term":
        return _term_digest(uid, fields)
    return digest([uid, str(key), dict(fields)])
    # @req- nvrect


def address_stamp_of(uid, data, entry_key):
    if entry_key is None:
        return stamp_of(uid, data)
    if entry_key == MEMBERS:
        return digest([uid, MEMBERS, entries(data) or {}])
    # @req+ REQ-63712597@H2PNhNLn6GfY okjacr
    held = flagged(data, entry_key)
    if held is not None:
        return digest([uid, entry_key, held])
    # @req- okjacr
    return entry_stamp_of(uid, data, entry_key)


def stamp_at(item, entry_key=None):
    return address_stamp_of(item.uid, item.data, entry_key)


def stamp(item):
    return stamp_of(item.uid, item.data)


# @req> REQ-88203622@QLXb8abUOMT3 zi6xxa
def citable(item):
    return kind_of(item.uid, item.data) in CITABLE


# @req> REQ-18176935@u-uprH5qBxMT r63o2r
# @req> REQ-34330878@Zd73-2hLzA6M ymaadg
def cited_stamp(item, entry=None):
    held = stamp(item)
    if entry or kind_of(item.uid, item.data) in ("parameter", "data"):
        held = digest([held, stamp_at(item, entry or MEMBERS)])
    return tag_stamp(held)


def cited_entries(item):
    if kind_of(item.uid, item.data) != "data":
        return {}
    return entries(item.data) or {}


# @req> REQ-22755763@jWQQtKhJ8JoO ez4hkv
def cited_item(store, address):
    named, entry = split_address(address)
    item = find(store, named)
    if entry is not None and entry not in cited_entries(item):
        raise ReqctlError(f"{address}: {named} is not a data item holding "
                          f"{entry} -- only an entry of a data item is cited "
                          "by its name")
    return item, entry


def tag_stamp(held):
    return held[:TAG_STAMP]


def mapping(data, key):
    value = data.get(key)
    if not isinstance(value, dict):
        return {}
    return {name: held for name, held in value.items()
            if isinstance(name, str)}


def _stated(fields, skip):
    held = []
    if not isinstance(fields, dict):
        return held
    for key, value in fields.items():
        if key in skip:
            continue
        if isinstance(value, dict):
            held += _stated(value, skip)
        elif isinstance(value, list):
            held += [str(one) for one in value]
        else:
            held.append(str(value))
    return held


def prose(data, skip=STATED_SKIP, item=True):
    pieces = [str(data.get("text") or data.get("definition") or "")]
    if item:
        pieces += _stated(data, ITEM_SKIP + skip)
    for fields in (entries(data) or {}).values():
        pieces += _stated(fields, skip)
    criteria = data.get("acceptance_criteria")
    for criterion in criteria if isinstance(criteria, list) else []:
        if isinstance(criterion, dict):
            pieces += [str(value) for value in criterion.values()]
        else:
            pieces.append(str(criterion))
    return "\n".join(pieces)


def prosed(data, paths, resolve, at=(), under=False):
    under = under or at in paths
    if isinstance(data, dict):
        return {key: prosed(value, paths, resolve, at + (str(key),), under)
                for key, value in data.items()}
    if isinstance(data, list):
        return [prosed(value, paths, resolve, at + (str(index),), under)
                for index, value in enumerate(data)]
    return resolve(data) if under and isinstance(data, str) else data


def references(data):
    return sorted({uid + rest for uid, rest in PARAM_REF.findall(prose(data))})


def concept_references(data):
    return sorted({address for _, address in CONCEPT_LINK.findall(prose(data))})


def unlinked_prose(data):
    # @req> REQ-96763217@Dg9sKJOE-5NX vintgg
    if data.get("kind") == "data":
        data = {**data, "entries": {
            key: {name: value for name, value in fields.items()
                  if name != "unit" or isinstance(value, dict)}
            if isinstance(fields, dict) else fields
            for key, fields in (entries(data) or {}).items()}}
    # @req> REQ-83702299@IgLtX0BfZTks et7k4t
    return PARAM_REF.sub(
        " ", CONCEPT_LINK.sub(" ", "\n".join(
            [prose(data, POLICED_SKIP, item=False)]
            + _stated(data, ITEM_SKIP + POLICED_ITEM_SKIP))))


def dependencies(data):
    return sorted(
        set(mapping(data, "relations"))
        | set(references(data))
        | set(concept_references(data))
    )


def expand_address(lookup, address):
    uid, rest = split_address(address)
    wanted = {uid}
    target = lookup(uid)
    held = entries(target) if target is not None else None
    if held is None or kind_of(uid, target) == "term":
        return wanted
    if rest is None:
        wanted.add(f"{uid}.{MEMBERS}")
    elif rest == "default":
        member = target.get("default")
        if member is not None:
            wanted.add(f"{uid}.{member}")
    else:
        wanted.add(f"{uid}.{rest.split('.', 1)[0]}")
    return wanted


def pin_addresses(lookup, data):
    wanted = set()
    for address in dependencies(data):
        wanted |= expand_address(lookup, address)
    return sorted(wanted)


def data_lookup(store):
    def lookup(uid):
        try:
            return find(store, uid).data
        except ReqctlError:
            return None
    return lookup


def is_suspect(store, item, address):
    pinned = mapping(item.data, "assessed").get(address)
    if not isinstance(pinned, str):
        return True
    uid, rest = split_address(address)
    return pinned != stamp_at(find(store, uid), rest)


def term_word(data):
    stated = term_fields(data).get("word")
    return stated.strip() if isinstance(stated, str) and stated.strip() else None


def handle_for(word):
    return re.sub(r"[^a-z0-9]+", "_", str(word).lower()).strip("_")


def term_fields(data):
    sole = next(iter((entries(data) or {}).values()), {})
    return sole if isinstance(sole, dict) else {}


def unclaimed(data):
    held = term_fields(data).get("unclaimed")
    return ({str(phrase): str(reason) for phrase, reason in held.items()}
            if isinstance(held, dict) else {})


def concept_at(uid, data, rest):
    if data is None:
        return None
    if rest is not None:
        held = entry_at(data, rest)
        return None if held is None else (
            held.get("name"), str(held.get("definition") or "").strip())
    if kind_of(uid, data) == "term":
        return (term_word(data),
                str(term_fields(data).get("definition") or "").strip())
    return data.get("name"), str(data.get("text") or "").strip()


def schema_path(root, name):
    return Path(root) / "requirements" / "schemas" / f"{name}.schema.yaml"


@functools.lru_cache(maxsize=None)
def _parsed_schema(path, stamped):
    # @req+ REQ-19913588@Pbi1CR5jtivz rnou7b
    try:
        declared = yaml.load(path.read_text(), Loader=Loader)
    except UnicodeDecodeError as error:
        raise ReqctlError(f"unreadable schema {path}: not valid UTF-8") from error
    except (OSError, yaml.YAMLError) as error:
        raise ReqctlError(f"unreadable schema {path}: {error}") from error
    except Exception as error:
        raise ReqctlError(f"unreadable schema {path}: a value YAML cannot build -- "
                          f"{type(error).__name__}: {error}") from error
    # @req- rnou7b
    # @req+ REQ-19913588@Pbi1CR5jtivz mszvfu
    try:
        Draft202012Validator.check_schema(declared)
        _refuse_unfollowable(path, DRAFT202012.create_resource(declared))
    except SchemaError as error:
        where = ".".join(str(p) for p in error.absolute_path) or "(schema)"
        raise ReqctlError(f"{path.name}: {where}: {error.message}") from error
    except RecursionError as error:
        raise ReqctlError(f"{path.name}: nests too deeply to check") from error
    # @req- mszvfu
    return declared


# @req> REQ-19913588@Pbi1CR5jtivz 4sbgsj
def _refuse_unfollowable(path, resource):
    try:
        walked = list(_walked(resource, ""))
        if any(specification_with(schema.get("$schema", ""), default=DRAFT202012)
               is not DRAFT202012
               or validator_for(schema, Draft202012Validator) is not Draft202012Validator
               for _, schema in walked[1:]):
            return
    except ValueError as error:
        raise ReqctlError(f"{path.name}: an $id or $schema is not an address -- "
                          f"{error}") from error
    root = resource.id() or ""
    registry = Registry().with_resource(root, resource)
    with contextlib.suppress(ValueError):
        registry = registry.crawl()
        if registry[root] is not resource:
            registry = registry.with_resource(root, resource)
    for base, keyword, ref in sorted({(base, keyword, schema[keyword])
                                      for base, schema in walked
                                      for keyword in ("$ref", "$dynamicRef")
                                      if keyword in schema}):
        try:
            address = base if ref.startswith("#") else urldefrag(urljoin(base, ref)).url
            if address not in registry and urlsplit(address).scheme:
                continue
            target = registry.resolver(base).lookup(ref).contents
        except Exception as error:
            raise ReqctlError(f"{path.name}: {keyword} {ref!r} cannot be followed") from error
        if not isinstance(target, (dict, bool)):
            raise ReqctlError(f"{path.name}: {keyword} {ref!r} names a value, not a schema")


def _walked(resource, base):
    base = urljoin(base, resource.id() or "")
    if isinstance(resource.contents, dict):
        yield base, resource.contents
    for sub in DRAFT202012.subresources_of(resource.contents):
        yield from _walked(DRAFT202012.create_resource(sub), base)


PACKAGED_SCHEMAS = Path(__file__).resolve().parent / "schemas"


def packaged_schema_path(name):
    return PACKAGED_SCHEMAS / f"{name}{SCHEMA_SUFFIX}"


def schema(root, name):
    # @req+ REQ-13148397@XXob_8TNNhHN 4fsesd
    stated = schema_path(root, name)
    path = stated
    # @req- 4fsesd
    # @req> REQ-44451070@VVBRK8IWFyvq idgq2r
    if not path.is_file():
        path = packaged_schema_path(name)
        if not path.is_file():
            raise ReqctlError(f"missing schema: {stated}")
    stat = path.stat()
    stamped = (stat.st_mtime_ns, stat.st_size)
    # @req> REQ-14895892@JjrTwHoJqTRe yz3x2d
    if path == stated and name in SCHEMA_NAMES.values():
        lacking = _unmarked(path, stamped, name)
        if lacking:
            raise RefusedCopy(f"{stated}: the shipped schema carries {lacking}, "
                              "which this copy lacks")
    return _parsed_schema(path, stamped)


class RefusedCopy(ReqctlError):
    pass


# @req+ REQ-14895892@JjrTwHoJqTRe a252bv
@functools.lru_cache(maxsize=None)
def _unmarked(path, stamped, name):
    from . import fields
    shipped = packaged_schema_path(name)
    stat = shipped.stat()
    held = _parsed_schema(shipped, (stat.st_mtime_ns, stat.st_size))
    stated = _parsed_schema(path, stamped)
    try:
        return fields.unmarked(
            held, stated, [kind for kind, named in SCHEMA_NAMES.items() if named == name])
    except ReqctlError as fault:
        raise RefusedCopy(f"{path}: {fault}") from fault
# @req- a252bv


SCHEMA_NAMES = {"requirement": "requirement", "guard": "guard",
                "parameter": "dictionary", "term": "dictionary",
                "data": "dictionary"}
SCHEMA_SUFFIX = ".schema.yaml"
RESERVED_SCHEMAS = frozenset(SCHEMA_NAMES.values()) | {"baseline"}


def schema_names(root):
    folder = Path(root) / "requirements" / "schemas"
    return sorted(path.name[: -len(SCHEMA_SUFFIX)]
                  for path in folder.glob(f"*{SCHEMA_SUFFIX}"))


def schema_name_for(kind):
    if kind not in SCHEMA_NAMES:
        raise ReqctlError(f"{kind}: not a {KINDS_NAMED} kind")
    return SCHEMA_NAMES[kind]


def schema_name_at(root, kind, name=None):
    if (name is not None and name not in RESERVED_SCHEMAS
            and schema_path(root, name).is_file()):
        return name
    return schema_name_for(kind)


def schema_for(root, kind, name=None):
    return schema(root, schema_name_at(root, kind, name))


BINDING = "x-binding"


def named_schemas(root):
    return [name for name in schema_names(root)
            if name not in RESERVED_SCHEMAS]


def binding_dimensions(root):
    # @req> REQ-68873210@hUPNlhiYKqih up7le5
    return [name for name in named_schemas(root)
            if schema(root, name).get(BINDING) is True]


def is_test(relative_path):
    return bool(TEST_PATH.search(relative_path))
