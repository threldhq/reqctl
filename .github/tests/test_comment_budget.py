#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import comment_budget

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def found_in(name, text):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / name
        spot.write_text(text)
        kind = comment_budget.syntax_of(spot)
        return comment_budget.FINDERS[kind](spot, comment_budget.read(spot))


def lines_in(name, text):
    return sum(end - line + 1 for _, line, end, _ in found_in(name, text))


def kinds_in(name, text):
    return [what for what, _, _, _ in found_in(name, text)]


for source in ("import os", "from x import y", "x = compute(y)", "count += 1",
               "held: int = 0", "def helper(x):", "class Thing:",
               "return None", "if found: raise SystemExit(1)",
               "for path in paths:", "while True:", "with open(p) as fh:",
               "assert held is None", "del cache[key]",
               "process(item)", "self.save()", "print(debug_var)",
               "corpus.read(where)", "pass", "break", "continue"):
    case(f"commented-out {source!r}", comment_budget.is_code(f"# {source}"), True)

for prose in ("a heredoc body is data on stdin, never an operand",
              "assembled, not written: a literal tag would be scanned",
              "symlinks are followed so a vendored tree is scanned like any other",
              "read() names it, and better",
              "Swiss grouping", "and this False", "and this a date object",
              "YAML 1.1 sexagesimal made this 90", "a dropped digit", "lowercase",
              "The floor is below the current figure on purpose: it catches a slide",
              "Pinned to commit, not tag. A tag is mutable and belongs to someone else",
              "not an argparse type=: argparse converts only ValueError",
              "one build per tree", "left for --check to name",
              "RIGHT SINGLE QUOTATION MARK, what autocorrect substitutes",
              "for now, the register holds one entry", "if in doubt, refuse",
              "try the cheaper path first", "pass over a file that lists nothing",
              "with care, this stays cheap", "return value is the exit code",
              "import order here follows the stdlib convention",
              "Three cases: a tag, a branch, a commit."):
    case(f"prose {prose[:24]!r}", comment_budget.is_code(f"# {prose}"), False)

for block in ("# old = some_function(arg1,\n#                      arg2)",
              "# config = {\n#     'key': 'value',\n# }",
              "# settings = {\n#     'a': 1,\n\n#     'b': 2,\n# }",
              "#    if x:\n#\tdo_it()"):
    case(f"commented-out block {block.splitlines()[0]!r}",
         comment_budget.is_code(block), True)
case("an empty comment is not code", comment_budget.is_code("#"), False)
case("a bare name is not code", comment_budget.is_code("# helper"), False)

for first, rest in comment_budget.HALVES:
    name = first + rest
    for spelling in (name, f"{first} {rest}", f"{first}_{rest}", f"{first}-{rest}"):
        case(f"{spelling} refused",
             comment_budget.marked(f"# {spelling}: later"), [name])
    case(f"{name.lower()} is not refused: lower case is not the convention",
         comment_budget.marked(f"# {name.lower()}: later"), [])

for prose in ("a pin the binder holds", "there is nothing to do here",
              "this is not a hack, it is the contract", "the mastodon case",
              "what is left to do", "to do that, the guard reads stdin",
              "fix me is not what this says"):
    case(f"prose {prose[:20]!r} carries no marker",
         comment_budget.marked(f"# {prose}"), [])

case("a shebang is not counted",
     lines_in("sample.py", "#!/usr/bin/env python3\n# real\nx = 1  # trailing\n"), 2)
case("a docstring costs every line it spans",
     lines_in("sample.py", '"""One\ntwo\nthree."""\nx = 1\n'), 3)
case("docstrings are found at module, class and method",
     kinds_in("sample.py", '"""M."""\n\n\nclass A:\n    """C."""\n\n'
                           '    def b(self):\n        """D."""\n'),
     ["docstring", "docstring", "docstring"])
case("a hash inside a python string is not a comment",
     lines_in("sample.py", 'x = "# not a comment"\ny = 1  # yes\n'), 1)

case("a hash comment costs one line each",
     lines_in("sample.yml", "# one\n# two\nkey: value\n"), 2)
case("a trailing hash comment is counted",
     lines_in("sample.yml", "uses: acme/thing@abc # v1.2.3\n"), 1)
case("a hash inside a quoted yaml scalar is not a comment",
     lines_in("sample.yml", 'run: echo "a value # not a comment"\n'), 0)
case("a real comment after a quoted scalar is still counted",
     lines_in("sample.yml", 'run: echo "a value" # a real comment\n'), 1)
case("a hash with no space is not a trailing comment",
     lines_in("sample.yml", "image: acme/thing:1.0#sha\n"), 0)

case("a slash comment is counted",
     lines_in("sample.mjs", "const a = 1; // why\n"), 1)
case("a block comment costs every line it spans",
     lines_in("sample.mjs", "/* one\n   two\n   three */\nconst a = 1;\n"), 3)
case("a url inside a string is not a comment",
     lines_in("sample.mjs", 'const a = "https://example.com/x";\n'), 0)
case("json is read for comments too",
     lines_in("sample.json", '{\n  // a note\n  "a": 1\n}\n'), 1)

case("a markup comment is counted",
     lines_in("sample.html", "<p>x</p>\n<!-- a note -->\n"), 1)
case("a markup comment costs every line it spans",
     lines_in("sample.md", "# Heading\n\n<!-- one\ntwo -->\n"), 2)
case("a markdown heading is not a comment",
     lines_in("sample.md", "# Heading\n\n## Another\n"), 0)
case("script inside markup is read for slash comments",
     lines_in("sample.html", "<body>\n<script>\n// a note\n</script>\n</body>\n"), 1)


def refused(name, write):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / "sample.py"
        write(spot)
        try:
            comment_budget.survey([str(spot)], allowed=set())
        except SystemExit as clean:
            case(f"{name} refuses cleanly", str(clean).startswith("cannot read"), True)
        else:
            faults.append(f"{name}: read a file it cannot read")


refused("a dangling symlink", lambda p: p.symlink_to(p.parent / "absent.py"))
refused("an undecodable byte", lambda p: p.write_bytes(b"x = 1  # \xff\xfe\n"))
refused("a file that is a directory", lambda p: p.mkdir())
refused("a file that will not tokenize",
        lambda p: p.write_text("def broken(:\n# a comment\n"))


def surveyed(name, text, allowed=frozenset()):
    with tempfile.TemporaryDirectory() as room:
        spot = Path(room) / name
        spot.write_bytes(text.encode() if isinstance(text, str) else text)
        counted, refusals = comment_budget.survey([str(spot)], allowed=set(allowed))
        return counted, [why for _, _, why, _ in refusals]


case("a commented-out block spanning lines is refused, not judged line by line",
     surveyed("sample.py", "x = 1\n# old = some_function(arg1,\n"
                           "#                      arg2)\n")[1],
     ["commented-out code"])
case("a block split by a blank line is still one block",
     surveyed("sample.py", "x = 1\n# settings = {\n#     'a': 1,\n\n"
                           "#     'b': 2,\n# }\n")[1],
     ["commented-out code"])
case("comments split by a line of code are not one block",
     surveyed("sample.py", "# a heredoc body is data on stdin,\nx = 1\n"
                           "# never an operand\n")[1], [])
case("a block of prose spanning lines is not refused",
     surveyed("sample.py", "x = 1\n# a heredoc body is data on stdin,\n"
                           "# never an operand\n")[1], [])
case("a marker comment that also parses as a statement is named once, "
     "as the marker",
     surveyed("sample.py", "x = 1\n# TODO: later\n")[1], ["TODO marker"])

for first, rest in comment_budget.HALVES:
    case(f"survey refuses a {first}{rest} marker, not just the matcher",
         f"{first}{rest} marker" in
         surveyed("sample.py", f"x = 1\n# {first}{rest}: later\n")[1], True)
    case(f"survey refuses a {first}{rest} marker in yaml too",
         surveyed("sample.yml", f"# {first}{rest}: later\nkey: value\n")[1],
         [f"{first}{rest} marker"])

case("a file type with no comment rule is refused, never skipped",
     surveyed("sample.rb", "# a comment nothing here knows how to read\n")[1],
     ["no comment rule for this file type"])
case("a file type with no comment rule counts nothing it cannot read",
     surveyed("sample.rb", "# a comment nothing here knows how to read\n")[0], 0)
case("a generated file is skipped",
     surveyed("sample.txt", "#\n# This file is autogenerated by pip-compile\n"
                            "#\nacme==1.0  # via thing\n")[0], 0)
case("a generated marker below the declared head does not exempt",
     surveyed("sample.txt", "# one\n# two\n# three\n# four\n# five\n"
                            "# autogenerated by nothing\n")[0], 6)
case("a binary file is skipped rather than refused",
     surveyed("sample.png", b"\x89PNG\r\n\x1a\n\x00\x00 a comment\n"), (0, []))
case("a corpus file is left to reqctl",
     comment_budget.survey(["requirements/reqs/REQ-10532346.yml"],
                           allowed=set()), (0, []))


case("survey charges a docstring every line it spans",
     surveyed("sample.py", '"""One\ntwo\nthree."""\nx = 1\n')[0], 3)
case("survey charges a block comment every line it spans",
     surveyed("sample.mjs", "/* one\n   two\n   three */\nconst a = 1;\n")[0], 3)
case("survey charges a markup comment every line it spans",
     surveyed("sample.html", "<p>x</p>\n<!-- one\ntwo\nthree -->\n")[0], 3)


def exempted(held, allowed):
    with tempfile.TemporaryDirectory() as room:
        spot = os.getcwd()
        for name, text in held.items():
            (Path(room) / name).write_text(text)
        os.chdir(room)
        try:
            counted, refusals = comment_budget.survey(sorted(held),
                                                      allowed=allowed)
            return counted, [why for _, _, why, _ in refusals]
        finally:
            os.chdir(spot)


IGNORE = "# zizmor: ignore[artipacked]"

case("an exempted directive is not counted",
     exempted({"sample.yml": f"with: {IGNORE}\n"}, {("sample.yml", IGNORE)}),
     (0, []))
case("an exemption that matches nothing is refused, so it cannot rot",
     exempted({"sample.yml": "key: value\n"},
              {("sample.yml", "# shellcheck disable=SC2016")}),
     (0, ["exemption matches nothing here"]))
case("an exemption is spent on its own file, never the same text elsewhere",
     exempted({"kept.yml": f"with: {IGNORE}\n", "other.yml": f"with: {IGNORE}\n"},
              {("kept.yml", IGNORE)}),
     (1, []))
case("a block matching an exemption is not judged as commented-out code",
     exempted({"sample.py": "x = 1\n# old = some_function(arg1,\n"
                            "#                      arg2)\n"},
              {("sample.py", "# old = some_function(arg1,"),
               ("sample.py", "#                      arg2)")}),
     (0, []))

for path, body in comment_budget.ALLOWED:
    case(f"the exemption in {path} is a directive a tool reads",
         body.startswith("# zizmor: ignore[") or body.startswith("# shellcheck "),
         True)
case("the exemptions are the three proven load-bearing directives",
     len(comment_budget.ALLOWED), 3)


def scanned_in(build):
    with tempfile.TemporaryDirectory() as room:
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        held = os.getcwd()
        os.chdir(room)
        try:
            return comment_budget.scanned()
        finally:
            os.chdir(held)


def staged(room):
    (room / "tracked.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=room, check=True)


case("a staged file is scanned", scanned_in(staged), ["tracked.py"])
case("an unstaged file is scanned too, or the guard misses the branch "
     "that adds the comments",
     scanned_in(lambda room: (staged(room), (room / "new.py").write_text(
         "# a comment nothing has staged yet\n"))),
     ["new.py", "tracked.py"])
case("an ignored file is not",
     scanned_in(lambda room: (staged(room),
                              (room / ".gitignore").write_text("skip.py\n"),
                              (room / "skip.py").write_text("# ignored\n"))),
     [".gitignore", "tracked.py"])
case("a file of any type is scanned, not just python",
     scanned_in(lambda room: (staged(room),
                              (room / "notes.md").write_text("x\n"),
                              (room / "shape.yml").write_text("a: 1\n"))),
     ["notes.md", "shape.yml", "tracked.py"])
case("a skill's own python is scanned like anything else",
     scanned_in(lambda room: (staged(room),
                              (room / ".claude" / "skills" / "s").mkdir(parents=True),
                              (room / ".claude" / "skills" / "s" / "s.py")
                              .write_text("x = 1\n"))),
     [".claude/skills/s/s.py", "tracked.py"])


def budget(ceiling):
    with contextlib.redirect_stdout(io.StringIO()):
        return comment_budget.main(ceiling)


counted, refusals = comment_budget.survey(comment_budget.scanned())
case("the repository refuses nothing today", [why for _, _, why, _ in refusals], [])
case("the budget refuses a count above it", budget(counted - 1), 1)
case("the budget refuses a count below it", budget(counted + 1), 1)
case("the budget passes only the count itself", budget(counted), 0)


def unlisted():
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        os.chdir(room)
        try:
            comment_budget.scanned()
        except SystemExit as broken:
            return str(broken)
        finally:
            os.chdir(held)
    return ""


case("a tree git cannot list is refused, not walked as empty",
     "cannot list files" in unlisted(), True)


def refusing_run(build, ceiling):
    with tempfile.TemporaryDirectory() as room:
        subprocess.run(["git", "init", "-q"], cwd=room, check=True)
        build(Path(room))
        held = os.getcwd()
        os.chdir(room)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = comment_budget.main(ceiling)
            return code, out.getvalue()
        finally:
            os.chdir(held)


def marked_file(room):
    (room / "bad.py").write_text("x = 1\n# TODO: fix this\n")
    subprocess.run(["git", "add", "-A"], cwd=room, check=True)


code, output = refusing_run(marked_file, 0)
case("main() reports a real fault via ::error and refuses", code, 1)
case("main()'s output names the fault",
     "TODO marker" in output, True)


CITE = "@" + "req+"
TAG = f"{CITE} GUARD-12345678@abcdefghijkl abcdef"
PINNED = f"# {TAG}"
RETIRED = "@" + "req: GUARD-12345678@abcdefghijkl"

case("a pinned citation costs the budget nothing",
     surveyed("cited.py", f"{PINNED}\nx = 1\n")[0], 0)
case("an unpinned citation costs the budget nothing either",
     surveyed("cited.py", f"# {CITE} GUARD-12345678 abcdef\nx = 1\n")[0], 0)
case("a one-comment citation costs the budget nothing either",
     surveyed("cited.py", f"# {'@' + 'req>'} GUARD-12345678@abcdefghijkl abcdef\nx = 1\n")[0], 0)
case("the retired single-line tag costs the budget as any comment does",
     surveyed("cited.py", f"# {RETIRED}\nx = 1\n")[0], 1)
case("prose beside a citation still costs the budget",
     surveyed("cited.py", f"{PINNED}\n# what this does\nx = 1\n")[0], 1)
case("a marker inside a citation is still refused",
     surveyed("cited.py", f"{PINNED} TODO\nx = 1\n")[1], ["TODO marker"])
case("a citation is never read as commented-out code",
     surveyed("cited.py", f"{PINNED}\nx = 1\n")[1], [])
case("commented-out code around a citation is still refused",
     surveyed("cited.py", f"{PINNED}\n# import os\n# x = compute(y)\n")[1],
     ["commented-out code"])
case("a citation is exempt in every comment syntax the guard reads",
     [surveyed(name, body)[0] for name, body in (
         ("cited.py", f"{PINNED}\nx = 1\n"),
         ("cited.py", f"x = 1  {PINNED}\n"),
         ("cited.js", f"// {TAG}\nx = 1\n"),
         ("cited.js", f"/* {TAG} */\nx = 1\n"),
         ("cited.md", f"<!-- {TAG} -->\n"))], [0] * 5)
case("a citation sharing its comment with anything else is not exempt",
     [surveyed(name, body)[0] for name, body in (
         ("cited.py", f"{PINNED} import os\nx = 1\n"),
         ("cited.js", f"// {TAG} and an essay\nx = 1\n"),
         ("cited.js", f"/* prose\n{TAG}\nmore prose\n*/\nx = 1\n"),
         ("cited.md", f"<!-- a note {TAG} and more -->\n"))], [1, 1, 4, 1])
case("a docstring holding a citation is still a docstring",
     surveyed("cited.py",
              f'"""\nprose one.\nprose two.\n{TAG}\n"""\nx = 1\n')[0], 5)
case("a citation inside commented-out code does not hide it",
     surveyed("cited.py",
              f"# result = f(arg1,\n{PINNED}\n#            arg2)\n")[1],
     ["commented-out code"])

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
