#!/usr/bin/env python3
import json
import subprocess
import sys
import tempfile
from pathlib import Path

faults = []


def reqctl(root, *args):
    done = subprocess.run(["reqctl", *args], cwd=root, capture_output=True, text=True,
                          check=False)
    return done.returncode, done.stdout + done.stderr


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def minted(root, text):
    code, said = reqctl(root, "new", "requirement", "--text", text)
    return said.strip().splitlines()[-1] if code == 0 else None


with tempfile.TemporaryDirectory() as held:
    root = Path(held)
    (root / "requirements").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    reqctl(root, "new", "term", "--term", "portal", "--alias", "web page",
           "--definition", "The page a person reads requirements on.",
           "--unclaimed", "reqctl portal=the command name",
           "--unclaimed", "web page cache=a browser store")
    word = minted(root, "When reqctl portal is run, the product shall open a page.")
    alias = minted(root, "When the web page cache is cleared, the product shall "
                         "open a page.")
    outside = minted(root, "When the portal loads, the product shall open a page.")
    reqctl(root, "revise", "portal", "--status", "approved")
    _, said = reqctl(root, "validate")
    problems = [line for line in said.splitlines() if " uses " in line]
    # @req+ REQ-24481048@ZhiYUpKwnPlA efpgbn
    case("the word inside a recorded phrase is accepted unlinked",
         [p for p in problems if p.startswith(f"{word}:")], [])
    case("an alias inside a recorded phrase is accepted unlinked",
         [p for p in problems if p.startswith(f"{alias}:")], [])
    case("the word outside any recorded phrase is still refused",
         any(p.startswith(f"{outside}:") and '"portal"' in p for p in problems), True)
    # @req- efpgbn
    # @req+ REQ-88221320@tXvROEk2-d6r fpppob
    case("each accepted occurrence is stated with the term and the phrase",
         f'{word}: "reqctl portal" is not portal -- the command name' in said
         and f'{alias}: "web page cache" is not portal -- a browser store' in said,
         True)
    _, stated = reqctl(root, "--json", "validate")
    case("the accepted occurrences are stated under --json too",
         f'{word}: "reqctl portal" is not portal -- the command name'
         in json.loads(stated)["unclaimed"], True)
    # @req- fpppob
    refusal = 'portal: records "reqctl portal" as not the term but gives no reason'
    code, said = reqctl(root, "revise", "portal", "--unclaimed", "reqctl portal=")
    # @req+ REQ-15469759@ETBwvNW6rbpC i3kojl
    case("recording a phrase without a reason is refused",
         code != 0 and refusal in said, True)
    held = root / "requirements" / "terms" / "portal.yml"
    held.write_text(held.read_text().replace("the command name", "''"))
    _, said = reqctl(root, "validate")
    case("a phrase recorded without a reason refuses the term and names it",
         refusal in said, True)
    # @req- i3kojl

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("unclaimed phrases self-test: 0 fault(s)")
sys.exit(0)
