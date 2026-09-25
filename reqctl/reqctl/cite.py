import difflib
import hashlib
import io
import json
import os
import subprocess
import re
import secrets
import tokenize
from pathlib import Path

from . import corpus
from .corpus import ReqctlError

OPEN, CLOSE, SINGLE = "+", "-", ">"
SIGN = re.compile(r"@req([+>-])(?=\s|$)")
MARKER = re.compile(
    rf"\A@req(?P<sign>[+>-])(?:\s+(?P<uid>(?:{corpus.KINDS})-\d+)"
    r"(?:@(?P<stamp>\S*))?)?(?:\s+(?P<id>\S+))?(?:\s+(?P<exclusive>exclusive))?\Z")
FORMER = re.compile(rf"@req:\s*((?:{corpus.KINDS})-\d+)")
DELIMITERS = re.compile(r"\A\s*(?:#+|<!--)\s*|\s*-->\s*\Z")
ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"
COMMENTS = {".py": ("# ", ""), ".md": ("<!-- ", " -->"), ".html": ("<!-- ", " -->")}


def markers(text):
    for number, line in enumerate(text.splitlines(), start=1):
        # @req+ REQ-52925332@wlFlbfJQbQ2g yuyqhd
        # @req+ REQ-12490145@DQLuzMctTPb5 dsvgt4
        if not SIGN.search(line):
            continue
        body = DELIMITERS.sub("", line).strip()
        yield number, body, MARKER.match(body)
        # @req- dsvgt4
        # @req- yuyqhd


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


def cut(path, text, spans):
    if Path(path).suffix != ".py":
        return []
    try:
        depths, starts, ends = _depths(text)
    except (tokenize.TokenError, IndentationError, SyntaxError) as broken:
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


def read(root):
    sources = list(_sources(root))
    citations, problems = parse(sources)
    return citations, problems + list(former(sources))


def former(sources):
    # @req> REQ-44164687@lSjyIVOw_1BK q2mqfm
    for relative, text in sources:
        for number, line in enumerate((text or "").splitlines(), start=1):
            for uid in FORMER.findall(line):
                yield (f"{relative}:{number}: names {uid} in a single-line "
                       "tag -- cite it with reqctl tag")


def cited(citations):
    held = {}
    for citation in citations:
        held.setdefault(citation["uid"], []).append(
            (citation["path"], citation["pinned"]))
    return held


def parse(sources):
    opened, problems, seen = [], [], {}
    for relative, text in sources:
        if text is None:
            problems.append(f"{relative}: unreadable while scanning for "
                            "statement citations")
            continue
        found = list(markers(text))
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
                # @req> REQ-44424329@--ePOFus7t2H det3om
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


def _citation(held, relative, start, close, first, last, marks):
    return {"id": held["id"], "uid": held["uid"], "pinned": held["stamp"] or "",
            "exclusive": bool(held["exclusive"]), "path": relative,
            "open": start, "close": close, "first": first, "last": last,
            "marks": marks}


def following(path, text, number):
    if Path(path).suffix == ".py":
        try:
            depths, starts, _ = _depths(text)
        except (tokenize.TokenError, IndentationError, SyntaxError):
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
    lines = text.splitlines()
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
    # @req> REQ-81857516@chYOQDPmuDuW ldlf2u
    for folder, subdirs, files in os.walk(root):
        subdirs[:] = [name for name in subdirs
                      if name not in corpus.SCAN_SKIP
                      and not name.endswith(".egg-info")
                      and Path(folder) / name != corpus_dir]
        for name in files:
            path = Path(folder) / name
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
            except OSError:
                yield str(path.relative_to(root)), None
                continue
            if b"\0" in raw:
                continue
            yield str(path.relative_to(root)), raw.decode(errors="ignore")


def mint(held):
    while True:
        # @req+ REQ-92239556@w0fSOmsCa6TA uprfcz
        identity = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if identity not in held:
            return identity
        # @req- uprfcz


def write(root, path, first, last, uid, stamp, exclusive=False):
    target = Path(path)
    if target.suffix not in COMMENTS:
        raise ReqctlError(f"{path}: citations are written only in "
                          f"{', '.join(sorted(COMMENTS))} files")
    lines = target.read_text().splitlines(keepends=True)
    if not 1 <= first <= last <= len(lines):
        raise ReqctlError(f"{path}: lines {first}-{last} are not in the file")
    held, _ = read(root)
    identity = mint({c["id"] for c in held})
    lead, tail = COMMENTS[target.suffix]
    indent = re.match(r"\s*", lines[first - 1]).group(0)
    word = " exclusive" if exclusive else ""
    whole = "".join(lines)
    single = _statement(path, whole, first, last)
    # @req+ REQ-60346603@eKFixVFgV9Xt ccwbjy
    # @req+ REQ-84469558@lQYICZeT2eTO 357m3m
    # @req+ REQ-61906662@vIt4Qdb6Q01L rr4c2l
    sign = SINGLE if single else OPEN
    opening = f"{indent}{lead}@req{sign} {uid}@{stamp} {identity}{word}{tail}\n"
    closing = [] if single else [f"{indent}{lead}@req{CLOSE} {identity}{tail}\n"]
    # @req- rr4c2l
    text = "".join(lines[:first - 1] + [opening] + lines[first - 1:last]
                   + closing + lines[last:])
    problems = [] if single else cut(path, text, [(identity, first + 1, last + 1)])
    if problems:
        raise ReqctlError("\n".join(problems))
    target.write_text(text)
    # @req- 357m3m
    # @req- ccwbjy
    return identity


def named(root, identity):
    held, problems = parse(_sources(root))
    if problems:
        raise ReqctlError("the code's citations do not read:\n" + "\n".join(problems))
    for citation in held:
        if citation["id"] == identity:
            return citation
    # @req> REQ-51778557@u-lwJ0bB2Txg 2j6t3u
    # @req> REQ-41024637@GwZanwxFaYmM cdi6vq
    raise ReqctlError(f"no statement citation names {identity}")


def _lines(root, citation):
    target = Path(root) / citation["path"]
    return target, target.read_bytes().decode().splitlines(keepends=True)


def repin(root, citation, stamp):
    # @req+ REQ-17757558@9_SHKLed0ssS lqd5pz
    target, lines = _lines(root, citation)
    at = citation["open"] - 1
    pinned = re.compile(rf"(@req[{OPEN}{SINGLE}]\s+{re.escape(citation['uid'])})(?:@\S*)?")
    # @req> REQ-18833394@wnCdGzhY7m6Z 62bkhg
    lines[at] = pinned.sub(lambda found: f"{found.group(1)}@{stamp}", lines[at], count=1)
    target.write_bytes("".join(lines).encode())
    # @req- lqd5pz


def remove(root, citation):
    target, lines = _lines(root, citation)
    marks = set(citation["marks"])
    # @req> REQ-81275367@LuNIjqeTrwb4 5gkn5k
    # @req> REQ-26984738@nD05toE71g-O a4ywox
    target.write_bytes("".join(line for number, line in enumerate(lines, start=1)
                               if number not in marks).encode())


def _statement(path, text, first, last):
    lines = text.splitlines()
    code = [n for n in range(first, last + 1) if lines[n - 1].strip()]
    if not code or code[0] != first:
        return False
    return following(path, text, first - 1) == (first, code[-1])


UNREAD = (tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT)


def _tokens(text, wanted):
    held, depth, first = [], 0, None
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.INDENT:
            depth += 1
        elif token.type == tokenize.DEDENT:
            depth -= 1
        if token.start[0] not in wanted or token.type in UNREAD:
            continue
        first = depth if first is None else first
        held.append([tokenize.tok_name[token.type], depth - first,
                     "" if token.type == tokenize.NEWLINE else token.string])
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
        split = text.splitlines()
        held = [split[n - 1] for n in sorted(wanted)]
        # @req- soehrs
    return hashlib.sha256(json.dumps(held).encode()).hexdigest()


def _rest(text, citation):
    kept, before = [], 0
    for number, line in enumerate(text.splitlines(), start=1):
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
    now_texts = {relative: text for relative, text in _sources(root)
                 if text is not None and SIGN.search(text)}
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
    # @req> REQ-70581878@7_JGPxsumznG w6qryd
    touched = sorted({row["uid"] for row in rows if row["state"] != ["moved"]})
    return {"base": commit, "citations": rows, "touches": touched}
