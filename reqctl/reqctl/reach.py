import ast
import io
import keyword
import posixpath
import tokenize

from . import corpus

# @req+ REQ-59827868@bWN38P4cOthQ 4pmkcf
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
        self.texts = {path.replace("\\", "/"): text for path, text in texts.items()
                      if text is not None and path.endswith(".py")}
        packages = {posixpath.dirname(path) for path in self.texts
                    if posixpath.basename(path) == "__init__.py"}
        self.roots = [".", *sorted({posixpath.dirname(folder) or "." for folder in packages
                                    if posixpath.dirname(folder) not in packages})]
        self.tables, self.streams, self.edges, self.digests = {}, {}, {}, {}

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
        return [found for chain in dict.fromkeys(self._chains(path, lines))
                for found in self._resolve(path, chain)]

    def _digest(self, key):
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

    def taken(self, path, lines):
        path = path.replace("\\", "/")
        if path not in self.texts:
            return []
        todo, seen = self._calls(path, set(lines)), set()
        while todo:
            key = todo.pop()
            if key in seen:
                continue
            seen.add(key)
            if key not in self.edges:
                self.edges[key] = self._calls(key[0], self._lines(key))
            todo += self.edges[key]
        return [[held, name, self._digest((held, name))] for held, name in sorted(seen)]
# @req- 4pmkcf
