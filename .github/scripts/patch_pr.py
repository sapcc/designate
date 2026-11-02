#!/usr/bin/env python3
"""Manage patches.yaml via PR metadata.

Subcommands:
  validate <patches.yaml> <branch>
      Parse and validate PR metadata from $PR_BODY. Writes a preview to
      $GITHUB_STEP_SUMMARY (or stdout if not set). Exit 1 on errors.

  apply <patches.yaml> <branch> <merge_sha> <pr_number> <pr_title>
      Assign the final patch ID, collect landed commits, write the
      patches.yaml entry. Re-validates before writing; exits 1 and
      refuses to write on error.

Environment:
  PR_BODY          — PR body text (required for both subcommands)
  GITHUB_STEP_SUMMARY — path to the Actions step summary file (optional)
  GITHUB_OUTPUT       — path to the Actions output file (optional)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

try:
    from ruamel.yaml import YAML as _YAML
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString
except ImportError:
    print("error: ruamel.yaml is required (pip install ruamel.yaml)", file=sys.stderr)
    raise SystemExit(2)

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_TYPES = {"patch", "fix", "port", "drop", "upstream"}
ID_RE = re.compile(r"^PATCH-(\d{3})(-F(\d{2}))?$")

# Status values that satisfy a dependency requirement
SATISFIED_STATUSES = {"integrated", "upstreamed"}


# ─── Errors ───────────────────────────────────────────────────────────────────

class ParseError(Exception):
    pass


# ─── Metadata parsing ─────────────────────────────────────────────────────────

def parse_metadata(body: str) -> dict[str, Any]:
    """Extract and normalise Patch Metadata fields from a PR body."""
    m = re.search(
        r"^## Patch Metadata\s*\n(.*?)(?:^## |\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if not m:
        raise ParseError("## Patch Metadata section not found in PR body")
    section = m.group(1)

    def field(label_re: str) -> str | None:
        fm = re.search(
            rf"\*\*{label_re}.*?:\*\*[ \t]*(.*?)$",
            section,
            re.MULTILINE,
        )
        if not fm:
            return None
        val = fm.group(1).strip()
        return val if val else None

    raw_type = field(r"Type")
    raw_pid = field(r"Patch-ID")
    raw_deps = field(r"New introduced dependency")
    raw_resolved = field(r"Resolved dependency")

    if raw_type is None:
        raise ParseError("Type field is missing from ## Patch Metadata")

    type_val = raw_type.lower().strip()

    patch_id: str | None = None
    if raw_pid and raw_pid.strip():
        patch_id = raw_pid.strip().upper()
        if not ID_RE.match(patch_id):
            raise ParseError(f"Invalid Patch-ID: {patch_id!r} (expected PATCH-NNN or PATCH-NNN-FNN)")

    def parse_ids(raw: str | None) -> list[str]:
        if not raw or not raw.strip():
            return []
        return [x.strip().upper() for x in raw.split(",") if x.strip()]

    return {
        "type": type_val,
        "patch_id": patch_id,
        "new_deps": parse_ids(raw_deps),
        "resolved_deps": parse_ids(raw_resolved),
    }


# ─── YAML I/O ────────────────────────────────────────────────────────────────

def _yaml() -> _YAML:
    y = _YAML()
    y.preserve_quotes = True
    return y


def _flow_seq(items: list) -> CommentedSeq:
    quoted = [DoubleQuotedScalarString(i) if isinstance(i, str) else i for i in items]
    seq = CommentedSeq(quoted)
    seq.fa.set_flow_style()
    return seq


def load_patches(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = _yaml().load(fh)
    except FileNotFoundError:
        raise SystemExit(f"error: file not found: {path}")
    except Exception as exc:
        raise SystemExit(f"error: invalid YAML in {path}:\n{exc}")
    if not isinstance(data, Mapping) or not isinstance(data.get("patches"), list):
        raise SystemExit(f"error: {path} does not look like a valid patches.yaml")
    return data


def write_patches(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        _yaml().dump(data, fh)


# ─── ID helpers ───────────────────────────────────────────────────────────────

def all_ids(data: dict) -> set[str]:
    return {p["id"] for p in data["patches"] if isinstance(p, Mapping) and "id" in p}


def next_patch_id(data: dict) -> str:
    nums = [
        int(m.group(1))
        for p in data["patches"]
        if isinstance(p, Mapping) and (m := ID_RE.match(p.get("id", ""))) and not m.group(2)
    ]
    return f"PATCH-{(max(nums, default=0) + 1):03d}"


def next_fix_id(data: dict, base_id: str) -> str:
    prefix = base_id + "-F"
    fix_nums = [
        int(m.group(3))
        for p in data["patches"]
        if isinstance(p, Mapping) and (m := ID_RE.match(p.get("id", ""))) and p["id"].startswith(prefix)
    ]
    return f"{base_id}-F{(max(fix_nums, default=0) + 1):02d}"


# ─── Cycle / reachability check ──────────────────────────────────────────────

def build_graph(data: dict) -> dict[str, list[str]]:
    graph: dict[str, list[str]] = {}
    for p in data["patches"]:
        if isinstance(p, Mapping) and "id" in p:
            graph[p["id"]] = [d for d in (p.get("depends_on") or []) if isinstance(d, str)]
    return graph


def has_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return a cycle as a list of IDs, or None if the graph is acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    found: list[str] | None = None

    def visit(node: str, stack: list[str]) -> None:
        nonlocal found
        if found:
            return
        color[node] = GRAY
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                found = stack[stack.index(dep):] + [dep]
                return
            if color[dep] == WHITE:
                visit(dep, stack)
        stack.pop()
        color[node] = BLACK

    for node in list(graph):
        if color[node] == WHITE:
            visit(node, [])
        if found:
            break
    return found


def _reaches(graph: dict[str, list[str]], start: str, target: str) -> bool:
    """Return True if target is transitively reachable from start."""
    visited: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph.get(node, []))
    return False


def branch_to_version(branch: str) -> str:
    """'stable/2026.2-m3' → '2026.2'"""
    m = re.search(r"stable/([\d.]+)-", branch)
    if not m:
        raise SystemExit(f"error: cannot extract version from branch name {branch!r}")
    return m.group(1)


# ─── Validation logic ─────────────────────────────────────────────────────────

def validate_meta(meta: dict, data: dict, patch_id: str) -> list[str]:
    """Return a list of error strings; empty means valid."""
    errors: list[str] = []
    ids = all_ids(data)

    if meta["type"] not in VALID_TYPES:
        errors.append(f"type {meta['type']!r} is not one of {sorted(VALID_TYPES)}")
        return errors

    if meta["type"] in ("fix", "port", "drop", "upstream"):
        if not meta["patch_id"]:
            errors.append(f"type={meta['type']} requires a Patch-ID")
        elif meta["patch_id"] not in ids:
            errors.append(f"Patch-ID {meta['patch_id']!r} not found in patches.yaml")

    if meta["type"] == "patch" and meta["patch_id"]:
        errors.append("new patch must not supply a Patch-ID; leave it empty")

    for dep in meta["new_deps"]:
        if dep not in ids and dep != patch_id:
            errors.append(f"dependency {dep!r} not found in patches.yaml")

    # Port: all effective dependencies must be integrated or upstreamed
    if meta["type"] == "port" and meta["patch_id"] and not errors:
        entry = next(
            (p for p in data["patches"] if isinstance(p, Mapping) and p.get("id") == meta["patch_id"]),
            None,
        )
        if entry is not None:
            existing_deps = [d for d in (entry.get("depends_on") or []) if d not in meta["resolved_deps"]]
            new_deps_eff = [d for d in meta["new_deps"] if d not in existing_deps]
            all_deps = existing_deps + new_deps_eff
            status_map = {
                p["id"]: p.get("status", "pending")
                for p in data["patches"]
                if isinstance(p, Mapping) and "id" in p
            }
            for dep in all_deps:
                if status_map.get(dep, "pending") not in SATISFIED_STATUSES:
                    errors.append(f"port blocked: dependency {dep!r} is not yet integrated or upstreamed")

    # Drop: blocked while any non-dropped patch still depends on the target
    if meta["type"] == "drop" and meta["patch_id"] and not errors:
        target = meta["patch_id"]
        status_map = {
            p["id"]: p.get("status", "pending")
            for p in data["patches"]
            if isinstance(p, Mapping) and "id" in p
        }
        for p in data["patches"]:
            if not isinstance(p, Mapping):
                continue
            if p.get("id") == target:
                continue
            if target in (p.get("depends_on") or []) and status_map.get(p["id"]) != "dropped":
                errors.append(f"drop blocked: {p['id']} still depends on {target!r}")

    # Fix: extra deps must not transitively reach the base (prevents consolidation cycles)
    if meta["type"] == "fix" and meta["patch_id"] and meta["new_deps"] and not errors:
        graph = build_graph(data)
        base = meta["patch_id"]
        for extra_dep in meta["new_deps"]:
            if extra_dep == base or _reaches(graph, extra_dep, base):
                errors.append(
                    f"fix back-reference: extra dependency {extra_dep!r} transitively reaches "
                    f"base {base!r}; restructure instead"
                )
                break

    # Cycle check with hypothetical new/updated entry
    if meta["type"] in ("patch", "fix") and not errors:
        graph = build_graph(data)
        base_deps: list[str] = [meta["patch_id"]] if meta["type"] == "fix" and meta["patch_id"] else []
        graph[patch_id] = base_deps + [d for d in meta["new_deps"] if d not in base_deps]
        cycle = has_cycle(graph)
        if cycle:
            errors.append("dependency cycle: " + " → ".join(cycle))
    elif meta["type"] == "port" and meta["new_deps"] and not errors:
        graph = build_graph(data)
        existing = graph.get(meta["patch_id"], [])
        graph[meta["patch_id"]] = list(dict.fromkeys(existing + meta["new_deps"]))
        cycle = has_cycle(graph)
        if cycle:
            errors.append("dependency cycle: " + " → ".join(cycle))

    return errors


# ─── Commit collection ────────────────────────────────────────────────────────

def landed_commits(merge_sha: str) -> list[str]:
    """Return 8-char SHAs landed via this merge, method-independent."""
    try:
        result = subprocess.run(
            ["git", "log", "--no-merges", "--format=%H", f"{merge_sha}^1..{merge_sha}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"error: git log failed: {exc.stderr.strip()}")
    return [sha[:8] for sha in result.stdout.strip().splitlines() if sha.strip()]


# ─── Step summary ─────────────────────────────────────────────────────────────

def write_summary(lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text)


def render_preview(meta: dict, patch_id: str, errors: list[str]) -> None:
    ok = "✓"
    fail = "✗"
    lines = ["## Patch Metadata — Validation\n"]
    lines.append("| Field | Value | Status |")
    lines.append("|-------|-------|--------|")

    type_ok = ok if meta["type"] in VALID_TYPES else fail
    lines.append(f"| Type | `{meta['type']}` | {type_ok} |")

    pid_label = meta["patch_id"] or f"(new → `{patch_id}`)"
    pid_status = ok if not any("Patch-ID" in e or "must not supply" in e for e in errors) else fail
    lines.append(f"| Patch-ID | `{pid_label}` | {pid_status} |")

    lines.append(f"| Assigned ID | `{patch_id}` | — |")

    if meta["new_deps"]:
        dep_ok = ok if not any("dependency" in e and "not found" in e for e in errors) else fail
        lines.append(f"| New dependencies | `{', '.join(meta['new_deps'])}` | {dep_ok} |")

    if meta.get("resolved_deps"):
        lines.append(f"| Resolved dependencies | `{', '.join(meta['resolved_deps'])}` | — |")

    lines.append("")
    if errors:
        lines.append(f"### {fail} Validation failed\n")
        for e in errors:
            lines.append(f"- {e}")
    else:
        lines.append(f"### {ok} All checks passed — entry will be written to `patches.yaml`")

    write_summary(lines)


# ─── Subcommands ─────────────────────────────────────────────────────────────

def cmd_validate(patches_path: str, branch: str) -> int:
    body = os.environ.get("PR_BODY", "")

    try:
        meta = parse_metadata(body)
    except ParseError as exc:
        write_summary([f"## Patch Metadata — Validation\n\n{exc}"])
        print(f"error: {exc}", file=sys.stderr)
        return 1

    data = load_patches(patches_path)

    if meta["type"] == "patch":
        patch_id = next_patch_id(data)
    elif meta["type"] == "fix" and meta["patch_id"]:
        patch_id = next_fix_id(data, meta["patch_id"])
    else:
        patch_id = meta["patch_id"] or "(unknown)"

    errors = validate_meta(meta, data, patch_id)
    render_preview(meta, patch_id, errors)

    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_apply(
    patches_path: str,
    branch: str,
    merge_sha: str,
    pr_number: str,
    pr_title: str,
) -> int:
    body = os.environ.get("PR_BODY", "")

    try:
        meta = parse_metadata(body)
    except ParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    data = load_patches(patches_path)

    if meta["type"] == "patch":
        patch_id = next_patch_id(data)
    elif meta["type"] == "fix":
        if not meta["patch_id"]:
            print("error: fix type requires a Patch-ID", file=sys.stderr)
            return 1
        patch_id = next_fix_id(data, meta["patch_id"])
    else:
        patch_id = meta["patch_id"] or ""

    errors = validate_meta(meta, data, patch_id)
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        print("error: refusing to write patches.yaml", file=sys.stderr)
        return 1

    commits = landed_commits(merge_sha)

    if meta["type"] in ("patch", "fix"):
        base_deps: list[str] = [meta["patch_id"]] if meta["type"] == "fix" else []
        all_new_deps = base_deps + [d for d in meta["new_deps"] if d not in base_deps]
        entry = CommentedMap({
            "id": patch_id,
            "title": pr_title,
            "depends_on": _flow_seq(all_new_deps),
            "status": "integrated",
            "commits": _flow_seq(commits),
            "pr": int(pr_number),
        })
        data["patches"].append(entry)

    elif meta["type"] == "port":
        for p in data["patches"]:
            if not isinstance(p, Mapping) or p.get("id") != patch_id:
                continue
            # Strip resolved deps from depends_on
            existing_deps = list(p.get("depends_on") or [])
            for r in meta["resolved_deps"]:
                if r in existing_deps:
                    existing_deps.remove(r)
            # Add new deps
            for d in meta["new_deps"]:
                if d not in existing_deps:
                    existing_deps.append(d)
            p["depends_on"] = _flow_seq(existing_deps)
            p["status"] = "integrated"
            p["commits"] = _flow_seq(commits)
            p["pr"] = int(pr_number)
            break

    elif meta["type"] == "drop":
        for p in data["patches"]:
            if isinstance(p, Mapping) and p.get("id") == patch_id:
                p["status"] = "dropped"
                p["commits"] = _flow_seq(commits)
                p["pr"] = int(pr_number)
                break

    elif meta["type"] == "upstream":
        for p in data["patches"]:
            if isinstance(p, Mapping) and p.get("id") == patch_id:
                p["status"] = "upstreamed"
                p["commits"] = _flow_seq(commits)
                p["pr"] = int(pr_number)
                break

    write_patches(patches_path, data)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(f"patch_id={patch_id}\n")
            fh.write(f"patch_type={meta['type']}\n")

    print(f"ok: patches.yaml updated — {patch_id} {meta['type']} (PR #{pr_number})")
    return 0


# ─── Entry point ──────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    if len(argv) < 2:
        _usage(argv[0])
        return 2

    cmd = argv[1]
    if cmd == "validate":
        if len(argv) < 4:
            _usage(argv[0])
            return 2
        return cmd_validate(argv[2], argv[3])
    if cmd == "apply":
        if len(argv) < 7:
            _usage(argv[0])
            return 2
        return cmd_apply(argv[2], argv[3], argv[4], argv[5], " ".join(argv[6:]))
    print(f"error: unknown subcommand {cmd!r}", file=sys.stderr)
    return 2


def _usage(prog: str) -> None:
    print(f"usage: {prog} validate <patches.yaml> <branch>", file=sys.stderr)
    print(f"       {prog} apply   <patches.yaml> <branch> <merge_sha> <pr_number> <pr_title>", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
