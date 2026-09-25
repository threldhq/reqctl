BEARINGS = ["same", "overlaps", "contradicts", "parent", "prerequisite",
            "restricted_by", "related"]
FINDINGS = ["covered_whole", "covered_part", "conflict", "derives_from",
            "depends_on", "constrains", "supersedes", "near"]
EDGES = ["derives_from", "depends_on", "constrains", "supersedes"]
REASON = {"type": "string", "minLength": 1, "maxLength": 300}
UID = {"type": "string", "pattern": "^(REQ|GUARD)-[0-9]{8}$|^proposal [0-9]+$"}
NAME = {"type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)?$"}


def _list(item):
    return {"type": "array", "items": item}


def _object(required, properties):
    return {"type": "object", "additionalProperties": False,
            "required": required, "properties": properties}


CITED = {"requirements": "^REQ-[0-9]{8}$", "guards": "^GUARD-[0-9]{8}$",
         "siblings": "^proposal [0-9]+$"}


def recall(scope):
    return _object(["shard", "batch", "results"], {
        "shard": {"type": "string"},
        "batch": {"type": "integer", "minimum": 1},
        "results": _list(_object(["proposal", "hits"], {
            "proposal": {"type": "integer", "minimum": 1},
            "hits": _list(_object(["uid", "bearing", "clause"], {
                "uid": {"type": "string", "pattern": CITED[scope]},
                "bearing": {"type": "string", "enum": BEARINGS},
                "clause": REASON,
            })),
        })),
    })

GROUP = _object(["proposal", "group", "findings"], {
    "proposal": {"type": "integer", "minimum": 1},
    "group": {"type": "integer", "minimum": 1},
    "findings": _list(_object(["uid", "kind", "clause", "reason"], {
        "uid": UID,
        "kind": {"type": "string", "enum": FINDINGS},
        "clause": REASON,
        "reason": REASON,
    })),
})

JUDGE = _object(["proposal", "covered_by", "conflicts", "relations", "nearest",
                 "values", "words", "faults", "questions"], {
    "proposal": {"type": "integer", "minimum": 1},
    "covered_by": _list(_object(["uids", "covers", "reason"], {
        "uids": {"type": "array", "minItems": 1, "items": UID},
        "covers": {"type": "string", "enum": ["whole", "part"]},
        "reason": REASON,
    })),
    "conflicts": _list(_object(["uid", "reason"], {
        "uid": UID, "reason": REASON,
    })),
    "relations": _list(_object(["target", "kind", "reason"], {
        "target": UID,
        "kind": {"type": "string", "enum": EDGES},
        "reason": REASON,
    })),
    "nearest": _list(_object(["uid", "why_not"], {
        "uid": UID, "why_not": REASON,
    })),
    "values": _list(_object(["value", "belongs_with", "reason"], {
        "value": {"type": "string", "minLength": 1, "maxLength": 60},
        "belongs_with": {"anyOf": [NAME, {"type": "null"}]},
        "reason": REASON,
    })),
    "words": _list(_object(["word", "defined_by", "reason"], {
        "word": {"type": "string", "minLength": 1, "maxLength": 60},
        "defined_by": {"anyOf": [NAME, {"type": "null"}]},
        "reason": REASON,
    })),
    "faults": _list(_object(["fault", "reason"], {
        "fault": {"type": "string", "enum": [
            "ambiguous", "unverifiable", "compound", "foreign_id",
            "undetermined_outcome", "inappropriate_implementation"]},
        "reason": REASON,
    })),
    "questions": _list({"type": "string", "minLength": 1, "maxLength": 300}),
})

CITING = {"covered_by": "uids", "conflicts": "uid", "relations": "target",
          "nearest": "uid"}
