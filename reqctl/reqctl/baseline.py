import subprocess
from pathlib import Path

import yaml

from .corpus import (CONFLICTED, FOLDERS, ReqctlError, atomic_write,
                     carriers, items, loads, raw, read, schema, sides, stamp,
                     validator)


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
        # @req> REQ-30898926@Vu28eWaG_1mE cr6glq
        raise ReqctlError(f"cannot run git: {error.strerror} -- install git "
                          "or put it on PATH") from error


def head_commit(root):
    result = _git(root, "rev-parse", "HEAD")
    if result.returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE ctk4fh
        raise ReqctlError("cannot read HEAD; a baseline must name a commit "
                          "-- commit once, then run `reqctl baseline "
                          "--generate`")
    return result.stdout.strip()


def uncommitted(root):
    result = _git(root, "status", "--porcelain", "--untracked-files=all")
    if result.returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE dj2esu
        raise ReqctlError(
            "cannot read git status; a baseline must record a committed corpus "
            "-- run inside a git work tree"
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
    # @req> REQ-10024282@x7WPiNHGRX8n 7qnfkg
    for side in sides(text):
        try:
            held = loads(side, where)
        except ReqctlError:
            held = None
        # @req> REQ-50767938@YGIjAYt9M2fF 5k3r7e
        if not isinstance(held, dict) or type(held.get("baseline")) is not int:
            # @req> REQ-30898926@Vu28eWaG_1mE ehhq6x
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
        # @req> REQ-30898926@Vu28eWaG_1mE zjwepm
        raise ReqctlError(
            "cannot read the remotes, so whether a default branch states a "
            "baseline cannot be told apart from there being none -- repair "
            "the remote configuration (`git remote -v` shows it), then retry"
        )
    if REMOTE not in listed.stdout.split():
        return None
    named = _git(root, "symbolic-ref", "-q", DEFAULT_HEAD)
    if named.returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE kkoqo5
        raise ReqctlError(
            "git does not say which branch of origin is the default one -- "
            "name it with `git remote set-head origin BRANCH`"
        )
    ref = named.stdout.strip()
    if _git(root, "rev-parse", "-q", "--verify", f"{ref}^{{commit}}").returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE ykp666
        raise ReqctlError(
            f"{ref} names no commit here, so the baseline the default branch "
            "states cannot be read -- fetch it"
        )
    return ref


def _carried(root, ref):
    where = path(root).relative_to(root).as_posix()
    listed = _git(root, "ls-tree", ref, "--", where)
    if listed.returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE wrwu46
        raise ReqctlError(
            f"cannot read the tree {ref} names, so whether it states a "
            f"baseline cannot be told: {listed.stderr.strip()} -- run `git "
            "fetch origin`, then retry"
        )
    # @req> REQ-51424927@vQb-YtKja6pq zi26im
    if not listed.stdout.strip():
        return None
    found = _git(root, "show", f"{ref}:{where}")
    if found.returncode:
        # @req> REQ-30898926@Vu28eWaG_1mE 7oljfr
        raise ReqctlError(
            f"{ref} states a baseline that cannot be read, and numbering "
            f"from this branch would bury it: {found.stderr.strip()} -- run "
            "`git fetch origin`, then retry"
        )
    held = loads(found.stdout, ref)
    if not isinstance(held, dict) or type(held.get("baseline")) is not int:
        # @req> REQ-30898926@Vu28eWaG_1mE 2ydsz4
        raise ReqctlError(
            f"{ref} states a baseline that does not say which one it is, so "
            "the number that follows it cannot be read -- on the default "
            "branch, by pull request, set `baseline` in that file to an "
            "integer by hand, then run `git fetch origin`"
        )
    return held["baseline"]


def _stated(root):
    if not path(root).is_file():
        return None
    held = read(path(root))
    if not isinstance(held, dict) or type(held.get("baseline")) is not int:
        # @req> REQ-30898926@Vu28eWaG_1mE h4golz
        raise ReqctlError(
            f"{path(root).name} does not say which baseline it holds, and a "
            "new one would bury that rather than settle it -- `reqctl "
            "baseline --check` names the fault; set `baseline` in that file "
            "to an integer by hand, then run `reqctl baseline --generate`"
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
    # @req> REQ-20411754@mcpvTzFw73NC d3ntho
    if claimed is not None:
        # @req> REQ-30898926@Vu28eWaG_1mE cbe5hq
        raise ReqctlError(
            f"{path(root).name} holds an unresolved merge, and no default "
            "branch says which baseline it follows -- add origin with `git "
            "remote add origin URL`, fetch it, then generate"
        )
    return stated, None


def generate(tree, root):
    approved = derive(tree)
    # @req> REQ-35349268@UFojthZ7FMKX xfjprt
    if not approved:
        # @req> REQ-30898926@Vu28eWaG_1mE 7cwxrz
        raise ReqctlError("nothing approved; a baseline of nothing states "
                          "nothing -- approve an item through a corpus pull "
                          "request, then run `reqctl baseline --generate`")
    # @req+ REQ-63399155@6l4OsixGYKDz ygxzq3
    numbered = _numbered(root)
    if numbered:
        # @req> REQ-30898926@Vu28eWaG_1mE rzgvee
        raise ReqctlError(
            f"{', '.join(held.name for held in numbered)}: the numbered layout "
            "was replaced by one baseline; delete it, then generate"
        )
    # @req- ygxzq3

    # @req+ REQ-85375321@NWiQynsqgVPX yvehmw
    shared = sorted(name for name, wore in carriers(tree).items()
                    if len(wore) > 1)
    if shared:
        # @req> REQ-30898926@Vu28eWaG_1mE bfwfke
        raise ReqctlError(
            f"{', '.join(shared)}: more than one item has carried this name, "
            "so a baseline stating it would name no one item -- rename one of "
            "them, then generate"
        )
    # @req- yvehmw

    # @req+ REQ-28086776@7S0DPOiDLvSm thbrwa
    previous, claimed = _previous(root)
    # @req+ REQ-73312524@Eij54nBVNhs0 mgwroy
    dirty = uncommitted(root)
    if dirty:
        # @req> REQ-30898926@Vu28eWaG_1mE jfjqxs
        raise ReqctlError(
            f"{', '.join(dirty)}: uncommitted -- commit the corpus, "
            "then generate"
        )
    # @req- mgwroy

    # @req+ REQ-87283234@HOs3YEHAJSD_ cc4ozn
    # @req> REQ-51424927@vQb-YtKja6pq n2tclj
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
        # @req> REQ-44642786@f_tuj97sj5Zn wywtng
        problems += [f"{uid}: approved but no baseline states it -- run "
                     "`reqctl baseline --generate`" for uid in sorted(derive(tree))]
        return None, problems

    # @req+ REQ-52307457@2GAIsxcSUISq w27scf
    # @req+ REQ-10024282@x7WPiNHGRX8n njzhlf
    claimed = _unresolved(path(root))
    if claimed is not None:
        stated = " and ".join(str(one) for one in sorted(set(claimed)))
        return None, problems + [
            f"{path(root).name}: holds an unresolved merge claiming {stated} "
            "-- `reqctl baseline --generate` cuts the one that follows both"
        ]
    # @req- njzhlf
    # @req- w27scf

    manifest = read(path(root))
    if not isinstance(manifest, dict):
        # @req> REQ-30898926@Vu28eWaG_1mE 5hz7xx
        return None, problems + [
            f"{path(root).name}: is not a mapping -- make it a mapping with "
            "an integer `baseline` by hand, then run `reqctl baseline "
            "--generate`"
        ]
    number = manifest.get("baseline")
    head = f"baseline {number}" if type(number) is int else path(root).name

    for error in sorted(validator(schema(root, "baseline")).iter_errors(manifest), key=str):
        where = ".".join(str(p) for p in error.absolute_path) or "(manifest)"
        # @req> REQ-30898926@Vu28eWaG_1mE ehqxmk
        problems.append(
            f"{head}: schema: {where}: {error.message} -- run `reqctl "
            "baseline --generate`, after setting `baseline` to an integer by "
            "hand if it is not one"
        )

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
        # @req> REQ-30898926@Vu28eWaG_1mE klxvpe
        return number, problems + [
            f"{head}: items is not a mapping -- run `reqctl baseline "
            "--generate`"
        ]

    # @req+ REQ-44642786@f_tuj97sj5Zn rfw24o
    current = derive(tree)
    # @req> REQ-13861816@OGhn1Q-Xs0__ db6w7v
    recorded = _restated(recorded, tree)
    for uid in sorted(set(recorded) - set(current)):
        # @req> REQ-30898926@Vu28eWaG_1mE b6pw73
        problems.append(
            f"{uid}: in baseline {number} but no longer approved -- run "
            "`reqctl baseline --generate`, or restore the approval with "
            f"`reqctl revise {uid} --status approved`"
        )
    for uid in sorted(set(current) - set(recorded)):
        # @req> REQ-30898926@Vu28eWaG_1mE ulq5g2
        problems.append(f"{uid}: approved but absent from baseline {number} "
                        "-- run `reqctl baseline --generate`")
    for uid in sorted(set(recorded) & set(current)):
        if recorded[uid] != current[uid]:
            # @req> REQ-30898926@Vu28eWaG_1mE tf3w5a
            problems.append(
                f"{uid}: changed since baseline {number}, so the baseline "
                "states a state the corpus no longer has -- run `reqctl "
                "baseline --generate`, or revert the change to the item"
            )
    # @req- rfw24o
    return number, problems
