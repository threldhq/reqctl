from .corpus import (CONFLICTED, Item, ReqctlError, loads, mapping, path_for,
                     read_text, same, save, sides)

PINS = "assessed"


def _side(text, where):
    held = loads(text, where)
    if not isinstance(held, dict):
        raise ReqctlError(
            f"{where.stem} holds an unresolved merge, and a side of it does "
            "not read as an item -- settle it by hand"
        )
    return held


def resolve(store, uid):
    # @req+ REQ-95299157@ZQGWNBottyNx w4qjbn
    path = path_for(store.root, uid)
    text = read_text(path)
    if not CONFLICTED.search(text):
        raise ReqctlError(f"{uid} holds no unresolved merge")
    ours, theirs = (_side(side, path) for side in sides(text))
    pinned = all(isinstance(held.get(PINS), dict) for held in (ours, theirs))
    skipped = {PINS} if pinned else set()
    spoken = {key: value for key, value in ours.items() if key not in skipped}
    answered = {key: value for key, value in theirs.items() if key not in skipped}
    gone = object()
    reached = sorted(key for key in set(spoken) | set(answered)
                     if not same(spoken.get(key, gone), answered.get(key, gone)))
    if reached:
        raise ReqctlError(
            f"{uid}: the merge reaches {', '.join(reached)}, which no pin "
            f"states -- settle {'it' if len(reached) == 1 else 'them'} by hand"
        )
    mine, yours = mapping(ours, PINS), mapping(theirs, PINS)
    kept = {key: value for key, value in mine.items()
            if same(yours.get(key, gone), value)}
    held = dict(spoken)
    held[PINS] = kept
    save(store, Item(uid, path, held))
    return path, sorted((set(mine) | set(yours)) - set(kept))
# @req- w4qjbn
