# Downstream Patch Engineering — Developer Guide

For concepts, manifest schema, and PR types see [patch-concept.md](patch-concept.md).
For porting patches to a new release see [patch-migration-guide.md](patch-migration-guide.md).

Each scenario shows the complete flow: git commands, what changes in `patches.yaml`, and how the PR looks when filled in.

---

## New Patch

```bash
git fetch upstream
git switch -c patch/PATCH-026-my-feature origin/stable/2026.2-m3

git add <files>
git commit -m "PATCH-026: my new feature"
git push -u origin patch/PATCH-026-my-feature
```

Review fixes — no rebase or force-push:

```bash
git add <files>
git commit -m "address review: ..."
git push
```

**`patches.yaml`** — add a new entry:

```yaml
- id: PATCH-026
  title: My new feature
  depends_on: []           # or [PATCH-XXX] if technically required
  upstream:
    status: downstream-only
  releases:
    "2026.2":
      status: integrated
      commits: [<sha>]
```

**PR:**

```
Title:  [PATCH-026] My new feature

Patch-ID:     PATCH-026
Type:         patch
Ticket/Issue: SAP-XXXXX
```

---

## Fix for a Merged Patch

A fix for a patch that is already `integrated` gets its own `-F01` entry. The original patch commit is never modified retroactively.

If the original patch PR is still open, the fix is just an additional commit in that PR — no new manifest entry needed.

```bash
git fetch origin
git switch -c fix/PATCH-005-F01-serial-overflow origin/stable/2026.2-m3

git add <files>
git commit -m "PATCH-005-F01: fix serial overflow on zone import"
git push -u origin fix/PATCH-005-F01-serial-overflow
```

**`patches.yaml`** — add a new `-F01` entry; the original entry is not modified:

```yaml
- id: PATCH-005-F01
  title: Fix serial overflow on zone import
  depends_on: [PATCH-005]   # always the patched entry; add further deps if needed
  upstream:
    status: downstream-only
  releases:
    "2026.2":
      status: integrated
      commits: [<sha>]
```

**PR:**

```
Title:  [PATCH-005-F01] Fix serial overflow on zone import

Patch-ID:     PATCH-005-F01
Type:         fix
Ticket/Issue: -
```

---

## Remove a Patch from the Running Release

Used when a merged patch needs to be reverted in the current release (e.g., regression, wrong approach). Dependent patches must be removed, adapted, or decoupled first.

Single-commit patch:

```bash
git switch -c remove/PATCH-026 origin/stable/2026.2-m3
git revert <patch-commit>
git push -u origin remove/PATCH-026
```

Patch with multiple fixes — revert in reverse order:

```bash
git switch -c remove/PATCH-026 origin/stable/2026.2-m3

git revert --no-commit <last-fix-commit>
git revert --no-commit <first-fix-commit>
git revert --no-commit <patch-commit>

git commit -m "PATCH-026: remove my new feature"
git push -u origin remove/PATCH-026
```

**`patches.yaml`** — set `status: dropped` for the current release:

```yaml
  releases:
    "2026.2":
      status: dropped
```

**PR:**

```
Title:  [PATCH-026] Drop: reverted due to regression

Patch-ID:     PATCH-026
Type:         removal
Ticket/Issue: SAP-XXXXX
```

---

## Infrastructure Change (Setup)

No patch ID. Used for changes to `patches.yaml` schema, PR template, CI workflows, or documentation.

```bash
git switch -c setup/extend-pr-template origin/stable/2026.2-m3

git add <files>
git commit -m "[SETUP] extend PR template checklist"
git push -u origin setup/extend-pr-template
```

**`patches.yaml`** — only if the schema itself changes (new field, `schema_version` bump). Otherwise no manifest change.

**PR:**

```
Title:  [SETUP] Extend PR template checklist

Patch-ID:     -
Type:         setup
Ticket/Issue: -
```

---

## Developer Checklist

```text
[ ] patches.yaml updated in the same PR (new entry or updated block)
[ ] depends_on entries are already integrated in the target branch
[ ] commits list contains the correct SHAs
[ ] Alembic revision added to patches.yaml migrations list (if applicable)
[ ] PR title follows [PATCH-XXX] / [SETUP] convention
[ ] Type field matches the scenario
```
