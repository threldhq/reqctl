#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "requirements-guard.py"
if not HOOK.is_file():
    sys.exit(f"guard not found at {HOOK}")
if not os.access(HOOK, os.X_OK):
    sys.exit(f"guard is not executable: {HOOK}")
D, A = "deny", "allow"
C = "clear"

WORKSPACE = tempfile.TemporaryDirectory()


def repo(name, branch, tracked_edit=False, untracked_file=False, ignored_file=False):
    root = Path(WORKSPACE.name) / name

    def git(*args):
        subprocess.run(["git", "-C", str(root), *args], check=True,
                       capture_output=True)

    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True,
                   capture_output=True)
    git("symbolic-ref", "HEAD", f"refs/heads/{branch}")
    git("config", "user.email", "guard-test@example.invalid")
    git("config", "user.name", "guard test")
    (root / "kept.txt").write_text("committed\n")
    if ignored_file:
        (root / ".gitignore").write_text("ignored.txt\n")
    git("add", "-A")
    git("commit", "-qm", "first")
    if tracked_edit:
        (root / "kept.txt").write_text("edited and never committed\n")
    if untracked_file:
        (root / "loose.txt").write_text("never added\n")
    if ignored_file:
        (root / "ignored.txt").write_text("build output\n")
    return {"CLAUDE_PROJECT_DIR": str(root)}


ON_MAIN = repo("on-main", "main")
ON_BRANCH = repo("on-branch", "claude/work")
TRACKED_EDIT = repo("tracked-edit", "claude/work", tracked_edit=True)
UNTRACKED = repo("untracked", "claude/work", untracked_file=True)
IGNORED_ONLY = repo("ignored-only", "claude/work", ignored_file=True)

NOT_A_REPO = Path(WORKSPACE.name) / "not-a-repo"
NOT_A_REPO.mkdir()
NO_REPO = {"CLAUDE_PROJECT_DIR": str(NOT_A_REPO), "GIT_CEILING_DIRECTORIES": WORKSPACE.name}

CASES = [
    (D, "Edit REQ item",        "Edit", {"file_path": "requirements/reqs/REQ-84927103.yml"}),
    (D, "Write PARAM item",     "Write", {"file_path": "/srv/checkout/requirements/params/PARAM-00042917.yml"}),
    (D, "Write baseline",       "Write", {"file_path": "requirements/baselines/BASELINE-0001.yml"}),
    (D, "Write the baseline",   "Write", {"file_path": "requirements/baseline.yml"}),
    (D, "Write baseline .yaml", "Write", {"file_path": "/srv/checkout/requirements/baseline.yaml"}),
    (D, "Edit the baseline",    "Edit", {"file_path": "requirements/baseline.yml"}),
    (D, "rm the baseline",      "Bash", {"command": "rm requirements/baseline.yml"}),
    (D, "redirect to baseline", "Bash", {"command": "echo x > requirements/baseline.yml"}),
    (D, "git checkout baseline", "Bash",
     {"command": "git checkout --theirs requirements/baseline.yml"}),
    (D, "cat the baseline",     "Bash", {"command": "cat requirements/baseline.yml"}),
    (D, "jq a data item",       "Bash", {"command": "jq . requirements/data/DATA-79972628.yml"}),
    (D, "wc the baseline",      "Bash", {"command": "wc -l requirements/baseline.yml"}),
    (A, "ls an item folder",    "Bash", {"command": "ls requirements/reqs"}),
    (A, "stat the baseline",    "Bash", {"command": "stat requirements/baseline.yml"}),
    (A, "git show baseline",    "Bash", {"command": "git show HEAD:requirements/baseline.yml"}),
    (D, "sed -i on corpus",     "Bash", {"command": "sed -i s/a/b/ requirements/reqs/REQ-84927103.yml"}),
    (D, "sed --in-place",       "Bash", {"command": "sed --in-place s/a/b/ requirements/reqs/REQ-84927103.yml"}),
    (D, "redirect into corpus", "Bash", {"command": "echo x > requirements/reqs/REQ-1.yml"}),
    (D, "rm an item",           "Bash", {"command": "rm requirements/reqs/REQ-1.yml"}),

    (D, "Edit TERM item",       "Edit", {"file_path": "requirements/terms/TERM-79972628.yml"}),
    (D, "Edit DATA item",       "Edit", {"file_path": "requirements/data/DATA-79972628.yml"}),
    (D, "redirect into data",   "Bash", {"command": "echo x > requirements/data/DATA-1.yml"}),
    (D, "rm a data item",       "Bash", {"command": "rm requirements/data/DATA-1.yml"}),
    (D, "read a data item",     "Bash", {"command": "cat requirements/data/DATA-79972628.yml"}),
    (D, "Write TERM item",      "Write", {"file_path": "/srv/checkout/requirements/terms/TERM-28439834.yml"}),
    (D, "redirect into terms",  "Bash", {"command": "echo x > requirements/terms/TERM-1.yml"}),
    (D, "sed -i on terms",      "Bash", {"command": "sed -i s/a/b/ requirements/terms/TERM-1.yml"}),
    (D, "rm a term",            "Bash", {"command": "rm requirements/terms/TERM-1.yml"}),
    (D, "glob over terms",      "Bash", {"command": "rm requirements/terms/*.yml"}),
    (A, "Write a terms look-alike", "Write", {"file_path": "requirements/terms-backup/notes.txt"}),

    (D, "git push --force",     "Bash", {"command": "git push --force origin main"}),
    (D, "git push -f",          "Bash", {"command": "git push -f"}),
    (D, "force-with-lease",     "Bash", {"command": "git push --force-with-lease -u origin br"}),

    (D, "append into corpus",   "Bash", {"command": "echo x >> requirements/params/PARAM-1.yml"}),
    (D, "tee into corpus",      "Bash", {"command": "echo x | tee requirements/reqs/REQ-1.yml"}),

    (A, "stderr redirect",      "Bash", {"command": "ls requirements/reqs requirements/params 2>/dev/null"}),
    (D, "read with a pager",    "Bash", {"command": "cat requirements/reqs/REQ-1.yml 2>&1"}),
    (A, "redirect elsewhere",   "Bash", {"command": "ls requirements/reqs > /tmp/listing.txt"}),

    (A, "Edit schema",          "Edit", {"file_path": "requirements/schemas/requirement.schema.yaml"}),
    (A, "Edit source",          "Edit", {"file_path": "src/api/handler.ts"}),

    (D, "Write notes into reqs", "Write", {"file_path": "requirements/reqs/notes.txt"}),
    (D, "Write a 7-digit uid",  "Write", {"file_path": "requirements/reqs/REQ-8492710.yml"}),
    (D, "Write a lowercase uid", "Write", {"file_path": "requirements/params/param-84927103.yml"}),
    (D, "Write a nested item",  "Write", {"file_path": "requirements/reqs/drafts/REQ-84927103.yml"}),
    (A, "Edit a lockfile",      "Edit", {"file_path": "reqctl/requirements-lock.txt"}),

    (A, "rm a backup look-alike", "Bash", {"command": "rm -rf requirements/reqs-backup/file.txt"}),
    (A, "sed an -old look-alike", "Bash", {"command": "sed -i s/a/b/ requirements/params-old/x.yml"}),
    (A, "rm a .bak look-alike",  "Bash", {"command": "rm requirements/reqs.bak/x"}),
    (A, "Write into a look-alike", "Write", {"file_path": "requirements/reqs-backup/notes.txt"}),
    (D, "quoted corpus dir",     "Bash", {"command": "rm -r 'requirements/reqs'"}),
    (A, "reqctl new",           "Bash", {"command": "reqctl new requirement"}),
    (A, "normal push",          "Bash", {"command": "git push -u origin claude/branch"}),
    (A, "list corpus",          "Bash", {"command": "ls requirements/reqs/"}),
    (D, "read an item",         "Bash", {"command": "cat requirements/reqs/REQ-84927103.yml"}),
    (D, "grep the corpus",      "Bash", {"command": "grep -rn 'shall' requirements/reqs/"}),
    (A, "ordinary git log",     "Bash", {"command": "git log --oneline -8"}),
    (A, "Read the README",      "Read", {"file_path": "/home/user/reqctl/README.md"}),
    (A, "Grep source",          "Grep", {"pattern": "capture", "path": "reqctl/"}),

    (D, "Read a requirement item", "Read", {"file_path": "requirements/reqs/REQ-84927103.yml"}),
    (D, "Read the baseline",    "Read", {"file_path": "requirements/baseline.yml"}),
    (D, "Grep the corpus",      "Grep", {"pattern": "shall", "path": "requirements/reqs"}),
    (D, "Glob the corpus",      "Glob", {"pattern": "requirements/reqs/*.yml"}),
    (A, "Read a schema",        "Read", {"file_path": "requirements/schemas/requirement.schema.yaml"}),

    (D, "redirect to a single-quoted item", "Bash", {"command": "echo x > 'requirements/reqs/REQ-1.yml'"}),
    (D, "redirect to a double-quoted item", "Bash", {"command": 'echo x >> "requirements/reqs/REQ-1.yml"'}),
    (D, "heredoc into a quoted item", "Bash",
     {"command": "cat > 'requirements/reqs/REQ-1.yml' <<'EOF'\nx\nEOF"}),
    (D, "redirect to a quoted dir prefix", "Bash",
     {"command": 'echo x > "requirements"/reqs/REQ-1.yml'}),

    (D, "glob root req*",       "Bash", {"command": "rm req*/reqs/REQ-1.yml"}),
    (D, "glob root requirement?", "Bash", {"command": "rm requirement?/reqs/REQ-1.yml"}),
    (D, "glob root bracket",    "Bash", {"command": "rm [r]equirements/reqs/REQ-1.yml"}),
    (D, "glob root brace",      "Bash", {"command": "rm {requirements,x}/reqs/REQ-1.yml"}),
    (A, "glob elsewhere stays allowed", "Bash", {"command": "rm -rf /tmp/build/*"}),

    (D, "backslash before an alphanumeric hides the root", "Bash",
     {"command": "rm req\\uirements/reqs/REQ-1.yml"}),

    (D, "git checkout an item",  "Bash", {"command": "git checkout HEAD~1 -- requirements/reqs/REQ-84927103.yml"}),
    (D, "git restore a corpus dir", "Bash", {"command": "git restore --source=HEAD~5 requirements/reqs/"}),
    (D, "git checkout params",  "Bash", {"command": "git checkout main -- requirements/params/"}),

    (D, "python heredoc writer", "Bash", {"command": "python3 - <<'EOF'\nopen('requirements/reqs/REQ-84927103.yml','w')\nEOF"}),
    (D, "python script file",   "Bash", {"command": "python3 /tmp/rewrite.py requirements/reqs/"}),
    (D, "node over the corpus", "Bash", {"command": "node -e \"require('fs').writeFileSync('requirements/reqs/REQ-1.yml','')\""}),

    (D, "force push +refspec",  "Bash", {"command": "git push origin +main"}),
    (D, "force push +HEAD:main", "Bash", {"command": "git push origin +HEAD:main"}),

    (D, "force push -uf",       "Bash", {"command": "git push -uf origin main"}),
    (D, "force push -fu",       "Bash", {"command": "git push -fu origin main"}),
    (D, "force push -nf",       "Bash", {"command": "git push -nf origin br"}),

    (A, "push -un is not force", "Bash", {"command": "git push -un origin br"}),
    (A, "follow-tags is not -f", "Bash", {"command": "git push --follow-tags origin br"}),
    (A, "-f in the next command", "Bash", {"command": "git push -u origin br; tar -cf /tmp/o.tar ."}),
    (A, "commit -m holding -f",  "Bash", {"command": "git commit -m 'use -f later'"}, ON_BRANCH),

    (A, "git log a corpus path", "Bash", {"command": "git log --oneline -- requirements/reqs/"}),
    (A, "git diff the corpus",  "Bash", {"command": "git diff requirements/reqs/REQ-84927103.yml"}),
    (A, "--no-pager reads",     "Bash",
     {"command": "git --no-pager diff -- requirements/reqs/"}),
    (A, "-P reads",             "Bash",
     {"command": "git -P log --oneline -- requirements/reqs/"}),
    (A, "--paginate reads",     "Bash",
     {"command": "git --paginate show HEAD:requirements/baseline.yml"}),
    (A, "-c before --no-pager", "Bash",
     {"command": "git -c core.pager=cat --no-pager diff -- requirements/reqs/"}),
    (D, "--no-pager does not lift a write", "Bash",
     {"command": "git --no-pager diff --output=requirements/reqs/REQ-84927103.yml HEAD"}),
    (A, "git status",           "Bash", {"command": "git status --short"}),
    (A, "python unrelated",     "Bash", {"command": "python3 -m pytest reqctl/tests -q"}),

    (D, "NotebookEdit an item",  "NotebookEdit",
     {"notebook_path": "/home/user/reqctl/requirements/reqs/REQ-84927103.yml", "new_source": "x"}),
    (D, "NotebookEdit baselines", "NotebookEdit",
     {"notebook_path": "/home/user/reqctl/requirements/baselines/scratch.ipynb", "new_source": "x"}),
    (A, "NotebookEdit elsewhere", "NotebookEdit",
     {"notebook_path": "/home/user/reqctl/analysis/notes.ipynb", "new_source": "x"}),

    (D, "double slash Edit",    "Edit", {"file_path": "requirements//reqs/REQ-84927103.yml"}),
    (D, "dot segment Write",    "Write", {"file_path": "requirements/./reqs/REQ-84927103.yml"}),
    (D, "double slash abs Edit", "Edit", {"file_path": "/home/user/reqctl/requirements//reqs/REQ-84927103.yml"}),
    (D, "double slash baseline", "Write", {"file_path": "requirements//baselines/BASELINE-0001.yml"}),
    (D, "double slash sed -i",  "Bash", {"command": "sed -i s/draft/approved/ requirements//reqs/REQ-84927103.yml"}),
    (D, "dot segment redirect", "Bash", {"command": "echo x > requirements/.//reqs/REQ-1.yml"}),
    (D, "double slash rm",      "Bash", {"command": "rm requirements//reqs/REQ-1.yml"}),

    (A, "revise citing add",    "Bash",
     {"command": "reqctl revise REQ-84927103 --rationale 'we should add a budget here'"}),
    (A, "reqctl context",       "Bash", {"command": "reqctl context REQ-84927103"}),
    (A, "reqctl relate",        "Bash", {"command": "reqctl relate REQ-84927103 depends_on REQ-51772094"}),
    (A, "git show an item",     "Bash", {"command": "git show HEAD:requirements/reqs/REQ-84927103.yml"}),

    (D, "git -C checkout",      "Bash", {"command": "git -C . checkout HEAD~1 -- requirements/reqs/REQ-84927103.yml"}),
    (D, "git -c restore",       "Bash", {"command": "git -c user.name=x restore requirements/reqs/REQ-84927103.yml"}),

    (D, "dot-dot Edit",         "Edit", {"file_path": "requirements/reqs/../reqs/REQ-84927103.yml"}),
    (D, "dot-dot abs Write",    "Write", {"file_path": "/home/user/reqctl/requirements/reqs/../reqs/REQ-84927103.yml"}),
    (D, "dot-dot into baselines", "Write", {"file_path": "requirements/xyz/../baselines/BASELINE-0001.yml"}),
    (D, "dot-dot mixed padding", "Edit", {"file_path": "requirements/.//reqs/../reqs/REQ-84927103.yml"}),
    (A, "dot-dot elsewhere",    "Edit", {"file_path": "../src/../src/handler.ts"}),

    (D, "tee into the corpus",  "Bash", {"command": "echo x | tee requirements/params/PARAM-1.yml"}),

    (D, "mcp write an item",    "mcp__github__create_or_update_file",
     {"owner": "threldhq", "repo": "reqctl", "path": "requirements/reqs/REQ-84927103.yml",
      "content": "status: approved", "message": "m", "branch": "b"}),
    (D, "mcp write a baseline", "mcp__github__create_or_update_file",
     {"path": "requirements/baselines/BASELINE-0001.yml", "content": "x"}),
    (D, "mcp delete an item",   "mcp__github__delete_file",
     {"path": "requirements/params/PARAM-40042917.yml", "message": "m"}),
    (D, "a tool invented later", "SomeFutureWriteTool",
     {"file_path": "requirements/reqs/REQ-84927103.yml"}),

    (D, "camelCase filePath",   "SomeFutureWriteTool",
     {"filePath": "requirements/reqs/REQ-84927103.yml"}),
    (D, "FilePath variant",     "mcp__foo__bar",
     {"FilePath": "requirements/baselines/BASELINE-0001.yml"}),
    (D, "upper-case PATH",      "mcp__foo__bar",
     {"PATH": "requirements/params/PARAM-00042917.yml"}),
    (A, "content key in camelCase", "mcp__foo__bar",
     {"fileContent": "requirements/reqs/REQ-84927103.yml"}),

    (D, "mcp push_files nested", "mcp__github__push_files",
     {"owner": "o", "repo": "r", "branch": "b", "message": "m",
      "files": [{"path": "requirements/reqs/REQ-84927103.yml", "content": "x"}]}),
    (D, "mcp push_files, second entry", "mcp__github__push_files",
     {"files": [{"path": "src/a.ts", "content": "x"},
                {"path": "requirements/baselines/BASELINE-0001.yml", "content": "x"}]}),
    (A, "mcp push_files elsewhere", "mcp__github__push_files",
     {"files": [{"path": "src/a.ts", "content": "x"}]}),


    (A, "mcp write elsewhere",  "mcp__github__create_or_update_file",
     {"path": "src/api/handler.ts", "content": "x"}),
    (A, "mcp read a pr",        "mcp__github__pull_request_read",
     {"method": "get", "owner": "threldhq", "repo": "reqctl", "pullNumber": 608}),

    (A, "edit source about the corpus", "Edit",
     {"file_path": "reqctl/reqctl/corpus.py",
      "old_string": "x", "new_string": "# see requirements/reqs/REQ-84927103.yml"}),

    (D, "mv an item away",      "Bash", {"command": "mv requirements/reqs/REQ-84927103.yml /tmp/x"}),
    (D, "cp over an item",      "Bash", {"command": "cp /tmp/x requirements/reqs/REQ-84927103.yml"}),
    (D, "truncate an item",     "Bash", {"command": "truncate -s 0 requirements/reqs/REQ-1.yml"}),
    (D, "dd over an item",      "Bash", {"command": "dd if=/dev/null of=requirements/reqs/REQ-1.yml"}),
    (D, "perl over the corpus", "Bash", {"command": "perl -pi -e s/a/b/ requirements/reqs/REQ-84927103.yml"}),
    (D, "ruby over the corpus", "Bash", {"command": "ruby -e 'x' requirements/reqs/REQ-1.yml"}),

    (A, "corpus path beside added",     "Bash", {"command": "git log --grep=added -- requirements/reqs/"}),
    (A, "corpus path beside committee", "Bash", {"command": "git log --grep=committee -- requirements/reqs/"}),

    (D, "cd into the corpus then sed", "Bash",
     {"command": "cd requirements/reqs && sed -i s/a/b/ REQ-84927103.yml"}),
    (D, "cd into the corpus then rm",  "Bash",
     {"command": "cd requirements/baselines; rm BASELINE-0001.yml"}),


    (A, "a quoted -f after push", "Bash", {"command": "git push origin br -o 'note -f'"}),


    (D, "a number under an arbitrary path key", "mcp__foo__bar", {"path": 3}),

    (D, "dest names an item", "mcp__foo__bar", {"dest": "requirements/reqs/REQ-84927103.yml"}),
    (D, "destination names a baseline", "mcp__foo__bar",
     {"destination": "requirements/baselines/BASELINE-0001.yml"}),
    (D, "filename names an item", "mcp__foo__bar",
     {"filename": "requirements/params/PARAM-00042917.yml"}),
    (D, "paths list names an item", "mcp__foo__bar",
     {"paths": ["src/a.ts", "requirements/reqs/REQ-84927103.yml"]}),
    (D, "curl into an item",    "Bash", {"command": "curl -s -o requirements/reqs/REQ-84927103.yml https://x/y"}),
    (D, "wget into an item",    "Bash", {"command": "wget -O requirements/reqs/REQ-84927103.yml https://x/y"}),
    (D, "install an item",      "Bash", {"command": "install -m 644 /tmp/m requirements/reqs/REQ-84927103.yml"}),
    (D, "rsync onto an item",   "Bash", {"command": "rsync -a /tmp/m requirements/reqs/REQ-84927103.yml"}),
    (D, "untar into the corpus", "Bash", {"command": "tar -xf /tmp/x.tar -C requirements/reqs/"}),
    (D, "openssl -out an item", "Bash", {"command": "openssl base64 -in /tmp/x -out requirements/reqs/REQ-84927103.yml"}),
    (D, "an editor on an item", "Bash", {"command": "ed requirements/reqs/REQ-84927103.yml"}),
    (D, "vim on an item",       "Bash", {"command": "vim requirements/reqs/REQ-84927103.yml"}),
    (D, "patch an item",        "Bash", {"command": "patch requirements/reqs/REQ-84927103.yml < /tmp/p"}),
    (D, "scp onto an item",     "Bash", {"command": "scp remote:/x requirements/reqs/REQ-84927103.yml"}),

    (D, "find -exec over the corpus", "Bash",
     {"command": "find requirements/reqs/ -name '*.yml' -exec sed -i s/a/b/ {} +"}),
    (D, "xargs onto an item",   "Bash", {"command": "xargs -I{} cp /tmp/m {} <<< requirements/reqs/REQ-84927103.yml"}),
    (D, "awk redirecting into an item", "Bash",
     {"command": "awk 'BEGIN{print > \"requirements/reqs/REQ-84927103.yml\"}'"}),

    (D, "head an item",         "Bash", {"command": "head -5 requirements/reqs/REQ-84927103.yml"}),
    (D, "wc an item",           "Bash", {"command": "wc -l requirements/reqs/REQ-84927103.yml"}),
    (D, "diff an item",         "Bash", {"command": "diff requirements/reqs/REQ-84927103.yml /tmp/other.yml"}),
    (A, "git status the corpus", "Bash", {"command": "git status requirements/reqs/"}),
    (A, "git add the corpus",   "Bash", {"command": "git add -A requirements/reqs/"}),
    (A, "git commit naming an item", "Bash",
     {"command": "git commit -m \"note about requirements/reqs/REQ-84927103.yml\""}, ON_BRANCH),

    (D, "pipe a read into xargs", "Bash",
     {"command": "grep -rl old requirements/reqs | xargs sed -i s/a/b/"}),
    (D, "pipe a listing into rm", "Bash", {"command": "ls requirements/reqs/*.yml | xargs rm"}),
    (D, "loop over a listing",  "Bash",
     {"command": "ls requirements/reqs | while read f; do rm $f; done"}),
    (D, "a write on the next line", "Bash",
     {"command": "cat notes.md\nsed -i s/a/b/ requirements/reqs/REQ-84927103.yml"}),
    (D, "yq in place",          "Bash", {"command": "yq -y -i '.text = 1' requirements/reqs/REQ-84927103.yml"}),
    (D, "sort -o an item",      "Bash", {"command": "sort /tmp/e.yml -o requirements/reqs/REQ-84927103.yml"}),
    (D, "uniq writing its second operand", "Bash", {"command": "uniq /tmp/in.yml requirements/reqs/REQ-84927103.yml"}),
    (D, "a glob over the corpus dirs", "Bash",
     {"command": "sed -i s/a/b/ requirements/*/*.yml"}),
    (D, "brace expansion over the corpus", "Bash",
     {"command": "rm requirements/{reqs,params}/*.yml"}),
    (D, "cd in then write",     "Bash", {"command": "cd requirements && rm reqs/*.yml"}),
    (D, "git --output into an item", "Bash", {"command": "git diff --output=requirements/reqs/REQ-84927103.yml HEAD"}),
    (D, "git apply into the corpus", "Bash",
     {"command": "git apply --directory=requirements/reqs /tmp/fix.diff"}),
    (D, "a branch name supplying a read word", "Bash",
     {"command": "git checkout diff-fix -- requirements/reqs"}),
    (D, "git rm with a read word in a comment", "Bash",
     {"command": "git rm --cached requirements/reqs/REQ-84927103.yml # add"}),
    (D, "a corpus edit behind a commented continuation", "Bash",
     {"command": "ls # \\\nsed -i s/a/b/ requirements/reqs/REQ-84927103.yml"}),
    (D, "an escaped space before a hash", "Bash",
     {"command": "echo a\\ #x; rm requirements/reqs/REQ-84927103.yml"}),
    (D, "process substitution", "Bash", {"command": "diff <(cp /tmp/e requirements/reqs/REQ-84927103.yml) /tmp/b"}),
    (D, "command substitution", "Bash", {"command": "grep -l requirements/reqs/REQ-84927103.yml \"$(rm -rf requirements/reqs/REQ-84927103.yml)\""}),
    (D, "an alias smuggled through -c", "Bash", {"command": "git -c alias.z='!rm requirements/reqs/REQ-84927103.yml' z"}),

    (D, "a read piped to a read", "Bash", {"command": "cat requirements/reqs/REQ-84927103.yml | grep shall"}),
    (A, "git log piped to head", "Bash", {"command": "git log -- requirements/reqs/ | head -20"}),
    (A, "git -C then a read",   "Bash", {"command": "git -C . log -- requirements/reqs/"}),

    (D, "echo label then a read", "Bash",
     {"command": "echo reqs; wc -l requirements/reqs/REQ-84927103.yml"}),
    (D, "printf label then a read", "Bash",
     {"command": "printf 'terms\\n' && cat requirements/terms/TERM-79972628.yml"}),
    (D, "printf redirect into corpus", "Bash",
     {"command": "printf x > requirements/reqs/REQ-1.yml"}),
    (D, "echo piped past a read into tee", "Bash",
     {"command": "echo x | tee requirements/terms/TERM-1.yml"}),

    (D, "alternation in a grep pattern", "Bash",
     {"command": "grep -E 'shall|should' requirements/reqs/REQ-84927103.yml"}),
    (D, "ampersand in a grep pattern", "Bash",
     {"command": "grep 'a&b' requirements/reqs/REQ-84927103.yml"}),
    (D, "pipe in a jq filter", "Bash",
     {"command": "jq '.text | length' requirements/reqs/REQ-84927103.yml"}),
    (D, "mkdir beside a read", "Bash",
     {"command": "mkdir -p /tmp/x && cat requirements/reqs/REQ-84927103.yml"}),
    (D, "export beside a read", "Bash",
     {"command": "export FOO=1; cat requirements/reqs/REQ-84927103.yml"}),
    (D, "subshell in the other command", "Bash",
     {"command": "echo \"$(date)\" ; cat requirements/reqs/REQ-84927103.yml"}),
    (A, "heredoc citing an item", "Bash",
     {"command": "cat > /tmp/msg.txt <<'EOF'\nImplements requirements/reqs/REQ-84927103.yml\nEOF"}),
    (A, "commit -F from a heredoc", "Bash",
     {"command": "git commit -F - <<'EOF'\nfeat: cover requirements/reqs/REQ-84927103.yml\nEOF"}, ON_BRANCH),
    (D, "checksum an item", "Bash",
     {"command": "sha256sum requirements/reqs/REQ-84927103.yml"}),
    (D, "cmp an item", "Bash",
     {"command": "cmp requirements/reqs/REQ-84927103.yml /tmp/other.yml"}),
    (A, "du the corpus", "Bash", {"command": "du -sh requirements"}),
    (A, "test an item exists", "Bash",
     {"command": "test -f requirements/reqs/REQ-84927103.yml"}),
    (A, "commit message naming push -f", "Bash",
     {"command": "git commit -m \"do not push -f here\""}, ON_BRANCH),

    (D, "rm -rf the corpus root",  "Bash", {"command": "rm -rf requirements"}),
    (D, "rm the root with a slash", "Bash", {"command": "rm -rf requirements/"}),
    (D, "mv the root away",        "Bash", {"command": "mv requirements /tmp/r"}),
    (D, "git rm the root",         "Bash", {"command": "git rm -r requirements"}),
    (D, "chmod the root",          "Bash", {"command": "chmod -R 000 requirements"}),
    (D, "git clean the corpus",    "Bash", {"command": "git clean -fd requirements/"}),
    (D, "tar the root away",       "Bash",
     {"command": "tar -cf /tmp/o.tar requirements"}),
    (D, "pushd then rm",           "Bash",
     {"command": "pushd requirements && rm reqs/REQ-84927103.yml"}),
    (D, "cd a dotted root",        "Bash",
     {"command": "cd ./requirements && rm reqs/REQ-84927103.yml"}),
    (D, "cd a quoted root",        "Bash",
     {"command": "cd \"requirements\" && rm reqs/REQ-84927103.yml"}),
    (D, "env -C into the root",    "Bash",
     {"command": "env -C requirements sed -i s/a/b/ reqs/REQ-84927103.yml"}),
    (D, "symlink the root",        "Bash", {"command": "ln -s requirements r"}),
    (A, "a look-alike beside the root rule", "Bash",
     {"command": "rm -rf requirements-old"}),
    (A, "the CI diff classifier run locally", "Bash",
     {"command": "PATTERN='^requirements/'\n"
                 "changed=$(git diff --name-only origin/main...HEAD)\n"
                 "echo \"$changed\" | grep -E \"$PATTERN\" || true"}),

    (D, "git apply a diff",   "Bash", {"command": "git apply /tmp/fix.diff"}),
    (D, "git am a series",    "Bash", {"command": "git am /tmp/series.mbox"}),
    (D, "patch from a diff",  "Bash", {"command": "patch -p1 < /tmp/fix.diff"}),

    (D, "quoted +refspec",    "Bash", {"command": "git push origin \"+main\""}),
    (D, "single-quoted +refspec", "Bash", {"command": "git push origin '+main'"}),
    (D, "push --mirror",      "Bash", {"command": "git push --mirror origin"}),
    (D, "push --delete",      "Bash", {"command": "git push origin --delete main"}),
    (D, "push a :refspec",    "Bash", {"command": "git push origin :main"}),
    (D, "force push inside sh -c", "Bash",
     {"command": "sh -c 'git push --force origin main'"}),
    (A, "push refspec with a colon inside", "Bash",
     {"command": "git push origin HEAD:main"}),

    (D, "files list names an item", "mcp__foo__bar",
     {"files": ["src/a.ts", "requirements/reqs/REQ-84927103.yml"]}),
    (D, "dir names the corpus", "mcp__foo__bar",
     {"dir": "requirements/reqs"}),
    (D, "output names an item", "mcp__foo__bar",
     {"output": "requirements/reqs/REQ-84927103.yml"}),
    (D, "a command key on another tool", "mcp__runner__exec",
     {"command": "rm requirements/reqs/REQ-84927103.yml"}),
    (D, "a script key on another tool", "mcp__runner__exec",
     {"script": "rm -rf requirements"}),
    (D, "a command key doing a read", "mcp__runner__exec",
     {"command": "cat requirements/reqs/REQ-84927103.yml"}),

    (D, "backslash-hidden corpus path", "Bash",
     {"command": "sed -i s/a/b/ requirements\\/reqs/REQ-84927103.yml"}),
    (D, "quote-split corpus path", "Bash",
     {"command": "sed -i s/a/b/ require''ments/reqs/REQ-84927103.yml"}),

    (D, "read piped to sort",   "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | sort"}),
    (D, "read piped to sed",    "Bash",
     {"command": "grep -rn shall requirements/reqs/ | sed s/shall/SHALL/"}),
    (D, "read piped to python", "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | python3 -c 'import sys; print(len(sys.stdin.read()))'"}),
    (D, "read piped to tee",    "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | tee $OUT"}),
    (D, "read piped to perl",   "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | perl -pe s/a/b/"}),
    (D, "read piped to node",   "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | node -e 0"}),
    (D, "sink sort writing -o", "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | sort -o $OUT"}),
    (D, "sink sed in place",    "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | sed -i s/a/b/ $OUT"}),
    (D, "sink awk redirecting", "Bash",
     {"command": "cat requirements/reqs/REQ-84927103.yml | awk '{print > f}'"}),

    (A, "a redirect inside a message", "Bash",
     {"command": "git commit -m \"moved x > requirements/reqs/REQ-84927103.yml\""}, ON_BRANCH),

    (D, "rm -r of dot",  "Bash", {"command": "rm -rf ."}),
    (D, "rm -r of star", "Bash", {"command": "rm -r *"}),
    (A, "rm -r of a named dir", "Bash", {"command": "rm -rf /tmp/build"}),
    (D, "rm -r of the project dir", "Bash",
     {"command": "rm -rf /srv/checkout"}, {"CLAUDE_PROJECT_DIR": "/srv/checkout"}),
    (D, "rm -r of an ancestor", "Bash",
     {"command": "rm -rf /srv"}, {"CLAUDE_PROJECT_DIR": "/srv/checkout"}),
    (A, "rm -r beside the project dir", "Bash",
     {"command": "rm -rf /srv/scratch"}, {"CLAUDE_PROJECT_DIR": "/srv/checkout"}),
    (D, "rm -r of ~/",   "Bash", {"command": "rm -rf ~/"}),
    (D, "rm -r of $HOME", "Bash", {"command": "rm -rf $HOME"}),
    (D, "rm -r of an unexpanded root", "Bash", {"command": "rm -rf $SCRATCH/build"}),
    (D, "rm -r of a relative project root", "Bash",
     {"command": "rm -rf ../checkout"}, {"CLAUDE_PROJECT_DIR": "/srv/checkout"}),

    (A, "the word in a heredoc",  "Bash",
     {"command": "python3 - <<'EOF'\nnote = 'all 62 requirements use the subject'\nEOF"}),
    (A, "the bare word in a heredoc body a writer reads", "Bash",
     {"command": "python3 - <<'EOF'\nrewrote the requirements folder today\nEOF"}),
    (A, "the bare word in a heredoc body a sink reads", "Bash",
     {"command": "sort -o /tmp/m.txt <<'EOF'\nrewrote the requirements folder today\nEOF"}),
    (A, "the word in a message",  "Bash",
     {"command": "git commit -m 'restate the requirements'"}, ON_BRANCH),
    (A, "the word in a variable", "Bash",
     {"command": "python3 -c \"print('requirements are approved')\""}),
    (D, "a real path in a heredoc", "Bash",
     {"command": "python3 - <<'EOF'\nopen('requirements/reqs/REQ-84927103.yml','w')\nEOF"}),
    (D, "the root as an operand",  "Bash", {"command": "rm -rf ./requirements"}),
    (D, "the root, absolute",      "Bash",
     {"command": "rm -rf /home/user/reqctl/requirements"}),
    (D, "the root via a variable", "Bash",
     {"command": "d=requirements; sed -i s/a/b/ $d/reqs/REQ-84927103.yml"}),
    (D, "the root via a brace",    "Bash",
     {"command": "p=requirements; rm ${p}/reqs/REQ-84927103.yml"}),

    (D, "commit on main",          "Bash", {"command": "git commit -m x"}, ON_MAIN),
    (A, "commit on a branch",      "Bash", {"command": "git commit -m x"}, ON_BRANCH),
    (D, "commit on main through -C", "Bash",
     {"command": "git -C . commit -m x"}, ON_MAIN),
    (A, "amend on a branch",       "Bash",
     {"command": "git commit --amend --no-edit"}, ON_BRANCH),
    (D, "amend on main",           "Bash",
     {"command": "git commit --amend --no-edit"}, ON_MAIN),

    (D, "assignment-prefixed commit on main", "Bash",
     {"command": "GIT_AUTHOR_NAME=x git commit -m x"}, ON_MAIN),
    (D, "env-prefixed commit on main", "Bash",
     {"command": "env git commit -m x"}, ON_MAIN),
    (D, "command-prefixed commit on main", "Bash",
     {"command": "command git commit -m x"}, ON_MAIN),
    (D, "assignment-prefixed push --force", "Bash",
     {"command": "PATH=/x git push --force origin main"}),

    (D, "checkout -- over an edit", "Bash",
     {"command": "git checkout -- kept.txt"}, TRACKED_EDIT),
    (A, "checkout -- with nothing to lose", "Bash",
     {"command": "git checkout -- kept.txt"}, ON_BRANCH),
    (D, "checkout the whole tree", "Bash", {"command": "git checkout ."}, TRACKED_EDIT),
    (D, "checkout -f over an edit", "Bash",
     {"command": "git checkout -f claude/work"}, TRACKED_EDIT),
    (A, "switching branch is not a restore", "Bash",
     {"command": "git checkout claude/work"}, TRACKED_EDIT),
    (D, "switch -f over an edit", "Bash",
     {"command": "git switch -f claude/work"}, TRACKED_EDIT),
    (D, "switch --discard-changes over an edit", "Bash",
     {"command": "git switch --discard-changes claude/work"}, TRACKED_EDIT),

    (D, "reset --hard over an edit", "Bash",
     {"command": "git reset --hard"}, TRACKED_EDIT),
    (A, "reset --soft keeps the worktree", "Bash",
     {"command": "git reset --soft HEAD~1"}, TRACKED_EDIT),
    (D, "restore over an edit",    "Bash",
     {"command": "git restore kept.txt"}, TRACKED_EDIT),
    (A, "restore --staged leaves the worktree", "Bash",
     {"command": "git restore --staged kept.txt"}, TRACKED_EDIT),

    (D, "clean -fd sweeps an untracked file", "Bash",
     {"command": "git clean -fd"}, UNTRACKED),
    (A, "clean -fd spares a tracked edit", "Bash",
     {"command": "git clean -fd"}, TRACKED_EDIT),
    (A, "clean without force does nothing", "Bash",
     {"command": "git clean -n"}, UNTRACKED),
    (A, "checkout -- spares an untracked file", "Bash",
     {"command": "git checkout -- kept.txt"}, UNTRACKED),
    (A, "reset --hard spares an untracked file", "Bash",
     {"command": "git reset --hard"}, UNTRACKED),
    (A, "clean -fd spares an ignored-only tree", "Bash",
     {"command": "git clean -fd"}, IGNORED_ONLY),
    (D, "clean -fdx sweeps an ignored file", "Bash",
     {"command": "git clean -fdx"}, IGNORED_ONLY),

    (D, "commit where git cannot be read", "Bash",
     {"command": "git commit -m x"}, NO_REPO),
    (D, "restore where git cannot be read", "Bash",
     {"command": "git checkout -- kept.txt"}, NO_REPO),
]

CITED = repo("cited", "claude/work")
MARK = "# @req" + "> REQ-00000001@aaaaaaaaaaaa aaaaaa"
(Path(CITED["CLAUDE_PROJECT_DIR"]) / "cited.py").write_text(f"{MARK}\nx = 1\n")

CASES += [
    (D, "Write adds a citation", "Write",
     {"file_path": "fresh.py", "content": f"{MARK}\ny = 1\n"}, CITED),
    (D, "Edit removes a citation", "Edit",
     {"file_path": "cited.py", "old_string": f"{MARK}\n", "new_string": ""}, CITED),
    (D, "Edit changes a citation's stamp", "Edit",
     {"file_path": "cited.py", "old_string": "@aaaaaaaaaaaa", "new_string": "@bbbbbbbbbbbb"}, CITED),
    (D, "Edit deletes cited code with its citation", "Edit",
     {"file_path": "cited.py", "old_string": f"{MARK}\nx = 1\n", "new_string": ""}, CITED),
    (D, "Write drops a citation", "Write",
     {"file_path": "cited.py", "content": "x = 1\n"}, CITED),
    (D, "MultiEdit removes a citation", "MultiEdit",
     {"file_path": "cited.py", "edits": [{"old_string": f"{MARK}\n", "new_string": ""}]}, CITED),
    (A, "Edit carries a citation through unchanged", "Edit",
     {"file_path": "cited.py", "old_string": f"{MARK}\nx = 1\n", "new_string": f"{MARK}\nx = 2\n"}, CITED),
    (A, "Edit leaves the citation alone", "Edit",
     {"file_path": "cited.py", "old_string": "x = 1", "new_string": "x = 2"}, CITED),
    (A, "Write keeps every citation", "Write",
     {"file_path": "cited.py", "content": f"{MARK}\nx = 3\n"}, CITED),
    (D, "shell appends a citation", "Bash",
     {"command": f"echo '{MARK}' >> cited.py"}, CITED),
    (D, "shell writes a citation through a script", "Bash",
     {"command": f"python3 - <<'PY'\nopen('cited.py', 'a').write('{MARK}')\nPY"}, CITED),
    (D, "shell edits a citation in place", "Bash",
     {"command": f"sed -i 's/{MARK[2:]}/{MARK[2:-1]}b/' cited.py"}, CITED),
    (D, "shell pipes a citation into a writer", "Bash",
     {"command": f"echo '{MARK}' | tee -a cited.py"}, CITED),
    (D, "shell deletes a citation by pattern", "Bash",
     {"command": "sed -i '/@req>/d' cited.py"}, CITED),
    (D, "shell splits a citation across quotes", "Bash",
     {"command": "sed -i '/@req'\"+\"'/d' cited.py"}, CITED),
    (D, "shell continues a citation edit onto a second line", "Bash",
     {"command": "sed '/@req>/d' \\\n-i cited.py"}, CITED),
    (D, "shell hides a citation edit behind a commented continuation", "Bash",
     {"command": "echo # \\\nsed -i '/@req>/d' cited.py"}, CITED),
    (A, "shell searches for citations", "Bash",
     {"command": "grep -rn '@req>' ."}, CITED),
    (A, "reqctl cites", "Bash",
     {"command": "reqctl tag cited.py --from 2 --to 2 --req REQ-00000001"}, CITED),
    (A, "reqctl re-pins", "Bash", {"command": "reqctl repin aaaaaa"}, CITED),
    (A, "reqctl removes a citation", "Bash", {"command": "reqctl untag aaaaaa"}, CITED),
]

UNREADABLE = [
    ("tool_input is a string", {"tool_name": "Edit", "tool_input": "requirements/reqs/REQ-1.yml"}),
    ("tool_input is a list",   {"tool_name": "Bash", "tool_input": ["rm requirements/reqs/REQ-1.yml"]}),
    ("file_path is a list",    {"tool_name": "Edit", "tool_input": {"file_path": ["requirements/reqs/REQ-1.yml"]}}),
    ("command is a list",      {"tool_name": "Bash", "tool_input": {"command": ["rm", "requirements/reqs/REQ-1.yml"]}}),
    ("payload is not an object", ["Edit", "requirements/reqs/REQ-1.yml"]),
]

fails = 0
for expected, label, tool, args, *env in CASES:
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args})
    out = subprocess.run(
        [str(HOOK)], input=payload, capture_output=True, text=True,
        env={**os.environ, **(env[0] if env else {})},
    )
    if out.returncode != 0:
        fails += 1
        print(f"FAIL  exit {out.returncode} (want {expected:5})  {label}"
              f"  {out.stderr.strip().splitlines()[-1] if out.stderr.strip() else ''}")
        continue
    got = A
    if out.stdout.strip():
        got = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"]
    ok = got == expected
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {got:5} (want {expected:5})  {label}")

for label, payload in UNREADABLE:
    out = subprocess.run(
        [str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True,
    )
    got = f"exit {out.returncode}"
    if out.returncode == 0 and out.stdout.strip():
        got = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"]
    elif out.returncode == 0:
        got = A
    ok = got == D
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {got:5} (want {D:5})  unreadable: {label}")

out = subprocess.run(
    [str(HOOK)], input='{"tool_name": "Ed', capture_output=True, text=True
)
ok = out.returncode == 0 and out.stdout.strip() and \
    json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == D
fails += not ok
print(f"{'ok  ' if ok else 'FAIL'}  {'deny' if ok else 'exit ' + str(out.returncode):5} "
      f"(want {D:5})  unreadable: truncated json")

REASONS = [
    ("Edit", {"file_path": "requirements/reqs/REQ-84927103.yml"}, "reqctl"),
    ("Edit", {"file_path": "requirements/reqs/REQ-84927103.yml"},
     "Direct write of a requirement item blocked"),
    ("Write", {"file_path": "requirements/baseline.yml"}, "Baselines are generated"),
    ("Write", {"file_path": "requirements/reqs/notes.txt"},
     "Direct write into the requirements corpus blocked"),
    ("Read", {"file_path": "requirements/reqs/REQ-84927103.yml"},
     "Direct read of the requirements corpus blocked"),
    ("Bash", {"command": "git push --force origin main"}, "Push with --force blocked"),
    ("Bash", {"command": "git commit -m x"}, "git checkout -b claude/", ON_MAIN),
    ("Bash", {"command": "git commit -m x"}, "Commit on main blocked", ON_MAIN),
    ("Bash", {"command": "git checkout -- kept.txt"}, "kept.txt", TRACKED_EDIT),
    ("Bash", {"command": "git checkout -- kept.txt"},
     "This discards uncommitted work", TRACKED_EDIT),
    ("Bash", {"command": "git clean -fd"}, "loose.txt", UNTRACKED),
    ("Bash", {"command": "git commit -m x"}, "could not read the repository", NO_REPO),
    ("Bash", {"command": "git apply /tmp/fix.diff"}, "git apply blocked"),
    ("Bash", {"command": "patch -p1 < /tmp/fix.diff"}, "patch(1) blocked"),
    ("Bash", {"command": "rm -rf ."}, "sweeps the requirements corpus"),
    ("Bash", {"command": "sed -i s/a/b/ requirements/reqs/REQ-84927103.yml"},
     "outside the known-safe forms"),
    ("Bash", {"command": ["rm", "requirements/reqs/REQ-1.yml"]},
     "could not read this tool call"),
    ("Edit", {"file_path": "cited.py", "old_string": "@aaaaaaaaaaaa",
              "new_string": "@bbbbbbbbbbbb"}, "written only by reqctl", CITED),
    ("Bash", {"command": f"echo '{MARK}' >> cited.py"}, "reqctl repin ID", CITED),
]

for tool, args, want, *env in REASONS:
    payload = json.dumps({"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": args})
    out = subprocess.run([str(HOOK)], input=payload, capture_output=True, text=True,
                         env={**os.environ, **(env[0] if env else {})})
    reason = ""
    if out.returncode == 0 and out.stdout.strip():
        reason = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    ok = want in reason
    fails += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  reason holds {want!r}"
          f"{'' if ok else f'; got {reason!r}'}")

total = len(CASES) + len(UNREADABLE) + len(REASONS) + 1
print(f"\n{total - fails}/{total} passed")
sys.exit(1 if fails else 0)
