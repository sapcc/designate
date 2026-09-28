# Downstream Patch Engineering — Migration Guide

For concepts, manifest schema, and PR types see [patch-concept.md](patch-concept.md).

---

## Migration to a New Release

### Setup

Create the new integration branch fresh from the corresponding upstream branch:

```bash
git fetch upstream
git switch -c stable/2028.2-m3 upstream/stable/2028.2
git push -u origin stable/2028.2-m3
```

Port any `[SETUP]` commits from the previous cycle that are still relevant (PR template changes, CI additions). Find them with:

```bash
git log --oneline --grep="\[SETUP\]" origin/stable/2026.2-m3
```

The initial bootstrap commit cannot be cherry-picked — it contains a release-specific `patches.yaml` state. Create it fresh:

```bash
# In patches.yaml: add a new releases."2028.2" block for every non-upstreamed patch
# (status: pending, commits: [])
git add patches.yaml .github/pull_request_template.md
git commit -m "[SETUP] bootstrap stable/2028.2-m3"
git push
```

### Porting order

1. Patches with `upstream.status: upstreamed` → open a `removal` PR immediately, set `releases."2028.2".status: dropped`. No further investigation needed.
2. Remaining patches → investigate against the new upstream, port in topological order (`depends_on` defines the sequence).
3. After each PR → update `patches.yaml`: set `status: integrated`, add commit SHAs.

---

## Port Scenarios

### Simple port

```bash
git fetch upstream
git switch -c patch/PATCH-004-soa-fields origin/stable/2028.2-m3
git cherry-pick <PATCH-004-COMMIT>

# resolve conflicts if any
git add <files>
git cherry-pick --continue

<test-command>
git push -u origin patch/PATCH-004-soa-fields
```

### Port with consolidated fixes

Only when the fixes do not introduce an additional dependency:

```bash
git switch -c patch/PATCH-001-auth origin/stable/2028.2-m3

git cherry-pick --no-commit <PATCH-001-COMMIT>
git cherry-pick --no-commit <PATCH-001-F01-COMMIT>
git cherry-pick --no-commit <PATCH-001-F02-COMMIT>

# resolve conflicts and adapt to new upstream
git status
git diff --cached
<test-command>

git commit -m "PATCH-001: add authentication foundation"
git push -u origin patch/PATCH-001-auth
```

### Patch dropped

A patch with `releases.<ver>.status: dropped` is not ported. Also skip:

- its associated fixes,
- any revert of the patch,
- patches that exclusively depend on it, if they are also dropped.

Never port a patch together with its own revert — the net effect is zero.

### Patch covered by upstream

When `upstream.status: upstreamed`:

1. Verify functional equivalence with the upstream implementation.
2. Run existing tests against the upstream implementation.
3. Check API, configuration, and data migration compatibility.
4. Do not port the old patch.
5. Port only any remaining downstream-specific portion as a reworked patch (same ID, update `upstream.note`).

---

## Alembic Migrations

### Immutability

Once a migration has run on any shared or production database:

- do not change `revision`,
- do not change `down_revision`,
- do not delete the file,
- do not modify `upgrade()`.

Create a new corrective or supplementary migration instead.

Code patches may be dropped in a future release. Executed database migrations remain part of the upgrade history permanently.

### Starting point

```text
Previous upstream:
1 → 2 → 3

Downstream (2024.2):
1 → 2 → 3 → 3.1 → 3.2 → 3.3

New upstream (2026.2):
1 → 2 → 3 → 4 → 5 → 6
```

Production database on the previous release:

```text
alembic_version = 3.3
```

### Recommended model: two branches + merge

Leave upstream and downstream migration files untouched:

```text
              ┌→ 4 → 5 → 6 ──────────┐
1 → 2 → 3 ────┤                      ├→ merge_2026.2
              └→ 3.1 → 3.2 → 3.3 ───┘
```

After all migration-bearing patch PRs are integrated, create a separate convergence PR:

```bash
git switch -c migration/merge-alembic-heads origin/stable/2026.2-m3

alembic heads
alembic merge \
  -m "merge 2026.2 upstream and downstream migrations" \
  6 3.3

git add <new-merge-migration>
git commit -m "merge upstream and downstream Alembic heads for 2026.2"
git push -u origin migration/merge-alembic-heads
```

The merge revision typically contains:

```python
revision = "merge_2026.2"
down_revision = ("6", "3.3")
```

All subsequent migrations in this cycle build on `merge_2026.2`.

**Existing database (upgrade path):** already has the downstream branch up to `3.3`. Alembic runs only the missing upstream branch:

```text
4 → 5 → 6 → merge_2026.2
```

**Fresh install:** traverses both branches and reaches the same merge head:

```text
1 → 2 → 3
          ├→ 4 → 5 → 6 ──────────┐
          └→ 3.1 → 3.2 → 3.3 ───┴→ merge_2026.2
```

### Timing of the merge revision

Git PR order and the Alembic graph are independent:

1. Merge patch PRs into the integration branch one by one.
2. Two Alembic heads may coexist temporarily — that is acceptable.
3. After the last migration-bearing port, create the merge-revision PR.
4. Require exactly one Alembic head before the release cut.
5. Only create new migrations after the merge revision is in.

During the build phase, `alembic upgrade heads` (plural) may be needed on integration environments. The final release must have a single head.

### Alternative: linear chain

Technically possible:

```text
1 → 2 → 3 → 3.1 → 3.2 → 3.3 → 4 → 5 → 6
```

This requires changing `4.down_revision` from `3` to `3.3` in the not-yet-published downstream state.

This approach is simpler but modifies an upstream migration file. It is only acceptable when:

- migration `4` has not been executed in any instance of the new release,
- migrations `4–6` are compatible with the schema after `3.3`,
- no operation is executed twice,
- the downstream change to upstream migration `4` is consciously maintained.

The reverse retroactive chain is not safe:

```text
1 → 2 → 3 → 4 → 5 → 6 → 3.1 → 3.2 → 3.3
```

A production database already at `3.3` would cause Alembic to treat `4–6` as already executed due to the changed ancestry.

### Semantic conflicts

A merge revision resolves the revision graph. It does not detect semantic overlap.

Safe:

```text
4:   creates notification table
3.1: creates authentication table
```

Problematic:

```text
4:   creates authentication table
3.1: also creates authentication table
```

Alembic would execute both on one path. Possible errors: table already exists, column already exists, data transformed twice, same structure with different semantics.

When identical or overlapping changes exist, an explicit bridge migration is required:

1. Inspect the current state of the previous-release database.
2. Validate schema and data equivalence.
3. Apply missing upstream changes selectively.
4. Transform divergent data.
5. Verify the result against a fresh new-release database.
6. Only then set the Alembic state deliberately.

`alembic stamp` executes no migration. Use it only when schema and data are demonstrably already at the target state. It is not a mechanism for skipping unknown errors.

---

## Production Upgrade

Run the migration against a clone of the production database before the cutover:

```text
Previous release — Production (Blue)
        │
        ├── Backup / Snapshot
        └── Clone
              │
              ▼
         New release — Green
              ├── Run upgrade path
              ├── Validate schema
              ├── Validate data
              ├── Run application tests
              └── Switch traffic
```

The Green database is not a blank installation. It contains all production data and the existing Alembic state.

### Before production

```bash
alembic current --verbose
alembic heads --verbose
alembic history --verbose
alembic upgrade head --sql > upgrade.sql
```

Review the generated SQL for:

```text
DROP TABLE
DROP COLUMN
CREATE TABLE on an already-existing table
ADD COLUMN on an already-existing column
CREATE INDEX on an already-existing index
ALTER COLUMN
UPDATE
DELETE
```

### Two mandatory test paths

**Fresh install:**

```bash
createdb test_fresh
DATABASE_URL=... alembic upgrade head
```

**Upgrade from previous release:**

```bash
# prepare a copy of the previous-release database with realistic data
alembic current        # expected: 3.3 (or previous head)

# with new-release code
alembic upgrade head
alembic current        # expected: merge_2026.2 or final head
```

Also verify: tables, columns, data types, constraints, indexes, row counts, primary and foreign keys, sequences, business invariants, transformed data values, application and regression tests.

### Preventing data loss

- Test backup and restore before the cutover.
- Mark destructive changes explicitly.
- Do not drop old structures in the same step if rollback is needed — use expand/contract.
- Stop writes or use controlled replication during the final copy / migration window.
- After cutover, be aware that rolling back loses any new writes made on the new release.

---

## Migration Checklist

```text
[ ] upstream/stable/<ver> fetched and up to date
[ ] stable/<ver>-m3 created fresh from upstream
[ ] [SETUP] commit: patches.yaml new release block added, relevant SETUP commits cherry-picked
[ ] Patches with upstream.status=upstreamed immediately dropped (removal PR)
[ ] Remaining patches investigated against new upstream
[ ] Dependency graph is acyclic
[ ] Patches ported in topological order
[ ] Alembic semantic overlaps classified
[ ] Merge revision created after last migration-bearing port
[ ] Exactly one final Alembic head
[ ] Fresh install successful
[ ] Upgrade on production clone successful
[ ] Schema, data, and application tests successful
[ ] Backup, cutover, and rollback plan reviewed
```

---

## References

- Alembic – Working with Branches: https://alembic.sqlalchemy.org/en/latest/branches.html
- Alembic – Commands: https://alembic.sqlalchemy.org/en/latest/api/commands.html
- Alembic – Tutorial: https://alembic.sqlalchemy.org/en/latest/tutorial.html
- Git – Cherry-pick: https://git-scm.com/docs/git-cherry-pick
- Git – Revert: https://git-scm.com/docs/git-revert
- GitHub – Pull request merge methods: https://docs.github.com/en/pull-requests/reference/pull-request-merges
- GitHub – Pull request templates: https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/creating-a-pull-request-template-for-your-repository
