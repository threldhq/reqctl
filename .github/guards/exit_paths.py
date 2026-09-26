#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "plugin" / "hooks"

faults, scanned = [], 0
for path in sorted(HOOKS.rglob("*.py")):
    scanned += 1
    try:
        tree = ast.parse(path.read_text())
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        faults.append(f"{path.relative_to(HOOKS)}: cannot parse: {error}")
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in ("exit", "quit"):
                faults.append(f"{path.relative_to(HOOKS)}:{node.lineno}: "
                              f"{func.id}() is the interpreter's; a hook "
                              "decides with sys.exit(0)")
            elif (isinstance(func, ast.Attribute)
                    and func.attr in ("exit", "_exit")
                    and not (len(node.args) == 1 and not node.keywords
                             and isinstance(node.args[0], ast.Constant)
                             and node.args[0].value == 0)):
                faults.append(f"{path.relative_to(HOOKS)}:{node.lineno}: "
                              f"an {func.attr} call that is not exit(0)")
        if isinstance(node, ast.Raise):
            exc = node.exc
            target = exc.func if isinstance(exc, ast.Call) else exc
            if isinstance(target, ast.Name) and target.id == "SystemExit":
                faults.append(f"{path.relative_to(HOOKS)}:{node.lineno}: "
                              "raise SystemExit bypasses the decision; "
                              "sys.exit(0) or deny()")

if not scanned:
    faults.append(f"no hook script found under {HOOKS}; a check that scanned "
                  "nothing has not passed")

for fault in faults:
    print(fault)
sys.exit(1 if faults else 0)
