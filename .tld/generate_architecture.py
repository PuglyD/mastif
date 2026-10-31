"""Generate the Python-hierarchy tlDiagram import for every implemented mastif layer.

Reads the source with ``ast`` (nothing is imported or executed), merges the hand-written
``.tld/curated.yaml``, and writes ``.tld/architecture.import.yaml``:

    package -> subpackage/module -> class/function/global/type alias -> method/property/attribute

Connectors come from static evidence only: imports, base classes, annotations, calls,
instantiation, raises, excepts, overrides, and attribute access on values whose type can be
inferred. Dynamic dispatch and unannotated values are not resolved, so the graph is a lower
bound. Each element is placed only where it is defined; tlDiagram draws cross-view connectors
itself as faded nodes pointing at the original.

From the repository root:
    python .tld/generate_architecture.py          # write the import file and print a summary
    python .tld/generate_architecture.py --apply  # also rebuild the live diagram from it
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOTS = [
    (Path("packages/mastif/src"), "mastif/kernel", "kernel"),
    (Path("packages/mastif/src"), "mastif/infra", "infra"),
    (Path("packages/mastif/src"), "mastif/resources", "resources"),
    (Path("packages/mastif/src"), "mastif/station", "station"),
    (Path("packages/mastif-testing/src"), "mastif_testing", "testing"),
]
OUT = Path(".tld/architecture.import.yaml")
CURATED = Path(".tld/curated.yaml")
PYTHON_ICON = "/icons/python.svg"

# Refs the overview and hand-written connectors use. Keeping them preserves those links.
MODULE_REFS = {
    "mastif.kernel": "kernel",
    "mastif.infra": "infra",
    "mastif.station": "station",
    "mastif_testing": "testing",
    "mastif.resources": "resources",
    "mastif.resources.channels": "builtin-channels",
    "mastif.resources.transports": "transports",
    "mastif.resources.contracts": "contracts",
    "mastif.resources.driver": "driver-spec",
    "mastif.resources.registry": "driver-registry",
    "mastif.resources.identity": "identity",
    "mastif.resources.errors": "resource-errors",
    "mastif.resources.transports.datagram": "datagrams",
    "mastif.resources.transports.factory": "io-factory",
    "mastif.resources.transports.lineio": "lines",
    "mastif.resources.transports.native": "native",
    "mastif.resources.transports.scpi": "scpi",
    "mastif.resources.transports.ssh": "ssh",
    "mastif.resources.transports.stream": "streams",
    "mastif.resources.transports.config": "transport-config",
    "mastif.kernel.ids": "identifiers",
    "mastif.kernel.results": "results",
    "mastif.kernel.verdict": "verdicts",
    "mastif.infra.errors": "infra-errors",
    "mastif.infra.logs": "logging",
    "mastif_testing.fakes": "fakes",
}
SYMBOL_REFS = {
    "mastif.resources.driver.build_resource": "resource-builder",
    "mastif.kernel.errors.MastifError": "kernel-errors",
    "mastif.kernel.units.Quantity": "quantities",
    "mastif.kernel.limits.evaluate": "limits",
    "mastif.infra.bootstrap.bootstrap": "bootstrap",
    "mastif.infra.config.create_settings": "settings",
    "mastif.infra.version.VersionInfo": "versions",
    "mastif.station.profile.StationProfile": "profile",
    "mastif.station.manager.ResourceHandle": "handles",
    "mastif.station.manager.ResourceManager": "lifecycle",
    "mastif.station.manager.ResourceManager._emit": "lifecycle-events",
    "mastif.station.manager.ResourceManager._verify_identity": "verification",
    "mastif.station.station.Station.require": "roles",
    "mastif.station.station.Station.__exit__": "shutdown",
    "mastif.station.station.Station.build": "station-build",
    "mastif_testing.conformance.assert_satisfies": "contract-tests",
    "mastif_testing.conformance.check_lifecycle": "lifecycle-tests",
}

RELATIONSHIPS = {"inherits": "inherits", "overrides": "inherits", "imports": "dependency",
                 "re-exports": "dependency", "calls": "calls"}
GRID_X, GRID_Y, MAX_ROWS = 460, 190, 10


def short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def first_line(node: ast.AST) -> str:
    doc = ast.get_docstring(node) if isinstance(
        node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ) else None
    return doc.strip().splitlines()[0] if doc else ""


def annotation_names(node: ast.AST | None) -> list[str]:
    """Dotted names used in an annotation, including inside string annotations."""
    if node is None:
        return []
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            try:
                names += annotation_names(ast.parse(child.value, mode="eval").body)
            except SyntaxError:
                pass
        elif isinstance(child, ast.Name):
            names.append(child.id)
        elif isinstance(child, ast.Attribute):
            dotted = dotted_name(child)
            if dotted:
                names.append(dotted)
    return names


def dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ast.unparse(node.args)
    returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
    return f"{prefix}{node.name}({args}){returns}"


def top_level_statements(body: list[ast.stmt]):
    """Module statements, looking through ``if`` and ``try`` blocks."""
    for stmt in body:
        if isinstance(stmt, ast.If):
            yield from top_level_statements(stmt.body)
            yield from top_level_statements(stmt.orelse)
        elif isinstance(stmt, ast.Try):
            yield from top_level_statements(stmt.body)
            for handler in stmt.handlers:
                yield from top_level_statements(handler.body)
            yield from top_level_statements(stmt.orelse)
        else:
            yield stmt


@dataclass
class Member:
    qualname: str
    kind: str
    name: str
    description: str
    anchor: str
    line: int
    node: ast.AST | None = None
    annotation: ast.AST | None = None
    ref: str = ""
    home: str = ""
    tags: list[str] = field(default_factory=list)
    members: dict[str, "Member"] = field(default_factory=dict)


@dataclass
class Module:
    dotted: str
    path: Path
    tree: ast.Module
    is_package: bool
    layer: str = ""
    ref: str = ""
    imports: dict[str, str] = field(default_factory=dict)
    symbols: dict[str, Member] = field(default_factory=dict)


modules: dict[str, Module] = {}
used_refs: set[str] = set(MODULE_REFS.values())


def make_ref(qualname: str, kind: str) -> str:
    if qualname in SYMBOL_REFS:
        used_refs.add(SYMBOL_REFS[qualname])
        return SYMBOL_REFS[qualname]
    # tld refs are lowercase, so Scpi and scpi would otherwise collide.
    ref = qualname.lower()
    if ref in used_refs:
        ref = f"{ref}-{kind}"
    used_refs.add(ref)
    return ref


def private_tag(name: str) -> list[str]:
    is_dunder = name.startswith("__") and name.endswith("__")
    return ["private"] if name.startswith("_") and not is_dunder else []


def load_modules() -> None:
    for src, relative, layer in ROOTS:
        for path in sorted((src / relative).rglob("*.py")):
            parts = path.relative_to(src).with_suffix("").parts
            is_package = parts[-1] == "__init__"
            dotted = ".".join(parts[:-1] if is_package else parts)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            module = Module(dotted, path, tree, is_package, layer)
            module.ref = MODULE_REFS.get(dotted, dotted.lower())
            used_refs.add(module.ref)
            modules[dotted] = module


def read_imports(module: Module) -> None:
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module.imports[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                module.imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"


def is_type_alias(stmt: ast.stmt) -> bool:
    if isinstance(stmt, ast.TypeAlias):
        return True
    if isinstance(stmt, ast.AnnAssign):
        return "TypeAlias" in annotation_names(stmt.annotation)
    return isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.BinOp) and isinstance(
        stmt.value.op, ast.BitOr
    )


def statement_targets(stmt: ast.stmt) -> list[str]:
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        return [stmt.target.id]
    if isinstance(stmt, ast.Assign):
        names = []
        for target in stmt.targets:
            for child in ast.walk(target):
                if isinstance(child, ast.Name):
                    names.append(child.id)
        return names
    if isinstance(stmt, ast.TypeAlias):
        return [stmt.name.id]
    return []


def typed_name(name: str, annotation: ast.AST | None) -> str:
    return short(f"{name}: {ast.unparse(annotation)}" if annotation else name, 70)


def read_class(module: Module, cls: ast.ClassDef) -> Member:
    qualname = f"{module.dotted}.{cls.name}"
    path = module.path.as_posix()
    bases = ", ".join(ast.unparse(base) for base in cls.bases)
    decorators = [ast.unparse(d) for d in cls.decorator_list]
    tags = private_tag(cls.name)
    if any(name.split(".")[-1] == "Protocol" for b in cls.bases for name in annotation_names(b)):
        tags.append("protocol")
    if any(d.startswith("dataclass") for d in decorators):
        tags.append("dataclass")
    summary = first_line(cls)
    header = f"class {cls.name}({bases})" if bases else f"class {cls.name}"
    member = Member(
        qualname, "class", cls.name, f"{header}. {summary}".strip(),
        f"{path}#{cls.name}", cls.lineno, cls, tags=tags, home=module.dotted,
    )
    member.ref = make_ref(qualname, "class")

    def add(name: str, kind: str, label: str, description: str, line: int, node=None, annotation=None):
        if name in member.members:
            return
        full = f"{qualname}.{name}"
        child = Member(
            full, kind, label, description, f"{path}#{cls.name}.{name}", line, node,
            annotation, tags=private_tag(name), home=module.dotted,
        )
        child.ref = make_ref(full, kind)
        member.members[name] = child

    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            decos = [ast.unparse(d) for d in stmt.decorator_list]
            if any(d.endswith("overload") for d in decos):
                continue
            is_property = any(d in ("property", "cached_property") or d.endswith(".setter") for d in decos)
            kind = "property" if is_property else "method"
            returns = f" -> {ast.unparse(stmt.returns)}" if stmt.returns else ""
            label = short(f"{stmt.name}{returns}" if is_property else f"{stmt.name}(){returns}", 70)
            add(stmt.name, kind, label, f"{signature(stmt)}. {first_line(stmt)}".strip(), stmt.lineno, stmt)
        elif isinstance(stmt, ast.ClassDef):
            add(stmt.name, "class", stmt.name, f"Nested class. {first_line(stmt)}".strip(), stmt.lineno, stmt)
        else:
            annotation = stmt.annotation if isinstance(stmt, ast.AnnAssign) else None
            for name in statement_targets(stmt):
                add(name, "attribute", typed_name(name, annotation), f"Class attribute of {cls.name}.",
                    stmt.lineno, stmt, annotation)
    # Instance attributes assigned through self; an unannotated one takes its type from
    # the parameter or constructor call that supplies it.
    for function in ast.walk(cls):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parameters = {a.arg: a.annotation for a in [*function.args.args, *function.args.kwonlyargs]}
        for stmt in ast.walk(function):
            target, declared, value = None, None, getattr(stmt, "value", None)
            if isinstance(stmt, ast.AnnAssign):
                target, declared = stmt.target, stmt.annotation
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                target = stmt.targets[0]
            if not (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id == "self"):
                continue
            inferred = declared
            if inferred is None and isinstance(value, ast.Name):
                inferred = parameters.get(value.id)
            elif inferred is None and isinstance(value, ast.Call):
                inferred = value.func
            shown = declared
            if shown is None and isinstance(value, ast.Name):
                shown = parameters.get(value.id)
            add(target.attr, "attribute", typed_name(target.attr, shown),
                f"Instance attribute of {cls.name}.", stmt.lineno, stmt, inferred)
    return member


def read_symbols(module: Module) -> None:
    path = module.path.as_posix()
    for stmt in top_level_statements(module.tree.body):
        if isinstance(stmt, ast.ClassDef):
            module.symbols.setdefault(stmt.name, read_class(module, stmt))
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name in module.symbols:
                continue
            full = f"{module.dotted}.{stmt.name}"
            returns = f" -> {ast.unparse(stmt.returns)}" if stmt.returns else ""
            symbol = Member(
                full, "function", short(f"{stmt.name}(){returns}", 70),
                f"{signature(stmt)}. {first_line(stmt)}".strip(), f"{path}#{stmt.name}", stmt.lineno,
                stmt, tags=private_tag(stmt.name), home=module.dotted,
            )
            symbol.ref = make_ref(full, "function")
            module.symbols[stmt.name] = symbol
        else:
            annotation = stmt.annotation if isinstance(stmt, ast.AnnAssign) else None
            for name in statement_targets(stmt):
                if name in module.symbols:
                    continue
                full = f"{module.dotted}.{name}"
                kind = "type-alias" if is_type_alias(stmt) else "global"
                word = "Type alias" if kind == "type-alias" else "Module global"
                symbol = Member(
                    full, kind, typed_name(name, annotation), f"{word} in {module.dotted}.",
                    f"{path}#{name}", stmt.lineno, stmt, annotation, tags=private_tag(name),
                    home=module.dotted,
                )
                symbol.ref = make_ref(full, kind)
                module.symbols[name] = symbol


def locate(qualified: str, depth: int = 0) -> Member | Module | str | None:
    """Resolve a fully qualified name to a symbol, module, or external element ref."""
    if depth > 6:
        return None
    if qualified in modules:
        return modules[qualified]
    owner, _, last = qualified.rpartition(".")
    if owner in modules:
        module = modules[owner]
        if last in module.symbols:
            return module.symbols[last]
        if last in module.imports:  # re-export through a package __init__
            return locate(module.imports[last], depth + 1)
        return None
    parent = locate(owner, depth + 1) if owner else None
    if isinstance(parent, Member) and last in parent.members:
        return parent.members[last]
    return None


def resolve(module: Module, name: str) -> Member | Module | str | None:
    head, _, rest = name.partition(".")
    if head in module.symbols:
        qualified = module.symbols[head].qualname
    elif head in module.imports:
        qualified = module.imports[head]
    else:
        return None
    return locate(f"{qualified}.{rest}" if rest else qualified)


def member_of(cls: Member, name: str, seen: set[str] | None = None) -> Member | None:
    """Find a member on a class or, statically, on its base classes."""
    seen = seen or set()
    if cls.qualname in seen:
        return None
    seen.add(cls.qualname)
    if name in cls.members:
        return cls.members[name]
    module = modules[cls.qualname.rpartition(".")[0]]
    for base in getattr(cls.node, "bases", []):
        for base_name in annotation_names(base):
            found = resolve(module, base_name)
            if isinstance(found, Member) and found.kind == "class":
                inherited = member_of(found, name, seen)
                if inherited:
                    return inherited
    return None


@dataclass
class Edge:
    verbs: list[str] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)


edges: dict[tuple[str, str, str], Edge] = defaultdict(Edge)
source_of: dict[tuple[str, str, str], str] = {}


def connect(view: str, source: str, target: str, verb: str, line: int, path: Path) -> None:
    if source == target:
        return
    edge = edges[(view, source, target)]
    if verb not in edge.verbs:
        edge.verbs.append(verb)
    if line not in edge.lines:
        edge.lines.append(line)
    source_of[(view, source, target)] = path.as_posix()


def ref_of(found: Member | Module | str) -> str:
    return found if isinstance(found, str) else found.ref


def class_type_of(module: Module, annotation: ast.AST | None) -> Member | None:
    for name in annotation_names(annotation):
        found = resolve(module, name)
        if isinstance(found, Member) and found.kind == "class":
            return found
    return None


def type_of(member: Member | None) -> Member | None:
    """The class a member evaluates to, from its annotation or return annotation."""
    if member is None:
        return None
    if member.kind == "class":
        return member
    annotation = member.annotation
    if annotation is None:
        annotation = getattr(member.node, "returns", None)
    return class_type_of(modules[member.home], annotation)


def infer(expr: ast.AST, module: Module, local: dict[str, Member], owner: Member | None) -> Member | None:
    """Best-effort static class of an expression; None when it cannot be shown."""
    if isinstance(expr, ast.Name):
        if expr.id == "self" and owner:
            return owner
        if expr.id in local:
            return local[expr.id]
        found = resolve(module, expr.id)
        return found if isinstance(found, Member) and found.kind == "class" else None
    if isinstance(expr, ast.Attribute):
        base = infer(expr.value, module, local, owner)
        return type_of(member_of(base, expr.attr)) if base else None
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name):
            found = resolve(module, func.id)
            return type_of(found) if isinstance(found, Member) else None
        if isinstance(func, ast.Attribute):
            base = infer(func.value, module, local, owner)
            return type_of(member_of(base, func.attr)) if base else None
    if isinstance(expr, (ast.Subscript, ast.Await, ast.Starred)):
        return infer(expr.value, module, local, owner)
    return None


def local_variables(node: ast.AST, module: Module, local: dict[str, Member], owner: Member | None) -> set[str]:
    """Fill ``local`` with inferred variable classes and return every locally bound name."""
    bound: set[str] = set(local)
    for _ in range(2):  # a second pass catches variables built from earlier variables
        for child in ast.walk(node):
            pairs: list[tuple[ast.AST, ast.AST | None]] = []
            if isinstance(child, ast.Assign):
                pairs = [(target, child.value) for target in child.targets]
            elif isinstance(child, ast.AnnAssign):
                declared = class_type_of(module, child.annotation)
                if isinstance(child.target, ast.Name):
                    bound.add(child.target.id)
                    if declared:
                        local[child.target.id] = declared
                continue
            elif isinstance(child, (ast.For, ast.comprehension)):
                pairs = [(child.target, child.iter)]
            elif isinstance(child, ast.withitem) and child.optional_vars is not None:
                pairs = [(child.optional_vars, child.context_expr)]
            elif isinstance(child, ast.NamedExpr):
                pairs = [(child.target, child.value)]
            for target, value in pairs:
                for name in ast.walk(target):
                    if isinstance(name, ast.Name):
                        bound.add(name.id)
                if isinstance(target, ast.Name) and value is not None:
                    inferred = infer(value, module, local, owner)
                    if inferred:
                        local[target.id] = inferred
    return bound


def scan_callable(module: Module, view: str, member: Member, owner: Member | None) -> None:
    """Record what a function or method's signature and body demonstrably reach."""
    node = member.node
    path = module.path
    source = member.ref

    def link(name: str, verb: str, line: int) -> None:
        found = resolve(module, name)
        if found is not None:
            connect(view, source, ref_of(found), verb, line, path)

    local: dict[str, Member] = {}
    parameter_names = {"self", "cls"}
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                *filter(None, [node.args.vararg, node.args.kwarg])]:
        parameter_names.add(arg.arg)
        for name in annotation_names(arg.annotation):
            link(name, f"parameter {arg.arg}", arg.lineno)
        arg_type = class_type_of(module, arg.annotation)
        if arg_type:
            local[arg.arg] = arg_type
    for name in annotation_names(node.returns):
        link(name, "returns", node.lineno)
    for decorator in node.decorator_list:
        for name in annotation_names(decorator):
            link(name, "decorated by", node.lineno)
    shadowed = parameter_names | local_variables(node, module, local, owner)

    handled: set[int] = set()

    def skip(tree: ast.AST | None) -> None:
        if tree is not None:
            handled.update(id(sub_node) for sub_node in ast.walk(tree))

    for field_node in [*node.args.defaults, *node.args.kw_defaults, *node.decorator_list, node.returns]:
        skip(field_node)
    for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                *filter(None, [node.args.vararg, node.args.kwarg])]:
        skip(arg.annotation)

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            handled.add(id(func))
            line = child.lineno
            if (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call)
                    and isinstance(func.value.func, ast.Name) and func.value.func.id == "super" and owner):
                for base in owner.node.bases:
                    for base_name in annotation_names(base):
                        found = resolve(module, base_name)
                        if isinstance(found, Member) and found.kind == "class":
                            target = member_of(found, func.attr)
                            if target:
                                connect(view, source, target.ref, "calls super", line, path)
                continue
            if isinstance(func, ast.Attribute):
                base = infer(func.value, module, local, owner)
                target = member_of(base, func.attr) if base else None
                if target:
                    connect(view, source, target.ref, "calls", line, path)
                    if isinstance(func.value, ast.Name):
                        handled.add(id(func.value))
                    continue
            name = dotted_name(func)
            if name == "isinstance" and len(child.args) == 2:
                for type_name in annotation_names(child.args[1]):
                    link(type_name, "checks isinstance", line)
                skip(child.args[1])
            elif name and name.split(".")[0] not in shadowed:
                found = resolve(module, name)
                if isinstance(found, Member) and found.kind == "class":
                    connect(view, source, found.ref, "instantiates", line, path)
                elif found is not None:
                    connect(view, source, ref_of(found), "calls", line, path)
                skip(func)
        elif isinstance(child, ast.Raise) and child.exc is not None:
            exc = child.exc.func if isinstance(child.exc, ast.Call) else child.exc
            skip(exc)
            name = dotted_name(exc)
            if name:
                link(name, "raises", child.lineno)
        elif isinstance(child, ast.ExceptHandler) and child.type is not None:
            for name in annotation_names(child.type):
                link(name, "catches", child.lineno)
            skip(child.type)
        elif isinstance(child, ast.AnnAssign):
            for name in annotation_names(child.annotation):
                link(name, "annotates local", child.lineno)
            skip(child.annotation)
        elif isinstance(child, ast.Attribute) and id(child) not in handled:
            base = infer(child.value, module, local, owner)
            target = member_of(base, child.attr) if base else None
            if target:
                verb = "writes" if isinstance(child.ctx, ast.Store) else "reads"
                connect(view, source, target.ref, verb, child.lineno, path)
                if isinstance(child.value, ast.Name):
                    handled.add(id(child.value))
        elif isinstance(child, ast.Name) and id(child) not in handled and child.id not in shadowed:
            if isinstance(child.ctx, ast.Load):
                link(child.id, "references", child.lineno)


def lift_cross_class_edges() -> None:
    """Point edges at another class's member to that class, naming the member in the verb.

    This keeps a view to its own members plus the classes they touch.
    """
    owner_class = {
        child.ref: (symbol.ref, child.qualname.rpartition(".")[2])
        for module in modules.values() for symbol in module.symbols.values()
        for child in symbol.members.values()
    }
    for key in list(edges):
        view, source, target = key
        if target not in owner_class or owner_class[target][0] == view:
            continue
        cls, bare = owner_class[target]
        edge = edges.pop(key)
        lifted = (view, source, cls)
        for verb in edge.verbs:
            verb = f"{verb.split(' ')[0]} {bare}"
            if verb not in edges[lifted].verbs:
                edges[lifted].verbs.append(verb)
        edges[lifted].lines += [n for n in edge.lines if n not in edges[lifted].lines]
        source_of[lifted] = source_of.pop(key)


def rollup(module: Module) -> None:
    """Summarise each class's member edges at the module view, one level up."""
    by_ref: dict[str, Member] = {}
    for symbol in module.symbols.values():
        by_ref[symbol.ref] = symbol
        for child in symbol.members.values():
            by_ref[child.ref] = symbol
    top_of: dict[str, str] = {}
    for other in modules.values():
        for symbol in other.symbols.values():
            top_of[symbol.ref] = symbol.ref
            for child in symbol.members.values():
                top_of[child.ref] = symbol.ref
    for symbol in module.symbols.values():
        if not symbol.members:
            continue
        for (view, source, target), edge in list(edges.items()):
            if view != symbol.ref:
                continue
            outer = top_of.get(target, target)
            if outer == symbol.ref:
                continue
            for verb in edge.verbs:
                connect(module.ref, symbol.ref, outer, verb.split(" ")[0], edge.lines[0], module.path)


def scan_module(module: Module) -> None:
    path = module.path
    for symbol in module.symbols.values():
        if symbol.kind == "class":
            for base in symbol.node.bases:
                for name in annotation_names(base):
                    found = resolve(module, name)
                    if found is not None:
                        connect(module.ref, symbol.ref, ref_of(found), "inherits", symbol.line, path)
            for decorator in symbol.node.decorator_list:
                for name in annotation_names(decorator):
                    found = resolve(module, name)
                    if found is not None:
                        connect(module.ref, symbol.ref, ref_of(found), "decorated by", symbol.line, path)
            for child in symbol.members.values():
                if child.kind in ("method", "property") and child.qualname.rpartition(".")[2] != "__init__":
                    bare = child.qualname.rpartition(".")[2]
                    for base in symbol.node.bases:
                        for name in annotation_names(base):
                            found = resolve(module, name)
                            if isinstance(found, Member) and found.kind == "class":
                                overridden = member_of(found, bare)
                                if overridden:
                                    connect(symbol.ref, child.ref, overridden.ref, "overrides", child.line, path)
                if child.kind == "attribute":
                    for name in annotation_names(child.annotation):
                        found = resolve(module, name)
                        if found is not None and getattr(found, "kind", "") != "function":
                            connect(symbol.ref, child.ref, ref_of(found), "typed as", child.line, path)
                elif child.kind in ("method", "property"):
                    scan_callable(module, symbol.ref, child, symbol)
        elif symbol.kind == "function":
            scan_callable(module, module.ref, symbol, None)
        else:
            for name in annotation_names(symbol.annotation):
                found = resolve(module, name)
                if found is not None:
                    connect(module.ref, symbol.ref, ref_of(found), "typed as", symbol.line, path)
            value = getattr(symbol.node, "value", None)
            if symbol.qualname.endswith(".__all__"):
                # Exports would pull every public symbol into the package view.
                exported = [c.value for c in ast.walk(value) if isinstance(c, ast.Constant)] if value else []
                symbol.description = f"Public API of {module.dotted}: {', '.join(map(str, exported))}."
                continue
            for name in annotation_names(value):
                found = resolve(module, name)
                if found is not None:
                    connect(module.ref, symbol.ref, ref_of(found), "references", symbol.line, path)


def scan_imports(module: Module, parent_ref: str) -> None:
    """Module-to-module edges in the owning package's view, labelled with imported names."""
    imported: dict[str, list[str]] = defaultdict(list)
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
            continue
        for alias in node.names:
            found = locate(f"{node.module}.{alias.name}")
            if isinstance(found, Member):
                target = modules[found.qualname.rpartition(".")[0]].ref
            elif found is None:
                continue
            else:
                target = ref_of(found)
            if target != module.ref and alias.name not in imported[target]:
                imported[target].append(alias.name)
    for target, names in imported.items():
        shown = ", ".join(names[:3]) + (f" +{len(names) - 3}" if len(names) > 3 else "")
        edge = edges[(parent_ref, module.ref, target)]
        reexport = module.is_package and any(
            m.ref == target and m.dotted.startswith(module.dotted + ".") for m in modules.values())
        edge.verbs.append(f"{'re-exports' if reexport else 'imports'} {shown}")
        edge.lines.append(1)
        source_of[(parent_ref, module.ref, target)] = module.path.as_posix()
        full_import_names[(parent_ref, module.ref, target)] = names


full_import_names: dict[tuple[str, str, str], list[str]] = {}


def layout(refs: list[str], view: str) -> dict[str, tuple[int, int]]:
    """Longest-path ranks left to right, wrapped so no column gets too tall."""
    local = set(refs)
    outgoing: dict[str, set[str]] = defaultdict(set)
    for (edge_view, source, target) in edges:
        if edge_view == view and source in local and target in local:
            outgoing[source].add(target)
    rank = {ref: 0 for ref in refs}
    for _ in refs:  # bounded relaxation, so cycles cannot loop forever
        changed = False
        for source, targets in outgoing.items():
            for target in targets:
                if rank[target] < rank[source] + 1 and rank[source] + 1 < len(refs):
                    rank[target] = rank[source] + 1
                    changed = True
        if not changed:
            break
    columns: dict[int, list[str]] = defaultdict(list)
    for ref in refs:
        columns[rank[ref]].append(ref)
    positions: dict[str, tuple[int, int]] = {}
    x = 0
    for column in sorted(columns):
        members = columns[column]
        for start in range(0, len(members), MAX_ROWS):
            for row, ref in enumerate(members[start: start + MAX_ROWS]):
                positions[ref] = (x * GRID_X, row * GRID_Y)
            x += 1
    return positions


def element(name, kind, description, file_path, parent, position, tags, layer, view_label=None):
    item = {
        "name": name, "kind": kind, "technology": "Python", "description": description,
        "file_path": file_path, "logo_url": PYTHON_ICON,
        "tags": sorted({"implemented", layer, *tags}),
        "placements": [{"parent": parent, "position_x": position[0], "position_y": position[1]}],
    }
    if view_label:
        item["has_view"] = True
        item["view_label"] = view_label
    return item


def parent_of(module: Module) -> Module | None:
    return modules.get(module.dotted.rpartition(".")[0])


def merge_curated(curated: dict, owner_view: dict[str, str]) -> list[dict]:
    """Put hand-written wording on the generated connector for the same pair.

    Overview connectors, and those from non-code elements, pass through unchanged and are
    returned. ``owner_view`` maps each generated ref to the view that owns it.
    """
    def chain(ref: str) -> set[str]:
        found = set()
        while ref in owner_view:
            found.add(ref)
            ref = owner_view[ref]
        return found

    passthrough = []
    for item in curated["connectors"]:
        source, target = item["source"], item["target"]
        if item["view"] == "root" or source not in owner_view:
            passthrough.append(item)
        elif source in chain(target) or target in chain(source):
            print(f"curated: dropped {source} -> {target} ({item['label']}): one contains the other")
        else:
            key = (owner_view[source], source, target)
            edges[key]  # creates the connector when the source shows no static evidence for it
            source_of.setdefault(key, "")
            curated_wording[key] = item
    return passthrough


curated_wording: dict[tuple[str, str, str], dict] = {}


def main() -> None:
    load_modules()
    for module in modules.values():
        read_imports(module)
        read_symbols(module)
    for module in modules.values():
        scan_module(module)
    lift_cross_class_edges()
    for module in modules.values():
        rollup(module)
    for module in modules.values():
        parent = parent_of(module)
        if parent is not None:
            scan_imports(module, parent.ref)

    views: dict[str, list[str]] = defaultdict(list)
    owner_view: dict[str, str] = {}
    for module in modules.values():
        parent = parent_of(module)
        views[parent.ref if parent else "root"].append(module.ref)
        owner_view[module.ref] = parent.ref if parent else "root"
        for symbol in module.symbols.values():
            views[module.ref].append(symbol.ref)
            owner_view[symbol.ref] = module.ref
            for child in symbol.members.values():
                views[symbol.ref].append(child.ref)
                owner_view[child.ref] = symbol.ref

    curated = yaml.safe_load(CURATED.read_text(encoding="utf-8"))
    passthrough = merge_curated(curated, owner_view)

    positions = {
        view: layout(refs, view) for view, refs in list(views.items())
        if view != "root"
    }

    elements = {}
    for module in modules.values():
        parent = parent_of(module)
        path = module.path.parent if module.is_package else module.path
        kind = "package" if parent is None else "subpackage" if module.is_package else "module"
        summary = first_line(module.tree)
        placement_view = parent.ref if parent else "root"
        position = positions[placement_view][module.ref] if parent else curated["root_positions"][module.ref]
        elements[module.ref] = element(
            module.dotted, kind, summary or f"Python {kind} {module.dotted}.", path.as_posix(),
            placement_view, position, [], module.layer, "Modules" if module.is_package else "Members",
        )
        for symbol in module.symbols.values():
            elements[symbol.ref] = element(
                symbol.name, symbol.kind, short(symbol.description, 600), symbol.anchor, module.ref,
                positions[module.ref][symbol.ref], symbol.tags, module.layer,
                "Members" if symbol.members else None,
            )
            for child in symbol.members.values():
                elements[child.ref] = element(
                    child.name, child.kind, short(child.description, 600), child.anchor, symbol.ref,
                    positions[symbol.ref][child.ref], child.tags, module.layer,
                )
    # tld matches new elements by name and kind, so those must be unique. It also trims the
    # middle of long names, so the distinguishing part goes first and the owner after it.
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for item in elements.values():
        seen[(item["name"], item["kind"])] += 1
    owners = {s.ref: m.dotted for m in modules.values() for s in m.symbols.values()}
    owners.update({c.ref: s.qualname for m in modules.values() for s in m.symbols.values()
                   for c in s.members.values()})
    for ref, item in elements.items():
        if seen[(item["name"], item["kind"])] > 1 and ref in owners:
            item["name"] = f"{item['name']} · {owners[ref].rpartition('.')[2]}"
    seen.clear()
    for item in elements.values():
        seen[(item["name"], item["kind"])] += 1
    for ref, item in elements.items():
        if seen[(item["name"], item["kind"])] > 1 and ref in owners:
            item["name"] = f"{item['name'].partition(' · ')[0]} · {owners[ref]}"
    for ref, item in curated["elements"].items():
        elements[ref] = item

    connectors = []
    for key, edge in sorted(edges.items()):
        view, source, target = key
        path = source_of[key]
        names = full_import_names.get(key)
        if names:
            evidence = f"{path} imports: {', '.join(names)}."
        elif edge.lines:
            lines = ", ".join(f"L{n}" for n in sorted(edge.lines)[:8])
            evidence = f"Static evidence in {path}: {lines}."
        else:
            evidence = ""
        verbs = sorted(edge.verbs, key=lambda v: (v.startswith("parameter"), v))
        found = ", ".join(verbs)
        wording = curated_wording.get(key)
        label = wording["label"] if wording else found
        description = evidence if len(found) <= 80 else f"Detected: {found}. {evidence}"
        if wording:
            detail = f" Detected: {found}." if found else ""
            description = f"{wording.get('description', '')}{detail} {evidence}".strip()
        first = verbs[0].split(" ")[0] if verbs else ""
        connectors.append({
            "view": view, "source": source, "target": target,
            "label": short(label, 80), "description": description,
            "relationship": RELATIONSHIPS.get(first, (wording or {}).get("relationship", "uses")),
            "direction": "forward", "style": "bezier",
        })
    connectors += passthrough

    OUT.write_text(
        yaml.safe_dump({"elements": elements, "connectors": connectors},
                       sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    counts: dict[str, int] = defaultdict(int)
    for item in elements.values():
        counts[item.get("kind")] += 1
    off_view = sum(1 for k in edges if k[2] not in views[k[0]])
    print(dict(counts), "elements:", len(elements), "connectors:", len(connectors), "cross-view:", off_view)
    print("connectors with hand-written wording but no static evidence:",
          [k[1:] for k in curated_wording if not edges[k].verbs])
    if "--apply" in sys.argv:
        apply()


def apply() -> None:
    """Rebuild the local diagram database from the import file.

    Removing placements one call at a time takes minutes and tld refuses while connectors
    use them, so this starts from an empty database. It keeps one copy as tld.db.bak, and
    the caller restarts ``tld serve`` afterwards. View IDs can change.
    """
    executable = str(Path(os.environ["LOCALAPPDATA"]) / "tld/bin/tld.exe")
    data_dir = Path(os.environ["USERPROFILE"]) / ".local/share/tldiagram"
    common = ["--workspace", ".", "--target", "local", "--data-dir", str(data_dir), "--format", "json", "--compact"]
    subprocess.run([executable, "stop", "--kill"], capture_output=True, timeout=30)
    database = data_dir / "tld.db"
    if database.exists():
        subprocess.run(
            [executable, "validate", "--source", "live", *common], capture_output=True, timeout=30
        )  # settles the write-ahead log before the copy
        shutil.copy2(database, data_dir / "tld.db.bak")
    for path in [database, data_dir / "tld.db-shm", data_dir / "tld.db-wal",
                 Path(".tld/elements.yaml"), Path(".tld/connectors.yaml"), Path(".tld/.tld.lock")]:
        path.unlink(missing_ok=True)
    result = subprocess.run(
        [executable, "import", str(OUT), *common], capture_output=True, encoding="utf-8", timeout=120
    )
    if result.returncode:
        raise SystemExit(f"tld import failed: {(result.stdout + result.stderr)[:600]}")
    print("rebuilt", flush=True)


if __name__ == "__main__":
    main()
