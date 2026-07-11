"""check_skill_registry.py
==========================
Read-only lint for the harness registry convention (``.claude/rules/skill-design.md``):
the root ``README.md`` index tables (Commands / Skills / Agents) must stay in sync with
what actually exists under ``.claude/`` — the registry-drift check borrowed from
nature-skills' install ``--check`` idea, adapted to an in-repo harness.

Checks
------
1. Bijection: every skill directory / command file / agent file has exactly one table
   row, and every row points at something that exists on disk (no orphans either way).
2. Links: every row's name is a markdown link whose target file exists.
3. Statuses: every row's Status is one of ``Draft`` / ``Beta`` / ``Stable``.
4. Minimum files (anatomy v2, router / static-dynamic split): every skill directory
   contains ``SKILL.md``, and ``manifest.yaml`` + ``README.md`` unless listed in
   ``VENDORED_SKILLS`` (vendored third-party skills keep their upstream README
   instead). The former per-skill ``PIPELINE.md`` was absorbed into each skill's
   ``README.md`` ("Pipeline" section) on 2026-07-11.

Usage (from the repo root)
--------------------------
    python .claude/scripts/check_skill_registry.py [--root <repo>] [--verbose]

Exit code: 0 = clean, 1 = violations found.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VALID_STATUSES = {"Draft", "Beta", "Stable"}

# Vendored third-party skills: exempt from the manifest.yaml + README.md requirement
# (they carry their upstream README instead) but still registered and status-labelled.
VENDORED_SKILLS = {"html-artifacts"}

# Directory names under .claude/skills that are not skills (shared layer, caches).
NON_SKILL_DIRS = {"_shared", "__pycache__"}

# README section heading -> (kind, expected path prefix of each row's link)
SECTIONS = {
    "### Commands": ("command", ".claude/commands/"),
    "### Skills": ("skill", ".claude/skills/"),
    "### Agents": ("agent", ".claude/agents/"),
}

_LINK_RE = re.compile(r"\[(?P<text>.+?)\]\((?P<path>[^)]+)\)")


def _split_row(line: str) -> list[str]:
    """Split a markdown table row into cells, honouring escaped ``\\|``."""
    cells = re.split(r"(?<!\\)\|", line.strip())
    # A well-formed row starts and ends with '|': drop the empty edge fragments.
    return [c.strip() for c in cells[1:-1]]


def _is_separator(cells: list[str]) -> bool:
    return all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c)


def parse_readme_tables(readme: Path) -> dict[str, list[dict]]:
    """Return {kind: [{name, path, status, line_no}, ...]} from the index tables."""
    rows: dict[str, list[dict]] = {"command": [], "skill": [], "agent": []}
    kind = prefix = None
    for line_no, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("### "):
            match = next((v for k, v in SECTIONS.items() if line.startswith(k)), None)
            kind, prefix = match if match else (None, None)
            continue
        if kind is None or not line.lstrip().startswith("|"):
            continue
        cells = _split_row(line)
        if not cells or _is_separator(cells) or cells[0] in ("Command", "Skill", "Agent"):
            continue
        link = _LINK_RE.search(cells[0])
        status = cells[1].strip("` ") if len(cells) > 1 else ""
        rows[kind].append(
            {
                "raw": cells[0],
                "path": link.group("path") if link else None,
                "status": status,
                "line_no": line_no,
                "prefix": prefix,
            }
        )
    return rows


def scan_disk(claude_dir: Path) -> dict[str, dict[str, Path]]:
    """Return {kind: {identity: path}} for what actually exists under .claude/."""
    skills = {
        d.name: d
        for d in sorted((claude_dir / "skills").iterdir())
        if d.is_dir() and d.name not in NON_SKILL_DIRS
    }
    commands = {p.stem: p for p in sorted((claude_dir / "commands").glob("*.md"))}
    agents = {p.stem: p for p in sorted((claude_dir / "agents").glob("*.md"))}
    return {"skill": skills, "command": commands, "agent": agents}


def identity_from_link(kind: str, link_path: str) -> str | None:
    """Derive the registry identity (dir name / file stem) from a row's link target."""
    parts = Path(link_path).parts
    try:
        idx = parts.index("skills" if kind == "skill" else kind + "s")
    except ValueError:
        return None
    if kind == "skill":
        return parts[idx + 1] if len(parts) > idx + 1 else None
    return Path(parts[idx + 1]).stem if len(parts) > idx + 1 else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--verbose", action="store_true", help="also print OK entries")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    readme = root / "README.md"
    claude_dir = root / ".claude"
    violations: list[str] = []

    tables = parse_readme_tables(readme)
    disk = scan_disk(claude_dir)

    for kind in ("command", "skill", "agent"):
        seen: dict[str, int] = {}
        for row in tables[kind]:
            where = f"README.md:{row['line_no']} [{kind}]"
            if row["path"] is None:
                violations.append(f"{where} row is not a markdown link: {row['raw']!r}")
                continue
            if not row["path"].startswith(row["prefix"]):
                violations.append(
                    f"{where} link {row['path']!r} does not point under {row['prefix']!r}"
                )
            if not (root / row["path"]).is_file():
                violations.append(f"{where} link target does not exist: {row['path']}")
            if row["status"] not in VALID_STATUSES:
                violations.append(
                    f"{where} invalid status {row['status']!r} "
                    f"(expected one of {sorted(VALID_STATUSES)})"
                )
            ident = identity_from_link(kind, row["path"])
            if ident is None:
                violations.append(f"{where} cannot derive identity from {row['path']!r}")
                continue
            if ident in seen:
                violations.append(
                    f"{where} duplicate row for {kind} {ident!r} "
                    f"(first at README.md:{seen[ident]})"
                )
            seen[ident] = row["line_no"]
            if ident not in disk[kind]:
                violations.append(f"{where} {kind} {ident!r} has no counterpart on disk")
            elif args.verbose:
                print(f"OK  {kind:7s} {ident:28s} {row['status']}")
        for ident in disk[kind]:
            if ident not in seen:
                violations.append(
                    f".claude {kind} {ident!r} is missing from the README index table"
                )

    for name, d in disk["skill"].items():
        if not (d / "SKILL.md").is_file():
            violations.append(f"skill {name!r} has no SKILL.md")
        if name not in VENDORED_SKILLS:
            for required in ("manifest.yaml", "README.md"):
                if not (d / required).is_file():
                    violations.append(
                        f"skill {name!r} has no {required} (add one per anatomy v2, "
                        f"or list the skill in VENDORED_SKILLS if vendored)"
                    )

    if violations:
        print(f"FAIL: {len(violations)} registry violation(s)\n" + "\n".join(
            f"  - {v}" for v in violations
        ))
        return 1
    counts = ", ".join(f"{len(disk[k])} {k}s" for k in ("command", "skill", "agent"))
    print(f"OK: README index tables in sync with .claude/ ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
