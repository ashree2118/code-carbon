"""Find potentially wasteful patterns in Python source with the `ast` module.

This never runs the code. Detection is deliberately conservative: each pattern
is a hint for the auditor, not proof that the code is slow.
"""

import ast
from dataclasses import dataclass, field

from app.schemas import DetectedPattern

# Query text used to retrieve matching green coding practices for each pattern.
PATTERN_QUERIES: dict[str, str] = {
    "nested_loop": "nested loops over collections, replace with dict or set lookups",
    "linear_search_in_loop": "membership test x in list, list.index or list.count inside a loop",
    "string_concat_in_loop": "string concatenation with += inside a loop, build with join",
    "append_loop": "list.append in a loop could be a list comprehension",
    "invariant_call_in_loop": "loop-invariant computation repeated on every iteration, compute it once before the loop",
    "file_io_in_loop": "file opened, read or written inside a loop",
    "regex_in_loop": "re.search or re.compile with a pattern string inside a loop",
    "uncached_recursion": "recursive function called repeatedly with the same arguments",
    "list_in_aggregate": "sum, any or all over a list comprehension instead of a generator",
    "pandas_row_iteration": "pandas iterrows row by row iteration",
    "queue_pop_front": "list.pop(0) or list.insert(0) used as a queue",
}

_MUTATING_METHODS = {
    "append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
    "add", "discard", "update", "setdefault", "popitem", "difference_update",
    "intersection_update", "symmetric_difference_update",
}
# Built-ins that walk their whole input, so repeating them in a loop is O(n) each time.
_LINEAR_BUILTINS = {"sorted", "sum", "min", "max", "set", "list", "tuple", "dict", "frozenset"}
_REGEX_FUNCS = {"compile", "search", "match", "fullmatch", "findall", "finditer", "sub", "subn", "split"}
_PATH_IO_METHODS = {"read_text", "write_text", "read_bytes", "write_bytes"}
_AGGREGATE_FUNCS = {"sum", "any", "all", "min", "max"}
_LOOP_TYPES = (ast.For, ast.AsyncFor, ast.While)
_SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(elt) for elt in target.elts))
    if isinstance(target, ast.Starred):
        return _target_names(target.value)
    root = _root_name(target)  # d[k] = v and obj.x = v change d and obj
    return {root} if root else set()


def _names_changed_in_loop(loop: ast.stmt) -> set[str]:
    """Names that may hold a different value on each iteration."""
    names: set[str] = set()
    for node in ast.walk(loop):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names |= _target_names(target)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            names |= _target_names(node.target)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            names |= _target_names(node.target)
        elif isinstance(node, ast.NamedExpr):
            names.add(node.target.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    names |= _target_names(item.optional_vars)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                names |= _target_names(target)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
        ):
            root = _root_name(node.func.value)
            if root:
                names.add(root)
    return names


def _value_kind(value: ast.AST) -> str | None:
    if isinstance(value, (ast.List, ast.ListComp)):
        return "list"
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("list", "sorted"):
        return "list"
    if isinstance(value, ast.JoinedStr) or (
        isinstance(value, ast.Constant) and isinstance(value.value, str)
    ):
        return "str"
    return None


def _walk_scope(body: list[ast.stmt]):
    """Walk a scope's statements without entering nested functions or classes."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, _SCOPE_TYPES):
                stack.append(child)


def _scope_kinds(body: list[ast.stmt]) -> dict[str, str]:
    """Map names to 'list' or 'str' when every assignment in the scope agrees."""
    kinds: dict[str, str | None] = {}
    for node in _walk_scope(body):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        kind = _value_kind(value)
        if kind is None:
            # `s = s + x` keeps the kind; any other assignment makes it unknown.
            is_self_concat = (
                isinstance(value, ast.BinOp)
                and isinstance(value.left, ast.Name)
                and value.left.id == target.id
            )
            if not is_self_concat:
                kinds[target.id] = None
            continue
        if kinds.get(target.id, kind) != kind:
            kinds[target.id] = None
        elif target.id not in kinds:
            kinds[target.id] = kind
    return {name: kind for name, kind in kinds.items() if kind}


def _is_self_call(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == name


def _is_cached(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in func.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
        if "cache" in name.lower():
            return True
    return False


@dataclass
class _Loop:
    node: ast.stmt
    changed: set[str]


@dataclass
class _Scope:
    kinds: dict[str, str]
    loops: list[_Loop] = field(default_factory=list)
    max_depth: int = 0


class _Analyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.patterns: dict[tuple[str, int], DetectedPattern] = {}
        self._scopes: list[_Scope] = []

    # Helpers

    @property
    def _scope(self) -> _Scope:
        return self._scopes[-1]

    @property
    def _in_loop(self) -> bool:
        return bool(self._scopes and self._scope.loops)

    def _add(self, kind: str, node: ast.AST, description: str) -> None:
        key = (kind, node.lineno)
        if key not in self.patterns:
            self.patterns[key] = DetectedPattern(
                kind=kind,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                description=description,
            )

    def _visit_scope(self, node: ast.AST, body: list[ast.stmt]) -> None:
        self._scopes.append(_Scope(kinds=_scope_kinds(body)))
        self.generic_visit(node)
        self._scopes.pop()

    # Scopes

    def visit_Module(self, node: ast.Module) -> None:
        self._visit_scope(node, node.body)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self_calls = sum(_is_self_call(n, node.name) for n in _walk_scope(node.body))
        if self_calls >= 2 and not _is_cached(node):
            self._add(
                "uncached_recursion",
                node,
                f"`{node.name}` calls itself {self_calls} times per call without caching, "
                "which can repeat the same work exponentially",
            )
        self._visit_scope(node, node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scope(node, node.body)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._scopes.append(_Scope(kinds={}))
        self.generic_visit(node)
        self._scopes.pop()

    # Loops

    def _visit_loop(self, node: ast.For | ast.AsyncFor | ast.While) -> None:
        scope = self._scope
        is_outermost = not scope.loops
        if is_outermost:
            scope.max_depth = 0

        # A for-loop's iterable is evaluated once, outside the loop body.
        if isinstance(node, ast.While):
            header: list[ast.AST] = []
        else:
            self.visit(node.iter)
            header = [node.target]
            self._check_append_loop(node)

        scope.loops.append(_Loop(node, _names_changed_in_loop(node)))
        scope.max_depth = max(scope.max_depth, len(scope.loops))
        for child in header + ([node.test] if isinstance(node, ast.While) else []) + node.body:
            self.visit(child)
        scope.loops.pop()
        for child in node.orelse:
            self.visit(child)

        if is_outermost and scope.max_depth >= 2:
            self._add(
                "nested_loop",
                node,
                f"Loops nested {scope.max_depth} levels deep; work grows with the product "
                "of the collection sizes",
            )

    visit_For = _visit_loop
    visit_AsyncFor = _visit_loop
    visit_While = _visit_loop

    def _check_append_loop(self, node: ast.For | ast.AsyncFor) -> None:
        if len(node.body) != 1 or node.orelse:
            return
        stmt = node.body[0]
        if isinstance(stmt, ast.If) and not stmt.orelse and len(stmt.body) == 1:
            stmt = stmt.body[0]
        if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
            return
        func = stmt.value.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "append"
            and isinstance(func.value, ast.Name)
            and self._scope.kinds.get(func.value.id) == "list"
        ):
            self._add(
                "append_loop",
                node,
                f"Loop only appends to `{func.value.id}`; a list comprehension does the same with less overhead",
            )

    # Statements and expressions inside loops

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if (
            self._in_loop
            and isinstance(node.op, ast.Add)
            and isinstance(node.target, ast.Name)
            and self._scope.kinds.get(node.target.id) == "str"
        ):
            self._add(
                "string_concat_in_loop",
                node,
                f"String `{node.target.id}` is extended with += inside a loop, copying it each time",
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if (
            self._in_loop
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.BinOp)
            and isinstance(node.value.op, ast.Add)
            and isinstance(node.value.left, ast.Name)
            and node.value.left.id == node.targets[0].id
            and self._scope.kinds.get(node.targets[0].id) == "str"
        ):
            name = node.targets[0].id
            self._add(
                "string_concat_in_loop",
                node,
                f"String `{name}` is rebuilt with `{name} = {name} + ...` inside a loop",
            )
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self._in_loop:
            for op, right in zip(node.ops, node.comparators):
                if (
                    isinstance(op, (ast.In, ast.NotIn))
                    and isinstance(right, ast.Name)
                    and self._scope.kinds.get(right.id) == "list"
                ):
                    self._add(
                        "linear_search_in_loop",
                        node,
                        f"Membership test on list `{right.id}` inside a loop scans the whole list each time",
                    )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else None
        name = func.id if isinstance(func, ast.Name) else None

        if attr in ("iterrows", "itertuples"):
            self._add("pandas_row_iteration", node, f"`.{attr}()` iterates a DataFrame row by row in Python")

        if name in _AGGREGATE_FUNCS and len(node.args) == 1 and isinstance(node.args[0], ast.ListComp):
            self._add(
                "list_in_aggregate",
                node,
                f"`{name}()` over a list comprehension builds a full list first; a generator avoids it",
            )

        if self._in_loop:
            self._check_call_in_loop(node, name, attr)
        self.generic_visit(node)

    def _check_call_in_loop(self, node: ast.Call, name: str | None, attr: str | None) -> None:
        func = node.func
        if name == "open" or attr in _PATH_IO_METHODS:
            self._add("file_io_in_loop", node, "File is opened, read or written on every loop iteration")

        if (
            attr in _REGEX_FUNCS
            and isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "re"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            self._add("regex_in_loop", node, f"`re.{attr}` with a fixed pattern inside a loop; compile it once")

        if attr in ("pop", "insert") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value == 0 and (attr == "insert" or len(node.args) == 1):
                self._add(
                    "queue_pop_front",
                    node,
                    f"`.{attr}(0)` on a list shifts every element; collections.deque is O(1)",
                )

        if attr in ("index", "count") and isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if self._scope.kinds.get(func.value.id) == "list":
                self._add(
                    "linear_search_in_loop",
                    node,
                    f"`{func.value.id}.{attr}()` inside a loop scans the whole list each time",
                )

        if name in _LINEAR_BUILTINS and node.args:
            self._check_invariant_call(node, name)

    def _check_invariant_call(self, node: ast.Call, name: str) -> None:
        # Only flag calls whose inputs are plain names that the loop never changes.
        arg_nodes = [n for arg in node.args for n in ast.walk(arg)]
        if any(isinstance(n, (ast.Call, ast.Lambda, ast.comprehension)) for n in arg_nodes):
            return
        used = {n.id for n in arg_nodes if isinstance(n, ast.Name)}
        if not used:
            return
        loop = self._scope.loops[-1]
        if used & loop.changed:
            return
        args = ", ".join(sorted(used))
        self._add(
            "invariant_call_in_loop",
            node,
            f"`{name}()` on `{args}` gives the same result every iteration; compute it once before the loop",
        )


def analyze_code(source: str) -> list[DetectedPattern]:
    """Return detected patterns sorted by line. Raises SyntaxError for invalid code."""
    tree = ast.parse(source)
    analyzer = _Analyzer()
    analyzer.visit(tree)
    return sorted(analyzer.patterns.values(), key=lambda p: (p.line_start, p.kind))
