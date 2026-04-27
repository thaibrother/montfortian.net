#!/usr/bin/env python3
"""
Pre-deploy privacy guard for montfortian.net

USAGE: python3 _verify_privacy.py
       (run before every commit/push that touches the site)

EXIT CODE:
  0 = clean — safe to push
  1 = LEAK FOUND — DO NOT PUSH

History:
  - 26 เม.ย. 69 — birth date regression (user: "สุดแสนอันตราย")
  - 27 เม.ย. 69 — search-index.json indexed brothers-age.html (user caught)
  - 27 เม.ย. 69 — discovered brothers-age.html LIVE on prod (file existed in git)
                  → user wants to keep file LOCAL only
                  → guard updated to check git-tracking, not file existence

Logic v2 (27 เม.ย. 69):
  - LOCAL file existence is OK for files in PRIVATE_LOCAL_OK list (e.g. brothers-age.html)
  - But these files MUST be in .gitignore AND NOT git-tracked
  - Forbidden text patterns scanned only in git-tracked files
"""
import os, sys, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# Files that MUST NOT be on the deployed site (i.e., must not be git-tracked)
# But these files MAY exist locally for personal viewing
PRIVATE_LOCAL_OK = {
    "brothers-age.html",
}

# Forbidden text patterns — these must NOT appear in any git-tracked file
FORBIDDEN_TEXT_PATTERNS = [
    (r'\bborn\s*:\s*"[\d-]+"', 'birth date data field'),
    (r'\bbornDisplay\s*:\s*"', 'birth date display field'),
    (r'🎂\s*Born', 'birth date display in HTML'),
    (r'>By Birth Date<', 'nav tab "By Birth Date"'),
]

errors = []
warnings = []

# Get list of git-tracked files
try:
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True, text=True, check=True
    )
    tracked = set(result.stdout.strip().split("\n"))
except Exception as e:
    errors.append(f"Could not run git ls-files: {e}")
    tracked = set()

# 1. Check PRIVATE_LOCAL_OK files are NOT git-tracked
for fname in PRIVATE_LOCAL_OK:
    matching_tracked = [t for t in tracked if Path(t).name == fname]
    if matching_tracked:
        for t in matching_tracked:
            errors.append(f"PRIVATE FILE IS GIT-TRACKED: {t} — must be untracked (run: git rm --cached {t})")
    # Also verify .gitignore covers it
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        ignored_patterns = gitignore.read_text(encoding="utf-8")
        if fname not in ignored_patterns:
            warnings.append(f"{fname} not in .gitignore — add it to prevent re-tracking")

# 2. Scan only GIT-TRACKED .html/.json/.js for forbidden patterns
for tracked_file in tracked:
    if not tracked_file:
        continue
    path = ROOT / tracked_file
    if not path.exists():
        continue
    if path.suffix.lower() not in {".html", ".json", ".js"}:
        continue
    if path.name == Path(__file__).name:
        continue
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    for pattern, label in FORBIDDEN_TEXT_PATTERNS:
        matches = list(re.finditer(pattern, text))
        if matches:
            errors.append(f"FORBIDDEN PATTERN ({label}) found {len(matches)}× in {tracked_file}")

# Report
print("=" * 60)
print("MONTFORTIAN.NET — PRIVACY DEPLOY GUARD (v2)")
print("=" * 60)

if warnings:
    print(f"\n⚠️  {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  ⚠ {w}")

if errors:
    print(f"\n🚨 LEAK FOUND — {len(errors)} issue(s):\n")
    for e in errors:
        print(f"  ❌ {e}")
    print(f"\n⚠️  DO NOT PUSH until resolved")
    print(f"\nFix instructions:")
    print(f"  - For tracked private files: run 'git rm --cached <file>'")
    print(f"  - For forbidden patterns: strip from listed file(s)")
    print(f"  - Re-run this script — must show CLEAN")
    sys.exit(1)
else:
    print("\n✅ CLEAN — no privacy leaks in tracked files")
    print(f"   Checked {len(tracked)} git-tracked file(s)")
    print(f"   Verified {len(PRIVATE_LOCAL_OK)} private file(s) NOT tracked")
    print(f"   Scanned {len(FORBIDDEN_TEXT_PATTERNS)} forbidden pattern(s)")
    print(f"\nSafe to commit + push")
    sys.exit(0)
