"""Unit tests for scripts/check_consistency.py"""
from __future__ import annotations

import sys
import os
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from check_consistency import main

# ─── Fixtures ────────────────────────────────────────────────────────────────

DATA_OK = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "title": "CI", "depends_on": [], "status": "integrated", "commits": ["a1b2c3d4"]},
        {"id": "PATCH-002", "title": "Reqs", "depends_on": [], "status": "integrated", "commits": ["b2c3d4e5"]},
        {"id": "PATCH-003", "title": "Zone", "depends_on": [], "status": "pending"},
    ],
}

DATA_WITH_DROPPED = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "status": "integrated", "commits": ["a1b2c3d4"]},
        {"id": "PATCH-002", "status": "dropped", "commits": ["dd000001"], "pr": 5},
    ],
}

DATA_WITH_UPSTREAMED = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "status": "integrated", "commits": ["a1b2c3d4"]},
        {"id": "PATCH-002", "status": "upstreamed", "commits": ["uu000001"], "pr": 6},
    ],
}

DATA_WITH_MIGRATIONS = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "status": "integrated", "commits": ["a1b2c3d4"], "migrations": ["m1m2m3m4"]},
    ],
}

DATA_EMPTY_INTEGRATED = {
    "schema_version": 1,
    "patches": [
        {"id": "PATCH-001", "title": "CI", "depends_on": [], "status": "pending"},
    ],
}

ARGV = ["check_consistency.py", "patches.yaml", "stable/2026.2", "stable/2026.2-m3"]


def _run(fork_delta: set, pr_commits: set, data: dict) -> int:
    with patch("check_consistency.load_patches", return_value=data), \
         patch("check_consistency._git_log", side_effect=[fork_delta, pr_commits]):
        return main(ARGV)


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestConsistencyCheck:
    def test_clean_state(self):
        fork_delta = {"a1b2c3d4", "b2c3d4e5", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 0

    def test_unaccounted_commit(self):
        fork_delta = {"a1b2c3d4", "b2c3d4e5", "deadbeef", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 1

    def test_missing_commit_from_fork(self):
        # b2c3d4e5 is integrated in patches.yaml but absent from fork
        fork_delta = {"a1b2c3d4", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 1

    def test_both_errors(self):
        fork_delta = {"a1b2c3d4", "deadbeef", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 1

    def test_pr_commits_excluded(self):
        # c3d4e5f6 is the current PR commit — not in patches.yaml yet, should not cause error
        fork_delta = {"a1b2c3d4", "b2c3d4e5", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 0

    def test_migrations_counted_as_known(self):
        fork_delta = {"a1b2c3d4", "m1m2m3m4", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_WITH_MIGRATIONS) == 0

    def test_migration_missing_from_fork(self):
        fork_delta = {"a1b2c3d4", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_WITH_MIGRATIONS) == 1

    def test_no_integrated_patches_passes(self):
        # Nothing integrated yet — fork should only contain PR commits
        fork_delta = {"c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_EMPTY_INTEGRATED) == 0

    def test_pending_patches_ignored(self):
        # pending patches don't contribute to known commits
        fork_delta = {"a1b2c3d4", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_OK) == 1  # b2c3d4e5 missing

    def test_dropped_commits_counted(self):
        # drop PR commits (empty or revert) must be in known_commits
        fork_delta = {"a1b2c3d4", "dd000001", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_WITH_DROPPED) == 0

    def test_dropped_commit_missing_from_fork(self):
        fork_delta = {"a1b2c3d4", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_WITH_DROPPED) == 1

    def test_upstreamed_commits_counted(self):
        fork_delta = {"a1b2c3d4", "uu000001", "c3d4e5f6"}
        pr_commits = {"c3d4e5f6"}
        assert _run(fork_delta, pr_commits, DATA_WITH_UPSTREAMED) == 0

    def test_wrong_arg_count(self):
        with patch("check_consistency.load_patches", return_value=DATA_OK):
            assert main(["check_consistency.py", "patches.yaml"]) == 2
