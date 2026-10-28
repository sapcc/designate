#!/usr/bin/env python3
"""Print the migration plan for a patches.yaml.

Reads the flat manifest and prints the order in which the still-`pending`
patches must be ported so that no patch is ported before the patches it
depends on. `integrated` and `upstreamed` dependencies are already satisfied
and impose no ordering; `dropped` patches are skipped entirely.

The order is a topological sort (Kahn's algorithm) of the pending patches,
with ties broken by patch ID so the output is deterministic.

With a commit source (an old branch's manifest, as a file or a git ref) each
patch line also gets the ready-to-run cherry-pick command, aggregating the
base patch's commits plus all of its fix entries' commits. new_cycle.py clears
commits and consolidates fixes away, so the commits live only in the previous
cycle's manifest — hence the separate source.

Usage:
    python3 scripts/plan.py [path/to/patches.yaml]
    python3 scripts/plan.py patches.yaml --commits-ref stable/2024.2-m3
    python3 scripts/plan.py patches.yaml --commits-from ../old/patches.yaml

Exit code 0 = plan printed, 1 = cycle or stale dependency, 2 = usage/parse error.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

try:
    from ruamel.yaml import YAML as _YAML
except ImportError:
    print("error: ruamel.yaml is required (pip install ruamel.yaml)", file=sys.stderr)
    raise SystemExit(2)

FIX_RE = re.compile(r"^(PATCH-\d{3})-F(\d{2})$")


def _load(path: str) -> dict:
    y = _YAML()
    try:
        with open(path, encoding="utf-8") as fh:
            return y.load(fh)
    except FileNotFoundError:
        print(f"error: file not found: {path}", file=sys.stderr)
        raise SystemExit(2)
    except Exception as exc:
        print(f"error: invalid YAML in {path}:\n{exc}", file=sys.stderr)
        raise SystemExit(2)


def _load_ref(ref: str, path: str = "patches.yaml") -> dict:
    r = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"error: could not read {path} at ref {ref!r}:\n{r.stderr.strip()}", file=sys.stderr)
        raise SystemExit(2)
    y = _YAML()
    try:
        return y.load(r.stdout)
    except Exception as exc:
        print(f"error: invalid YAML in {ref}:{path}:\n{exc}", file=sys.stderr)
        raise SystemExit(2)


def _collect_commits(source: dict) -> dict[str, list[str]]:
    """Map each base patch id → its commits plus all its fix entries' commits,
    in application order (base first, then fixes sorted by -Fnn)."""
    base: dict[str, list[str]] = {}
    fixes: dict[str, list[tuple[int, list[str]]]] = {}
    for p in (source.get("patches") or []):
        if not isinstance(p, dict):
            continue
        pid = p.get("id", "")
        commits = [str(c) for c in (p.get("commits") or [])]
        m = FIX_RE.match(pid)
        if m:
            fixes.setdefault(m.group(1), []).append((int(m.group(2)), commits))
        else:
            base[pid] = commits

    result: dict[str, list[str]] = {}
    for pid, commits in base.items():
        combined = list(commits)
        for _, fix_commits in sorted(fixes.get(pid, [])):
            combined.extend(fix_commits)
        result[pid] = combined
    return result


def plan(data: dict, commits: dict[str, list[str]] | None = None) -> int:
    patches = [p for p in (data.get("patches") or []) if isinstance(p, dict)]
    status = {p["id"]: p.get("status", "pending") for p in patches if "id" in p}
    title = {p["id"]: p.get("title", "") for p in patches if "id" in p}

    # The worklist is every base patch that still has to be ported into the new
    # cycle: skip fix entries (they fold into their base) and skip patches that
    # are not ported at all — dropped (gone) and upstreamed (upstream has them).
    SKIP = {"dropped", "upstreamed"}
    worklist = [
        p["id"] for p in patches
        if "id" in p and not FIX_RE.match(p["id"]) and p.get("status") not in SKIP
    ]
    worklist_set = set(worklist)

    # Blockers for each patch = its deps that are themselves still on the worklist.
    blockers: dict[str, list[str]] = {}
    warnings: list[str] = []
    for pid in worklist:
        p = next(x for x in patches if x.get("id") == pid)
        blocking = []
        for d in (p.get("depends_on") or []):
            st = status.get(d)
            if st is None:
                warnings.append(f"{pid}: depends on unknown id {d!r}")
            elif st == "dropped":
                warnings.append(f"{pid}: depends on dropped patch {d!r}")
            elif d in worklist_set:
                blocking.append(d)
            # upstreamed / not on worklist → already satisfied, not a blocker
        blockers[pid] = blocking

    # Kahn's algorithm, ties broken by id for determinism.
    indegree = {pid: len(blockers[pid]) for pid in worklist}
    dependents: dict[str, list[str]] = {pid: [] for pid in worklist}
    for pid, bl in blockers.items():
        for b in bl:
            dependents[b].append(pid)

    ready = sorted(pid for pid in worklist if indegree[pid] == 0)
    order: list[str] = []
    while ready:
        pid = ready.pop(0)
        order.append(pid)
        for child in dependents[pid]:
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()

    release = data.get("release", "?")
    upstreamed = sum(1 for p in patches if p.get("status") == "upstreamed")
    dropped = sum(1 for p in patches if p.get("status") == "dropped")
    fixes = sum(1 for p in patches if FIX_RE.match(p.get("id", "")))

    show_commits = commits is not None and any(commits.get(pid) for pid in order)

    print(f"Migration plan: {release}")
    print(f"  to port: {len(worklist)}   upstreamed: {upstreamed}   dropped: {dropped}   fixes folded: {fixes}")
    print()

    if not order:
        print("  nothing to port.")
    else:
        width = max(len(order[i]) for i in range(len(order)))
        for i, pid in enumerate(order, 1):
            after = blockers[pid]
            suffix = f"   ← after {', '.join(after)}" if after else ""
            print(f"  {i:>3}. {pid:<{width}}  {title[pid]}{suffix}")
            if show_commits:
                shas = commits.get(pid) or []
                if shas:
                    print(f"       git cherry-pick -x -n {' '.join(shas)}")
                else:
                    print("       (no commits in source — port by hand)")

    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)

    leftover = [pid for pid in worklist if pid not in set(order)]
    if leftover:
        print(f"error: dependency cycle among {', '.join(sorted(leftover))}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog=argv[0], description="Print the migration plan for a patches.yaml.")
    ap.add_argument("patches", nargs="?", default="patches.yaml",
                    help="manifest to plan (default: patches.yaml)")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--commits-from", metavar="FILE",
                     help="old manifest file to read cherry-pick commits from")
    src.add_argument("--commits-ref", metavar="REF",
                     help="git ref to read the old manifest (patches.yaml) from")
    args = ap.parse_args(argv[1:])

    data = _load(args.patches)
    if args.commits_from:
        source = _load(args.commits_from)
    elif args.commits_ref:
        source = _load_ref(args.commits_ref)
    else:
        source = data  # commits come inline when planning the old manifest itself

    return plan(data, _collect_commits(source))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
