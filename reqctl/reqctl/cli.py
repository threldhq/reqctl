import argparse
import json
import os
import sys
import threading
import webbrowser

from . import baseline as _baseline
from . import cite
from . import corpus
from . import fields as _fields
from . import graph
from . import portal as _portal
from . import resolve as _resolve
from . import write as _write
from . import validate as _validate
from .corpus import ReqctlError

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

BETWEEN_ITEMS = "\n\n" + "-" * 60 + "\n\n"


def _emit(args, data, text):
    print(json.dumps(data, indent=2) if args.json else text)


def _refuse_invalid(root, said):
    problems = _validate.run(root)
    if problems:
        raise ReqctlError("the corpus does not validate; fix these, "
                          f"then {said}:\n" + "\n".join(problems))


def cmd_new(args):
    store, _ = corpus.load()
    item = _write.create(store, args.kind, vars(args))
    _emit(args, {"uid": item.uid, "path": str(item.path)}, item.uid)
    return EXIT_OK


def cmd_lint(args):
    store, _ = corpus.load()
    # @req> REQ-85308584@uUWJjK4FALNI sri72v
    uid, _, _, problems = _write.prepare(store, args.kind, vars(args),
                                         placeholder="draft")
    faults = [problem.removeprefix(f"{uid}: ") for problem in problems]
    if args.json:
        _emit(args, {"faults": faults}, "")
    elif faults:
        print("\n".join(faults), file=sys.stderr)
    else:
        print("no faults")
    return EXIT_INVALID if faults else EXIT_OK


def _describe(tree, item):
    data = corpus.raw(item)
    uid = str(item.uid)
    _refuse_broken(uid, data)
    out = {
        "uid": uid,
        "kind": corpus.kind_of(uid, data),
        "status": data.get("status"),
        "stamp": corpus.stamp(item),
        "text": str(data.get("text") or "").strip(),
    }
    if corpus.kind_of(uid, data) in ("requirement", "guard"):
        out.update(
            references=corpus.references(data),
            concepts=corpus.concept_references(data),
            acceptance_criteria=data.get("acceptance_criteria") or [],
        )
        if corpus.kind_of(uid, data) == "requirement":
            out.update(
                type=data.get("type"),
                verification=data.get("verification"),
                priority=data.get("priority"),
            )
    elif corpus.kind_of(uid, data) == "term":
        out.pop("text")
        fields = corpus.term_fields(data)
        out.update(
            term=corpus.term_word(data),
            aliases=fields.get("aliases") or [],
            definition=str(fields.get("definition") or "").strip(),
        )
        # @req> REQ-22686458@dmNVoBq6qCcv q5tknl
        out["unclaimed"] = corpus.unclaimed(data)
    elif corpus.kind_of(uid, data) == "data":
        out.update(name=data.get("name"), entries=corpus.entries(data) or {})
    else:
        out.update(
            name=data.get("name"),
            value=_dict_value(data),
            unit=data.get("unit"),
            value_type=data.get("value_type"),
        )
        described = {key: fields for key, fields
                     in (corpus.entries(data) or {}).items() if fields}
        if described:
            out["entries"] = described
    if data.get("default") is not None:
        out["default"] = data.get("default")
    if data.get("rationale"):
        out["rationale"] = str(data["rationale"]).strip()
    return out


def _refuse_broken(uid, data):
    if (corpus.kind_of(uid, data) not in ("requirement", "guard")
            and corpus.entries(data) is None):
        raise ReqctlError(
            f"{uid}: has no entries -- `reqctl validate` names the fault"
        )


def _dict_value(data):
    return sorted(corpus.entries(data) or {})


def _criterion(mapping):
    if not isinstance(mapping, dict):
        return str(mapping)
    return (f"given {mapping.get('given')} / when {mapping.get('when')} "
            f"/ then {mapping.get('then')}")


def _shown(data):
    held = corpus.entries(data) or {}
    suffix = f" {data.get('unit')}" if data.get("unit") else ""
    default = data.get("default")
    return ", ".join(f"{key}{suffix}" + (" (default)" if key == default else "")
                     for key in held)


def _value(value, unit):
    suffix = f" {unit}" if unit else ""
    return ", ".join(f"{member}{suffix}" for member in value)


def _plain(value):
    return _value(value, None) if isinstance(value, list) else str(value)


def _entry_fields(fields):
    # @req> REQ-73719888@XIgPxcvuvzqA 3wgrmj
    return ", ".join(f"{name}: {_plain(value)}"
                     for name, value in (fields or {}).items())


def _nests(fields):
    return any(isinstance(value, dict) for value in (fields or {}).values())


def _entry_lines(key, fields, depth=0):
    if depth == 0 and not _nests(fields):
        shown = _entry_fields(fields)
        return [f"- {key}" + (f" — {shown}" if shown else "")]
    # @req+ REQ-18993149@VIDeNo4AUi4V s5nw3l
    held = [f"{'  ' * depth}- {key}"]
    for name, value in (fields or {}).items():
        if isinstance(value, dict):
            held += _entry_lines(name, value, depth + 1)
        else:
            # @req> REQ-73719888@XIgPxcvuvzqA g5txax
            held.append(f"{'  ' * (depth + 1)}- {name}: {_plain(value)}")
    return held
    # @req- s5nw3l


def _render(fields, order=None):
    keys = order or list(fields)
    width = max((len(k) for k in keys if fields.get(k) is not None), default=0)
    lines = []
    for key in keys:
        value = fields.get(key)
        if value in (None, [], "", {}):
            continue
        if isinstance(value, dict):
            value = "; ".join(
                f"{name} -- {held if isinstance(held, str) else _entry_fields(held)}"
                if held else str(name)
                for name, held in value.items()
            )
        if isinstance(value, list):
            value = ", ".join(_criterion(v) if isinstance(v, dict) else str(v)
                              for v in value)
        lines.append(f"{key.replace('_', ' '):<{width}}  {value}")
    return "\n".join(lines)


def cmd_revise(args):
    tree, _ = corpus.load()
    changed = _write.revise(tree, args.uid, vars(args))
    if not changed:
        _emit(args, {"uid": args.uid, "changed": {}, "already_held": True},
              f"{args.uid}: already holds everything passed; nothing written")
        return EXIT_OK
    note = ""
    if changed.get("status") == "approved":
        note = "\n  proposed as approved -- it is approved when this merges to main"
    spread = changed.get("reworded")
    if spread:
        note += (f"\n  reworded {spread['links']} link(s) across "
                 f"{len(spread['items'])} item(s)")
        if spread["repinned"]:
            note += (f"\n  re-pinned {spread['repinned']} item(s) whose target "
                     "only changed a word")
        for held in spread["articles"]:
            note += f"\n    article: {held}"
        if spread["left"]:
            note += ("\n  still showing another word, yours to reword or leave: "
                     + ", ".join(spread["left"]))
    _emit(
        args,
        {"uid": args.uid, "changed": changed},
        f"{args.uid}: " + ", ".join(sorted(changed)) + note,
    )
    return EXIT_OK


def cmd_relate(args):
    tree, _ = corpus.load()
    repinned = _write.relate(tree, args.source, args.relation, args.target)
    note = (
        ": re-pinned to the target's current state"
        if repinned
        else "\n  unassessed -- reread both, then run the same relate to pin it"
    )
    _emit(
        args,
        {"source": args.source, "relation": args.relation, "target": args.target,
         "repinned": repinned},
        f"{args.source} {args.relation} {args.target}" + note,
    )
    return EXIT_OK


def cmd_unrelate(args):
    tree, _ = corpus.load()
    removed = _write.unrelate(tree, args.source, args.target)
    _emit(args, {"source": args.source, "target": args.target,
                 "removed": removed},
          f"{args.source} no longer links to {args.target}"
          + ("" if removed else " (it already did not)"))
    return EXIT_OK


def cmd_delete(args):
    tree, root = corpus.load()
    # @req> REQ-43148967@9Lf3h_L4BXne nghnwd
    _refuse_invalid(root, "remove")
    where = _write.delete(tree, args.uid)
    _emit(args, {"uid": args.uid, "path": str(where)},
          f"{args.uid} removed. No baseline stated it, so nothing it said is "
          "taken back.")
    return EXIT_OK


def cmd_rename(args):
    tree, _ = corpus.load()
    moved = _write.rename(tree, args.uid, args.name)
    _emit(args, {"uid": args.uid, "name": args.name, "moved": moved},
          f"{args.uid} answers to {args.name}. "
          f"{len(moved)} item(s) now address it by that name.")
    return EXIT_OK


def cmd_refile(args):
    tree, _ = corpus.load()
    repinned = _write.refile(tree, args.uid)
    _emit(args, {"uid": args.uid, "kind": "data", "repinned": repinned},
          f"{args.uid} is filed as a data item. "
          f"{len(repinned)} item(s) had a pin to it refreshed.")
    return EXIT_OK


def _resolved(text, store):
    # @req+ REQ-70783238@WJenY0g8kyTE lxx4c3
    # @req> REQ-68562495@N9XFtOP49a-e i2bing
    def parameter(match):
        try:
            item = corpus.find(store, match.group(1))
        except ReqctlError:
            return match.group(0)
        fields = item.data
        held = corpus.entries(fields)
        if held is None:
            return match.group(0)
        unit = fields.get("unit")
        rest = match.group(2)[1:] if match.group(2) else None
        if rest is None:
            shown = _shown(fields)
        elif rest == "default":
            member = fields.get("default")
            if member is None:
                return match.group(0)
            shown = f"{member} {unit}" if unit else str(member)
        else:
            entry, _, field = rest.partition(".")
            if entry not in held:
                return match.group(0)
            if field:
                value = (held[entry] or {}).get(field)
                if isinstance(value, list):
                    value = _value(value, None) or None
                if value is None:
                    return match.group(0)
                shown = field if isinstance(value, dict) else str(value)
            else:
                shown = f"{entry} {unit}" if unit else entry
        return f"[**{shown}**](#{item.uid})"
    # @req- lxx4c3

    # @req> REQ-73719888@XIgPxcvuvzqA 5ubj6l
    def term(match):
        uid, rest = corpus.split_address(match.group(2))
        try:
            found = corpus.find(store, uid)
        except ReqctlError:
            return match.group(1)
        if rest is not None and rest not in (corpus.entries(found.data) or {}):
            return match.group(1)
        return f"[{match.group(1)}](#{found.uid})"

    text = corpus.PARAM_REF.sub(parameter, " ".join(str(text or "").split()))
    return corpus.CONCEPT_LINK.sub(term, text)


def cmd_export(args):
    tree, root = corpus.load()
    wanted = None if args.all else "approved"
    if args.json:
        held = {str(item.uid): dict(corpus.raw(item))
                for item in corpus.items(tree)}
        print(json.dumps({uid: data for uid, data in sorted(held.items())
                          if not wanted or data.get("status") == wanted},
                         indent=2, default=str))
        return EXIT_OK

    lines = ["# requirements", ""]
    if wanted:
        lines += ["Approved requirements only. Use these when judging whether a new",
                  "idea is already covered, contradicts something, or belongs beside", "one of them.", ""]
    used_by = {}
    for item in corpus.items(tree):
        for address in corpus.concept_references(corpus.raw(item)):
            target, _ = corpus.split_address(address)
            try:
                target = corpus.find(tree, target).uid
            except ReqctlError:
                pass
            used_by.setdefault(target, []).append(str(item.uid))

    count = 0
    for item in corpus.items(tree):
        stored = corpus.raw(item)
        if wanted and stored.get("status") != wanted:
            continue
        count += 1
        uid = str(item.uid)
        _refuse_broken(uid, stored)
        # @req+ REQ-59874866@yPeFb-1_Yaja 6drjr2
        try:
            declared = set(_validate.prose_paths(root, uid, stored))
        except ReqctlError as unreadable:
            raise ReqctlError(f"{uid}: {unreadable}") from unreadable
        data = corpus.prosed(stored, declared,
                             lambda text: _resolved(text, tree))
        # @req- 6drjr2
        lines.append(f'<a id="{uid}"></a>')
        lines.append(f"## {uid}")
        if corpus.kind_of(uid, data) == "term":
            fields = corpus.term_fields(data)
            lines.append(f"**{corpus.term_word(data)}** — "
                         f"{' '.join(str(fields.get('definition') or '').split())}")
            aliases = fields.get("aliases") or []
            if aliases:
                lines.append(f"- also: {', '.join(str(a) for a in aliases)}")
            lines.append(f"- status: {data.get('status')}")
            users = sorted(used_by.get(uid, ()))
            if users:
                lines.append("- used by: "
                             + ", ".join(f"[{u}](#{u})" for u in users))
            lines.append("")
            continue
        if corpus.kind_of(uid, data) in ("requirement", "guard"):
            lines.append(str(data.get("text") or ""))
            lines.append("")
            lines.append(f"- status: {data.get('status')}")
            if corpus.kind_of(uid, data) == "requirement":
                lines.append(
                    f"- type: {data.get('type')} · verification: "
                    f"{data.get('verification')} · priority: {data.get('priority')}")
            for target, relation in sorted(corpus.mapping(data, "relations").items()):
                lines.append(f"- {relation} {target}")
            for criterion in data.get("acceptance_criteria") or []:
                lines.append(f"- {_criterion(criterion)}")
        elif corpus.kind_of(uid, data) == "data":
            lines.append(f"`{data.get('name')}`")
            if data.get("text"):
                lines.append(str(data.get("text")))
            for key, fields in (corpus.entries(data) or {}).items():
                lines += _entry_lines(key, fields)
            lines.append(f"- status: {data.get('status')}")
        else:
            lines.append(f"{str(data.get('text') or '')} "
                         f"**{_shown(data)}** "
                         f"(`{data.get('name')}`)")
            for key, fields in (corpus.entries(data) or {}).items():
                if fields:
                    lines += _entry_lines(key, fields)
            lines.append(f"- status: {data.get('status')}")
        if data.get("rationale"):
            lines.append(f"- rationale: {data['rationale']}")
        lines.append("")

    if not count:
        lines.append("_Nothing approved yet._")
    print("\n".join(lines))
    return EXIT_OK


def _behind(row, data):
    if row is None:
        return ""
    if row["pinned"]:
        return f"   SUSPECT -- pinned @{row['pinned']}, now @{row['held']}"
    return "   SUSPECT -- no stamp; cite it again with reqctl tag"


def _context(store, item, dependents, tags):
    uid = item.uid
    kinds = corpus.mapping(item.data, "relations")
    pins = corpus.mapping(item.data, "assessed")

    outgoing = []
    for target in sorted(kinds):
        entry = {
            "target": target,
            "relation": kinds.get(target),
            "assessed_against": pins.get(target),
        }
        try:
            corpus.find(store, target)
        except ReqctlError:
            entry.update(suspect=True, missing=True)
        else:
            entry.update(suspect=corpus.is_suspect(store, item, target),
                         missing=False)
        outgoing.append(entry)

    incoming = [
        {
            "source": other.uid,
            "relation": corpus.mapping(other.data, "relations").get(uid)
            or "references",
            "suspect": corpus.is_suspect(store, other, uid),
        }
        for other in dependents.get(uid, ()) if other.uid != uid
    ]

    lookup = corpus.data_lookup(store)
    parameters = []
    for address in corpus.references(item.data):
        target, rest = corpus.split_address(address)
        entry = {"uid": address, "assessed_against": pins.get(address)}
        try:
            fields = corpus.find(store, target).data
        except ReqctlError:
            entry.update(name=None, value=None, unit=None, status=None,
                         missing=True, suspect=True)
        else:
            held = corpus.flagged(fields, rest)
            entry.update(name=fields.get("name"),
                         value=sorted(held) if held is not None
                         else _dict_value(fields),
                         unit=fields.get("unit"), status=fields.get("status"),
                         missing=False,
                         suspect=any(corpus.is_suspect(store, item, pin)
                                     for pin in corpus.expand_address(
                                         lookup, address)))
        parameters.append(entry)

    concepts = []
    for address in corpus.concept_references(item.data):
        entry = {"uid": address, "assessed_against": pins.get(address)}
        target, rest = corpus.split_address(address)
        try:
            fields = corpus.find(store, target).data
        except ReqctlError:
            fields = None
        held = corpus.concept_at(target, fields, rest)
        if held is None:
            entry.update(word=None, definition=None, status=None, missing=True,
                         suspect=True)
        else:
            entry.update(word=held[0], definition=held[1],
                         status=fields.get("status"), missing=False,
                         suspect=corpus.is_suspect(store, item, address))
        concepts.append(entry)

    # @req> REQ-19896380@2sOnckMwnWfx 7iy6c4
    cited = [(path, pinned) for path, pinned in tags.get(uid, [])
             if not corpus.is_test(path)]
    references = list(dict.fromkeys(path for path, _ in cited))
    described = _describe(store, item)
    behind = {
        path: {"path": path, "pinned": pinned or None,
               "held": corpus.tag_stamp(described["stamp"])}
        for path, pinned in cited
        if uid.startswith(("REQ-", "GUARD-"))
        and pinned != corpus.tag_stamp(described["stamp"])
    }
    data = {
        **described,
        "outgoing": outgoing,
        "incoming": incoming,
        "parameters": parameters,
        "concepts": concepts,
        "implementation": references,
        "stale": list(behind.values()),
        "suspect_links": sum(
            1 for r in outgoing + parameters + concepts if r["suspect"]
        ),
    }
    if (uid.startswith("TERM-") and item.data.get("status") != "approved"
            and corpus.term_word(item.data)):
        data["unlinked_elsewhere"] = _validate.unlinked_elsewhere(
            uid, item.data,
            {other.uid: other.data for other in corpus.items(store)},
            store.root,
        )

    blocks = [_render(described)]
    linked = (
        ("parameters", "parameter", parameters,
         lambda r: f"{r['name']} = {_value(r['value'], r['unit'])}"),
        ("concepts", "concept", concepts,
         lambda r: f"{r['word']} -- {r['definition']}"),
    )
    for label, noun, rows, summary in linked:
        if rows:
            blocks.append(
                f"\n{label}\n"
                + "\n".join(
                    f"  {r['uid']}  MISSING -- no such {noun}" if r["missing"]
                    else f"  {r['uid']}  {summary(r)}"
                    + (f"   {str(r['status']).upper()} -- not approved"
                       if r["status"] != "approved" else "")
                    + ("   SUSPECT -- reread, then revise "
                       f"{uid} --ack {r['uid']}" if r["suspect"] else "")
                    for r in rows
                )
            )
    if outgoing:
        blocks.append(
            "\ndepends on\n"
            + "\n".join(
                f"  {r['relation']} {r['target']}"
                + ("   MISSING -- no such item" if r["missing"]
                   else "   SUSPECT -- reassess before implementing" if r["suspect"]
                   else "")
                for r in outgoing
            )
        )
    if incoming:
        blocks.append(
            "\ndepended on by\n"
            + "\n".join(
                f"  {r['source']} {r['relation']}"
                f"{'   SUSPECT' if r['suspect'] else ''}"
                for r in incoming
            )
        )
    carrying = data.get("unlinked_elsewhere")
    if carrying is not None:
        blocks.append(
            "\napproving it\n"
            + (f"  {len(carrying)} item(s) then fail until each links this term\n"
               + "\n".join(f"  {other}" for other in carrying)
               if carrying else
               "  nothing else carries its words unlinked")
        )
    blocks.append(
        "\nimplementation\n"
        + ("\n".join(f"  {p}{_behind(behind.get(p), data)}"
                      for p in references) or "  none")
    )
    return data, "\n".join(blocks)


def cmd_context(args):
    store, root = corpus.load()
    tags = cite.cited(cite.read(root)[0])
    dependents = {}
    for other in corpus.items(store):
        for target in {corpus.split_address(a)[0]
                       for a in corpus.dependencies(other.data)}:
            dependents.setdefault(target, []).append(other)

    rows = []
    for uid in dict.fromkeys(args.uid):
        try:
            rows.append(_context(store, corpus.find(store, uid),
                                 dependents, tags))
        except ReqctlError as fault:
            rows.append(({"uid": uid, "error": str(fault)},
                         _render({"uid": uid, "unreadable": str(fault)})))

    held = [data for data, _ in rows]
    if all("error" in data for data in held):
        raise ReqctlError("; ".join(data["error"] for data in held))

    if args.json:
        _emit(args, held, "")
        return EXIT_OK

    for data in held:
        if "error" in data:
            print(f"reqctl: {data['error']}", file=sys.stderr)
    print(BETWEEN_ITEMS.join(text for _, text in rows))
    return EXIT_OK


def _handle(uid, data):
    if corpus.kind_of(uid, data) == "term":
        fields = corpus.term_fields(data)
        aliases = ", ".join(str(a) for a in fields.get("aliases") or [])
        word = corpus.term_word(data) or ""
        return f"{word} ({aliases})" if aliases else word
    if corpus.kind_of(uid, data) in ("requirement", "guard"):
        return " ".join(str(data.get("text") or "").split())
    return str(data.get("name") or "")


def _occurring(store, path, kind):
    records = {str(item.uid): corpus.raw(item) for item in corpus.items(store)}
    text = corpus.read_text(path)
    if kind == "parameter":
        return _validate.occurring_values(records, text)
    return _validate.occurring(records, text)


def cmd_smell(args):
    text = corpus.read_text(args.path)
    found = _validate.pronouns(text)
    if args.json:
        _emit(args, {"path": args.path,
                     "pronouns": [{"word": word, "at": at}
                                  for at, word in found]}, "")
        return EXIT_OK
    if not found:
        print("no pronouns")
        return EXIT_OK
    for at, word in found:
        around = " ".join(text[max(0, at - 30):at + 30].split())
        line = text.count("\n", 0, at) + 1
        print(f"{line}: {word} -- {around}")
    return EXIT_OK


def cmd_list(args):
    if args.within and args.kind not in ("term", "parameter"):
        raise ReqctlError("--in reads prose for what an item fixes -- the "
                          "words a term defines, the value a parameter holds; "
                          "it applies to `list term` and `list parameter` alone")
    store, _ = corpus.load()
    occurring = _occurring(store, args.within, args.kind) if args.within else None
    rows = []
    for item in corpus.items(store):
        uid = str(item.uid)
        data = corpus.raw(item)
        kind = corpus.kind_of(uid, data)
        if args.kind and kind != args.kind:
            continue
        rows.append({"uid": uid, "kind": kind, "status": data.get("status"),
                     "handle": _handle(uid, data)})
    if occurring is not None:
        rows = [{**row, "matched": occurring[row["uid"]]}
                for row in rows if row["uid"] in occurring]
    rows.sort(key=lambda r: (r["kind"] or "", r["handle"].lower(), r["uid"]))

    if args.json:
        _emit(args, {"items": rows}, "")
        return EXIT_OK
    if not rows:
        print("no items" + (f" of kind {args.kind}" if args.kind else "")
              + (f" occurring in {args.within}" if args.within else ""))
        return EXIT_OK
    width = max(len(r["status"] or "") for r in rows)
    for row in rows:
        handle = row["handle"]
        if row["kind"] != "term" and len(handle) > 72:
            handle = handle[:71] + "…"
        suffix = "  -- " + ", ".join(row["matched"]) if occurring is not None else ""
        print(f"{row['uid']}  {(row['status'] or ''):<{width}}  {handle}{suffix}")
    return EXIT_OK


def cmd_validate(args):
    root = corpus.find_root()
    exempted: list[str] = []
    problems = _validate.run(root, exempted)
    count = len(corpus.item_files(root))
    if args.json:
        _emit(args, {"valid": not problems, "items": count, "problems": problems,
                     "unclaimed": exempted}, "")
        return EXIT_INVALID if problems else EXIT_OK
    # @req> REQ-88221320@tXvROEk2-d6r gvnev6
    if exempted:
        print("\n".join(exempted))
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"\n{len(problems)} problem(s) across {count} item(s)", file=sys.stderr)
    else:
        print(f"corpus valid: {count} item(s)")
    return EXIT_INVALID if problems else EXIT_OK


def cmd_trace(args):
    tree, root = corpus.load()
    data = graph.trace(tree, root, args.uid)
    if args.json:
        _emit(args, data, "")
    else:
        for row in data["rows"]:
            print(f"{row['uid']}  {row['status']}")
            for path in row["implementation"]:
                print(f"    impl  {path}")
        if data["unimplemented"]:
            print("\nawaiting implementation: " + ", ".join(data["unimplemented"]))
        # @req> REQ-35979865@-t3USRO-BKGk wht4dr
        if data["deprecated"]:
            print("\ncited though deprecated")
            for row in data["deprecated"]:
                print(f"  {row['uid']}  {row['path']}")
        if data["stale"]:
            print("\nbehind the corpus", file=sys.stderr)
            for row in data["stale"]:
                print(f"  {row['uid']}  {row['path']}  "
                      f"pinned @{row['pinned']}, now @{row['held']}",
                      file=sys.stderr)
        if data["problems"]:
            print("\n".join(data["problems"]), file=sys.stderr)
    return EXIT_INVALID if data["problems"] or data["stale"] else EXIT_OK


# @req> REQ-78685242@62t3Pc4LqF05 da5qxm
def _listed(store, uid, entries):
    if not uid.startswith(("REQ-", "GUARD-")):
        return []
    item = corpus.find(store, uid)
    before = corpus.mapping(item.data, corpus.CITATION_LIST)
    held = dict(before)
    for identity, taken in entries.items():
        if taken is None:
            held.pop(identity, None)
        else:
            held[identity] = taken
    if held == before:
        return []
    if held:
        item.data[corpus.CITATION_LIST] = held
    else:
        item.data.pop(corpus.CITATION_LIST, None)
    return [(item.path, corpus.dump(item.data))]


def cmd_tag(args):
    tree, root = corpus.load()
    # @req+ REQ-62782894@QlfQx33Br2KT nmyxfc
    if not len(args.first) == len(args.last) == len(args.req):
        raise ReqctlError("name --from, --to and --req once for each citation")
    asked = []
    for first, last, req in zip(args.first, args.last, args.req):
        item = corpus.find(tree, req)
        if not str(item.uid).startswith(("REQ-", "GUARD-")):
            raise ReqctlError(f"{req}: only a requirement or a guard is cited")
        asked.append((first, last, str(item.uid),
                      corpus.tag_stamp(corpus.stamp(item))))
    change, written = cite.tagged(root, args.path, asked, args.exclusive)
    # @req- nmyxfc
    changes = [change]
    # @req> REQ-75539229@OyOJtrpdfVnQ c7r3ff
    # @req> REQ-89706423@_mbcyBulaUGb wrzqdw
    for uid in dict.fromkeys(uid for _, uid, _ in written):
        changes += _listed(tree, uid, {identity: taken
                                       for identity, named, taken in written
                                       if named == uid})
    # @req> REQ-65668011@6eXnj2-53DtA 4pj4jj
    corpus.write_all(changes)
    identities = [identity for identity, _, _ in written]
    _emit(args, {"ids": identities, "path": args.path}, "\n".join(identities))
    return EXIT_OK


def cmd_repin(args):
    tree, root = corpus.load()
    citation = cite.named(root, args.id)
    item = corpus.find(tree, citation["uid"])
    # @req> REQ-70626698@ybHsrTlF-wU1 dhjmro
    if corpus.raw(item).get("status") == "deprecated":
        raise ReqctlError(f"{citation['uid']} is deprecated -- a citation of it "
                          f"is removed, not re-pinned: `reqctl untag {args.id}`")
    stamp = corpus.tag_stamp(corpus.stamp(item))
    changes = [cite.repinned(root, citation, stamp)]
    # @req> REQ-64846889@pHOO0sEc7V1K 7dhw4d
    # @req> REQ-17757558@4j9rQN-e61OY tevb2p
    changes += _listed(tree, citation["uid"], {args.id: cite.standing(root, citation)})
    # @req> REQ-65668011@6eXnj2-53DtA 34djjj
    corpus.write_all(changes)
    _emit(args, {"id": args.id, "path": citation["path"], "stamp": stamp},
          f"{args.id} in {citation['path']} pinned @{stamp}")
    return EXIT_OK


def cmd_untag(args):
    tree, root = corpus.load()
    citation = cite.named(root, args.id)
    changes = [cite.untagged(root, citation)]
    # @req> REQ-13298390@OIZCRlURf3pq utmfsc
    # @req> REQ-81275367@rZszCCP31YAU olrtj5
    if citation["uid"] in {str(item.uid) for item in corpus.items(tree)}:
        changes += _listed(tree, citation["uid"], {args.id: None})
    # @req> REQ-65668011@6eXnj2-53DtA jwd2cj
    corpus.write_all(changes)
    _emit(args, {"id": args.id, "path": citation["path"]},
          f"{args.id} removed from {citation['path']}")
    return EXIT_OK


def cmd_unlist(args):
    tree, root = corpus.load()
    item = corpus.find(tree, args.uid)
    uid = str(item.uid)
    # @req> REQ-97939970@lyVUGGzeSEQW xrna4u
    if (not uid.startswith(("REQ-", "GUARD-"))
            or args.id not in corpus.mapping(item.data, corpus.CITATION_LIST)):
        raise ReqctlError(f"{uid}: its citation list does not hold {args.id}")
    # @req+ REQ-59136977@5NZtW-PM9X2O s3g7ya
    # @req> REQ-81063063@J51Kuu-RKFjK rphl5n
    if any(citation["id"] == args.id and citation["uid"] == uid
           for citation in cite.readable(root)):
        raise ReqctlError(
            f"{uid}: a statement citation names {args.id} -- reqctl untag "
            f"{args.id} removes the citation, reqctl repin {args.id} re-pins it")
    # @req> REQ-56797974@xJHqq1DXePrs tn22pk
    corpus.write_all(_listed(tree, uid, {args.id: None}))
    # @req- s3g7ya
    _emit(args, {"uid": uid, "id": args.id},
          f"{args.id} removed from the citation list of {uid}")
    return EXIT_OK


def cmd_compare(args):
    root = corpus.find_root()
    ref = args.base or _baseline._default_ref(root)
    if ref is None:
        raise ReqctlError("no origin to compare against -- name one with --base")
    data = cite.compare(root, ref)
    lines = [f"{row['id']}  {row['uid']}  {row['path']}  {', '.join(row['state'])}"
             for row in data["citations"]]
    lines.append("touches: " + (", ".join(data["touches"]) or "nothing"))
    _emit(args, data, "\n".join(lines))
    return EXIT_OK


# @req> REQ-49576265@dETVQnFJ79Sd pihyx4
def _opened(url):
    if not webbrowser.open(url):
        print(f"no browser opened; open {url} in one", file=sys.stderr)


def cmd_portal(args):
    held = _portal.repository(os.getcwd())
    # @req+ REQ-49576265@dETVQnFJ79Sd wx5icq
    server = _portal.server()
    # @req> REQ-53764133@s638VvRMfEgi f7ob5l
    url = f"http://{_portal.HOST}:{_portal.PORT}/?repo={held}"
    _emit(args, {"repository": held, "url": url},
          f"the portal on {held} is at {url} -- Ctrl-C stops it")
    sys.stdout.flush()
    threading.Thread(target=_opened, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    # @req- wx5icq
    return EXIT_OK


def cmd_resolve(args):
    store, _ = corpus.load()
    path, dropped, unlisted = _resolve.resolve(store, args.uid)
    said = f"{args.uid}: resolved"
    if dropped:
        acks = " ".join(f"--ack {gone}" for gone in dropped)
        said += (f"; the merge conflicted {', '.join(dropped)}, now suspect "
                 f"-- reread, then reqctl revise {args.uid} {acks}")
    if unlisted:
        said += (f"; the merge conflicted citations {', '.join(unlisted)}, now "
                 f"unlisted -- read each against {args.uid}, then reqctl repin "
                 "it")
    _emit(args, {"uid": args.uid, "path": str(path), "dropped": dropped,
                 "unlisted": unlisted}, said)
    return EXIT_OK


def cmd_baseline(args):
    tree, root = corpus.load()

    if args.generate:
        # @req> REQ-64286515@d0Nt8dNubZNP nb26v5
        _refuse_invalid(root, "generate")
        number, path, count, claimed = _baseline.generate(tree, root)
        said = (
            f"baseline {number} written with {count} approved item(s).\n"
            "It states what is approved; it does not approve anything."
        )
        if claimed:
            stated = " and ".join(str(one) for one in sorted(set(claimed)))
            said = (
                f"an unresolved merge claiming {stated} was regenerated rather "
                "than merged.\n" + said
            )
        _emit(
            args,
            {"baseline": number, "path": str(path), "items": count,
             "resolved": claimed},
            said,
        )
        return EXIT_OK

    number, problems = _baseline.check(tree, root)
    if args.json:
        _emit(args, {"baseline": number, "valid": not problems, "problems": problems}, "")
    elif problems:
        print("\n".join(problems), file=sys.stderr)
        if number is not None:
            print(f"\nbaseline {number} does not match the corpus", file=sys.stderr)
    elif number is None:
        print("no baseline yet")
    else:
        print(f"baseline {number} matches the corpus")
    return EXIT_INVALID if problems else EXIT_OK

def _command(sub, name, said):
    return sub.add_parser(name, help=said, description=said)


RESERVED = ("json", "command", "func", "uid", "kind")
FIELDED = ("new", "lint", "revise")


def _field_arguments(s, flags, taken=()):
    for flag in flags:
        if flag.dest in taken and flag.entries:
            continue
        if flag.dest in RESERVED + tuple(taken):
            raise ReqctlError(f"a kind schema gives a field {flag.flag}, which "
                              "reqctl takes for its own; mark the field readOnly "
                              "if tooling writes it, or give it another x-flag")
        try:
            if flag.switch:
                s.add_argument(flag.flag, action="store_true", default=None)
            else:
                s.add_argument(flag.flag, choices=list(flag.choices) or None,
                               action="append" if flag.repeated else "store",
                               type=flag.convert, metavar=flag.metavar)
        except argparse.ArgumentError as clash:
            raise ReqctlError(f"a kind schema gives a field {flag.flag}, which "
                              f"reqctl takes for its own: {clash}") from None


def _item_arguments(s, flags):
    s.add_argument("kind", choices=list(_write.KINDS))
    # @req> REQ-71965656@LcOQ8O1Sqy_n f7bkcf
    _field_arguments(s, flags)


def _fielded(argv):
    return next((token for token in argv if not token.startswith("-")),
                None) in FIELDED


def build_parser(root, fielded):
    flags = _fields.flags(root) if fielded else []
    clears = _fields.clears(root) if fielded else []
    p = argparse.ArgumentParser(
        prog="reqctl",
        description="The requirements corpus under requirements/ is read and "
                    "written only through these commands. --json goes before "
                    "the command: reqctl --json <command> ...",
    )
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True)

    s = _command(sub, "new", "mint a requirement, parameter, term or data item")
    _item_arguments(s, flags)
    s.add_argument("--uid", help="mint a requirement or guard under this uid "
                                 "rather than a fresh one")
    s.set_defaults(func=cmd_new)

    s = _command(sub, "lint",
                 "report the faults new would refuse an item for, writing "
                 "nothing")
    _item_arguments(s, flags)
    s.set_defaults(func=cmd_lint)

    s = _command(sub, "revise",
                 "change an item's fields, pin its links with --ack, or edit "
                 "a data entry")
    s.add_argument("uid")
    # @req> REQ-91205530@RtIsl4zWjUDc ctnzp2
    _field_arguments(s, flags + clears, _write.OPERATIONS)
    s.add_argument("--ack", dest="ack", action="append",
                   metavar="NAME | NAME.ENTRY",
                   help="pin a referenced parameter or linked term at its "
                        "current state; repeat for each one")
    s.add_argument("--handle", metavar="KEY",
                   help="terms: the entry key, snake_case; the word it wore "
                        "moves into the entry where a word is not already "
                        "stated")
    s.add_argument("--kind", choices=list(_write.KINDS))
    s.add_argument("--entry", metavar="KEY",
                   help="the existing entry --set writes to")
    s.add_argument("--new-entry", dest="new_entry", metavar="KEY",
                   help="add a data entry, applying --set to it")
    s.add_argument("--set", dest="set", action="append", metavar="FIELD=VALUE",
                   help="a field on --entry's entry; repeat for each one")
    s.add_argument("--append", dest="append", action="append",
                   metavar="FIELD=VALUE",
                   help="add one member to a set field; repeat for each member")
    s.add_argument("--unset", dest="unset", action="append", metavar="FIELD",
                   help="drop a field from --entry's entry; repeat for each one")
    s.add_argument("--drop-entry", dest="drop_entry", metavar="KEY",
                   help="remove a data entry; its fields go with it")
    s.add_argument("--reword", dest="reword", action="append", metavar="OLD=NEW",
                   help="a word this term's links show, and what it becomes; "
                        "--term rewrites its own word without this")
    s.set_defaults(func=cmd_revise)

    s = _command(sub, "relate",
                 "record a relation between requirements, from the statement "
                 "making the claim toward the one it leans on")
    s.add_argument("source", help="the requirement making the claim")
    s.add_argument("relation", choices=list(_write.RELATIONS))
    s.add_argument("target", help="the requirement it points at")
    s.set_defaults(func=cmd_relate)

    s = _command(sub, "unrelate", "remove a relation")
    s.add_argument("source")
    s.add_argument("target")
    s.set_defaults(func=cmd_unrelate)

    s = _command(sub, "rename",
                 "give a term, a parameter or a data item another name, "
                 "moving its file and every reference that reaches it")
    s.add_argument("uid")
    s.add_argument("name")
    s.set_defaults(func=cmd_rename)

    s = _command(sub, "refile",
                 "file a parameter as the data item it is, moving its file "
                 "and dropping the value_type a data item does not carry")
    s.add_argument("uid")
    s.set_defaults(func=cmd_refile)

    s = _command(sub, "delete",
                 "remove a draft nothing points at; an item the corpus has "
                 "stated is deprecated, never removed")
    s.add_argument("uid")
    s.set_defaults(func=cmd_delete)

    s = _command(sub, "export",
                 "print the corpus as markdown, or raw with --json")
    s.add_argument("--all", action="store_true", help="include drafts and deprecated")
    s.set_defaults(func=cmd_export)

    s = _command(sub, "context",
                 "everything around each item named: fields, links, suspicion, "
                 "code. Inspection only -- what it cannot read it marks, and it "
                 "fails only when nothing named resolves")
    s.add_argument("uid", nargs="+", metavar="UID")
    s.set_defaults(func=cmd_context)

    s = _command(sub, "list",
                 "one line per item -- what the corpus holds, without "
                 "reading all of it")
    s.add_argument("kind", nargs="?",
                   choices=list(_write.KINDS),
                   help="limit to one kind; omit for everything")
    s.add_argument("--in", dest="within", metavar="PATH",
                   help="terms and parameters only: keep those whose word, "
                        "alias or value occurs in the prose at PATH, and name "
                        "which matched")
    s.set_defaults(func=cmd_list)

    s = _command(sub, "smell",
                 "name the pronouns in prose a statement is drafted from; "
                 "what it finds is advice, not a refusal")
    s.add_argument("path", metavar="PATH", help="the prose to read")
    s.set_defaults(func=cmd_smell)

    s = _command(sub, "validate",
                 "check every item and every cross-link; exit 1 on problems")
    s.set_defaults(func=cmd_validate)

    s = _command(sub, "trace",
                 "map @req tags in code to the corpus; exit 1 on problems")
    s.add_argument("uid", nargs="?", help="limit the trace to one item")
    s.set_defaults(func=cmd_trace)

    s = _command(sub, "tag",
                 "cite a requirement at lines of a file, writing one comment "
                 "over a single code statement and a pair of comments over "
                 "more; repeat --from, --to and --req to cite several, each "
                 "numbered as the file stands before the command")
    s.add_argument("path")
    # @req+ REQ-62782894@QlfQx33Br2KT ou2zvt
    s.add_argument("--from", dest="first", type=int, action="append",
                   required=True)
    s.add_argument("--to", dest="last", type=int, action="append", required=True)
    s.add_argument("--req", action="append", required=True)
    # @req- ou2zvt
    s.add_argument("--exclusive", action="store_true")
    s.set_defaults(func=cmd_tag)

    s = _command(sub, "repin",
                 "re-pin a citation to the stamp its requirement carries now, "
                 "once the code is read against the statement that stands")
    s.add_argument("id")
    s.set_defaults(func=cmd_repin)

    s = _command(sub, "untag", "remove a citation")
    s.add_argument("id")
    s.set_defaults(func=cmd_untag)

    s = _command(sub, "unlist",
                 "remove from a requirement's citation list an identity that "
                 "no citation of that requirement names")
    s.add_argument("uid")
    s.add_argument("id")
    s.set_defaults(func=cmd_unlist)

    s = _command(sub, "compare",
                 "state which citations this branch added, deleted, moved or "
                 "changed since it left the default branch, and the "
                 "requirements they name")
    s.add_argument("--base")
    s.set_defaults(func=cmd_compare)

    s = _command(sub, "portal",
                 "serve the portal on the repository origin names, and open "
                 "the browser at it")
    s.set_defaults(func=cmd_portal)

    s = _command(sub, "resolve",
                 "settle an item whose unresolved merge falls within its "
                 "pins and citation list, dropping the pins and citations the "
                 "merge conflicted")
    s.add_argument("uid")
    s.set_defaults(func=cmd_resolve)

    s = _command(sub, "baseline", "the manifest of what is approved")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true",
                   help="compare the baseline against the corpus")
    g.add_argument("--generate", action="store_true",
                   help="write the next baseline from what is approved")
    s.set_defaults(func=cmd_baseline)

    return p


def _drop_output():
    try:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    except (OSError, ValueError):
        pass


# @req> REQ-61484030@n7khA9l0yAgr s75lcl
def _fault(as_json, error):
    if as_json and sys.stdout is not None:
        try:
            print(json.dumps({"error": str(error)}, indent=2), flush=True)
            return EXIT_INVALID
        except OSError:
            _drop_output()
    print(f"reqctl: {error}", file=sys.stderr)
    return EXIT_INVALID


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    # @req+ REQ-19913588@zNetOTQBhHYZ zh6xly
    try:
        parser = build_parser(_fields.root(), _fielded(argv))
    except (ReqctlError, OSError, UnicodeError) as error:
        return _fault("--json" in argv, error)
    # @req- zh6xly
    try:
        args = parser.parse_args(argv)
    except SystemExit as usage:
        if "--json" in argv and usage.code:
            print(json.dumps({"error": "usage: the fault is on stderr; "
                                       "`reqctl --help` lists the commands"},
                             indent=2))
        raise
    # @req> REQ-51372579@dWaIOhXJzQnK kknvo3
    if sys.stdout is None:
        reader, writer = os.pipe()
        os.close(reader)
        sys.stdout = os.fdopen(writer, "w")
    # @req+ REQ-19913588@zNetOTQBhHYZ dw57fs
    try:
        # @req> REQ-24406170@M08jCONzg-4u 3ofubr
        with corpus.all_or_nothing():
            done = args.func(args)
            sys.stdout.flush()
            return done
    except BrokenPipeError:
        _drop_output()
        # @req> REQ-51372579@dWaIOhXJzQnK ihfdn7
        return EXIT_INVALID
    except (ReqctlError, OSError, UnicodeError) as error:
        return _fault(args.json, error)
    # @req- dw57fs


if __name__ == "__main__":
    sys.exit(main())
