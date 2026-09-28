#!/usr/bin/env python3
"""Validate a pull request title against the downstream patch convention.

Accepted formats:
    [PATCH-001] Short description
    [PATCH-005-F01] Fix serial overflow
    [SETUP] Add PR template and patches manifest

The description after the closing bracket must be at least 3 characters.

Usage:
    python3 scripts/check_pr_title.py "[PATCH-001] My feature"
    PR_TITLE="[SETUP] ..." python3 scripts/check_pr_title.py
"""
from __future__ import annotations

import os
import re
import sys

PATTERN = re.compile(r"^\[(PATCH-\d{3}(-F\d{2})?|SETUP)\] .{3,}$")

EXAMPLES = """\
Valid title formats:
    [PATCH-001] CI / Concourse setup            (new patch or port)
    [PATCH-011] Drop: upstreamed in 2026.2      (removal)
    [PATCH-023] Rework: adapt to threading      (rework)
    [PATCH-005-F01] Fix serial overflow         (fix)
    [SETUP] Add PR template and patches manifest (infrastructure)"""


def check(title: str) -> bool:
    return bool(PATTERN.match(title))


def main(argv: list[str]) -> int:
    title = argv[1] if len(argv) > 1 else os.environ.get("PR_TITLE", "")
    title = title.strip()

    if not title:
        print("error: no PR title provided (argv[1] or $PR_TITLE)", file=sys.stderr)
        print(EXAMPLES, file=sys.stderr)
        return 2

    if check(title):
        print(f"ok: {title!r}")
        return 0

    print(f"error: PR title does not follow the convention:\n    {title!r}\n", file=sys.stderr)
    print(EXAMPLES, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
