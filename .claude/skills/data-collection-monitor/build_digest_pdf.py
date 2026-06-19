"""Render an HTML file to PDF using the locally-installed headless Chrome / Edge.

Provenance (vendored copy — sub-project independence):
    source : .claude/skills/generate-pdf-report/build_pdf.py
    copied : 2026-06-15
    symbols: find_browser(), html_to_pdf()
    reason : keep the data-collection-monitor skill self-contained (no cross-skill
             sys.path import). Same Chromium ``--print-to-pdf`` approach — highest
             fidelity on Windows with zero extra deps (no WeasyPrint/GTK, no Playwright).
    note   : not kept in sync with the source; do not edit the function bodies unless
             the upstream toolchain changes.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

# Common Chromium-family install locations (in priority order).
_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def find_browser() -> str:
    """Return the path to a usable Chromium-family browser executable."""
    for name in ("chrome", "chrome.exe", "msedge", "msedge.exe"):
        found = shutil.which(name)
        if found:
            return found
    for path in _CANDIDATES:
        if Path(path).exists():
            return path
    raise FileNotFoundError(
        "No Chrome or Edge found. Install a Chromium-family browser or pass an explicit path."
    )


def html_to_pdf(html: Path, out: Path, browser: str | None = None) -> Path:
    """Print *html* to *out* PDF with headless Chrome/Edge."""
    browser = browser or find_browser()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Delete any stale PDF first so a failed render errors loudly rather than
    # silently leaving the previous file. If the target is locked (open in a
    # PDF reader) fall back to a timestamped name.
    try:
        out.unlink(missing_ok=True)
    except PermissionError:
        out = out.with_name(f"{out.stem}_{int(time.time())}{out.suffix}")
        print(f"[build_digest_pdf] target PDF is locked (open in a reader?); writing to: {out.name}")
    url = html.resolve().as_uri()  # file:///... so Chrome can read local assets

    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-pdf-header-footer",  # drop the default date/URL header & footer
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={out.resolve()}",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not out.exists():
        sys.stderr.write((result.stdout or "") + "\n" + (result.stderr or "") + "\n")
        raise RuntimeError(f"PDF render failed (exit={result.returncode})")
    print(f"[build_digest_pdf] wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
    return out
