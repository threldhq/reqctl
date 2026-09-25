from . import cite, corpus


def trace(tree, root, uid=None):
    citations, cited_problems = cite.read(root)
    tags = cite.cited(citations)
    # @req> REQ-76962559@j8u3NeYOT_2k dyday2
    if uid:
        corpus.find(tree, uid)
    known = {str(item.uid) for item in corpus.items(tree)}

    rows, problems, unimplemented, stale = [], list(cited_problems), [], []
    for item in corpus.items(tree):
        current = str(item.uid)
        # @req> REQ-64570886@39w5gpQE9c9Z jzenja
        if uid and current != uid:
            continue
        data = corpus.raw(item)
        cited = tags.get(current, [])
        files = list(dict.fromkeys(path for path, _ in cited))
        implementation = [p for p in files if not corpus.is_test(p)]
        tests = [p for p in files if corpus.is_test(p)]
        rows.append(
            {
                "uid": current,
                "status": data.get("status"),
                "implementation": implementation,
                "tests": tests,
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
                    problems.append(
                        f"{current}: {path} cites it without the stamp it was "
                        "written against -- cite it again with reqctl tag"
                    )
                elif pinned != held:
                    stale.append({"uid": current, "path": path,
                                  "pinned": pinned, "held": held})
            if not implementation:
                unimplemented.append(current)
            # @req+ REQ-26361925@EMfIgZyFH4bw soom6a
            # @req> REQ-76258226@8oshGhfGWgBF kmi47r
            elif data.get("verification") == "automated_test" and not tests:
                problems.append(
                    f"{current}: verification is automated_test but no test references it"
                )
            # @req- soom6a

    if not uid:
        for tagged in sorted(tags):
            if tagged not in known:
                problems.append(
                    f"{tagged}: referenced by "
                    f"{', '.join(dict.fromkeys(p for p, _ in tags[tagged]))}"
                    " but no "
                    "such requirement"
                )

    return {"rows": rows, "problems": problems, "stale": stale,
            "unimplemented": sorted(unimplemented),
            "citations": [c for c in citations if not uid or c["uid"] == uid]}
