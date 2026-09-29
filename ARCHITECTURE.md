# CRAFT architecture

## Product boundary

CRAFT is the interactive presentation and workflow layer. CrIStMa is the
crystallographic computation layer.

```text
structure file
    ↓
CrIStMa canonical structure and immutable scientific results
    ↓
CRAFT document/cache
    ↓
presentation projections
    ↓
tree, tables, scene, comparison and export
```

CrIStMa owns:

- structural file parsing and canonical structure models;
- symmetry, periodic geometry and stable scientific identities;
- contacts, coordination shells and polyhedra;
- structural units, structural blocks, rings and periodic topology;
- scientific status, diagnostics, evidence and provenance.

CRAFT owns:

- asynchronous requests and result caching;
- scene meshes, materials, colours and visibility;
- selection, editing and saved presentation state;
- tables, reports, comparison and export workflows;
- BFDH morphology, twins and striation.

CRAFT may project an immutable scientific result for display. A projection must
not infer missing contacts, alter coordination membership, or silently fall
back to another scientific implementation.

## Canonical document boundary

`StructureDocument.structure` is the canonical CrIStMa structure.
`StructureDocument.legacy_projection` is a temporary CRAFT display model used
by renderers and presentation code that have not yet migrated. It contains no
back-reference to the canonical structure and is not a scientific authority.

Every background result is stored with its complete `request_key`. A result is
accepted only when that key still matches the active document request. CRAFT
execution states (`LOADING`, `READY`, `FAILED`, `STALE`) are separate from
CrIStMa scientific states such as `AMBIGUOUS` and `INCOMPLETE`.

## Vertical migration rule

Scientific layers move one at a time:

```text
CrIStMa immutable result released
    ↓
CRAFT consumes it through one production route
    ↓
real-structure acceptance passes
    ↓
the corresponding CRAFT calculation is deleted
```

There is no permanent dual stack and no legacy fallback. Production migration
status is:

1. contact orbits and coordination shells — migrated;
2. polyhedron orbits and geometry — migrated;
3. molecules, rings and intermolecular contacts — migrated;
4. coordination nodes, linkers and building units — migrated;
5. structural blocks and periodic topology — migrated;
6. comparison fingerprints and stable-ID mapping — in progress;
7. removal of the remaining compatibility display model — pending.

CRAFT consumes the final CrIStMa result objects. It must not aggregate
intermediate pair, incidence or shell-orbit objects into a competing scientific
result.

## Rendering invariants

- One UI row represents one stable scientific orbit ID.
- Symmetry-expanded instances are materialized only when a scene needs them.
- Primary contacts are initially visible; secondary contacts are available but
  initially hidden.
- Partial scientific results remain visible with their diagnostics.
- Colours and visibility are CRAFT state and never alter scientific identity.
- Structural blocks and mechanical blocks remain distinct concepts.
- Enabling a block may hide its internal representation while preserving
  connector atoms; disabling it restores the previous visibility state.
- Infinite chains, layers and frameworks use bounded representative fragments.

## Transitional dependencies

The compatibility display projection and several presentation/reference helpers
remain temporarily. Organic, molecular, MOF and reticular scientific analysis
already comes from CrIStMa. `pymatgen` is used only by CRAFT-specific morphology
and reference helpers; it is not a parser, scientific fallback or repair route.

## Unavailable scientific results

When CrIStMa returns no result, a partial result or a diagnostic state, CRAFT
shows that state and the available data. It does not reconstruct missing science
locally or restore an older result.

Structure-series mechanics is deliberately unavailable in the production
workflow until CrIStMa publishes a stable immutable series result. CRAFT may
load several structures and present them, but it must not perform independent
site matching, Kabsch motion decomposition or mechanism inference.
