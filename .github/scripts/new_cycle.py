#!/usr/bin/env python3
"""Generate a fresh patches.yaml for a new integration branch.

Reads the previous branch's manifest and produces a clean file for the
next cycle:

  - dropped entries are removed.
  - fix entries (PATCH-NNN-F0x) are consolidated into their base patch:
    the base inherits the fix's extra dependencies, the fix entry is removed.
    This is always safe because a fix whose extra dep would create a cycle
    on consolidation is already rejected at creation time.
  - status is reset to 'pending' (upstreamed entries keep 'upstreamed').
  - note is carried forward — it is the institutional memory for the cycle.
  - commits and pr are cleared (they belonged to the old branch).

Usage:
    python3 scripts/new_cycle.py <old-patches.yaml> <new-branch>

The result is written to stdout. Redirect to the new patches.yaml:
    python3 scripts/new_cycle.py patches.yaml stable/2026.2-m3 > new-patches.yaml
"""
from __future__ import annotations

import io
import re
import sys

try:
    from ruamel.yaml import YAML as _YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
except ImportError:
    print("error: ruamel.yaml is required (pip install ruamel.yaml)", file=sys.stderr)
    raise SystemExit(2)

ID_RE = re.compile(r"^PATCH-(\d{3})(-F(\d{2}))?$")


def _yaml() -> _YAML:
    y = _YAML()
    y.preserve_quotes = True
    return y


def _flow_seq(items: list) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq


def generate(old_path: str, new_branch: str) -> dict:
    y = _yaml()
    try:
        with open(old_path, encoding="utf-8") as fh:
            old = y.load(fh)
    except FileNotFoundError:
        raise SystemExit(f"error: file not found: {old_path}")
    except Exception as exc:
        raise SystemExit(f"error: invalid YAML in {old_path}:\n{exc}")

    old_patches: list = old.get("patches") or []

    # Collect all fix entries and their bases
    fixes: dict[str, dict] = {}      # base_id → {extra_deps: list}
    base_ids: set[str] = set()
    for p in old_patches:
        if not isinstance(p, dict):
            continue
        m = ID_RE.match(p.get("id", ""))
        if m and m.group(2):  # fix entry
            base_id = f"PATCH-{m.group(1)}"
            extra_deps = [d for d in (p.get("depends_on") or []) if d != base_id]
            if base_id not in fixes:
                fixes[base_id] = {"extra_deps": []}
            for d in extra_deps:
                if d not in fixes[base_id]["extra_deps"]:
                    fixes[base_id]["extra_deps"].append(d)
        elif m and not m.group(2):
            base_ids.add(p["id"])

    new_patches: list[CommentedMap] = []
    for p in old_patches:
        if not isinstance(p, dict):
            continue

        pid = p.get("id", "")
        m = ID_RE.match(pid)
        if not m:
            continue

        # Skip fix entries — they get consolidated into their base
        if m.group(2):
            continue

        old_status = p.get("status", "pending")

        # dropped entries are not carried over
        if old_status == "dropped":
            continue

        new_status = "upstreamed" if old_status == "upstreamed" else "pending"

        # Merge fix extra-deps into base
        existing_deps = list(p.get("depends_on") or [])
        if pid in fixes:
            for d in fixes[pid]["extra_deps"]:
                if d not in existing_deps:
                    existing_deps.append(d)

        entry = CommentedMap()
        entry["id"] = pid
        entry["title"] = p.get("title", "")
        entry["depends_on"] = _flow_seq(existing_deps)
        entry["status"] = new_status
        note = p.get("note")
        if note:
            entry["note"] = note
        # commits and pr are not carried forward

        new_patches.append(entry)

    result = CommentedMap()
    result["schema_version"] = old.get("schema_version", 1)
    result["release"] = new_branch
    result["patches"] = new_patches
    return result


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(f"usage: {argv[0]} <old-patches.yaml> <new-branch>", file=sys.stderr)
        return 2

    data = generate(argv[1], argv[2])
    buf = io.StringIO()
    _yaml().dump(data, buf)
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
