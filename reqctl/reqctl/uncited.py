import ast
import difflib
import io
import re
import tokenize
from pathlib import PurePosixPath

from . import cite, corpus, settings
from .reach import Reach

# @req> REQ-27534660@OcqGUyoB-NOR zu7qeg
MODES = ("all", "changed_lines")
# @req> uncited_code_exemptions@zlVU6_sD_Cmy 7z5oma
EXEMPTIONS = {
    "claude_md": {"files": "any file named CLAUDE.md in any folder"},
    "claude_rules": {"files": "every file under a .claude/rules folder"},
    "license": {"files": "any file whose name begins LICENSE in any folder"},
    "readme": {"files": "any file named README or README.* in any folder"},
}
EXEMPT_FILES = {
    "claude_md": re.compile(r"(?:^|/)CLAUDE\.md$"),
    "claude_rules": re.compile(r"(?:^|/)\.claude/rules/"),
    "license": re.compile(r"(?:^|/)LICENSE[^/]*$"),
    "readme": re.compile(r"(?:^|/)README(?:\.[^/]*)?$"),
}
HASHED = (".yml", ".yaml", ".toml", ".sh", ".cfg", ".txt")
COMMENTED = (".py", ".js", ".md", ".html", *HASHED)
# @req> commentless_formats.json@zjmZ8jE-Au2_ yjmqbb
COMMENTLESS = (".json",)
SCRIPT = (("//", None), ("/*", "*/"))
MARKUP = (("<!--", "-->"),)
UNREAD = (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
          tokenize.DEDENT, tokenize.ENDMARKER)
IMPORT = re.compile(r"^[ \t]*import\b(?!\s*\()[^;]*?(['\"])[^'\"\n]*\1[ \t]*;?",
                    re.MULTILINE | re.DOTALL)


def _lines(text):
    return io.StringIO(text).readlines()


def _fenced(text, pairs, quoted):
    quiet, inside = set(), None
    for number, line in enumerate(_lines(text), 1):
        code, at = False, 0
        while at < len(line):
            if inside:
                end = line.find(inside, at)
                at, inside = (len(line), inside) if end < 0 else (end + len(inside), None)
                continue
            if quoted and line[at] in "'\"`":
                close = line.find(line[at], at + 1)
                code, at = True, len(line) if close < 0 else close + 1
                continue
            opened = next((pair for pair in pairs if line.startswith(pair[0], at)), None)
            if opened and opened[1] is None:
                break
            if opened:
                inside, at = opened[1], at + len(opened[0])
                continue
            code = code or not line[at].isspace()
            at += 1
        if line.strip() and not code:
            quiet.add(number)
    return quiet


def _python(text):
    held = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type not in UNREAD:
                held.update(range(token.start[0], token.end[0] + 1))
        tree = ast.parse(text)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        return set()
    imports = {line for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))
               for line in range(node.lineno, (node.end_lineno or node.lineno) + 1)}
    return imports | {number for number, line in enumerate(_lines(text), 1)
                      if line.strip() and number not in held}


def _script(text):
    imports = {line for found in IMPORT.finditer(text)
               for line in range(text.count("\n", 0, found.start()) + 1,
                                 text.count("\n", 0, found.end()) + 2)}
    return imports | _fenced(text, SCRIPT, True)


# @req> REQ-58348893@GQ3L2sQGRlkW yvnqdz
def code_lines(path, text):
    suffix = PurePosixPath(path).suffix
    lines = _lines(text)
    quiet = {number for number, line in enumerate(lines, 1) if not line.strip()}
    if suffix == ".py":
        quiet |= _python(text)
    elif suffix == ".js":
        quiet |= _script(text)
    elif suffix in (".md", ".html"):
        quiet |= _fenced(text, MARKUP, False)
        close = cite._front(text)
        quiet |= {number for number, line in enumerate(lines, 1)
                  if 1 < number < close and line.lstrip().startswith("#")}
        quiet |= {1, close} if close else set()
    elif suffix in HASHED:
        quiet |= {number for number, line in enumerate(lines, 1)
                  if line.lstrip().startswith("#")}
    return [number for number in range(1, len(lines) + 1) if number not in quiet]


# @req> REQ-97409889@RWCU92P-iWbp 2c3ddu
def exempt(path):
    return corpus.is_test(path) or any(EXEMPT_FILES[entry].search(path)
                                       for entry in EXEMPTIONS)


def unknown_syntax(path):
    return PurePosixPath(path).suffix not in COMMENTED + COMMENTLESS


def _moved(path, was, now):
    before, after = code_lines(path, was), code_lines(path, now)
    was_lines, now_lines = _lines(was), _lines(now)
    matcher = difflib.SequenceMatcher(None, [was_lines[n - 1].rstrip("\r\n") for n in before],
                                      [now_lines[n - 1].rstrip("\r\n") for n in after],
                                      autojunk=False)
    return {after[at] for tag, _, _, first, last in matcher.get_opcodes() if tag != "equal"
            for at in range(first, last)}


# @req> REQ-27097724@BlP6FCylGOKS a5rd75
def _changed(root, base, texts):
    fork = cite._git(root, "merge-base", "HEAD", base).strip()
    named = cite._git(root, "-c", "core.quotePath=false", "diff", "--name-only",
                      "--no-renames", "-z", fork, "--").split("\0")
    named += cite._git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    held = set(filter(None, cite._git(root, "ls-tree", "-r", "--name-only", "-z",
                                      fork).split("\0")))
    changed = {}
    for path in filter(None, named):
        if texts.get(path) is None:
            continue
        was = cite._git(root, "show", f"{fork}:{path}") if path in held else ""
        changed[path] = _moved(path, was, texts[path])
    return changed


def _spans(numbers):
    spans = []
    for number in numbers:
        if spans and spans[-1][1] == number - 1:
            spans[-1][1] = number
        else:
            spans.append([number, number])
    return spans


def _remedy(path, first, last):
    if PurePosixPath(path).suffix in cite.COMMENTS:
        return f"cite it with reqctl tag {path} --from {first} --to {last} --req UID"
    return f"have the item governing it hold the whole file with reqctl tag {path} --req UID"


# @req> REQ-27534660@OcqGUyoB-NOR tml2jy
def problems(tree, root, citations, base=None):
    mode = settings.table(settings.read(root)[1], "uncited_code")["check"]["mode"]
    if mode not in MODES or (mode == "changed_lines" and not base):
        return []
    texts = {path.replace("\\", "/"): text for path, text in cite._sources(root)}
    reach = Reach(texts)
    covered = {(citation["path"], line) for citation in citations
               for line in citation["lines"]}
    for citation in citations:
        covered |= reach.reached(citation["path"], citation["lines"])
    whole = {path for item in corpus.items(tree)
             for path in corpus.mapping(item.data, corpus.WHOLE_FILES)}
    # @req> REQ-27097724@BlP6FCylGOKS jo2uxv
    changed = _changed(root, base, texts) if mode == "changed_lines" else None
    found = []
    for path, text in sorted(texts.items()):
        if text is None or path in whole or exempt(path):
            continue
        lines = code_lines(path, text)
        # @req> REQ-27097724@BlP6FCylGOKS x7jy55
        if changed is not None:
            lines = [line for line in lines if line in changed.get(path, ())]
        # @req+ REQ-33946954@dE-TCnSywwn3 u54yfr
        # @req+ REQ-46463201@OD-ZDKioCyPa aoss24
        uncovered = [line for line in lines if (path, line) not in covered]
        if uncovered and unknown_syntax(path):
            found.append(f"{path}: reqctl knows no comment syntax for this file -- have the "
                         f"item governing it hold the whole file with reqctl tag {path} "
                         "--req UID, or add its comment syntax to reqctl")
            continue
        # @req- aoss24
        # @req- u54yfr
        for first, last in _spans(uncovered):
            found.append(f"{path}:{first}-{last}: no statement citation covers this code "
                         f"-- {_remedy(path, first, last)}, or delete it")
    return found
