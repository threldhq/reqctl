import ast
import io
import keyword
import posixpath
import re
import tokenize

from . import corpus, typescript

SCRIPTED = (".js", ".html", *typescript.SUFFIXES)
CLASSIC = re.compile(r"<script(?=[\s/>])(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)"
                     r"(?:</script(?=[\s/>])|\Z)", re.IGNORECASE)
TYPED = re.compile(r"""\btype\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""", re.IGNORECASE)
JAVASCRIPT = {"", "text/javascript", "application/javascript", "text/ecmascript",
              "application/ecmascript"}
LEXED = re.compile(r""""(?:\\[\s\S]|[^"\\\n])*"|'(?:\\[\s\S]|[^'\\\n])*'"""
                   r"|(?P<tick>`)|(?P<brace>[{}])"
                   r"|(?P<remark>//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)|<!--[^\n]*|^[ \t]*-->[^\n]*)"
                   r"|(?P<pattern>/(?![*/])(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\n\[])+/[A-Za-z]*)",
                   re.MULTILINE)
PATTERN_AFTER = set("(,=:[!&|?{};+-*%<>~^")
PATTERN_WORDS = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void",
                 "throw", "yield", "await", "instanceof"}
PIECE = re.compile(r"[A-Za-z_$][\w$]*|\d[\w.]*|\.\.\.|[-+*/%&|^!<>=?:~]+|[{}()\[\];,.]")
IDENTIFIER = re.compile(r"[A-Za-z_$][\w$]*\Z")
CONTINUING = re.compile(r"(?!\+\+\Z|--\Z)[-+*/%&|^!<>=?:~]+\Z|[(\[,.]\Z|\.\.\.\Z")
OPENS, CLOSES = "{([", "})]"
BINDINGS = ("const", "let", "var")

# @req+ REQ-59827868@eeHZvhZPFhD3 4pmkcf
DEFINED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
ASSIGNED = (ast.Assign, ast.AnnAssign)
NESTED = (ast.If, ast.Try, ast.TryStar)
UNREAD = (tokenize.COMMENT, tokenize.NL, tokenize.ENDMARKER, tokenize.INDENT,
          tokenize.DEDENT)


def _statements(body):
    for node in body:
        yield node
        if isinstance(node, NESTED):
            for branch in ("body", "orelse", "finalbody"):
                yield from _statements(getattr(node, branch, []))
            for handler in getattr(node, "handlers", []):
                yield from _statements(handler.body)


def _bound(target):
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _bound(element)


def _span(node):
    first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
    return first, node.end_lineno or node.lineno


class Reach:
    def __init__(self, texts):
        # @req> REQ-22608177@cdmX9Aqh6XXC 2ap6ns
        self.texts = {path.replace("\\", "/"): text for path, text in texts.items()
                      if text is not None and path.endswith((".py", *SCRIPTED))}
        packages = {posixpath.dirname(path) for path in self.texts
                    if posixpath.basename(path) == "__init__.py"}
        self.roots = [".", *sorted({posixpath.dirname(folder) or "." for folder in packages
                                    if posixpath.dirname(folder) not in packages})]
        self.tables, self.streams, self.edges, self.digests = {}, {}, {}, {}
        self.scripts = {}

    # @req> REQ-22608177@cdmX9Aqh6XXC upntcv
    # @req> REQ-45330509@y34lW04HzVzy ad2sq3
    # @req> REQ-71419978@R9LaJT-ldfB9 eci2zb
    def _scripted(self, path):
        if path not in self.scripts:
            self.scripts[path] = (_typed(path, self.texts[path]) if path.endswith(typescript.SUFFIXES)
                                  else _script(path, self.texts[path]))
        return self.scripts[path]

    def _module(self, base):
        base = posixpath.normpath(base)
        for found in (base + ".py", posixpath.join(base, "__init__.py")):
            if found in self.texts:
                return found
        return None

    def _absolute(self, dotted, near):
        for root in (posixpath.dirname(near) or ".", *self.roots):
            found = self._module(posixpath.join(root, *dotted.split(".")))
            if found:
                return found
        return None

    def _relative(self, near, level, dotted):
        base = posixpath.dirname(near)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        return self._module(posixpath.join(base or ".", *(dotted or "").split(".")))

    def _table(self, path):
        if path in self.tables:
            return self.tables[path]
        # @req> REQ-22608177@cdmX9Aqh6XXC wgjme7
        # @req> REQ-45330509@y34lW04HzVzy egzrhu
        if path.endswith(SCRIPTED):
            self.tables[path] = (_reading(path, self.texts[path]).table
                                 if path.endswith(typescript.SUFFIXES)
                                 else _declarations(self._scripted(path)[0]))
            return self.tables[path]
        table = self.tables[path] = {}
        try:
            tree = ast.parse(self.texts[path])
        except (SyntaxError, ValueError):
            return table
        for node in _statements(tree.body):
            if isinstance(node, DEFINED):
                table.setdefault(node.name, []).append(("def", _span(node)))
            elif isinstance(node, ASSIGNED):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for target in targets:
                    for name in _bound(target):
                        table.setdefault(name, []).append(("def", _span(node)))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    dotted = alias.name if alias.asname else alias.name.split(".")[0]
                    found = self._absolute(dotted, path)
                    if found:
                        table.setdefault(alias.asname or dotted, []).append(("module", found))
            elif isinstance(node, ast.ImportFrom):
                source = (self._relative(path, node.level, node.module) if node.level
                          else self._absolute(node.module or "", path))
                for alias in node.names:
                    if source and alias.name != "*":
                        table.setdefault(alias.asname or alias.name, []).append(
                            ("from", (source, alias.name)))
        return table

    def _within(self, module, rest, seen):
        if not rest:
            return []
        held = self._resolve(module, rest, seen)
        if held or not module.endswith("__init__.py"):
            return held
        below = self._module(posixpath.join(posixpath.dirname(module), rest[0]))
        return self._within(below, rest[1:], seen) if below else []

    def _resolve(self, path, chain, seen=frozenset()):
        head, rest = chain[0], chain[1:]
        found = []
        for kind, what in self._table(path).get(head, []):
            if kind == "def":
                found.append((path, head))
            elif kind == "module":
                found += self._within(what, rest, seen)
            elif kind == "from" and what not in seen:
                source, name = what
                found += self._within(source, (name, *rest), seen | {what})
        return found

    def _stream(self, path):
        if path not in self.streams:
            held, depth = [], 0
            try:
                for token in tokenize.generate_tokens(io.StringIO(self.texts[path]).readline):
                    depth += {tokenize.INDENT: 1, tokenize.DEDENT: -1}.get(token.type, 0)
                    held.append((token.start[0], token.type, depth, token.string))
            except (tokenize.TokenError, IndentationError, SyntaxError):
                held = []
            self.streams[path] = held
        return self.streams[path]

    def _chains(self, path, lines):
        chains, chain, after_dot = [], [], False
        for line, kind, _, text in self._stream(path):
            if line not in lines or kind in UNREAD:
                continue
            if kind == tokenize.NAME and not keyword.iskeyword(text):
                if after_dot:
                    if chain:
                        chain.append(text)
                else:
                    if chain:
                        chains.append(tuple(chain))
                    chain = [text]
                after_dot = False
                continue
            after_dot = kind == tokenize.OP and text == "."
            if not after_dot and chain:
                chains.append(tuple(chain))
                chain = []
        if chain:
            chains.append(tuple(chain))
        return chains

    def _lines(self, key):
        path, name = key
        return {line for kind, span in self._table(path).get(name, []) if kind == "def"
                for line in range(span[0], span[1] + 1)}

    def _calls(self, path, lines):
        # @req> REQ-22608177@cdmX9Aqh6XXC um45e2
        # @req> REQ-71419978@R9LaJT-ldfB9 oyqqn7
        if path.endswith(SCRIPTED):
            pieces, table = self._scripted(path)[0], self._table(path)
            return [(path, name) for name in dict.fromkeys(
                piece for at, (line, piece) in enumerate(pieces)
                if line in lines and piece in table and (at == 0 or pieces[at - 1][1] != "."))]
        return [found for chain in dict.fromkeys(self._chains(path, lines))
                for found in self._resolve(path, chain)]

    def _digest(self, key):
        # @req> REQ-22608177@cdmX9Aqh6XXC g2mzok
        if key not in self.digests and key[0].endswith(SCRIPTED):
            said, remarks = self.texts[key[0]].split("\n"), self._scripted(key[0])[1]
            self.digests[key] = corpus.digest([said[n - 1].rstrip() for n in sorted(self._lines(key))
                                               if n not in remarks])
        if key not in self.digests:
            lines = self._lines(key)
            held, first = [], None
            for line, kind, depth, text in self._stream(key[0]):
                if line in lines and kind not in UNREAD:
                    first = depth if first is None else first
                    held.append([tokenize.tok_name[kind], depth - first,
                                 "" if kind == tokenize.NEWLINE else text])
            self.digests[key] = corpus.digest(
                held or [self.texts[key[0]].splitlines()[n - 1] for n in sorted(lines)])
        return self.digests[key]

    def _closure(self, path, lines):
        path = path.replace("\\", "/")
        if path not in self.texts:
            return set()
        todo, seen = self._calls(path, set(lines)), set()
        while todo:
            key = todo.pop()
            if key in seen:
                continue
            seen.add(key)
            if key not in self.edges:
                self.edges[key] = self._calls(key[0], self._lines(key))
            todo += self.edges[key]
        return seen

    def taken(self, path, lines):
        return [[held, name, self._digest((held, name))]
                for held, name in sorted(self._closure(path, lines))]

    def reached(self, path, lines):
        return {(key[0], line) for key in self._closure(path, lines)
                for line in self._lines(key)}
# @req- 4pmkcf


def _reading(path, text):
    return typescript.read(posixpath.splitext(path)[1], text)


def remarked(text, spans):
    chars = list(text)
    for start, end, kept in spans:
        if not kept:
            _blanked(chars, start, end)
    return {number for number, (said, kept) in
            enumerate(zip(text.split("\n"), "".join(chars).split("\n")), start=1)
            if said.strip() and not kept.strip()}


def _typed(path, text):
    reading = _reading(path, text)
    return reading.names, remarked(text, reading.spans)


def _blanked(chars, start, end):
    for at in range(start, end):
        if chars[at] != "\n":
            chars[at] = " "


def _bodies(path, text):
    if path.endswith(".js"):
        return [(0, len(text))]
    held = []
    for script in CLASSIC.finditer(text):
        typed = TYPED.search(script["attrs"])
        kind = next((one for one in typed.groups() if one is not None), "") if typed else ""
        if kind.strip().lower() in JAVASCRIPT:
            held.append(script.span("body"))
    return held


def _opens_pattern(text, at):
    back = at - 1
    while back >= 0 and text[back].isspace():
        back -= 1
    if back < 0 or text[back] in PATTERN_AFTER:
        return True
    word = back
    while word >= 0 and (text[word].isalnum() or text[word] in "_$"):
        word -= 1
    return text[word + 1:back + 1] in PATTERN_WORDS


def _lexed(text, at, end, code, bare, closing):
    depth = 0
    while (found := LEXED.search(text, at, end)) is not None:
        start, at = found.start(), found.end()
        if found["brace"] is not None:
            if closing and found[0] == "{":
                depth += 1
            elif closing and depth:
                depth -= 1
            elif closing:
                return at
        elif found["tick"] is not None:
            at = _template(text, at, end, code, bare)
            code[start] = "0"
        elif found["pattern"] is not None and not _opens_pattern(text, start):
            at = start + 1
        else:
            _blanked(code, start, at)
            if found["remark"] is not None:
                _blanked(bare, start, at)
            else:
                code[start] = "0"
    return end


def _template(text, at, end, code, bare):
    start = at - 1
    while at < end:
        if text[at] == "\\":
            at += 2
        elif text[at] == "`":
            _blanked(code, start, at + 1)
            return at + 1
        elif text.startswith("${", at):
            _blanked(code, start, at + 2)
            at = _lexed(text, at + 2, end, code, bare, closing=True)
            start = at - 1
        else:
            at += 1
    _blanked(code, start, end)
    return end


def _script(path, text):
    code, bare, at = list(text), list(text), 0
    for start, end in [*_bodies(path, text), (len(text), len(text))]:
        for chars in (code, bare):
            _blanked(chars, at, start)
        _lexed(text, start, end, code, bare, closing=False)
        at = end
    pieces, line, last = [], 1, 0
    joined = "".join(code)
    for found in PIECE.finditer(joined):
        line += joined.count("\n", last, found.start())
        last = found.start()
        pieces.append((line, found[0]))
    remarks = {number for number, (said, kept) in
               enumerate(zip(text.split("\n"), "".join(bare).split("\n")), start=1)
               if said.strip() and not kept.strip()}
    return pieces, remarks


def _declared(pieces, at):
    names, depth, kind = [], 0, pieces[at][1]
    at += 1
    if kind == "function":
        while at < len(pieces) and pieces[at][1] == "*":
            at += 1
        if at < len(pieces) and IDENTIFIER.match(pieces[at][1]):
            names.append(pieces[at][1])
        opened = False
        while at < len(pieces):
            line, piece = pieces[at]
            opened = opened or (piece == "{" and depth == 0)
            depth += (piece in OPENS) - (piece in CLOSES)
            at += 1
            if opened and depth == 0:
                return names, line, at
        return names, pieces[-1][0], at
    expecting, patterned = True, False
    while at < len(pieces):
        line, piece = pieces[at]
        if depth == 0 and (piece in BINDINGS or piece == "function" and _starts(pieces, at)):
            return names, pieces[at - 1][0], at
        at += 1
        opening = depth == 0 and expecting and piece in ("{", "[")
        if IDENTIFIER.match(piece) and (depth == 0 and expecting or patterned):
            names.append(piece)
        if depth == 0:
            expecting = piece == ","
            if piece == ";":
                return names, line, at
        depth += (piece in OPENS) - (piece in CLOSES)
        patterned = (patterned or opening) and depth > 0
    return names, pieces[-1][0], at


def _starts(pieces, at):
    if at == 0:
        return True
    line, before = pieces[at - 1]
    if before in ("async", "export", "default") and (at < 2 or pieces[at - 2][1] != "."):
        return _starts(pieces, at - 1)
    return before in (";", "}") or (line < pieces[at][0] and not CONTINUING.match(before))


def _declarations(pieces):
    table, depth, at = {}, 0, 0
    while at < len(pieces):
        line, piece = pieces[at]
        if depth == 0 and (piece in BINDINGS and (at == 0 or pieces[at - 1][1] != ".")
                           or piece == "function" and _starts(pieces, at)):
            first = (pieces[at - 1][0] if piece == "function" and at
                     and pieces[at - 1][1] == "async" else line)
            names, last, at = _declared(pieces, at)
            for name in names:
                table.setdefault(name, []).append(("def", (first, last)))
            continue
        depth += (piece in OPENS) - (piece in CLOSES)
        at += 1
    return table
