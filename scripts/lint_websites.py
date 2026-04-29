#!/usr/bin/env python3
"""
lint_websites.py — pre-push checks for fsgthailand.org / montfortian.net

Catches recurring mistakes:
  - "14 schools" / "14 Schools" / "14 โรง"  (public-facing — not historical)
  - "St. Bernadette" / "World Voice Day" stale calendar badges
  - Thai-only content on montfortian.net (audience = Religious worldwide, English)
  - Brother birth dates leaking to public
  - brothers-age.html in git-tracked area

Usage:
    cd ~/Github/<repo>
    python3 scripts/lint_websites.py

Exit codes:
    0  — clean, safe to push
    1  — errors found, fix before push
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT.name  # repo folder name = site name guess

# Pages that are "historical context" allowed to keep "14 โรง" (e.g. supervision in 2568)
HISTORICAL_ALLOWLIST = {
    "hrm-supervision-objectives.html",
    "ict-admin-objectives.html",
    "ict-info-objectives.html",
    "ict-swis-objectives.html",
    "hrm-admin-objectives.html",
    "swis/confirm-loop.html",
    "work-calendar.html",
}

EXCLUDE_DIRS = {"_old_to_delete", ".git", "node_modules"}


def html_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.html"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


# ─── Checks ──────────────────────────────────────────────────────

def check_school_count(errors: list[str], files: list[Path]) -> None:
    """Catches '14 Schools' regressions in public-facing pages.
    Skips HTML comments (not user-visible) and historical context pages."""
    pat = re.compile(r"\b14\s+(Schools?|โรงเรียน)\b", re.IGNORECASE)
    comment_pat = re.compile(r"^\s*<!--.*-->\s*$")
    for p in files:
        if rel(p) in HISTORICAL_ALLOWLIST:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if comment_pat.match(line):
                continue  # HTML comment — not visible
            if pat.search(line):
                errors.append(
                    f"{rel(p)}:{line_no}: '14 Schools' — should be 15 (ACEP included). "
                    f"Line: {line.strip()[:100]}"
                )


def check_stale_calendar(errors: list[str], files: list[Path]) -> None:
    """Catches static calendar badge ghosts."""
    needles = [
        ("St. Bernadette Soubirous", "Stale static calendar badge"),
        ("World Voice Day", "Stale static calendar badge"),
        ("Easter — 3rd Week", "Stale static calendar week label"),
        ("Easter &mdash; 3rd Week", "Stale static calendar week label"),
    ]
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for needle, msg in needles:
                if needle in line:
                    errors.append(f"{rel(p)}:{line_no}: {msg}: '{needle}'")


def check_thai_in_montfortian(warnings: list[str], files: list[Path]) -> None:
    """montfortian.net audience = Religious worldwide, English. Thai blocks → warn."""
    if "montfortian" not in SITE:
        return
    # Skip news.html (mixed-language editorial allowed) — but warn
    thai_re = re.compile(r"[฀-๿]+")
    for p in files:
        # Allow pages that are explicitly Thai (e.g. news editorial about Thailand)
        # Just warn so user can decide
        text = p.read_text(encoding="utf-8", errors="ignore")
        # Strip <script>...</script> blocks (data may contain Thai) and HTML comments
        stripped = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
        stripped = re.sub(r"<!--[\s\S]*?-->", "", stripped)
        thai = thai_re.findall(stripped)
        thai_chars = sum(len(t) for t in thai)
        if thai_chars > 50:  # threshold — small attribution OK
            warnings.append(
                f"{rel(p)}: {thai_chars} Thai chars detected. "
                f"montfortian.net target = Religious worldwide (English). "
                f"Confirm intentional or translate."
            )


def _git_tracked_files() -> set[str]:
    """Return paths git is actually tracking. Used to skip false positives
    on locally-present-but-gitignored files (e.g. brothers-age.html)."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        )
        return set(out.stdout.splitlines())
    except Exception:
        return set()  # if not a git repo, return empty (no filtering)


def check_birth_dates(errors: list[str], files: list[Path]) -> None:
    """Brother birth dates must not appear on git-tracked public pages.
    Locally-present-but-gitignored files (brothers-age.html) are OK."""
    bad_patterns = [
        r"🎂\s*Born",
        r"data-born=",
        r"bornDisplay",
        r'"born"\s*:',
        r"By\s+Birth\s+Date",
    ]
    pat = re.compile("|".join(bad_patterns))
    tracked = _git_tracked_files()

    for p in files:
        rp = rel(p)
        # Only error if brothers-age.html is git-tracked (would be deployed)
        if p.name == "brothers-age.html":
            if tracked and rp in tracked:
                errors.append(
                    f"{rp}: TRACKED in git — would be deployed publicly. "
                    f"Run: git rm --cached {rp} && add to .gitignore"
                )
            # if untracked → fine, file is local-only by .gitignore
            continue

        # Check other files for birth date leaks (only those tracked)
        if tracked and rp not in tracked:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                errors.append(
                    f"{rp}:{line_no}: Brother birth date pattern leaking. "
                    f"Line: {line.strip()[:120]}"
                )


def check_dead_url_markers(warnings: list[str], files: list[Path]) -> None:
    """Known dead URLs that must never be used again."""
    dead = [
        "www.sg-gabrielites.org",
        "www.brothersofsaintgabriel.org",
        "www.cect.or.th",
    ]
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), 1):
            for d in dead:
                if d in line:
                    warnings.append(f"{rel(p)}:{line_no}: dead URL '{d}'")


def check_calendar_data_present(errors: list[str], warnings: list[str]) -> None:
    """Calendar badge engine must have JSON for CURRENT year (error).
    Next year is a warning (lead time reminder)."""
    from datetime import date

    js_path = ROOT / "js" / "liturgical-calendar.js"
    if not js_path.exists():
        return  # no calendar engine = no requirement
    today = date.today()
    cur = ROOT / "data" / f"rome_calendar_{today.year}.json"
    nxt = ROOT / "data" / f"rome_calendar_{today.year + 1}.json"
    if not cur.exists():
        errors.append(
            f"missing data/rome_calendar_{today.year}.json "
            f"— TODAY's badge will be empty. Run convert_calendar.py."
        )
    if not nxt.exists() and today.month >= 11:
        warnings.append(
            f"missing data/rome_calendar_{today.year + 1}.json "
            f"— prepare next year's calendar before Jan 1."
        )


# ─── Main ─────────────────────────────────────────────────────────

def main() -> int:
    files = html_files()
    errors: list[str] = []
    warnings: list[str] = []

    check_school_count(errors, files)
    check_stale_calendar(errors, files)
    check_birth_dates(errors, files)
    check_thai_in_montfortian(warnings, files)
    check_dead_url_markers(warnings, files)
    check_calendar_data_present(errors, warnings)

    print(f"=== lint_websites: {SITE} ({len(files)} html) ===")
    if warnings:
        print(f"\n⚠  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠  {w}")

    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  ❌ {e}")
        print(f"\n→ Fix these before push.")
        return 1

    if not warnings and not errors:
        print("✓ clean — safe to push")
    elif warnings:
        print(f"\n→ {len(warnings)} warnings (non-blocking). Push at your discretion.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
