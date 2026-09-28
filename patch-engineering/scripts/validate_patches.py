#!/usr/bin/env python3
"""Validate patches.yaml — the downstream patch inventory.

Checks (structural, deterministic):
  1. File is valid YAML.
  2. schema_version is a positive integer.
  3. Every patch has: id, title, depends_on, upstream, releases.
  4. Patch IDs match the naming convention and are unique.
  5. depends_on references existing patch IDs.
  6. No patch depends on itself.
  7. The dependency graph is acyclic.
  8. upstream.status uses only allowed values.
  9. Every release status uses only allowed values.
 10. (best effort) Alembic revisions listed under a release exist as files
     somewhere under a migrations directory, if one is found.

Exit code 0 = all checks pass, 1 = validation errors, 2 = usage/parse error.

Usage:
    python3 scripts/validate_patches.py [path/to/patches.yaml]
"""
from __future__ import annotations

import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    raise SystemExit(2)

ID_RE = re.compile(r"^PATCH-\d{3}(-F\d{2})?$")
UPSTREAM_STATUS = {"downstream-only", "upstreamed"}
RELEASE_STATUS = {"pending", "integrated", "dropped"}


class Validator:
    def __init__(self, path: str):
        self.path = path
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def run(self) -> int:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except FileNotFoundError:
            print(f"error: file not found: {self.path}", file=sys.stderr)
            return 2
        except yaml.YAMLError as exc:
            print(f"error: invalid YAML in {self.path}:\n{exc}", file=sys.stderr)
            return 2

        if not isinstance(data, dict):
            self.err("top-level document must be a mapping")
            return self._report()

        self._check_schema_version(data)
        patches = data.get("patches")
        if not isinstance(patches, list):
            self.err("'patches' must be a list")
            return self._report()

        ids = self._check_entries(patches)
        self._check_dependencies(patches, ids)
        self._check_migrations(patches)

        return self._report()

    def _check_schema_version(self, data: dict) -> None:
        sv = data.get("schema_version")
        if not isinstance(sv, int) or isinstance(sv, bool) or sv < 1:
            self.err(f"schema_version must be a positive integer, got {sv!r}")

    def _check_entries(self, patches: list) -> set[str]:
        seen: set[str] = set()
        for i, p in enumerate(patches):
            where = f"patches[{i}]"
            if not isinstance(p, dict):
                self.err(f"{where}: entry must be a mapping")
                continue

            pid = p.get("id")
            if not isinstance(pid, str) or not ID_RE.match(pid):
                self.err(f"{where}: invalid id {pid!r} "
                         f"(expected PATCH-NNN or PATCH-NNN-FNN)")
            else:
                where = pid
                if pid in seen:
                    self.err(f"duplicate patch id: {pid}")
                seen.add(pid)

            if not p.get("title"):
                self.err(f"{where}: missing title")

            if not isinstance(p.get("depends_on"), list):
                self.err(f"{where}: depends_on must be a list")

            self._check_upstream(where, p.get("upstream"))
            self._check_releases(where, p.get("releases"))

        return seen

    def _check_upstream(self, where: str, upstream) -> None:
        if not isinstance(upstream, dict):
            self.err(f"{where}: upstream must be a mapping")
            return
        status = upstream.get("status")
        if status not in UPSTREAM_STATUS:
            self.err(f"{where}: upstream.status {status!r} not in "
                     f"{sorted(UPSTREAM_STATUS)}")

    def _check_releases(self, where: str, releases) -> None:
        if not isinstance(releases, dict) or not releases:
            self.err(f"{where}: releases must be a non-empty mapping")
            return
        for ver, block in releases.items():
            rwhere = f"{where}.releases[{ver!r}]"
            if not isinstance(block, dict):
                self.err(f"{rwhere}: must be a mapping")
                continue
            status = block.get("status")
            if status not in RELEASE_STATUS:
                self.err(f"{rwhere}: status {status!r} not in "
                         f"{sorted(RELEASE_STATUS)}")
            if "commits" in block and not isinstance(block["commits"], list):
                self.err(f"{rwhere}: commits must be a list")
            if "migrations" in block and not isinstance(block["migrations"], list):
                self.err(f"{rwhere}: migrations must be a list")

    def _check_dependencies(self, patches: list, ids: set[str]) -> None:
        graph: dict[str, list[str]] = {}
        for p in patches:
            if not isinstance(p, dict):
                continue
            pid = p.get("id")
            deps = p.get("depends_on")
            if not isinstance(pid, str) or not isinstance(deps, list):
                continue
            graph[pid] = []
            for dep in deps:
                if dep == pid:
                    self.err(f"{pid}: depends on itself")
                    continue
                if dep not in ids:
                    self.err(f"{pid}: depends_on unknown id {dep!r}")
                    continue
                graph[pid].append(dep)

        self._check_acyclic(graph)

    def _check_acyclic(self, graph: dict[str, list[str]]) -> None:
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {n: WHITE for n in graph}

        def visit(node: str, stack: list[str]) -> None:
            color[node] = GRAY
            stack.append(node)
            for dep in graph.get(node, []):
                if color.get(dep) == GRAY:
                    cycle = stack[stack.index(dep):] + [dep]
                    self.err("dependency cycle: " + " -> ".join(cycle))
                elif color.get(dep) == WHITE:
                    visit(dep, stack)
            stack.pop()
            color[node] = BLACK

        for node in graph:
            if color[node] == WHITE:
                visit(node, [])

    def _check_migrations(self, patches: list) -> None:
        base = os.path.dirname(os.path.abspath(self.path))
        mig_dirs = [
            os.path.join(dp, d)
            for dp, dirs, _ in os.walk(base)
            for d in dirs
            if d == "versions" and "alembic" in dp.replace(os.sep, "/")
        ]
        if not mig_dirs:
            # No migration tree in this checkout — cannot verify, skip.
            return

        known: set[str] = set()
        for d in mig_dirs:
            for fn in os.listdir(d):
                if fn.endswith(".py"):
                    known.add(fn[:-3])

        for p in patches:
            if not isinstance(p, dict):
                continue
            pid = p.get("id", "?")
            for ver, block in (p.get("releases") or {}).items():
                if not isinstance(block, dict):
                    continue
                for rev in block.get("migrations", []) or []:
                    if not any(str(rev) in name for name in known):
                        self.warn(f"{pid}.releases[{ver!r}]: migration "
                                  f"{rev!r} not found under any alembic/versions/")

    def _report(self) -> int:
        for w in self.warnings:
            print(f"warning: {w}", file=sys.stderr)
        if self.errors:
            for e in self.errors:
                print(f"error: {e}", file=sys.stderr)
            print(f"\n{len(self.errors)} error(s) in {self.path}", file=sys.stderr)
            return 1
        print(f"ok: {self.path} is valid")
        return 0


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else "patches.yaml"
    return Validator(path).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
