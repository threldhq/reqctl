import re
from pathlib import Path

from .baseline import _default_ref, _git
from .corpus import ReqctlError, loads, mapping

SETTINGS = Path("requirements") / "settings.yml"
PINNED = re.compile(r"claude-[a-z0-9.-]*[0-9][a-z0-9.-]*")
AGENTS = "elucidate_agents"
NESTED = ("nest each value under its data item, entry and field, as "
          "review_limits: {page_bytes: {quantity: 10485760}}")
# @req+ REQ-87066486@AtzPEAcAbJ1v 7yxrtp
# @req> review_limits@S5WLKWwLWBaM ulaguu
REVIEW_LIMITS = {
    "fetch_attempts": {"quantity": 3},
    "fetch_seconds": {"quantity": 60},
    "page_bytes": {"quantity": 5242880},
    "redirects": {"quantity": 5},
    "summary_lines": {"quantity": 10},
}
# @req> challenge_bounds@AvWATCpAYqRO j6wvnl
CHALLENGE_BOUNDS = {
    "agent_ceiling": {"quantity": 150},
    "floor_k": {"quantity": 10},
    "judge_bound": {"quantity": 45},
    "judge_group": {"quantity": 20},
    "recall_batch": {"quantity": 40},
}
# @req> elucidate_agents@CN8gGihmCaVl bmtivj
ELUCIDATE_AGENTS = {
    "best_in_class": {"model": "claude-sonnet-5-5", "effort": "high"},
    "coverage": {"model": "claude-sonnet-5-5", "effort": "high"},
    "recall": {"model": "claude-sonnet-5-5", "effort": "medium"},
    "judge": {"model": "claude-opus-5-5", "effort": "high"},
}
# @req> portal_token_permissions@vjGyU5xrFJwz xjvwbq
PORTAL_TOKEN_PERMISSIONS = {
    "actions": {"access": "read and write"},
    "contents": {"access": "read"},
    "pull_requests": {"access": "read"},
}
SHIPPED = {"review_limits": REVIEW_LIMITS, "challenge_bounds": CHALLENGE_BOUNDS,
           AGENTS: ELUCIDATE_AGENTS,
           "portal_token_permissions": PORTAL_TOKEN_PERMISSIONS}
# @req- 7yxrtp


def path(root):
    return Path(root) / SETTINGS


# @req> REQ-32331515@Nn3qX9jMrAU- bl2ps5
# @req> REQ-42769459@biZgG4XwBVRY ipg3lp
def _default(root):
    try:
        return _default_ref(root)
    except ReqctlError:
        return None


def _leaves(held, shipped, at):
    if not isinstance(held, dict) or not isinstance(shipped, dict):
        yield at, held, shipped
        return
    if not held and not shipped:
        yield at, held, shipped
    for key, value in held.items():
        yield from _leaves(value, shipped.get(key, {}), (*at, key))


def faults(document):
    if document is None:
        return []
    # @req> REQ-99278123@vBQXVC8aZZp3 fv2afe
    if not isinstance(document, dict):
        return [f"{document!r} names no value a settings file may replace -- "
                f"{NESTED}"]
    found = []
    for at, value, shipped in _leaves(document, SHIPPED, ()):
        key = ".".join(map(str, at))
        if isinstance(shipped, dict):
            # @req> REQ-99278123@vBQXVC8aZZp3 qgpb6a
            found.append(f"{key} names no value a settings file may replace -- "
                         f"{NESTED}")
        elif type(value) is not type(shipped):
            # @req> REQ-78887253@ZroFZuS_zv0q yaohat
            found.append(f"{key}: {value!r} is not of the YAML type of the "
                         f"{shipped!r} the product ships")
        elif at[-1] == "quantity" and value < 1:
            # @req> REQ-21585959@QkioE_Ciddeh qjsy3y
            found.append(f"{key}: {value!r} is not a whole number of at least "
                         "one")
        elif at[-1] == "model" and not PINNED.fullmatch(value):
            # @req> REQ-15362279@YwMnA4sMLpfF 3pjtrt
            found.append(f"{key}: {value!r} is not a pinned model ID, such as "
                         "claude-opus-5-5")
    # @req+ REQ-59792666@dkbVbhN0Y4FS sspl2m
    for entry, fields in mapping(document, AGENTS).items():
        if (isinstance(fields, dict) and {"model", "effort"} & fields.keys()
                and not (fields.get("model") and fields.get("effort"))):
            found.append(f"{AGENTS}.{entry} states a model without an effort, "
                         "or an effort without a model -- state both")
    # @req- sspl2m
    return found


# @req> REQ-32331515@Nn3qX9jMrAU- m5bqyr
# @req> REQ-34403718@OXYW6pAY1oxO 7tnuse
def read(root):
    ref = _default(root)
    # @req> REQ-42769459@biZgG4XwBVRY mfrzc7
    if ref is None:
        return None, {}
    named = SETTINGS.as_posix()
    where = f"{ref.removeprefix('refs/remotes/')}:{named}"
    listed = _git(root, "ls-tree", ref, "--", named)
    if listed.returncode:
        raise ReqctlError(f"cannot read the tree {ref} names, so whether it "
                          f"holds {named} cannot be told: "
                          f"{listed.stderr.strip()}")
    # @req> REQ-31526771@dzOAej5vGh2Y wa4iuz
    if not listed.stdout.strip():
        return where, {}
    shown = _git(root, "show", f"{ref}:{named}")
    if shown.returncode:
        raise ReqctlError(f"{where} cannot be read: {shown.stderr.strip()}")
    document = loads(shown.stdout, where)
    found = faults(document)
    # @req> REQ-99278123@vBQXVC8aZZp3 lcnls5
    # @req> REQ-78887253@ZroFZuS_zv0q iywc46
    # @req> REQ-21585959@QkioE_Ciddeh blmk44
    # @req> REQ-15362279@YwMnA4sMLpfF fxnobd
    # @req> REQ-59792666@dkbVbhN0Y4FS txoz2e
    if found:
        raise ReqctlError(f"{where} cannot be used -- correct it on the "
                          "default branch:\n"
                          + "\n".join(f"  {fault}" for fault in found))
    return where, {".".join(at): value
                   for at, value, _ in _leaves(document or {}, SHIPPED, ())}


# @req> REQ-40447106@_7d9O2HDnoPr jyttul
# @req> REQ-31526771@dzOAej5vGh2Y ncvzwe
def table(stated, item):
    return {entry: {field: stated.get(f"{item}.{entry}.{field}", value)
                    for field, value in fields.items()}
            for entry, fields in SHIPPED[item].items()}


def quantities(stated, item):
    return {entry: fields["quantity"]
            for entry, fields in table(stated, item).items()}
