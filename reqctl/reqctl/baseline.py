import subprocess
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from .corpus import (CONFLICTED, FOLDERS, ReqctlError, atomic_write,
                     carriers, items, loads, raw, read, schema, sides, stamp)


def path(root):
    return Path(root) / "requirements" / "baseline.yml"


def _numbered(root):
    folder = Path(root) / "requirements" / "baselines"
    return sorted(
        held
        for pattern in ("BASELINE-*.yml", "BASELINE-*.yaml")
        for held in folder.glob(pattern)
    )


def derive(tree):
    return {
        item.uid: stamp(item)
        for item in items(tree)
        if raw(item).get("status") == "approved"
    }


def _git(root, *args):
    try:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True)
    except OSError as error:
        raise ReqctlError(f"cannot run git: {error.strerror}") from error


def head_commit(root):
    result = _git(root, "rev-parse", "HEAD")
    if result.returncode:
        raise ReqctlError("cannot read HEAD; a baseline must name a commit")
    return result.stdout.strip()


def uncommitted(root):
    result = _git(root, "status", "--porcelain", "--untracked-files=all")
    if result.returncode:
        raise ReqctlError(
            "cannot read git status; a baseline must record a committed corpus"
        )
    folders = {f"requirements/{folder}" for folder in FOLDERS.values()}
    dirty = set()
    for line in result.stdout.splitlines():
        for named in line[3:].split(" -> "):
            parent = named.rpartition("/")[0]
            if parent in folders and named.endswith((".yml", ".yaml")):
                dirty.add(named)
    return sorted(dirty)


def _unresolved(where):
    try:
        text = Path(where).read_text()
    except (OSError, UnicodeDecodeError):
        return None
    if not CONFLICTED.search(text):
        return None
    claimed = []
    for side in sides(text):
        try:
            held = loads(side, where)
        except ReqctlError:
            held = None
        # @req> REQ-50767938@YGIjAYt9M2fF 5k3r7e
        if not isinstance(held, dict) or type(held.get("baseline")) is not int:
            raise ReqctlError(
                f"{Path(where).name} holds an unresolved merge, and a side of "
                "it does not read as a baseline -- resolve the conflict by "
                "hand, then generate"
            )
        claimed.append(held["baseline"])
    return claimed


DEFAULT_HEAD = "refs/remotes/origin/HEAD"
REMOTE = "origin"


def _default_ref(root):
    listed = _git(root, "remote")
    if listed.returncode:
        raise ReqctlError(
            "cannot read the remotes, so whether a default branch states a "
            "baseline cannot be told apart from there being none -- "
            "numbering from this branch would skip the one it owes"
        )
    if REMOTE not in listed.stdout.split():
        return None
    named = _git(root, "symbolic-ref", "-q", DEFAULT_HEAD)
    if named.returncode:
        raise ReqctlError(
            "git does not say which branch of origin is the default one, so "
            "numbering from a guess could bury the baseline the real one "
            "states -- name it with `git remote set-head origin BRANCH`, "
            "then generate"
        )
    ref = named.stdout.strip()
    if _git(root, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}").returncode:
        raise ReqctlError(
            f"{ref} names no commit here, so the baseline the default branch "
            "states cannot be read, and numbering from this branch would skip "
            "the one it owes -- fetch it, then generate"
        )
    return ref


def _carried(root, ref):
    where = path(root).relative_to(root).as_posix()
    listed = _git(root, "ls-tree", ref, "--", where)
    if listed.returncode:
        raise ReqctlError(
            f"cannot read the tree {ref} names, so whether it states a "
            f"baseline cannot be told: {listed.stderr.strip()}"
        )
    if not listed.stdout.strip():
        return None
    found = _git(root, "show", f"{ref}:{where}")
    if found.returncode:
        raise ReqctlError(
            f"{ref} states a baseline that cannot be read, and numbering "
            f"from this branch would bury it: {found.stderr.strip()}"
        )
    held = loads(found.stdout, ref)
    if not isinstance(held, dict) or type(held.get("baseline")) is not int:
        raise ReqctlError(
            f"{ref} states a baseline that does not say which one it is, so "
            "the number that follows it cannot be read"
        )
    return held["baseline"]


def _stated(root):
    if not path(root).is_file():
        return None
    held = read(path(root))
    if not isinstance(held, dict) or type(held.get("baseline")) is not int:
        raise ReqctlError(
            f"{path(root).name} does not say which baseline it holds, and a "
            "new one would bury that rather than settle it -- `reqctl "
            "baseline --check` names the fault"
        )
    return held["baseline"]


def _previous(root):
    claimed = _unresolved(path(root)) if path(root).is_file() else None
    # @req> REQ-25777470@4o7sac7TLlHi lmbowm
    stated = None if claimed is not None else _stated(root)
    # @req+ REQ-43924642@SDx_e7a7A1XM bbqmqm
    ref = _default_ref(root)
    if ref is not None:
        return _carried(root, ref), claimed
    # @req- bbqmqm
    if claimed is not None:
        raise ReqctlError(
            f"{path(root).name} holds an unresolved merge, and no default "
            "branch says which baseline it follows -- fetch origin, then "
            "generate"
        )
    # @req> REQ-51424927@vQb-YtKja6pq 4nzywx
    return stated, None


def generate(tree, root):
    approved = derive(tree)
    # @req> REQ-35349268@w6VRV3NDc1pr xfjprt
    if not approved:
        raise ReqctlError("nothing approved; a baseline of nothing states nothing")
    # @req+ REQ-63399155@6l4OsixGYKDz ygxzq3
    numbered = _numbered(root)
    if numbered:
        raise ReqctlError(
            f"{', '.join(held.name for held in numbered)}: the numbered layout "
            "was replaced by one baseline; delete it, then generate"
        )
    # @req- ygxzq3

    # @req+ REQ-85375321@yRXlpC7hB1lb yvehmw
    shared = sorted(name for name, wore in carriers(tree).items()
                    if len(wore) > 1)
    if shared:
        raise ReqctlError(
            f"{', '.join(shared)}: more than one item has carried this name, "
            "so a baseline stating it would name no one item -- rename one of "
            "them, then generate"
        )
    # @req- yvehmw

    # @req+ REQ-28086776@tkXHKMQwei2Z thbrwa
    previous, claimed = _previous(root)
    # @req+ REQ-73312524@KSSGrwMjCS4F mgwroy
    dirty = uncommitted(root)
    if dirty:
        raise ReqctlError(
            f"{', '.join(dirty)}: uncommitted -- commit the corpus, "
            "then generate"
        )
    # @req- mgwroy

    # @req+ REQ-87283234@NazXGi81RwTf cc4ozn
    manifest = {
        "baseline": (previous or 0) + 1,
        "commit": head_commit(root),
        "supersedes": previous,
        "items": approved,
    }
    atomic_write(
        path(root),
        yaml.safe_dump(manifest, default_flow_style=False, sort_keys=True),
    )
    # @req- cc4ozn
    return manifest["baseline"], path(root), len(approved), claimed
    # @req- thbrwa


def _restated(recorded, tree):
    wore = carriers(tree)
    held = {}
    for name, pinned in recorded.items():
        under = wore[name][0] if len(wore.get(name, ())) == 1 else name
        held[name if under in held else under] = pinned
    return held


def check(tree, root):
    # @req> REQ-40107714@PF63p4qjxWxa r2i5nz
    problems = [
        f"{held.name}: the numbered layout was replaced by one baseline; "
        "delete it and run `reqctl baseline --generate`"
        for held in _numbered(root)
    ]

    if not path(root).is_file():
        approved = derive(tree)
        if approved:
            problems.append(
                f"{len(approved)} item(s) are approved but no baseline states "
                "them -- run `reqctl baseline --generate`"
            )
        return None, problems

    # @req+ REQ-52307457@2GAIsxcSUISq w27scf
    claimed = _unresolved(path(root))
    if claimed is not None:
        stated = " and ".join(str(one) for one in sorted(set(claimed)))
        return None, problems + [
            f"{path(root).name}: holds an unresolved merge claiming {stated} "
            "-- `reqctl baseline --generate` cuts the one that follows both"
        ]
    # @req- w27scf

    manifest = read(path(root))
    if not isinstance(manifest, dict):
        return None, problems + [f"{path(root).name}: is not a mapping"]
    number = manifest.get("baseline")
    head = f"baseline {number}" if type(number) is int else path(root).name

    validator = Draft202012Validator(schema(root, "baseline"))
    for error in sorted(validator.iter_errors(manifest), key=str):
        where = ".".join(str(p) for p in error.absolute_path) or "(manifest)"
        problems.append(f"{head}: schema: {where}: {error.message}")

    # @req> REQ-60457693@ttVu9qsRnPG9 43d4hx
    if type(number) is int:
        stated = manifest.get("supersedes")
        follows = number - 1 if number > 1 else None
        if stated != follows:
            problems.append(
                f"{head}: supersedes {stated!r}, but the count before "
                f"{number} is {follows!r} -- a hand edit or a bad merge; "
                "run `reqctl baseline --generate` on the corrected corpus"
            )

    recorded = manifest.get("items")
    if not isinstance(recorded, dict):
        return number, problems + [f"{head}: items is not a mapping"]

    # @req+ REQ-44642786@TqRUT-VDn-ps rfw24o
    current = derive(tree)
    # @req> REQ-13861816@banV6DgxKI1S db6w7v
    recorded = _restated(recorded, tree)
    for uid in sorted(set(recorded) - set(current)):
        problems.append(f"{uid}: in baseline {number} but no longer approved")
    for uid in sorted(set(current) - set(recorded)):
        problems.append(f"{uid}: approved but absent from baseline {number}")
    for uid in sorted(set(recorded) & set(current)):
        if recorded[uid] != current[uid]:
            problems.append(
                f"{uid}: changed since baseline {number} "
                "-- the baseline states a state the corpus no longer has"
            )
    # @req- rfw24o
    return number, problems
