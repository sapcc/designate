"""Unit tests for scripts/patch_pr.py"""
from __future__ import annotations

import io
import sys
import os
from unittest.mock import patch as mock_patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from patch_pr import (
    ParseError,
    parse_metadata,
    validate_meta,
    next_patch_id,
    next_fix_id,
    has_cycle,
    build_graph,
    branch_to_version,
    _flow_seq,
    _yaml,
    cmd_apply,
    load_patches,
    write_patches,
)

# ─── Fixtures ────────────────────────────────────────────────────────────────

DATA = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "title": "CI", "depends_on": [], "status": "integrated", "commits": ["a1b2c3d4"], "pr": 1},
        {"id": "PATCH-002", "title": "Reqs", "depends_on": ["PATCH-001"], "status": "integrated", "commits": ["b2c3d4e5"], "pr": 2},
        {"id": "PATCH-003", "title": "Zone Import", "depends_on": [], "status": "pending"},
        {"id": "PATCH-004", "title": "SOA Fields", "depends_on": ["PATCH-003"], "status": "pending"},
        {"id": "PATCH-005", "title": "Zone Serial", "depends_on": ["PATCH-002"], "status": "pending"},
        {"id": "PATCH-001-F01", "title": "Fix CI", "depends_on": ["PATCH-001"], "status": "integrated", "commits": ["c3d4e5f6"], "pr": 3},
    ],
}

BODY_PATCH = """\
## Patch Metadata

- **Type:** patch
- **Patch-ID (fix/port/drop only — existing ID e.g. PATCH-003; new patch: leave empty):**
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):** PATCH-003
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):**

## Purpose
"""

BODY_FIX = """\
## Patch Metadata

- **Type:** fix
- **Patch-ID (fix/port/drop only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-002
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):**
"""

BODY_PORT = """\
## Patch Metadata

- **Type:** port
- **Patch-ID (fix/port/drop only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-005
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):**
"""

BODY_PORT_WITH_RESOLVED = """\
## Patch Metadata

- **Type:** port
- **Patch-ID (fix/port/drop only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-004
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):** PATCH-003
"""

BODY_DROP = """\
## Patch Metadata

- **Type:** drop
- **Patch-ID (fix/port/drop only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-004
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):**
"""


BODY_UPSTREAM = """\
## Patch Metadata

- **Type:** upstream
- **Patch-ID (fix/port/drop/upstream only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-004
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale deps to drop):**
"""


# ─── parse_metadata ───────────────────────────────────────────────────────────

class TestParseMetadata:
    def test_patch_type(self):
        m = parse_metadata(BODY_PATCH)
        assert m["type"] == "patch"
        assert m["patch_id"] is None
        assert m["new_deps"] == ["PATCH-003"]
        assert m["resolved_deps"] == []

    def test_fix_type(self):
        m = parse_metadata(BODY_FIX)
        assert m["type"] == "fix"
        assert m["patch_id"] == "PATCH-002"
        assert m["resolved_deps"] == []

    def test_port_type(self):
        m = parse_metadata(BODY_PORT)
        assert m["type"] == "port"
        assert m["patch_id"] == "PATCH-005"

    def test_port_with_resolved_dep(self):
        m = parse_metadata(BODY_PORT_WITH_RESOLVED)
        assert m["type"] == "port"
        assert m["patch_id"] == "PATCH-004"
        assert m["resolved_deps"] == ["PATCH-003"]

    def test_drop_type(self):
        m = parse_metadata(BODY_DROP)
        assert m["type"] == "drop"
        assert m["patch_id"] == "PATCH-004"

    def test_upstream_type(self):
        m = parse_metadata(BODY_UPSTREAM)
        assert m["type"] == "upstream"
        assert m["patch_id"] == "PATCH-004"

    def test_missing_section_raises(self):
        with pytest.raises(ParseError, match="not found"):
            parse_metadata("## Something Else\n- **Type:** patch")

    def test_missing_type_raises(self):
        with pytest.raises(ParseError, match="Type field"):
            parse_metadata("## Patch Metadata\n- **Ticket/Issue:** #1")

    def test_invalid_patch_id_raises(self):
        body = "## Patch Metadata\n- **Type:** fix\n- **Patch-ID:** NOT_VALID\n"
        with pytest.raises(ParseError, match="Invalid Patch-ID"):
            parse_metadata(body)

    def test_whitespace_normalization(self):
        body = "## Patch Metadata\n- **Type:**  PORT  \n- **Patch-ID:**  patch-003  \n"
        m = parse_metadata(body)
        assert m["type"] == "port"
        assert m["patch_id"] == "PATCH-003"

    def test_placeholder_type_rejected(self):
        body = "## Patch Metadata\n- **Type:** patch | fix | port | drop\n"
        m = parse_metadata(body)
        assert m["type"] == "patch | fix | port | drop"

    def test_multiple_deps(self):
        body = "## Patch Metadata\n- **Type:** patch\n- **New introduced dependency:** PATCH-001, PATCH-002\n"
        m = parse_metadata(body)
        assert m["new_deps"] == ["PATCH-001", "PATCH-002"]

    def test_multiple_resolved_deps(self):
        body = "## Patch Metadata\n- **Type:** port\n- **Patch-ID:** PATCH-005\n- **Resolved dependency:** PATCH-001, PATCH-002\n"
        m = parse_metadata(body)
        assert m["resolved_deps"] == ["PATCH-001", "PATCH-002"]


# ─── ID helpers ───────────────────────────────────────────────────────────────

class TestIdHelpers:
    def test_next_patch_id(self):
        assert next_patch_id(DATA) == "PATCH-006"

    def test_next_patch_id_empty(self):
        assert next_patch_id({"schema_version": 1, "patches": []}) == "PATCH-001"

    def test_next_fix_id_existing(self):
        assert next_fix_id(DATA, "PATCH-001") == "PATCH-001-F02"

    def test_next_fix_id_none_existing(self):
        assert next_fix_id(DATA, "PATCH-003") == "PATCH-003-F01"


# ─── cycle check ─────────────────────────────────────────────────────────────

class TestCycleCheck:
    def test_no_cycle(self):
        graph = {"A": ["B"], "B": ["C"], "C": []}
        assert has_cycle(graph) is None

    def test_direct_cycle(self):
        graph = {"A": ["B"], "B": ["A"]}
        assert has_cycle(graph) is not None

    def test_indirect_cycle(self):
        graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
        assert has_cycle(graph) is not None

    def test_self_cycle(self):
        graph = {"A": ["A"]}
        assert has_cycle(graph) is not None


# ─── validate_meta ────────────────────────────────────────────────────────────

class TestValidateMeta:
    def test_valid_new_patch(self):
        meta = {"type": "patch", "patch_id": None, "new_deps": ["PATCH-003"], "resolved_deps": []}
        assert validate_meta(meta, DATA, "PATCH-006") == []

    def test_patch_with_existing_id_fails(self):
        meta = {"type": "patch", "patch_id": "PATCH-001", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-006")
        assert any("must not supply" in e for e in errors)

    def test_fix_missing_patch_id_fails(self):
        meta = {"type": "fix", "patch_id": None, "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-001-F02")
        assert any("requires a Patch-ID" in e for e in errors)

    def test_fix_nonexistent_base_fails(self):
        meta = {"type": "fix", "patch_id": "PATCH-999", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-999-F01")
        assert any("PATCH-999" in e for e in errors)

    def test_unknown_dep_fails(self):
        meta = {"type": "patch", "patch_id": None, "new_deps": ["PATCH-999"], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-006")
        assert any("PATCH-999" in e for e in errors)

    def test_valid_drop(self):
        meta = {"type": "drop", "patch_id": "PATCH-004", "new_deps": [], "resolved_deps": []}
        assert validate_meta(meta, DATA, "PATCH-004") == []

    def test_drop_blocked_by_dependents(self):
        meta = {"type": "drop", "patch_id": "PATCH-003", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-003")
        assert any("PATCH-004" in e and "depends on" in e for e in errors)

    def test_drop_nonexistent_id_fails(self):
        meta = {"type": "drop", "patch_id": "PATCH-999", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-999")
        assert any("PATCH-999" in e for e in errors)

    def test_valid_upstream(self):
        meta = {"type": "upstream", "patch_id": "PATCH-004", "new_deps": [], "resolved_deps": []}
        assert validate_meta(meta, DATA, "PATCH-004") == []

    def test_upstream_nonexistent_id_fails(self):
        meta = {"type": "upstream", "patch_id": "PATCH-999", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-999")
        assert any("PATCH-999" in e for e in errors)

    def test_port_allowed_integrated_deps(self):
        meta = {"type": "port", "patch_id": "PATCH-005", "new_deps": [], "resolved_deps": []}
        assert validate_meta(meta, DATA, "PATCH-005") == []

    def test_port_blocked_unintegrated_dep(self):
        meta = {"type": "port", "patch_id": "PATCH-004", "new_deps": [], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-004")
        assert any("port blocked" in e and "PATCH-003" in e for e in errors)

    def test_port_resolved_dep_unblocks(self):
        meta = {"type": "port", "patch_id": "PATCH-004", "new_deps": [], "resolved_deps": ["PATCH-003"]}
        assert validate_meta(meta, DATA, "PATCH-004") == []

    def test_fix_back_reference_rejected(self):
        # fix PATCH-001, extra dep PATCH-002 — PATCH-002 depends on PATCH-001 → back-reference
        meta = {"type": "fix", "patch_id": "PATCH-001", "new_deps": ["PATCH-002"], "resolved_deps": []}
        errors = validate_meta(meta, DATA, "PATCH-001-F02")
        assert any("back-reference" in e for e in errors)

    def test_fix_extra_dep_ok(self):
        # fix PATCH-002, extra dep PATCH-003 — PATCH-003 has no path to PATCH-002 → allowed
        meta = {"type": "fix", "patch_id": "PATCH-002", "new_deps": ["PATCH-003"], "resolved_deps": []}
        assert validate_meta(meta, DATA, "PATCH-002-F01") == []

    def test_cycle_via_port_fails(self):
        data = {
            "schema_version": 1,
            "patches": [
                {"id": "PATCH-001", "title": "A", "depends_on": ["PATCH-002"], "status": "integrated"},
                {"id": "PATCH-002", "title": "B", "depends_on": [], "status": "integrated"},
            ],
        }
        meta = {"type": "port", "patch_id": "PATCH-002", "new_deps": ["PATCH-001"], "resolved_deps": []}
        errors = validate_meta(meta, data, "PATCH-002")
        assert any("cycle" in e.lower() for e in errors)


# ─── branch_to_version ───────────────────────────────────────────────────────

class TestBranchToVersion:
    def test_normal(self):
        assert branch_to_version("stable/2026.2-m3") == "2026.2"

    def test_other_cycle(self):
        assert branch_to_version("stable/2024.2-m3") == "2024.2"


# ─── commit SHA quoting ───────────────────────────────────────────────────────

class TestCommitShaQuoting:
    def test_ambiguous_sha_written_as_string(self):
        # SHAs like 4984e802 match YAML 1.1 float pattern — must be quoted
        seq = _flow_seq(["4984e802", "deadbeef"])
        buf = io.StringIO()
        _yaml().dump({"commits": seq}, buf)
        raw = buf.getvalue()
        assert '"4984e802"' in raw or "'4984e802'" in raw

    def test_roundtrip_preserves_sha_as_string(self):
        seq = _flow_seq(["4984e802", "1e100aaa"])
        buf = io.StringIO()
        _yaml().dump({"commits": seq}, buf)
        buf.seek(0)
        data = _yaml().load(buf)
        for sha in data["commits"]:
            assert isinstance(sha, str), f"SHA {sha!r} was parsed as {type(sha).__name__}, expected str"


# ─── cmd_apply — drop / upstream commit recording ────────────────────────────

BODY_DROP_APPLY = """\
## Patch Metadata

- **Type:** drop
- **Patch-ID (fix/port/drop/upstream only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-004
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale inherited deps to drop):**
"""

BODY_UPSTREAM_APPLY = """\
## Patch Metadata

- **Type:** upstream
- **Patch-ID (fix/port/drop/upstream only — existing ID e.g. PATCH-003; new patch: leave empty):** PATCH-004
- **New introduced dependency (optional, comma-separated, e.g. PATCH-003):**
- **Resolved dependency (fix/port only — optional, comma-separated — stale inherited deps to drop):**
"""


def _apply(body: str, tmp_path, commits: list[str] | None = None):
    patches_file = tmp_path / "patches.yaml"
    write_patches(str(patches_file), DATA)
    with mock_patch("patch_pr.landed_commits", return_value=commits or ["aa000001"]), \
         mock_patch.dict(os.environ, {"PR_BODY": body}):
        rc = cmd_apply(str(patches_file), "stable/2026.2-m3", "mergesha", "42", "Test PR")
    return rc, load_patches(str(patches_file))


class TestCmdApplyDropUpstream:
    def test_drop_records_commits_and_pr(self, tmp_path):
        rc, data = _apply(BODY_DROP_APPLY, tmp_path, commits=["dd000001"])
        assert rc == 0
        entry = next(p for p in data["patches"] if p["id"] == "PATCH-004")
        assert entry["status"] == "dropped"
        assert list(entry["commits"]) == ["dd000001"]
        assert entry["pr"] == 42

    def test_drop_empty_commit_recorded(self, tmp_path):
        rc, data = _apply(BODY_DROP_APPLY, tmp_path, commits=["ee000002"])
        assert rc == 0
        entry = next(p for p in data["patches"] if p["id"] == "PATCH-004")
        assert entry["status"] == "dropped"
        assert list(entry["commits"]) == ["ee000002"]

    def test_upstream_records_commits_and_pr(self, tmp_path):
        rc, data = _apply(BODY_UPSTREAM_APPLY, tmp_path, commits=["uu000001"])
        assert rc == 0
        entry = next(p for p in data["patches"] if p["id"] == "PATCH-004")
        assert entry["status"] == "upstreamed"
        assert list(entry["commits"]) == ["uu000001"]
        assert entry["pr"] == 42
