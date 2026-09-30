from . import cite, corpus


def unstamped(uid, path):
    return (f"{uid}: {path} cites it without the stamp it was written "
            "against -- cite it again with reqctl tag")


def listing(tree, citations, uid=None):
    named = {(citation["uid"], citation["id"]) for citation in citations}
    listed = {str(item.uid): corpus.mapping(item.data, corpus.CITATION_LIST)
              for item in corpus.items(tree)
              if str(item.uid).startswith(("REQ-", "GUARD-"))}
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
        # @req+ REQ-32191310@ot16I3lSs2Nu pmll7c
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


def trace(tree, root, uid=None):
    citations, cited_problems = cite.read(root, digested=True)
    # @req+ REQ-19896380@2sOnckMwnWfx 6rtw6m
    shown = [c for c in citations if not corpus.is_test(c["path"])]
    tags = cite.cited(shown)
    # @req- 6rtw6m
    # @req> REQ-76962559@j8u3NeYOT_2k dyday2
    if uid:
        corpus.find(tree, uid)
    known = {str(item.uid) for item in corpus.items(tree)}

    rows, problems, unimplemented, stale, deprecated = [], list(cited_problems), [], [], []
    # @req> REQ-19896380@2sOnckMwnWfx aes6o5
    for citation in citations:
        if corpus.is_test(citation["path"]) and (not uid or citation["uid"] == uid):
            problems.append(
                f"{citation['path']}: citation {citation['id']} of "
                f"{citation['uid']} is in a test -- reqctl untag {citation['id']}")
    for item in corpus.items(tree):
        current = str(item.uid)
        # @req> REQ-64570886@39w5gpQE9c9Z jzenja
        if uid and current != uid:
            continue
        data = corpus.raw(item)
        cited = tags.get(current, [])
        files = list(dict.fromkeys(path for path, _ in cited))
        rows.append(
            {
                "uid": current,
                "status": data.get("status"),
                "implementation": files,
            }
        )
        if current.startswith(("PARAM-", "DATA-", "TERM-")) and files:
            noun, holds = (("term", "a definition")
                           if current.startswith("TERM-")
                           else ("parameter", "a value")
                           if current.startswith("PARAM-")
                           else ("data item", "a value"))
            problems.append(
                f"{current}: referenced by {', '.join(files)} -- a {noun} "
                f"is {holds}; nothing implements it. Tag the requirement "
                "stated against it instead"
            )
        # @req> REQ-35979865@-t3USRO-BKGk iz2v2g
        if (current.startswith(("REQ-", "GUARD-"))
                and data.get("status") == "deprecated" and cited):
            deprecated += [{"uid": current, "path": path} for path
                           in dict.fromkeys(p for p, pinned in cited if pinned)]
            problems += [unstamped(current, path)
                         for path, pinned in cited if not pinned]
            continue
        if data.get("status") != "approved":
            if files:
                problems.append(
                    f"{current}: referenced by {', '.join(files)} but is "
                    f"{data.get('status')}, not approved"
                )
            continue
        if current.startswith(("REQ-", "GUARD-")):
            held = corpus.tag_stamp(corpus.stamp(item)) if cited else None
            for path, pinned in cited:
                # @req> REQ-75161909@bnqFzGCM1y16 7df3my
                if not pinned:
                    problems.append(unstamped(current, path))
                elif pinned != held:
                    stale.append({"uid": current, "path": path,
                                  "pinned": pinned, "held": held})
            if not files:
                unimplemented.append(current)

    if not uid:
        for tagged in sorted(tags):
            if tagged not in known:
                problems.append(
                    f"{tagged}: referenced by "
                    f"{', '.join(dict.fromkeys(p for p, _ in tags[tagged]))}"
                    " but no "
                    "such requirement"
                )
    # @req> REQ-67655319@ezp6TxUzJ72E eznv3q
    # @req> REQ-13384695@P9NXsZKZp683 qtu6ly
    # @req> REQ-32191310@ot16I3lSs2Nu 65dur7
    problems += listing(tree, citations, uid)

    return {"rows": rows, "problems": problems, "stale": stale,
            "deprecated": deprecated, "unimplemented": sorted(unimplemented),
            "citations": [c for c in shown if not uid or c["uid"] == uid]}
