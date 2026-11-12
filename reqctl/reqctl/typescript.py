import functools
from dataclasses import dataclass, field

import tree_sitter
import tree_sitter_typescript

GRAMMARS = {".ts": tree_sitter.Language(tree_sitter_typescript.language_typescript()),
            ".tsx": tree_sitter.Language(tree_sitter_typescript.language_tsx())}
SUFFIXES = tuple(GRAMMARS)
KEPT = ("string", "template_string", "regex", "jsx_text")
TYPED = ("type_annotation", "type_arguments", "type_parameters", "type_alias_declaration",
         "interface_declaration", "type_query", "implements_clause", "extends_type_clause",
         "nested_type_identifier", "type_predicate_annotation", "asserts_annotation",
         "ambient_declaration", "import_statement")
NAMED = ("identifier", "shorthand_property_identifier")
TAGS = ("jsx_opening_element", "jsx_closing_element", "jsx_self_closing_element")
EMBEDDING = ("jsx_expression", "jsx_opening_element", "jsx_self_closing_element")
DECLARED = ("function_declaration", "generator_function_declaration", "enum_declaration")
BINDING = ("lexical_declaration", "variable_declaration")


@dataclass
class Reading:
    spans: list = field(default_factory=list)
    literals: dict = field(default_factory=dict)
    regions: list = field(default_factory=list)
    table: dict = field(default_factory=dict)
    names: list = field(default_factory=list)
    imports: set = field(default_factory=set)
    broken: int | None = None


def _bound(node):
    if node is None:
        return []
    if node.type in ("identifier", "shorthand_property_identifier_pattern"):
        return [node.text.decode()]
    if node.type == "pair_pattern":
        return _bound(node.child_by_field_name("value"))
    if node.type in ("object_assignment_pattern", "assignment_pattern"):
        return _bound(node.child_by_field_name("left"))
    if node.type in ("object_pattern", "array_pattern", "rest_pattern"):
        return [name for child in node.named_children for name in _bound(child)]
    return []


# @req> REQ-45330509@y34lW04HzVzy u54ghq
def _declarations(root):
    table = {}
    for outer in root.named_children:
        inner = outer.child_by_field_name("declaration") if outer.type == "export_statement" else outer
        if inner is None:
            continue
        span = (outer.start_point.row + 1, outer.end_point.row + 1)
        if inner.type in DECLARED:
            names = _bound(inner.child_by_field_name("name"))
        elif inner.type in BINDING:
            names = [name for child in inner.named_children if child.type == "variable_declarator"
                     for name in _bound(child.child_by_field_name("name"))]
        else:
            names = []
        for name in names:
            table.setdefault(name, []).append(("def", span))
    return table


def _intrinsic(node):
    parent = node.parent
    return (parent is not None and parent.type in TAGS
            and parent.child_by_field_name("name") == node and node.text[:1].islower())


def _region(node):
    if node.type == "jsx_element":
        opened, closed = node.child_by_field_name("open_tag"), node.child_by_field_name("close_tag")
        return (opened.end_point if opened else node.start_point,
                closed.start_point if closed else node.end_point, True)
    if node.type in EMBEDDING:
        return node.start_point, node.end_point, False
    return None


def _among(regions, at):
    held = [region for region in regions if region[0] <= at < region[1]]
    return bool(held) and max(held, key=lambda region: region[0])[2]


def _offsets(text):
    lines = text.split("\n")
    starts, at = [], 0
    for line in lines:
        starts.append(at)
        at += len(line) + 1
    return lambda point: starts[point.row] + len(
        lines[point.row].encode()[:point.column].decode(errors="ignore"))


# @req+ REQ-60833823@pdX0Xr4bVNDt n7el7s
# @req+ REQ-71419978@R9LaJT-ldfB9 v46n7n
@functools.cache
def read(suffix, text):
    tree = tree_sitter.Parser(GRAMMARS[suffix]).parse(text.encode())
    reading, offset = Reading(), _offsets(text)
    reading.table = _declarations(tree.root_node)
    every, todo = [], [tree.root_node]
    while todo:
        node = todo.pop()
        every.append(node)
        todo += reversed(node.children)
    reading.regions = [region for node in every if (region := _region(node)) is not None]
    reading.broken = next((node.start_point.row + 1 for node in every
                           if node.is_error or node.is_missing), None)
    held_until = typed_until = -1
    for node in every:
        if node.start_byte >= held_until and (node.type == "comment" or node.type in KEPT):
            rendered = node.type != "comment" or _among(reading.regions, node.start_point)
            reading.spans.append((offset(node.start_point), offset(node.end_point), rendered))
            held_until = node.end_byte
            if node.type == "template_string":
                reading.literals.update(dict.fromkeys(
                    range(node.start_point.row + 2, node.end_point.row + 1), "template literal"))
        if node.type == "import_statement":
            reading.imports.update(range(node.start_point.row + 1, node.end_point.row + 2))
        if node.type in TYPED or node.type.endswith("_type"):
            typed_until = max(typed_until, node.end_byte)
        if node.type in NAMED and node.start_byte >= typed_until and not _intrinsic(node):
            reading.names.append((node.start_point.row + 1, node.text.decode()))
    return reading
# @req- v46n7n
# @req- n7el7s


# @req> REQ-62110789@XlGrbQnAd80g 3nom7d
# @req> REQ-29782682@vNwe2DOIu-N0 ckfd4o
def blanked(text, marked):
    return "\n".join(" " * len(line) if number in marked else line
                     for number, line in enumerate(text.split("\n"), start=1))


def embedded(suffix, text, marked):
    reading = read(suffix, blanked(text, marked))
    return {**reading.literals, **{number: "JSX element" for number in marked
                                   if _among(reading.regions, (number - 1, 0))}}
