import subprocess
from pathlib import Path

from . import corpus
from .corpus import FOLDERS, ReqctlError


def _git(root, *args, given=b"", absent=None):
    try:
        found = subprocess.run(["git", *args], cwd=root, input=given,
                               capture_output=True, check=False)
    except OSError as error:
        raise ReqctlError(f"cannot run git: {error.strerror}") from error
    if found.returncode not in (0, absent):
        raise ReqctlError(f"cannot read the history: git {args[0]} -- "
                          f"{found.stderr.decode(errors='replace').strip()}")
    return None if found.returncode else found.stdout


def _uid(path):
    parts = path.split("/")
    if len(parts) == 3 and parts[2].endswith((".yml", ".yaml")) and not parts[2].startswith("."):
        return parts[2].rpartition(".")[0]
    return None


# @req> REQ-82027237@R-XinrGfTNzL q4dejo
# @req> REQ-73796163@qg5x9Wvk_AEp bdp26a
def carried(uid, data, blocks=frozenset()):
    return corpus.stamp_of(uid, data), {
        key: corpus.entry_stamp_of(uid, data, key)
        for key in [*(corpus.entries(data) or {}),
                    *(f"{block}.{member}" for block in sorted(blocks)
                      for member in corpus.held_block(data, block) or {})]}


def _flat(value):
    return " ".join(corpus.plain(value).split())


# @req> REQ-50929621@tSdGG-tCMu8G dvvyvi
# @req> REQ-24608716@rrTjNN2Ay0D0 w7fcu5
def lines(row):
    width = max(len(key) for key in row["now"])
    return "".join(
        f"\n    {key.replace('_', ' '):<{width}}  pinned  "
        f"{'unknown' if row['then'] is None else _flat(row['then'].get(key))}"
        f"\n    {'':<{width}}  now     {_flat(held)}"
        for key, held in row["now"].items())


class History:
    def __init__(self, root, kinds=FOLDERS):
        self.root = root
        self.folders = [f"requirements/{FOLDERS[kind]}" for kind in kinds]
        self._rows, self._head = None, {}
        self._blobs, self._parsed, self._states = {}, {}, {}

    def _load(self):
        if self._rows is not None:
            return
        if _git(self.root, "rev-parse", "-q", "--verify", "HEAD", absent=1) is None:
            self._rows = {}
            return
        # @req+ REQ-59306961@EGz7Ll3e9FKA dm7ihn
        shallow = Path(self.root) / _git(self.root, "rev-parse", "--git-path",
                                         "shallow").decode().strip()
        grafted = set(shallow.read_text().split()) if shallow.is_file() else set()
        # @req- dm7ihn
        rows, commit = {}, None
        # @req+ REQ-82027237@R-XinrGfTNzL efmrhh
        for line in _git(self.root, "log", "--full-history", "--no-show-signature", "-c",
                         "--raw", "--root", "--no-renames", "--no-abbrev",
                         "--format=%H %ct %cI", "HEAD", "--",
                         *self.folders).decode(errors="replace").splitlines():
            if not line.startswith(":"):
                if line:
                    sha, when, iso = line.split()
                    commit = sha, int(when), None if sha in grafted else iso
                continue
            meta, _, path = line.partition("\t")
            uid = _uid(path)
            if uid is None:
                continue
            count = len(meta) - len(meta.lstrip(":"))
            shas = [sha if sha.strip("0") else None
                    for sha in meta.split()[count + 1:2 * count + 2]]
            row = rows.setdefault(uid, {}).setdefault(
                commit[0], [*commit[1:], None, [None] * count])
            row[2] = row[2] or shas[count]
            row[3] = [was or held for was, held in zip(row[3], shas[:count])]
        ordered = {uid: sorted(held.values(), key=lambda row: -row[0])
                   for uid, held in rows.items()}
        # @req- efmrhh
        head = {_uid(path): meta.split()[2] for meta, _, path in (
            line.partition("\t") for line in _git(
                self.root, "ls-tree", "-r", "HEAD", "--",
                *self.folders).decode(errors="replace").splitlines())}
        wanted = {sha for held in ordered.values() for row in held
                  for sha in (row[2], *row[3]) if sha} | set(head.values())
        out = _git(self.root, "cat-file", "--batch",
                   given="".join(f"{sha}\n" for sha in wanted).encode())
        at = 0
        for sha in wanted:
            end = out.index(b"\n", at)
            _, kind, *size = out[at:end].decode().split()
            if not size:
                raise ReqctlError(f"cannot read the history: git cat-file -- {sha} {kind}")
            at = end + 2 + int(size[0])
            if kind == "blob":
                self._blobs[sha] = out[end + 1:at - 1]
        self._head, self._rows = head, ordered

    def _held(self, uid, sha):
        if sha not in self._parsed:
            try:
                held = corpus.loads(self._blobs[sha].decode(), f"{uid} at {sha}",
                                    aliases=False)
            except (KeyError, UnicodeDecodeError, ReqctlError):
                held = None
            self._parsed[sha] = held if isinstance(held, dict) else None
        return self._parsed[sha]

    def _carried(self, uid, sha, blocks):
        if (uid, sha) not in self._states:
            held = self._held(uid, sha)
            self._states[uid, sha] = None if held is None else carried(uid, held, blocks)
        return self._states[uid, sha]

    # @req> REQ-59306961@EGz7Ll3e9FKA jw6cdl
    # @req> REQ-82027237@R-XinrGfTNzL aum3ke
    # @req> REQ-73796163@qg5x9Wvk_AEp x43h3h
    def updated(self, uid, data):
        self._load()
        blocks = corpus.addressable_blocks(self.root, uid, data)
        now = carried(uid, data, blocks)
        if self._carried(uid, self._head.get(uid), blocks) != now:
            return None
        return next((iso for _, iso, new, parents in self._rows.get(uid, ())
                     if self._carried(uid, new, blocks) == now
                     and all(self._carried(uid, parent, blocks) != now
                             for parent in parents)),
                    None)

    # @req> REQ-50929621@tSdGG-tCMu8G qgp2gz
    # @req> REQ-24608716@rrTjNN2Ay0D0 xyk6zv
    def _beside(self, uid, data, pinned, stamped, fields):
        then = None
        if isinstance(pinned, str):
            self._load()
            then = next((fields(held) for row in self._rows.get(uid, ())
                         if (held := self._held(uid, row[2])) is not None
                         and stamped(held) == pinned), None)
        return {"then": then, "now": fields(data)}

    # @req> REQ-24608716@rrTjNN2Ay0D0 vjkk2b
    def cited(self, uid, data, entry, pinned):
        return self._beside(
            uid, data, pinned,
            lambda held: corpus.cited_stamp(corpus.Item(uid, None, held), entry),
            lambda held: corpus.cited_fields(uid, held, entry))

    # @req> REQ-24608716@rrTjNN2Ay0D0 dzvsq3
    def pinned(self, uid, data, rest, pinned):
        return self._beside(
            uid, data, pinned,
            lambda held: corpus.address_stamp_of(uid, held, rest),
            lambda held: corpus.covered(uid, held, rest))
