#!/usr/bin/env python3
import ast
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "plugin" / "hooks"
ENDS = {"exit", "_exit"}
ENDING = {"abort", "kill", "killpg", "execl", "execle", "execlp",
          "execlpe", "execv", "execve", "execvp", "execvpe", "fexecve"}
VALUES = {"quit", "SystemExit"}
TAKEN = ENDS | ENDING
REFUSED = ENDING | {"error", "parse_args", "parse_known_args"}
NAMED = TAKEN | VALUES | REFUSED

faults, scanned, admitted = [], 0, 0
for path in sorted(HOOKS.rglob("*.py")):
    scanned += 1
    # @req+ GUARD-83168738@zhoOQpGgBd9R 4kckqu
    try:
        tree = ast.parse(path.read_text())
    except (OSError, UnicodeDecodeError, SyntaxError) as error:
        faults.append(f"{path.relative_to(HOOKS)}: cannot parse: {error}")
        continue
    # @req- 4kckqu
    # @req+ REQ-51060455@Z5EVUURxm1nV qrn3wi
    failed_write = {id(statement.value)
                    for deny in tree.body
                    if isinstance(deny, ast.FunctionDef) and deny.name == "deny"
                    for handler in deny.body if isinstance(handler, ast.Try)
                    for caught in handler.handlers
                    if isinstance(caught.type, ast.Name) and caught.type.id == "OSError"
                    for statement in caught.body if isinstance(statement, ast.Expr)}
    called = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        at = f"{path.relative_to(HOOKS)}:{getattr(node, 'lineno', 0)}: "
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*" or alias.name in NAMED:
                    faults.append(f"{at}imports {alias.name} from {node.module}; "
                                  "a hook decides with sys.exit(0) or deny()")
        named = (node.attr if isinstance(node, ast.Attribute)
                 else node.id if isinstance(node, ast.Name) else None)
        if named in VALUES or (named in ENDS and isinstance(node, ast.Name)):
            faults.append(f"{at}{named} is not the hook's; a hook decides with "
                          "sys.exit(0) or deny()")
        elif named in TAKEN and id(node) not in called:
            faults.append(f"{at}{named} taken as a value; call sys.exit(0) or "
                          "deny() where the hook decides")
        if isinstance(node, ast.Constant) and node.value in NAMED:
            faults.append(f"{at}{node.value!r} names an exit; call sys.exit(0) "
                          "or deny() where the hook decides")
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        args = [arg.value if isinstance(arg, ast.Constant) else None
                for arg in node.args]
        status = (args[0] if len(args) == 1 and not node.keywords
                  and type(args[0]) is int else None)
        if isinstance(func, ast.Name) and func.id == "getattr" and (
                len(args) < 2 or not isinstance(args[1], str)):
            faults.append(f"{at}a getattr the guard cannot tell from an exit; "
                          "name the attribute outright")
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr in REFUSED:
            faults.append(f"{at}{func.attr}() ends the hook without its "
                          "decision; sys.exit(0) or deny()")
        elif (func.attr == "exit" and isinstance(func.value, ast.Name)
                and func.value.id == "sys" and status == 2
                and id(node) in failed_write):
            admitted += 1
            if admitted > 1:
                faults.append(f"{at}a second sys.exit(2) a failed write of a "
                              "deny decision reaches; the hooks hold one, in "
                              "the module-level deny")
        elif func.attr in ENDS and status != 0:
            faults.append(f"{at}an {func.attr} call that is not exit(0), nor the "
                          "exit(2) the module-level deny reaches when its "
                          "decision cannot be written")
    # @req- qrn3wi

if not scanned:
    faults.append(f"no hook script found under {HOOKS}; a check that scanned "
                  "nothing has not passed")

for fault in faults:
    print(fault)
sys.exit(1 if faults else 0)
