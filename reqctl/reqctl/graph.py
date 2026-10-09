from pathlib import Path

from . import cite, corpus


def unstamped(uid, path):
    return (f"{uid}: {path} cites it without the stamp it was written "
            "against -- cite it again with reqctl tag")


def listing(tree, citations, uid=None):
    named = {(citation["uid"], citation["id"]) for citation in citations}
    # @req> REQ-77594104@x3D--4236Dno 7nucmz
    listed = {str(item.uid): corpus.mapping(item.data, corpus.CITATION_LIST)
              for item in corpus.items(tree)
              if corpus.citable(item)}
    problems = []
    # @req> REQ-13384695@P9NXsZKZp683 3lmvqm
    for owner, held in listed.items():
        if uid and owner != uid:
            continue
        for identity in sorted(i for i in held if (owner, i) not in named):
            problems.append(
                f"{owner}: its citation list holds {identity}, which no "
                f"statement citation names together with {owner} -- "
                f"reqctl unlist {owner} {identity}")
    for citation in citations:
        owner, identity = citation["uid"], citation["id"]
        if (uid and owner != uid) or owner not in listed:
            continue
        # @req+ REQ-67655319@ezp6TxUzJ72E wqruf3
        # @req+ REQ-32191310@aZkvQ6hvIwPv pmll7c
        if identity not in listed[owner]:
            problems.append(
                f"{citation['path']}: citation {identity} of {owner} is not in "
                f"its citation list -- read it against {owner}, then reqctl "
                f"repin {identity}")
        elif listed[owner][identity] != citation["digest"]:
            problems.append(
                f"{citation['path']}: citation {identity} of {owner} covers "
                "lines that changed since its citation list took their digest "
                f"-- read them against {owner}, then reqctl repin {identity}")
        # @req- pmll7c
        # @req- wqruf3
    return problems


def whole(tree, tags, root=None, uid=None):
    # @req+ REQ-30061042@b7B9U8dkoUHI cgpbde
    problems = []
    for item in corpus.items(tree):
        owner = str(item.uid)
        if not corpus.citable(item):
            continue
        for path, held in corpus.mapping(item.data, corpus.WHOLE_FILES).items():
            held = held if isinstance(held, dict) else {}
            tags.setdefault(owner, []).append((path, held.get("pinned") or "", None))
            if root is None or (uid and owner != uid):
                continue
            target = (Path(root) / path).resolve()
            if not target.is_relative_to(Path(root).resolve()):
                problems.append(f"{owner}: it holds a whole-file citation of {path}, "
                                "which is not a file of the code base")
                continue
            try:
                text = target.read_bytes().decode()
            except (OSError, UnicodeDecodeError):
                problems.append(f"{owner}: it holds a whole-file citation of {path}, "
                                "which does not read")
                continue
            if held.get("digest") != cite.whole(path, text):
                problems.append(
                    f"{path}: the whole-file citation {owner} holds covers a file "
                    f"that changed since it took its digest -- read it against "
                    f"{owner}, then reqctl tag {path} --req {owner}")
    return problems
    # @req- cgpbde


def trace(tree, root, uid=None):
    citations, cited_problems = cite.read(root, digested=True)
    # @req+ REQ-19896380@2sOnckMwnWfx 6rtw6m
    shown = [c for c in citations if not corpus.is_test(c["path"])]
    tags = cite.cited(shown)
    # @req- 6rtw6m
    # @req+ REQ-30061042@b7B9U8dkoUHI eizlko
    cited_problems += whole(tree, tags, root, uid)
    # @req- eizlko
    # @req> REQ-76962559@NU0P43-PPSGC dyday2
    if uid:
        corpus.find(tree, uid)
    known = {str(item.uid) for item in corpus.items(tree)}

    rows, problems, unimplemented, stale, deprecated = [], list(cited_problems), [], [], []
    # @req> REQ-19896380@2sOnckMwnWfx aes6o5
    # @req> REQ-52825760@f9HMlzmiwhyn 5aendb
    for citation in citations:
        if corpus.is_test(citation["path"]) and (not uid or citation["uid"] == uid):
            problems.append(
                f"{citation['path']}: citation {citation['id']} of "
                f"{citation['uid']} is in a test -- reqctl untag {citation['id']}")
    for item in corpus.items(tree):
        current = str(item.uid)
        # @req> REQ-64570886@Zckz3LzHUzXn jzenja
        if uid and current != uid:
            continue
        data = corpus.raw(item)
        cited = tags.get(current, [])
        files = list(dict.fromkeys(path for path, _, _ in cited))
        rows.append(
            {
                "uid": current,
                "status": data.get("status"),
                "implementation": files,
            }
        )
        if files and not corpus.citable(item):
            problems.append(
                f"{current}: referenced by {', '.join(files)} -- only a "
                "requirement, a guard, a parameter or a data item is cited. "
                "Tag the requirement stated against it instead"
            )
        # @req> REQ-35979865@pd7CVJ7isMys iz2v2g
        # @req> REQ-77594104@x3D--4236Dno tizjds
        if (corpus.citable(item)
                and data.get("status") == "deprecated" and cited):
            deprecated += [{"uid": current, "path": path} for path
                           in dict.fromkeys(p for p, pinned, _ in cited if pinned)]
            problems += [unstamped(current, path)
                         for path, pinned, _ in cited if not pinned]
            continue
        if data.get("status") != "approved":
            if files:
                problems.append(
                    f"{current}: referenced by {', '.join(files)} but is "
                    f"{data.get('status')}, not approved"
                )
            continue
        # @req> REQ-77594104@x3D--4236Dno lgfhiu
        if corpus.citable(item):
            for path, pinned, entry in cited:
                # @req+ REQ-74122607@f-RdDZCNkgqC pbsx4y
                address = f"{current}.{entry}" if entry else current
                if entry and entry not in corpus.cited_entries(item):
                    problems.append(f"{address}: referenced by {path} but no such entry")
                    continue
                held = corpus.cited_stamp(item, entry)
                # @req- pbsx4y
                # @req> REQ-75161909@GUQmRsLIBj6Z 7df3my
                if not pinned:
                    problems.append(unstamped(address, path))
                elif pinned != held:
                    stale.append({"uid": address, "path": path,
                                  "pinned": pinned, "held": held})
        # @req> REQ-73027720@SebUlS2i_noq 3aqkc5
        if current.startswith(("REQ-", "GUARD-")) and not files:
            unimplemented.append(current)

    if not uid:
        for tagged in sorted(tags):
            if tagged not in known:
                problems.append(
                    f"{tagged}: referenced by "
                    f"{', '.join(dict.fromkeys(p for p, _, _ in tags[tagged]))}"
                    " but no "
                    "such requirement"
                )
    # @req> REQ-67655319@ezp6TxUzJ72E eznv3q
    # @req> REQ-13384695@P9NXsZKZp683 qtu6ly
    # @req> REQ-32191310@aZkvQ6hvIwPv 65dur7
    problems += listing(tree, citations, uid)

    return {"rows": rows, "problems": problems, "stale": stale,
            "deprecated": deprecated, "unimplemented": sorted(unimplemented),
            "citations": [c for c in shown if not uid or c["uid"] == uid]}
