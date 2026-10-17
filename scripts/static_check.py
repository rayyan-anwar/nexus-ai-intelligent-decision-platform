"""Lightweight static checks used when the full dependency set cannot be installed.

1. Undefined names: a name that is read but never bound anywhere in the module and is not a builtin.
2. Unused imports (like ruff F401).
3. Broken internal imports: ``from .x import y`` where module x exists but defines no top-level ``y``.

This is NOT a replacement for ruff/mypy (CI runs those); it is a safety net for offline environments.
"""

import ast
import builtins
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/app").resolve()
PKG = ROOT.name
BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__"}


def bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if not isinstance(node, ast.ClassDef):
                a = node.args
                for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
                    names.add(arg.arg)
        elif isinstance(node, ast.Lambda):
            a = node.args
            for arg in a.posonlyargs + a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
                names.add(arg.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def top_level(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out.add(n.id)
    return out


def unused_imports(tree: ast.Module, path: Path) -> list[tuple[int, str]]:
    """Imported names never referenced in the module (mirrors ruff F401). ``__init__`` re-exports are skipped."""
    if path.name == "__init__.py":
        return []
    imported: dict[str, int] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if a.name != "*":
                    imported[(a.asname or a.name).split(".")[0]] = node.lineno
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used |= {n.value.id for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)}
    text_refs = " ".join(c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str))
    lines = path.read_text().splitlines()
    return [
        (ln, name)
        for name, ln in imported.items()
        if name not in used and name not in text_refs.split() and "noqa" not in lines[ln - 1]
    ]


problems = 0
files = sorted(ROOT.rglob("*.py"))
trees = {f: ast.parse(f.read_text(), str(f)) for f in files}
exports = {f: top_level(t) for f, t in trees.items()}

for f, tree in trees.items():
    rel = f.relative_to(ROOT.parent)
    for lineno, name in unused_imports(tree, f):
        print(f"{rel}:{lineno}: unused import '{name}'")
        problems += 1
    known = bound_names(tree) | BUILTINS
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id not in known:
            print(f"{rel}:{node.lineno}: undefined name '{node.id}'")
            problems += 1
        if isinstance(node, ast.ImportFrom) and node.level > 0:
            base = f.parent
            for _ in range(node.level - 1):
                base = base.parent
            parts = node.module.split(".") if node.module else []
            target = base.joinpath(*parts)
            module_file = target.with_suffix(".py") if parts else base / "__init__.py"
            if parts and not module_file.exists():
                module_file = target / "__init__.py"
            if not module_file.exists():
                print(f"{rel}:{node.lineno}: relative import of missing module '{'.'.join(parts)}'")
                problems += 1
                continue
            for alias in node.names:
                if alias.name == "*" or module_file not in exports:
                    continue
                if alias.name not in exports[module_file] and not (module_file.parent / alias.name).exists() and not (module_file.parent / f"{alias.name}.py").exists():
                    print(f"{rel}:{node.lineno}: '{alias.name}' is not defined in {module_file.relative_to(ROOT.parent)}")
                    problems += 1
print(f"checked {len(files)} files, {problems} problem(s)")
sys.exit(1 if problems else 0)
