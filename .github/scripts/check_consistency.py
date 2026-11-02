#!/usr/bin/env python3
"""Check fork consistency: (fork_delta - pr_commits) must match patches.yaml integrated commits."""
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping

sys.path.insert(0, os.path.dirname(__file__))
from patch_pr import load_patches


def _git_log(base: str, head: str) -> set[str]:
    result = subprocess.run(
        ["git", "log", "--no-merges", "--format=%H", f"{base}..{head}"],
        capture_output=True, text=True, check=True,
    )
    return {sha[:8] for sha in result.stdout.strip().splitlines() if sha.strip()}


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"usage: {argv[0]} <patches.yaml> <upstream_base> <pr_base_ref>", file=sys.stderr)
        return 2

    patches_path, upstream_base, pr_base_ref = argv[1], argv[2], argv[3]

    data = load_patches(patches_path)

    COUNTED_STATUSES = {"integrated", "dropped", "upstreamed"}

    known: set[str] = set()
    for p in data["patches"]:
        if not isinstance(p, Mapping) or p.get("status") not in COUNTED_STATUSES:
            continue
        for c in (p.get("commits") or []):
            known.add(str(c)[:8])
        for c in (p.get("migrations") or []):
            known.add(str(c)[:8])

    fork_delta = _git_log(f"origin/{upstream_base}", "HEAD")
    pr_commits = _git_log(f"origin/{pr_base_ref}", "HEAD")
    fork_minus_pr = fork_delta - pr_commits

    errors: list[str] = []

    unaccounted = fork_minus_pr - known
    if unaccounted:
        errors.append(
            f"commits in fork not accounted for in patches.yaml: {', '.join(sorted(unaccounted))}"
        )

    missing = known - fork_delta
    if missing:
        errors.append(
            f"commits listed as integrated in patches.yaml missing from fork: {', '.join(sorted(missing))}"
        )

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1

    print(
        f"ok: consistency check passed "
        f"({len(fork_minus_pr)} accounted commits, {len(pr_commits)} in this PR)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
