<!-- Title format:
     [PATCH-XXX] Short description          (new patch or port)
     [PATCH-XXX] Drop: reason               (removal)
     [PATCH-XXX] Rework: reason             (substantial rewrite)
     [PATCH-XXX-F01] Fix short description  (fix)
     [SETUP] Short description              (no patch affected)
-->

## Patch Metadata

- **Patch-ID:** PATCH-XXX
- **Type:** patch | fix | removal | rework
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
