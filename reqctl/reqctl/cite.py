import difflib
import functools
import io
import os
import subprocess
import re
import secrets
import stat
import tokenize
from pathlib import Path

import yaml

from . import corpus
from .corpus import ReqctlError

OPEN, CLOSE, SINGLE = "+", "-", ">"
SIGN = re.compile(r"@req([+>-])(?=\s|$)")
# @req> REQ-88203622@QLXb8abUOMT3 y644wh
# @req> REQ-22755763@jWQQtKhJ8JoO 5upe6v
MARKER = re.compile(
    rf"\A@req(?P<sign>[+>-])(?:\s+(?P<uid>(?:{corpus.KINDS})-\d+"
    rf"|{corpus.NAME}(?:\.{corpus.NAME})?(?=@))"
    r"(?:@(?P<stamp>\S*))?)?(?:\s+(?P<id>\S+))?(?:\s+(?P<exclusive>exclusive))?\Z")
FORMER = re.compile(rf"@req:\s*((?:{corpus.KINDS})-\d+)")
# @req+ REQ-52925332@wlFlbfJQbQ2g tup4w2
MARKUP = re.compile(r"\A\s*<!--\s*|\s*-->\s*\Z")
DELIMITERS = {**dict.fromkeys((".py", ".yml", ".yaml"), re.compile(r"\A\s*#+\s*")),
              ".js": re.compile(r"\A\s*//\s*")}
# @req- tup4w2
ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
# @req> REQ-60346603@eKFixVFgV9Xt ulk4ve
COMMENTS = {**dict.fromkeys((".py", ".yml", ".yaml"), ("# ", "")),
            ".md": ("<!-- ", " -->"), ".html": ("<!-- ", " -->"), ".js": ("// ", "")}


# @req> REQ-52925332@wlFlbfJQbQ2g cczml5
def _feed_lines(text):
    return io.StringIO(text).readlines()


def markers(text, suffix):
    for number, line in enumerate(_feed_lines(text), start=1):
        # @req+ REQ-52925332@wlFlbfJQbQ2g yuyqhd
        # @req+ REQ-12490145@DQLuzMctTPb5 dsvgt4
        if not SIGN.search(line):
            continue
        body = DELIMITERS.get(suffix, MARKUP).sub("", line).strip()
        yield number, body, MARKER.match(body)
        # @req- dsvgt4
        # @req- yuyqhd


@functools.cache
def _depths(text):
    depth, depths, starts, ends = 0, {}, set(), set()
    fresh = True
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        kind, line = token.type, token.start[0]
        if kind == tokenize.INDENT:
            depth += 1
        elif kind == tokenize.DEDENT:
            depth -= 1
        elif kind == tokenize.NEWLINE:
            ends.add(line)
            fresh = True
        elif kind not in (tokenize.NL, tokenize.COMMENT, tokenize.ENDMARKER):
            for spanned in range(token.start[0], token.end[0] + 1):
                depths.setdefault(spanned, depth)
            if fresh:
                starts.add(line)
                fresh = False
    return depths, starts, ends


@functools.cache
def _indents(text):
    spans, flows = [], []
    for event in yaml.parse(text, Loader=corpus.Loader):
        start, end = event.start_mark, event.end_mark
        if isinstance(event, yaml.CollectionStartEvent) and event.flow_style:
            flows.append(start)
            continue
        if isinstance(event, yaml.CollectionEndEvent) and flows:
            start = flows.pop()
        spans.append(range(start.line + 1, end.line + 1 + bool(end.column)))
    inside = {n for span in spans for n in span[1:]}
    depths = {}
    for number, line in enumerate(_feed_lines(text), start=1):
        body = line.strip()
        if body and (number in inside or not body.startswith("#")):
            depths[number] = len(_indent(line)) + (body == "-" or body.startswith("- "))
    ends = set(depths)
    for span in spans:
        ends.difference_update([n for n in span if n in depths][:-1])
    return depths, set(depths) - inside, ends


NESTS = {".py": _depths, ".yml": _indents, ".yaml": _indents}


def cut(path, text, spans):
    read = NESTS.get(Path(path).suffix)
    if read is None:
        return []
    try:
        depths, starts, ends = read(text)
    except (tokenize.TokenError, IndentationError, SyntaxError, yaml.YAMLError) as broken:
        return [f"{path}: cannot read its nest levels ({broken}), so no "
                "citation in it can be checked"]
    problems = []
    for identity, first, last in spans:
        code = [n for n in range(first, last + 1) if n in depths]
        if not code:
            continue
        level = depths[code[0]]
        after = [n for n in depths if n > last]
        # @req> REQ-41552912@euPwJfYbRxVH fu7y6n
        if (code[0] not in starts or code[-1] not in ends
                or any(depths[n] < level for n in code)
                or (after and depths[min(after)] > level)):
            problems.append(
                f"{path}: citation {identity} cuts a block -- it must cover "
                "whole statements at the nest level of its first line")
    return problems


# @req+ REQ-82335572@jy-6pa6WK1sz jflstj
# @req+ REQ-79989567@oWj5HjnXcM0G 6fth2x
REMARKS = {**dict.fromkeys((".py", ".yml", ".yaml"), re.compile(r"^[ \t]*#[^\n]*", re.M)),
           **dict.fromkeys((".md", ".html"), re.compile(r"<!--[\s\S]*?(?:-->|\Z)")),
           ".js": re.compile(r"""(?P<kept>"(?:\\[\s\S]|[^"\\\n])*"|'(?:\\[\s\S]|[^'\\\n])*'"""
                             r"""|`(?:\\[\s\S]|[^`\\])*`)|//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)""")}


def hollow(texts, citations):
    problems = []
    for citation in citations:
        path, text = citation["path"], texts[citation["path"]]
        read = NESTS.get(Path(path).suffix)
        try:
            code = set(read(text)[0]) if read else None
        except (tokenize.TokenError, IndentationError, SyntaxError, yaml.YAMLError):
            code = None
        if code is None:
            bare = REMARKS[Path(path).suffix].sub(
                lambda found: found.groupdict().get("kept") or "\n" * found[0].count("\n"),
                text)
            code = {n for n, line in enumerate(_feed_lines(bare), start=1) if line.strip()}
        if code.isdisjoint(range(citation["first"], citation["last"] + 1)):
            problems.append(f"{path}: citation {citation['id']} covers no code statement")
    return problems
# @req- 6fth2x
# @req- jflstj


def read(root, digested=False):
    sources = list(_sources(root))
    citations, problems = parse(sources)
    # @req> REQ-32191310@ot16I3lSs2Nu yjp5s6
    if digested:
        texts = dict(sources)
        for citation in citations:
            citation["digest"] = digest(citation["path"], texts[citation["path"]],
                                        citation["lines"])
    # @req> REQ-79989567@oWj5HjnXcM0G x7gvxd
    problems += hollow(dict(sources), [c for c in citations if len(c["marks"]) == 2])
    return citations, problems + list(former(sources))


def former(sources):
    # @req> REQ-44164687@lSjyIVOw_1BK q2mqfm
    for relative, text in sources:
        for number, line in enumerate(_feed_lines(text or ""), start=1):
            for uid in FORMER.findall(line):
                yield (f"{relative}:{number}: names {uid} in a single-line "
                       "tag -- cite it with reqctl tag")


def cited(citations):
    held = {}
    for citation in citations:
        held.setdefault(citation["uid"], []).append(
            (citation["path"], citation["pinned"], citation["entry"]))
    return held


def parse(sources):
    opened, problems, seen = [], [], {}
    for relative, text in sources:
        # @req> REQ-35805881@37XtC4gyD98k 5h3hpr
        if text is None:
            problems.append(f"{relative}: unreadable while scanning for "
                            "statement citations")
            continue
        found = list(markers(text, Path(relative).suffix))
        if not found:
            continue
        if Path(relative).suffix not in COMMENTS:
            problems.append(
                f"{relative}: carries a statement citation, but citations are "
                f"read only in {', '.join(sorted(COMMENTS))} files")
            continue
        live, spans, singles = {}, [], []
        # @req+ REQ-73349683@BNT8xnMPL2bn gqpqj6
        for number, body, parsed in found:
            # @req> REQ-11268295@pg6jZYgo_eww q7622j
            if parsed is None or not parsed["id"]:
                problems.append(f"{relative}:{number}: `{body}` names no "
                                "citation identity")
                continue
            identity = parsed["id"]
            if parsed["sign"] in (OPEN, SINGLE):
                if not parsed["uid"]:
                    problems.append(f"{relative}:{number}: citation {identity} "
                                    "names no requirement")
                    continue
                # @req> REQ-44424329@FMmHjrkfDEYR det3om
                if identity in seen:
                    problems.append(
                        f"{relative}:{number}: citation {identity} is also "
                        f"opened at {seen[identity]} -- an identity names one "
                        "citation")
                seen.setdefault(identity, f"{relative}:{number}")
                if parsed["sign"] == SINGLE:
                    singles.append((number, parsed))
                    continue
                live[identity] = (number, parsed)
            elif identity not in live:
                problems.append(f"{relative}:{number}: closes citation "
                                f"{identity}, which is not open here")
            else:
                start, held = live.pop(identity)
                spans.append((identity, start + 1, number - 1))
                opened.append(_citation(held, relative, start, number,
                                        start + 1, number - 1, [start, number]))
        for identity, (number, _) in live.items():
            problems.append(f"{relative}:{number}: opens citation {identity} "
                            "and never closes it")
        # @req- gqpqj6
        for number, held in singles:
            span = following(relative, text, number)
            # @req> REQ-95865306@K4a2U5EVbqcv ytqmle
            if span is None:
                problems.append(f"{relative}:{number}: citation {held['id']} "
                                "has no code statement after it")
                continue
            opened.append(_citation(held, relative, number, span[1], *span,
                                    [number]))
        problems += cut(relative, text, spans)
    return covered(opened), problems


# @req> REQ-22755763@jWQQtKhJ8JoO rafirp
def _citation(held, relative, start, close, first, last, marks):
    uid, _, entry = held["uid"].partition(".")
    return {"id": held["id"], "uid": uid, "entry": entry or None,
            "address": held["uid"], "pinned": held["stamp"] or "",
            "exclusive": bool(held["exclusive"]), "path": relative,
            "open": start, "close": close, "first": first, "last": last,
            "marks": marks}


def following(path, text, number):
    read = NESTS.get(Path(path).suffix)
    if read is not None:
        try:
            depths, starts, _ = read(text)
        except (tokenize.TokenError, IndentationError, SyntaxError, yaml.YAMLError):
            depths = None
        # @req> REQ-42668747@GGAkEqZHFwdI cfabxh
        if depths is not None:
            later = sorted(n for n in starts if n > number)
            if not later:
                return None
            first = later[0]
            level = depths[first]
            beyond = [n for n in later if n > first and depths[n] <= level]
            last = max(n for n in depths
                       if first <= n and (not beyond or n < beyond[0]))
            return first, last
    lines = _feed_lines(text)
    # @req> REQ-37846580@Hp5GeJsazpl4 lrybex
    for at in range(number, len(lines)):
        if lines[at].strip() and not SIGN.search(lines[at]):
            return at + 1, at + 1
    return None


def covered(citations):
    marks = {(c["path"], line) for c in citations for line in c["marks"]}
    for citation in citations:
        lines = []
        for line in range(citation["first"], citation["last"] + 1):
            if (citation["path"], line) in marks:
                continue
            spanning = [c for c in citations if c["path"] == citation["path"]
                        and c["first"] <= line <= c["last"]]
            # @req+ REQ-33202540@RFae-fb4VZk9 6o76zm
            # @req+ REQ-97852648@wuO70aYdOpyH fto5gh
            claimed = [c for c in spanning if c["exclusive"]]
            # @req> REQ-17608335@ejFjhGoCg5c7 4makw7
            owners = ([max(claimed, key=lambda c: c["open"])] if claimed
                      else spanning)
            # @req- fto5gh
            # @req- 6o76zm
            if citation in owners:
                lines.append(line)
        citation["lines"] = lines
    return citations


def _sources(root):
    root = Path(root)
    corpus_dir = root / "requirements"
    # @req+ REQ-35805881@37XtC4gyD98k ofycdw
    unread = []
    # @req> REQ-81857516@chYOQDPmuDuW ldlf2u
    for folder, subdirs, files in os.walk(root, onerror=unread.append):
        subdirs[:] = [name for name in subdirs
                      if name not in corpus.SCAN_SKIP
                      and not name.endswith(".egg-info")
                      and Path(folder) / name != corpus_dir]
        for name in files:
            path = Path(folder) / name
            try:
                if not stat.S_ISREG(path.stat().st_mode):
                    continue
                raw = path.read_bytes()
            except FileNotFoundError:
                continue
            except OSError:
                yield str(path.relative_to(root)), None
                continue
            if b"\0" in raw:
                continue
            yield str(path.relative_to(root)), raw.decode(errors="ignore")
    for failure in unread:
        yield str(Path(failure.filename).relative_to(root)), None
    # @req- ofycdw


def mint(held):
    while True:
        # @req+ REQ-92239556@4-oyw0syx-xA uprfcz
        identity = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if identity not in held:
            return identity
        # @req- uprfcz


def _ending(line):
    return line[len(line.rstrip("\r\n")):]


# @req> REQ-89706423@_mbcyBulaUGb rkepcq
def _indent(line):
    body = line.rstrip("\r\n")
    return body[:len(body) - len(body.lstrip())]


# @req> REQ-89706423@_mbcyBulaUGb 5nywje
def _inserted(lines, before, after):
    ending = next((_ending(line) for line in lines if _ending(line)), "\n")
    out = []
    for number, line in enumerate(lines, start=1):
        out += [marker + (_ending(line) or ending)
                for _, _, marker in sorted(before.get(number, []))]
        closings = [marker for _, _, marker in sorted(after.get(number, []))]
        if closings and not _ending(line):
            out += [line + ending, ending.join(closings)]
            continue
        out.append(line)
        out += [marker + (_ending(line) or ending) for marker in closings]
    return "".join(out)


# @req> REQ-73851379@mlF6V9oGscj_ 26lc4r
def _duplicates(path, found, asked):
    marks = {line for citation in found for line in citation["marks"]}
    spanned = {citation["id"]: tuple(n for n in range(citation["first"],
                                                     citation["last"] + 1)
                                     if n not in marks)
               for citation in found}
    order = list(asked)
    problems = []
    for identity, (first, last, uid, _) in asked.items():
        for other in found:
            earlier = (other["id"] not in asked
                       or order.index(other["id"]) < order.index(identity))
            if (other["address"] == uid and earlier
                    and spanned[other["id"]] == spanned[identity]):
                problems.append(
                    f"{path}: lines {first}-{last} are already cited for {uid}"
                    + (" by this command" if other["id"] in asked
                       else f" by citation {other['id']}"))
                break
    return problems


# @req> REQ-60346603@eKFixVFgV9Xt e2efde
def tagged(root, path, asked, exclusive=False):
    target = Path(path)
    if target.suffix not in COMMENTS:
        raise ReqctlError(f"{path}: citations are written only in "
                          f"{', '.join(sorted(COMMENTS))} files")
    text = target.read_bytes().decode()
    lines = _feed_lines(text)
    # @req> REQ-65738797@3jHtqzLVQUal msfg5w
    for first, last, _, _ in asked:
        if not 1 <= first <= last <= len(lines):
            raise ReqctlError(f"{path}: lines {first}-{last} are not in the file")
    sources = list(_sources(root))
    held, problems = parse(sources)
    # @req> REQ-35805881@37XtC4gyD98k kz4urn
    if any(text is None for _, text in sources):
        raise ReqctlError("the code's citations do not read:\n" + "\n".join(problems))
    taken = {c["id"] for c in held}
    lead, tail = COMMENTS[target.suffix]
    word = " exclusive" if exclusive else ""
    # @req+ REQ-81417723@gBALpnqtdVL6 kmbhnk
    # @req+ REQ-62782894@QlfQx33Br2KT k2lzwu
    before, after, minted = {}, {}, []
    for at, (first, last, uid, stamp) in enumerate(asked):
        identity = mint(taken)
        taken.add(identity)
        minted.append(identity)
        indent = _indent(lines[first - 1])
        # @req+ REQ-61906662@vIt4Qdb6Q01L 4z5goa
        single = _statement(path, text, first, last)
        sign = SINGLE if single else OPEN
        # @req+ REQ-84469558@lQYICZeT2eTO hp5jwl
        before.setdefault(first, []).append(
            (-last, at, f"{indent}{lead}@req{sign} {uid}@{stamp} {identity}{word}{tail}"))
        if not single:
            after.setdefault(last, []).append(
                (-first, -at, f"{indent}{lead}@req{CLOSE} {identity}{tail}"))
        # @req- hp5jwl
        # @req- 4z5goa
    written = _inserted(lines, before, after)
    # @req- k2lzwu
    # @req- kmbhnk
    found, _ = parse([(path, written)])
    new = [c for identity in minted for c in found if c["id"] == identity]
    # @req+ REQ-65738797@3jHtqzLVQUal zkxsxx
    problems = cut(path, written, [(c["id"], c["first"], c["last"])
                                   for c in new if len(c["marks"]) == 2])
    # @req> REQ-82335572@jy-6pa6WK1sz 5lq35y
    problems += hollow({path: written}, new)
    problems += _duplicates(path, found, dict(zip(minted, asked)))
    if problems:
        raise ReqctlError("\n".join(problems))
    # @req- zkxsxx
    return ((target, written.encode()),
            [(c["id"], c["uid"], digest(path, written, c["lines"])) for c in new])


# @req> REQ-64846889@pHOO0sEc7V1K 6vgx2i
def standing(root, citation):
    text = (Path(root) / citation["path"]).read_bytes().decode()
    return digest(citation["path"], text, citation["lines"])


def readable(root):
    held, problems = parse(_sources(root))
    if problems:
        raise ReqctlError("the code's citations do not read:\n" + "\n".join(problems))
    return held


def named(root, identity):
    for citation in readable(root):
        if citation["id"] == identity:
            return citation
    # @req> REQ-51778557@SqqYYPmC67aK 2j6t3u
    # @req> REQ-41024637@zO8Xp3QDg6LT cdi6vq
    raise ReqctlError(f"no statement citation names {identity}")


def _lines(root, citation):
    target = Path(root) / citation["path"]
    return target, _feed_lines(target.read_bytes().decode())


def repinned(root, citation, stamp):
    # @req+ REQ-17757558@4j9rQN-e61OY lqd5pz
    target, lines = _lines(root, citation)
    at = citation["open"] - 1
    pinned = re.compile(rf"(@req[{OPEN}{SINGLE}]\s+{re.escape(citation['address'])})(?:@\S*)?")
    # @req> REQ-18833394@wnCdGzhY7m6Z 62bkhg
    lines[at] = pinned.sub(lambda found: f"{found.group(1)}@{stamp}", lines[at], count=1)
    return target, "".join(lines).encode()
    # @req- lqd5pz


def untagged(root, citation):
    target, lines = _lines(root, citation)
    marks = set(citation["marks"])
    # @req> REQ-81275367@rZszCCP31YAU 5gkn5k
    # @req> REQ-26984738@nD05toE71g-O a4ywox
    return target, "".join(line for number, line in enumerate(lines, start=1)
                           if number not in marks).encode()


def _statement(path, text, first, last):
    lines = _feed_lines(text)
    code = [n for n in range(first, last + 1) if lines[n - 1].strip()]
    if not code or code[0] != first:
        return False
    return following(path, text, first - 1) == (first, code[-1])


UNREAD = (tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT)


@functools.cache
def _stream(text):
    held, depth = [], 0
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.INDENT:
            depth += 1
        elif token.type == tokenize.DEDENT:
            depth -= 1
        held.append((token.start[0], token.type, depth, token.string))
    return held


def _tokens(text, wanted):
    held, first = [], None
    for line, kind, depth, string in _stream(text):
        if line not in wanted or kind in UNREAD:
            continue
        first = depth if first is None else first
        held.append([tokenize.tok_name[kind], depth - first,
                     "" if kind == tokenize.NEWLINE else string])
    return held


def digest(path, text, lines):
    wanted = set(lines)
    held = None
    if Path(path).suffix == ".py":
        try:
            # @req> REQ-31471659@hKmNhTkU9xOA suqekj
            held = _tokens(text, wanted)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            held = None
    if held is None:
        # @req+ REQ-15770866@PJj7anRT1m47 soehrs
        split = [line.rstrip("\r\n") for line in _feed_lines(text)]
        held = [split[n - 1] for n in sorted(wanted)]
        # @req- soehrs
    return corpus.digest(held)


def _rest(text, citation):
    kept, before = [], 0
    for number, line in enumerate(_feed_lines(text), start=1):
        if citation["open"] <= number <= citation["close"] or not line.strip():
            continue
        kept.append(line.strip())
        before += number < citation["open"]
    return kept, before


def crossed(was, was_text, now, now_text):
    # @req+ REQ-56906371@rALaP5YBvHg7 vvu3g7
    if was["path"] != now["path"]:
        return True
    old, old_before = _rest(was_text, was)
    new, new_before = _rest(now_text, now)
    matcher = difflib.SequenceMatcher(None, old, new, autojunk=False)
    return any((i + k < old_before) != (j + k < new_before)
               for i, j, size in matcher.get_matching_blocks()
               for k in range(size))
    # @req- vvu3g7


def _git(root, *args):
    found = subprocess.run(["git", *args], cwd=root, capture_output=True,
                           text=True, check=False)
    if found.returncode:
        raise ReqctlError(f"git {' '.join(args)}: {found.stderr.strip()}")
    return found.stdout


def _carried(root, commit):
    listed = subprocess.run(
        ["git", "grep", "-l", "-z", "-E", "@req[+>-]( |$)", commit, "--"],
        cwd=root, capture_output=True, text=True, check=False)
    if listed.returncode not in (0, 1):
        raise ReqctlError(f"cannot read {commit}: {listed.stderr.strip()}")
    for named in filter(None, listed.stdout.split("\0")):
        relative = named.split(":", 1)[1]
        yield relative, _git(root, "show", f"{commit}:{relative}")


def compare(root, ref):
    commit = _git(root, "merge-base", "HEAD", ref).strip()
    was_texts = dict(_carried(root, commit))
    # @req> REQ-35805881@37XtC4gyD98k wge7e5
    now_texts = {relative: text for relative, text in _sources(root)
                 if text is None or SIGN.search(text)}
    was, _ = parse(was_texts.items())
    now, problems = parse(now_texts.items())
    if problems:
        raise ReqctlError("the code's citations do not read:\n"
                          + "\n".join(problems))
    # @req+ REQ-36428128@leY8_I39CMWw a5i7lc
    before = {c["id"]: c for c in was}
    after = {c["id"]: c for c in now}
    # @req- a5i7lc
    rows = []
    for identity in sorted(set(before) | set(after)):
        old, new = before.get(identity), after.get(identity)
        # @req+ REQ-56906371@rALaP5YBvHg7 bicxbc
        if old is None or new is None:
            held = new or old
            rows.append({"id": identity, "uid": held["uid"],
                         "path": held["path"],
                         "state": ["added"] if old is None else ["deleted"]})
            continue
        state = []
        if crossed(old, was_texts[old["path"]], new, now_texts[new["path"]]):
            state.append("moved")
        if (digest(old["path"], was_texts[old["path"]], old["lines"])
                != digest(new["path"], now_texts[new["path"]], new["lines"])):
            state.append("changed")
        if state:
            rows.append({"id": identity, "uid": new["uid"], "path": new["path"],
                         "state": state})
        # @req- bicxbc
    # @req> REQ-70581878@qWy6X2qJfi1h w6qryd
    touched = sorted({row["uid"] for row in rows if row["state"] != ["moved"]})
    return {"base": commit, "citations": rows, "touches": touched}
