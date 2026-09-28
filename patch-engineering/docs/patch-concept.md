# Downstream Patch Engineering — Concepts

## Branch Model

```text
upstream/stable/<ver>
      │
      ▼
origin/stable/<ver>           # unmodified mirror of upstream
      │
      └── origin/stable/<ver>-m3   # downstream integration branch
```

Current cycle:

```text
upstream/stable/2026.2
      │
      ▼
origin/stable/2026.2
      │
      └── origin/stable/2026.2-m3
```

Rules:

- `origin/stable/<ver>` mirrors upstream exclusively — no downstream commits.
- `stable/<ver>-m3` is a protected integration branch.
- All changes reach the integration branch through pull requests only.
- Exception: a one-time `[SETUP]` commit directly on the new integration branch adds `patches.yaml` and the PR template at the start of each cycle.
- Published integration branches are never rebased or force-pushed.
- A new integration branch is created fresh from the corresponding upstream branch.
- Downstream patches are ported to the new integration branch in a controlled, ordered fashion.

---

## Patch Concept

A patch is a logically coherent downstream change with a stable identifier:

```text
PATCH-001: CI / Concourse Setup
PATCH-004: SOA fields editable via API
PATCH-023: Pools RBAC (SOV/IAAS)
```

The patch ID is stable across releases even when commit SHAs and implementation change:

```text
PATCH-001
├── 2024.2 commit: a111111
└── 2026.2 commit: e555555
```

The commit SHA is a technical pointer. The patch ID is the logical identity.

### Same patch or new patch?

| Situation | Action |
|---|---|
| Fix in a still-open PR | Additional commit in the same PR |
| Fix for an already-merged patch | Separate fix PR, e.g. `PATCH-001-F01` |
| Upstream fully replaces patch | Do not port; mark as `dropped` |
| Upstream partially replaces patch | Port remaining downstream portion; rework if needed |
| Architecture and purpose change substantially | New patch ID |
| Patch no longer needed | Do not port; revert in current release if required |

---

## Patch Dependencies

Patches form a directed acyclic graph (DAG).

```text
PATCH-001 ─────► PATCH-002
    │
    └──────────► PATCH-005
                    ▲
                    │
PATCH-004 ──────────┘
```

- `PATCH-002` requires `PATCH-001`.
- `PATCH-005` requires both `PATCH-001` and `PATCH-004`.
- `PATCH-001` and `PATCH-004` are independent.

A dependent patch is only ported after all its prerequisites are integrated in the target branch. A patch whose `depends_on` entries are not yet integrated is implicitly blocked — no separate status field is needed.

### Fix with an extra dependency

```text
PATCH-001 → PATCH-002 → PATCH-001-F01
```

`PATCH-001-F01` fixes `PATCH-001` logically but requires `PATCH-002` technically.

```yaml
id: PATCH-001-F01
depends_on: [PATCH-001, PATCH-002]
```

This fix must not be consolidated into `PATCH-001` when doing so would create a cycle:

```text
PATCH-001' → PATCH-002 → PATCH-001'
```

Options:

1. Keep the fix as a separate patch behind `PATCH-002`.
2. Extract shared base functionality into an independent patch.
3. Consciously merge inseparable patches into a single unit.

---

## Commit and PR Strategy

### Work-in-progress commits vs. portable units

Intermediate commits are allowed during a PR:

```text
Implement zone serial API
Fix tests
Address review
Fix edge case in serial validation
```

When the entire PR represents a single logical change, merge it via **squash and merge**:

```text
PATCH-005: add zone serial API
```

Not every PR must be squashed. Meaningful atomic commits may be preserved:

```text
PATCH-005A: Add audit event model
PATCH-005B: Add audit persistence
PATCH-005C: Integrate authentication events
```

Sub-commits should only be preserved when they are genuinely:

- portable independently,
- removable independently,
- representing a separate dependency,
- testable in isolation, or
- submittable upstream separately.

**Guiding rule:** squash progress commits, preserve independent changes.

### Separate PRs over force-push

When individual parts may need to be cherry-picked independently later, separate PRs are the cleanest approach:

```text
PR 1 → PATCH-005A
PR 2 → PATCH-005B, depends_on: PATCH-005A
PR 3 → PATCH-005C, depends_on: PATCH-005A
```

Each PR may be squashed internally. On the integration branch the portable units remain as individual commits.

---

## Patch Manifest (`patches.yaml`)

`patches.yaml` is the authoritative inventory of downstream patches. It answers questions that Git alone cannot reliably answer:

- Which commits belong to the same logical change?
- What dependencies exist between patches?
- What must be ported to the next release?
- What has been dropped or taken upstream?
- Which Alembic revisions belong to a patch?

The file lives in the repository root. It is updated in the same PR whenever a patch is created, ported, or dropped. Status changes are always a side effect of a real code PR — never a standalone commit.

### Example

```yaml
schema_version: 1

patches:
  - id: PATCH-001
    title: Authentication foundation
    depends_on: []
    upstream:
      status: downstream-only
    releases:
      "2024.2":
        status: integrated
        commits: [a111111]
        migrations: [d200]
      "2026.2":
        status: pending
        commits: []

  - id: PATCH-001-F01
    title: Correct expired-token handling
    depends_on: [PATCH-001, PATCH-002]
    upstream:
      status: downstream-only
    releases:
      "2024.2":
        status: integrated
        commits: [c333333]
      "2026.2":
        status: pending
        commits: []
```

### Upstream status

| Value | Meaning |
|---|---|
| `downstream-only` | No upstream equivalent; patch must always be ported. Use `.note` to document known overlap or caveats from the last investigation. |
| `upstreamed` | Upstream contains an equivalent change; patch can be dropped. |

`upstream.status` is evaluated at migration time. A patch that was partially covered by upstream and reworked to keep only the remaining portion is still `downstream-only` — whatever is maintained downstream is by definition downstream-only.

### Release status

| Value | Meaning |
|---|---|
| `pending` | Not yet ported to this release |
| `integrated` | Merged into the integration branch for this release |
| `dropped` | Intentionally not ported to this release |

A patch with `upstream.status: upstreamed` and `releases.<ver>.status: dropped` receives no new release block in future cycles — it is permanently closed. A `dropped` patch with `upstream.status: downstream-only` should be re-evaluated in the next cycle.

### When to update

Update `patches.yaml` in the same PR when:

- a patch or fix is created,
- a dependency is added or removed,
- a patch is ported to a new release (update `status` and `commits`),
- a patch is dropped,
- upstream takes over a patch,
- an Alembic migration is added,
- a new release block is introduced.

---

## PR Template

File: `.github/pull_request_template.md`

```markdown
<!-- Title format:
     [PATCH-001] CI/Concourse Setup              (new patch or port)
     [PATCH-011] Drop: upstreamed in 2026.2      (removal)
     [PATCH-023] Rework: adapt to threading      (rework)
     [PATCH-005-F01] Fix serial overflow         (fix)
     [SETUP] Add PR template and patches manifest (infrastructure)
-->

## Patch Metadata

- **Patch-ID:** PATCH-XXX
- **Type:** patch | fix | removal | rework | setup
- **Ticket/Issue:**

## Purpose

<!-- Problem and rationale for this downstream change -->

## Technical change

<!-- Implementation details, interfaces, and data changes -->

## Checklist

- [ ] Patch is a clearly scoped, independent unit.
- [ ] `depends_on` entries are listed and already integrated.
- [ ] Existing tests pass; new tests added or absence justified.
- [ ] `patches.yaml` updated.
- [ ] Breaking changes and security impact documented.

**If schema change:**
- [ ] Alembic revision referenced in `patches.yaml`.
- [ ] Upgrade from previous release tested.
```

### PR types

| Type | When |
|---|---|
| `patch` | New patch introduced or ported to a new release |
| `fix` | `-F01` fix for an already-integrated patch |
| `removal` | Patch dropped or `upstream.status` updated — `patches.yaml` only, no code |
| `rework` | Same patch ID, substantially new implementation |
| `setup` | Infrastructure changes unrelated to a specific patch (PR template, `patches.yaml` schema, CI) |

---

## CI Checks

Two GitHub Actions enforce the conventions on every pull request:

| Workflow | Script | Verifies |
|---|---|---|
| `.github/workflows/pr-title.yml` | `scripts/check_pr_title.py` | PR title matches `[PATCH-NNN] …`, `[PATCH-NNN-FNN] …`, or `[SETUP] …` |
| `.github/workflows/validate-patches.yml` | `scripts/validate_patches.py` | Manifest structure and dependency graph (see below) |

`validate_patches.py` checks:

1. YAML is valid.
2. `schema_version` is a positive integer.
3. Patch IDs match the naming convention and are unique.
4. `depends_on` references existing IDs.
5. No patch depends on itself.
6. The dependency graph is acyclic.
7. Only allowed values are used for `upstream.status` and `releases.<ver>.status`.
8. Alembic revisions listed in the manifest exist as files (best effort — skipped when no `alembic/versions/` tree is present in the checkout).

Both scripts are plain Python 3 (`re` + `PyYAML`) so they run identically in CI and locally:

```bash
python3 scripts/check_pr_title.py "[PATCH-026] My feature"
python3 scripts/validate_patches.py patches.yaml
```

The PR title check is what makes `git log --grep "[PATCH-NNN]"` a reliable tracking mechanism — it is the only guarantee that every commit carries its patch ID.

Automation does not replace the human judgment required to assess whether a dependency is truly satisfied or whether an upstream solution is genuinely equivalent.

---

## Do's and Don'ts

### Do's

- Use stable patch IDs.
- Treat each PR as a portable unit.
- Document dependencies in `depends_on`.
- Only change integration branches through pull requests.
- Keep `patches.yaml` up to date in every patch PR.
- Build new integration branches fresh from `upstream/stable/<ver>`.
- Port patches in topological order.
- Skip patches that are dropped or covered by upstream.
- Leave executed Alembic migrations untouched.
- Merge Alembic heads explicitly before release.
- Test both fresh install and upgrade from the previous release.
- Test production upgrades on a clone of the production database first.

### Don'ts

- Rebase or force-push published integration branches.
- Use commit SHAs as a stable patch identity.
- Mix independent features into a single patch.
- Consolidate a fix when doing so creates a dependency cycle.
- Blindly cherry-pick all old commits.
- Port a patch together with its own revert.
- Delete or re-link executed Alembic revisions.
- Assume Alembic detects duplicate schema effects automatically.
- Run `alembic upgrade head` in production without prior SQL review.
- Use `alembic stamp` without proven schema and data equivalence.
- Test only the fresh-install path.
