#!/usr/bin/env python3
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
CALLED = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+\.py)")

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def ran(argv, cwd, **given):
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              check=False, **given)
    except OSError as broken:
        return subprocess.CompletedProcess(argv, 127, "", str(broken))


def entries(name):
    return sorted(json.loads(ran(["reqctl", "--json", "context", name],
                                 ROOT).stdout)[0]["entries"])


def front(path):
    found = FRONT.match(path.read_text()) if path.is_file() else None
    return (yaml.safe_load(found.group(1)) or {}) if found else {}


def hooks(plugin):
    held = json.loads((plugin / "hooks" / "hooks.json").read_text())
    return [hook["command"] for group in held["hooks"]["PreToolUse"]
            for hook in group["hooks"]]


def holds(plugin, component):
    name, _, kind = component.rpartition("_")
    name = name.replace("_", "-")
    if kind == "skill":
        return front(plugin / "skills" / name / "SKILL.md").get("name") == name
    if kind == "agent":
        return front(plugin / "agents" / f"{name}.md").get("name") == name
    script = f"{PLUGIN_ROOT}/hooks/{name}.py"
    return (kind == "hook" and (plugin / "hooks" / f"{name}.py").is_file()
            and any(script in command for command in hooks(plugin)))


# @req+ REQ-38288492@1yCh_1wG8N-l fm5pgn
listed = json.loads(MARKETPLACE.read_text())
plugin = ROOT / next(one["source"] for one in listed["plugins"]
                     if one["name"] == "reqctl")

case("the plugin holds each plugin component",
     [one for one in entries("plugin_components") if not holds(plugin, one)], [])
# @req- fm5pgn

# @req+ REQ-13684791@_iUnF2f3QtDP vfxkgo
skill = plugin / "skills" / "elucidate"
steps = entries("synthesis_steps")
scripts = {step: [str(path.relative_to(skill)) for path in skill.rglob(f"{step}.py")]
           for step in steps}
calls = set(CALLED.findall((skill / "SKILL.md").read_text()))
case("the plugin holds a script for each synthesis step, and the elucidate "
     "skill calls it",
     [step for step, held in scripts.items() if len(held) != 1
      or not set(held) & calls], [])
with tempfile.TemporaryDirectory() as held:
    source = Path(held) / "reqctl"
    shutil.copytree(ROOT / "reqctl", source, ignore=shutil.ignore_patterns(
        "build", "*.egg-info", "__pycache__"))
    ran([sys.executable, "-m", "pip", "wheel", "--no-deps",
         "--no-build-isolation", "--no-index", "--quiet",
         "--wheel-dir", held, str(source)], ROOT)
    wheels = sorted(Path(held).glob("reqctl-*.whl"))
    members = zipfile.ZipFile(wheels[0]).namelist() if wheels else []
case("the reqctl wheel as built holds none of the synthesis steps",
     (len(wheels), [member for member in members if Path(member).stem in steps]),
     (1, []))
# @req- vfxkgo

# @req> REQ-61212158@EISsRx_ntdvz tguind
with tempfile.TemporaryDirectory() as held:
    repo, installed = Path(held) / "repo", Path(held) / "plugin"
    repo.mkdir()
    ran(["git", "init", "-q"], repo)
    within = plugin.relative_to(ROOT)
    shipping = ran(["git", "ls-files", "-z", "--cached", "--others",
                    "--exclude-standard", "--", str(within)], ROOT).stdout
    for each in filter(None, shipping.split("\0")):
        target = installed / Path(each).relative_to(within)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / each, target)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo),
           "CLAUDE_PLUGIN_ROOT": str(installed)}
    item = repo / "requirements" / "reqs" / "REQ-10000001.yml"
    asked = [("Bash", {"command": "git status"}, None),
             ("Write", {"file_path": str(item), "content": "text: x\n"}, "deny")]
    decided = []
    for command in hooks(installed):
        argv = shlex.split(command.replace(PLUGIN_ROOT, str(installed)))
        for tool, given, _ in asked:
            done = ran(argv, repo, env=env, input=json.dumps(
                {"tool_name": tool, "tool_input": given}))
            said = (json.loads(done.stdout)["hookSpecificOutput"]
                    ["permissionDecision"] if done.stdout.strip() else None)
            decided.append((tool, done.returncode, said))
    unloaded = [path.parent.name for path in (installed / "skills").glob("*/SKILL.md")
                if not (front(path).get("name") and front(path).get("description"))]
    case("the installed plugin's hook and skills run in a repository holding no "
         "requirements folder",
         (decided, unloaded, ran(["reqctl", "validate"], repo, env=env).returncode),
         ([(tool, 0, want) for tool, _, want in asked], [], 0))

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("plugin self-test: 0 fault(s)")
sys.exit(0)
