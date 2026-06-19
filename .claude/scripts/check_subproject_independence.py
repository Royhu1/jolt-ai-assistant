"""check_subproject_independence.py
====================================
Read-only lint for the sub-project independence convention (2026-06-11):
workspace sub-projects may only depend on stdlib/pip packages, the versioned
``src/jolt_toolkit`` package, and their own files — never on another
sub-project's code.

The check walks ``*.py`` files under the governed workspace roots and flags
every ``sys.path.insert``/``sys.path.append`` whose target resolves to a
DIFFERENT sub-project (targets pointing at ``src`` or at the file's own
sub-project are allowed). Frozen snapshots are whitelisted and reported as
GRANDFATHERED instead of failing.

Detection is AST-based and follows one level of module-scope name assignment,
so the common pattern ``_LIB = ROOT / "x" / "y"; sys.path.insert(0, str(_LIB))``
is resolved correctly.

Usage (from the repo root)
--------------------------
    python .claude/scripts/check_subproject_independence.py [--root <repo>] [--verbose]

Exit code: 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# Workspace roots governed by the convention. A sub-project is the first
# directory level below a root; files directly under a root belong to a
# pseudo sub-project named "." of that root.
GOVERNED_ROOTS = (
    "data_analysis_workspace",
    "research_projects",
    "publication_workspace",
    "monthly_presentation",
)

# Path prefixes (posix, repo-relative) of the SCANNED FILE that are exempt:
# frozen snapshots predating the convention, and deprecated graveyards.
WHITELIST_PREFIXES = (
    "monthly_presentation/",
    "data_analysis_workspace/deprecated/",
)

SKIP_DIRS = {"__pycache__", ".ipynb_checkpoints", ".git", "node_modules"}


def _flatten_path_expr(node: ast.AST, names: dict[str, ast.AST], depth: int = 0) -> list[str]:
    """Flatten a Path-style expression into ordered path segments.

    Handles: string constants (split on / and \\), Name lookups (one level,
    recursively bounded), ``str(...)`` wrappers, ``Path(...)`` calls and
    ``a / b / c`` BinOp chains. Unknown nodes yield no segments.
    """
    if depth > 6:
        return []
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [s for s in node.value.replace("\\", "/").split("/") if s and s != "."]
    if isinstance(node, ast.Name):
        target = names.get(node.id)
        return _flatten_path_expr(target, names, depth + 1) if target is not None else []
    if isinstance(node, ast.Call):
        func = node.func
        fname = func.id if isinstance(func, ast.Name) else (
            func.attr if isinstance(func, ast.Attribute) else "")
        if fname in {"str", "Path", "PurePath", "resolve", "absolute"} and node.args:
            return _flatten_path_expr(node.args[0], names, depth + 1)
        # Path(__file__).resolve().parents[n] etc. — treat as opaque prefix
        return []
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return (_flatten_path_expr(node.left, names, depth + 1)
                + _flatten_path_expr(node.right, names, depth + 1))
    if isinstance(node, ast.Subscript):  # e.g. parents[3] — opaque
        return []
    return []


def _module_level_names(tree: ast.Module) -> dict[str, ast.AST]:
    """Map of module-scope simple assignments: name -> value expression."""
    out: dict[str, ast.AST] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name):
            out[stmt.targets[0].id] = stmt.value
    return out


def _own_subproject(rel: Path) -> tuple[str, str]:
    """(root, subproject) identity of a repo-relative file path."""
    parts = rel.parts
    root = parts[0]
    sub = parts[1] if len(parts) > 2 else "."
    return root, sub


def check_file(py: Path, repo: Path) -> list[dict]:
    """Return a list of finding dicts for one file."""
    rel = py.relative_to(repo)
    try:
        tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as e:
        return [{"kind": "WARN", "file": rel, "line": e.lineno or 0,
                 "detail": f"syntax error, skipped: {e.msg}"}]
    names = _module_level_names(tree)
    own = _own_subproject(rel)
    findings = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"insert", "append"}):
            continue
        value = node.func.value
        if not (isinstance(value, ast.Attribute) and value.attr == "path"
                and isinstance(value.value, ast.Name) and value.value.id == "sys"):
            continue
        path_arg = node.args[-1] if node.args else None
        segments = _flatten_path_expr(path_arg, names) if path_arg is not None else []
        if not segments:
            findings.append({"kind": "UNRESOLVED", "file": rel, "line": node.lineno,
                             "detail": "target not statically resolvable"})
            continue
        if "src" in segments:
            continue  # the shared toolkit — always allowed
        target = None
        for i, seg in enumerate(segments):
            if seg in GOVERNED_ROOTS:
                target = (seg, segments[i + 1] if i + 1 < len(segments) else ".")
                break
        if target is None:
            continue  # own-dir relative insert or non-governed location
        if target == own:
            continue  # importing from its own sub-project — allowed
        whitelisted = any(rel.as_posix().startswith(p) for p in WHITELIST_PREFIXES)
        findings.append({
            "kind": "GRANDFATHERED" if whitelisted else "VIOLATION",
            "file": rel, "line": node.lineno,
            "detail": f"-> {target[0]}/{target[1]} (target: {'/'.join(segments)})",
        })
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="sub-project independence lint (read-only)")
    ap.add_argument("--root", default=None, help="repo root (default: two levels up)")
    ap.add_argument("--verbose", action="store_true",
                    help="also print GRANDFATHERED / UNRESOLVED / WARN entries")
    args = ap.parse_args(argv)

    repo = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    n_files = 0
    findings: list[dict] = []
    for root in GOVERNED_ROOTS:
        base = repo / root
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            if any(part in SKIP_DIRS for part in py.parts):
                continue
            n_files += 1
            findings.extend(check_file(py, repo))

    violations = [f for f in findings if f["kind"] == "VIOLATION"]
    shown = findings if args.verbose else violations
    for f in sorted(shown, key=lambda f: (str(f["file"]), f["line"])):
        print(f'{f["kind"]} {f["file"].as_posix()}:{f["line"]} {f["detail"]}')
    print(f'{len(violations)} violation(s) / {n_files} files scanned'
          + (f' ({len(findings) - len(violations)} non-violation entries hidden;'
             f' use --verbose)' if not args.verbose and len(findings) > len(violations)
             else ""))
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
