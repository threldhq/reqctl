#!/usr/bin/env python3
import contextlib
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "guards"))
import rules_scope

faults = []

TREE = ["app/index.tsx", "app/routes/note.tsx", "__tests__/routes.test.tsx",
        ".github/workflows/ci.yml", ".github/install-gitleaks.sh",
        ".claude/hooks/session-start.sh", "reqctl/reqctl/cli.py", "README.md"]


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def matches(pattern, path):
    return bool(rules_scope.matcher(pattern).match(path))


def why(paths):
    listed = "\n".join(f'  - "{one}"' for one in paths)
    return rules_scope.faults(f"---\npaths:\n{listed}\n---\n\n# Rule\n",
                              "rule.md", TREE)


case("a directory glob reaches what is under it",
     matches("app/**", "app/routes/note.tsx"), True)
case("a directory glob stops at its own directory",
     matches("app/**", "__tests__/routes.test.tsx"), False)
case("a doubled star spans no directory at all",
     matches(".github/**/*.sh", ".github/install-gitleaks.sh"), True)
case("a doubled star spans several directories",
     matches("**/*.sh", ".claude/hooks/session-start.sh"), True)
case("a single star stops at the separator",
     matches("*.md", "app/index.md"), False)
case("a single star reaches within one segment",
     matches("reqctl/**/*.py", "reqctl/reqctl/cli.py"), True)
case("a question mark takes one character",
     matches("app/inde?.tsx", "app/index.tsx"), True)
case("a question mark does not take the separator",
     matches("app?index.tsx", "app/index.tsx"), False)
case("a class takes what it lists", matches("app/[ir]ndex.tsx",
                                            "app/index.tsx"), True)
case("a negated class refuses what it lists",
     matches("app/[!i]ndex.tsx", "app/index.tsx"), False)

def refusing(text, wanted):
    return any(wanted in one
               for one in rules_scope.faults(text, "rule.md", TREE))


def scoped(paths, wanted):
    return any(wanted in one for one in why(paths))


case("a rule scoped to the tree passes", why(["app/**", "**/*.sh"]), [])
case("a rule scoped to nothing is refused",
     scoped(["tests/**"], "matches no file in the tree"), True)
case("a rule scoped to everything is refused",
     scoped(["**/*"], "matches every file in the tree"), True)
case("patterns reaching every file only together are refused",
     scoped(["app/**", "__tests__/**", ".github/**", ".claude/**",
             "reqctl/**", "*.md"], "matches every file in the tree"), True)
case("one dead glob among live ones is still refused",
     len(why(["app/**", "src/**/*.ts"])), 1)
case("an unclosed class is refused, not raised",
     scoped(["app/[index.tsx"], "is not a glob: unclosed bracket"), True)
case("braces are refused rather than guessed at",
     scoped(["app/**/*.{ts,tsx}"], "expands braces; write each pattern out"),
     True)
case("a path that is not a string is refused",
     refusing("---\npaths:\n  - 7\n---\n\n# Rule\n", "is not a string"),
     True)

case("a rule with no frontmatter is refused",
     refusing("# Rule\n", "names no paths"), True)
case("a rule with frontmatter naming no paths is refused",
     refusing("---\nname: rule\n---\n\n# Rule\n", "names no paths"), True)
case("a bare string of paths is refused",
     refusing('---\npaths: "app/**"\n---\n\n# Rule\n',
              "not a list of globs"), True)
case("an empty list of paths is refused",
     refusing("---\npaths: []\n---\n\n# Rule\n", "not a list of globs"),
     True)
case("frontmatter that is not a mapping is refused",
     refusing("---\n7\n---\n\n# Rule\n", "not a mapping"), True)
case("frontmatter that is not YAML is refused",
     refusing("---\npaths: [\n---\n\n# Rule\n", "frontmatter is not YAML"),
     True)


def unlisted():
    with tempfile.TemporaryDirectory() as room:
        held = os.getcwd()
        os.chdir(room)
        try:
            rules_scope.tracked()
        except SystemExit as broken:
            return str(broken)
        finally:
            os.chdir(held)
    return ""


case("a tree git cannot list is refused, not walked as empty",
     "cannot list files" in unlisted(), True)


def scope():
    with contextlib.redirect_stdout(io.StringIO()):
        return rules_scope.main()


case("every rule in the repository reaches a file today", scope(), 0)


def scoped_in(build):
    with tempfile.TemporaryDirectory() as room:
        build(Path(room))
        held = os.getcwd()
        os.chdir(room)
        try:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = rules_scope.main()
            return code, out.getvalue()
        finally:
            os.chdir(held)


code, message = scoped_in(lambda room: None)
case("a missing .claude/rules directory is refused, not a silent pass",
     code, 1)
case("the refusal names the missing directory",
     ".claude/rules" in message, True)


def unscoped_rule(room):
    subprocess.run(["git", "init", "-q"], cwd=room, check=True)
    rules = room / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "bad.md").write_text("# a rule with no frontmatter\n")


code, message = scoped_in(unscoped_rule)
case("main() reports a real fault via ::error and refuses", code, 1)
case("main()'s output names the fault",
     "::error::" in message and "names no paths" in message, True)

if faults:
    print("\n".join(faults))
    sys.exit(1)
sys.exit(0)
