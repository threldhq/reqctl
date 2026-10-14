from .corpus import (CITATION_LIST, CONFLICTED, Item, ReqctlError, loads,
                     mapping, path_for, read_text, same, save, sides)

PINS = "assessed"
GONE = object()


def _side(text, where):
    # @req> REQ-49870454@KKNV-vdY6oM1 ilmqvb
    held = loads(text, where, aliases=False)
    if not isinstance(held, dict):
        raise ReqctlError(
            f"{where.stem} holds an unresolved merge, and a side of it does "
            "not read as an item -- settle it by hand"
        )
    return held


def _reached(path, text):
    ours, theirs = (_side(side, path) for side in sides(text))
    pinned = all(isinstance(held.get(PINS), dict) for held in (ours, theirs))
    skipped = ({PINS} if pinned else set()) | {CITATION_LIST}
    spoken = {key: value for key, value in ours.items() if key not in skipped}
    answered = {key: value for key, value in theirs.items() if key not in skipped}
    return ours, theirs, skipped, spoken, sorted(
        str(key) for key in set(spoken) | set(answered)
        if not same(spoken.get(key, GONE), answered.get(key, GONE)))


def merged(path, text):
    # @req+ REQ-38498011@eJXtv0pwMf-A 3sjv5b
    try:
        reached = _reached(path, text)[-1]
    except ReqctlError:
        return f"{path} holds an unresolved merge"
    if not reached:
        return (f"{path} holds an unresolved merge within its pins and citation "
                f"list -- `reqctl resolve {path.stem}` settles it")
    return (f"{path} holds an unresolved merge reaching {', '.join(reached)}, "
            "outside its pins and citation list")
    # @req- 3sjv5b


def resolve(store, uid):
    # @req+ REQ-95299157@dJzPK-VOKyQG w4qjbn
    path = path_for(store.root, uid)
    text = read_text(path)
    if not CONFLICTED.search(text):
        raise ReqctlError(f"{uid} holds no unresolved merge")
    ours, theirs, skipped, spoken, reached = _reached(path, text)
    if reached:
        raise ReqctlError(
            f"{uid}: the merge reaches {', '.join(reached)}, outside its pins "
            f"and citation list -- settle {'it' if len(reached) == 1 else 'them'}"
            " by hand"
        )
    held = dict(spoken)
    dropped = {}
    for key in sorted(skipped):
        mine, yours = mapping(ours, key), mapping(theirs, key)
        kept = {name: value for name, value in mine.items()
                if same(yours.get(name, GONE), value)}
        if kept or key == PINS:
            held[key] = kept
        dropped[key] = sorted((set(mine) | set(yours)) - set(kept))
    save(store, Item(uid, path, held))
    return path, dropped.get(PINS, []), dropped[CITATION_LIST]
# @req- w4qjbn
