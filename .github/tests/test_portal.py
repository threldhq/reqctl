#!/usr/bin/env python3
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
PAGE = Path(__file__).resolve().parent / "portal_page.mjs"
RECORDER = """import sys
import urllib.request
from pathlib import Path

url, page, opened = sys.argv[1:]
try:
    direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    Path(page).write_bytes(direct.open(url, timeout=10).read())
except OSError as broken:
    Path(page).write_text(str(broken))
Path(opened).write_text(url)
"""
NAMED = re.compile(r"(?<![\w./:${-])([A-Za-z0-9-]+)/[A-Za-z0-9._-]+(?![\w/-])")
MEDIA = {"application", "text", "image", "font"}
CORPUS = "https://api.github.com/repos/{}/contents/corpus.json?ref=corpus-view"

faults = []


def case(name, got, want):
    if got != want:
        faults.append(f"{name}: expected {want}, got {got}")


def ran(argv, cwd, **given):
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                              check=False, **given)
    except (OSError, subprocess.TimeoutExpired) as broken:
        return subprocess.CompletedProcess(argv, 127, "", str(broken))


def repository(where, origin=None):
    where.mkdir()
    ran(["git", "init", "-q"], where)
    if origin:
        ran(["git", "remote", "add", "origin", origin], where)
    return where


def opened(page, search, remembered):
    done = ran(["node", str(PAGE), str(page), search, json.dumps(remembered)],
               ROOT)
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return {"drawn": done.stderr.strip(), "remembered": {}, "fetched": []}


with tempfile.TemporaryDirectory() as held:
    held = Path(held)
    source = held / "reqctl"
    shutil.copytree(ROOT / "reqctl", source, ignore=shutil.ignore_patterns(
        "build", "*.egg-info", "__pycache__"))
    ran([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
         "--no-index", "--quiet", "--wheel-dir", str(held), str(source)], ROOT)
    try:
        bundled = zipfile.ZipFile(next(held.glob("reqctl-*.whl"))).read(
            "reqctl/portal.html")
    except (StopIteration, KeyError):
        bundled = b""

    # @req+ REQ-90709998@VH8IkfXENTM5 ape4wa
    script = bundled[bundled.find(b"<script>"):].decode()
    case("the bundled portal writes no owner/repo",
         (sorted(set(re.findall(r"/repos/(.{9})", script))),
          sorted({found.group(0) for found in NAMED.finditer(script)
                  if found.group(1) not in MEDIA} - {"owner/repo"})),
         (["${repo()}"], []))
    # @req- ape4wa

    recorder = held / "recorder.py"
    recorder.write_text(RECORDER)
    served, opening = held / "served.html", held / "opened.txt"
    env = {**os.environ,
           "BROWSER": f"{sys.executable} {recorder} %s {served} {opening}"}

    # @req+ REQ-95796962@YsAwm-tWkbqN tltq7z
    elsewhere = held / "elsewhere"
    elsewhere.mkdir()
    for where in (elsewhere, repository(held / "unnamed"),
                  repository(held / "gitlab", "https://gitlab.com/owner/repo.git")):
        done = ran(["reqctl", "portal"], where, env=env, timeout=30)
        case(f"reqctl portal in {where.name} opens nothing and says why in "
             "one line", (done.returncode, len(done.stderr.splitlines()),
                          done.stderr.startswith("reqctl: "), opening.exists()),
             (1, 1, True, False))
    # @req- tltq7z

    # @req+ REQ-49576265@TZb-gviCuP5Y mqifye
    here = repository(held / "here", "https://github.com/owner/repo.git")
    running = subprocess.Popen(["reqctl", "portal"], cwd=here, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                               text=True)
    deadline = time.monotonic() + 30
    while (not (opening.exists() and opening.read_text())
           and running.poll() is None and time.monotonic() < deadline):
        time.sleep(0.1)
    url = urlsplit(opening.read_text() if opening.exists() else "")
    running.send_signal(signal.SIGINT)
    try:
        running.wait(timeout=15)
    except subprocess.TimeoutExpired:
        running.kill()
    case("reqctl portal opens the browser at a local address serving the "
         "portal the wheel bundles",
         (url.hostname, served.exists() and served.read_bytes() == bundled,
          running.returncode, running.stderr.read()),
         ("127.0.0.1", True, 0, ""))
    # @req- mqifye

    # @req+ REQ-53764133@hNDAdKGPLVUD 55xuwr
    search = f"?{url.query}"
    moved = opened(served, search, {"reqportal-repo": "other/repo",
                                    "reqportal-token": "t"})
    case("the portal remembers origin's repository in place of another and "
         "reads the corpus from it",
         (moved["remembered"].get("reqportal-repo"), moved["fetched"]),
         ("owner/repo", [CORPUS.format("owner/repo")]))
    # @req- 55xuwr

    # @req+ REQ-58466257@mDNTJurzxVOx 64qro5
    fresh = opened(served, search, {})
    case("the portal opens on origin's repository without the repository box",
         ('id="place"' in fresh["drawn"],
          'Repository: <span class="mono">owner/repo</span>' in fresh["drawn"]),
         (False, True))
    # @req- 64qro5

if faults:
    print("\n".join(faults))
    sys.exit(1)
print("portal self-test: 0 fault(s)")
sys.exit(0)
