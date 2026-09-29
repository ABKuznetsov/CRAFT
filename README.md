# CRAFT — Crystallographic Representation, Analysis and Framework Toolkit

Desktop application for inspecting, presenting and comparing crystal
structures. CRAFT is the interactive shell; CrIStMa is its crystallographic
computation layer:

```text
structural files → CrIStMa immutable scientific results
                 → CRAFT scenes, tables, reports and comparison
```

CRAFT does not contain independent CIF/RES/POSCAR/PDB/XYZ parsers and does not
recalculate contacts, coordination, polyhedra, structural units, blocks, rings
or topology. It presents the canonical structures, identities, diagnostics and
provenance returned by CrIStMa. CRAFT-specific BFDH morphology, twins,
striation, interaction state and report workflows remain in this application.

## Why this architecture

The desktop stack is **PySide6 + PyVistaQt/VTK**. CrIStMa is the only source of
canonical structures and reusable crystallographic science. CRAFT currently
retains a compatibility projection for renderers that have not yet migrated;
that projection is not a second scientific model.

`pymatgen` remains a direct dependency only for CRAFT-specific morphology and
reference helpers. It is not a structural input fallback and is not used to
repair or replace a CrIStMa result.

## Current capabilities

- structural-file loading exclusively through CrIStMa, retaining its canonical
  structure, diagnostics, stable scientific identities and loss-preserving
  source document;
- progressive background installation of CrIStMa contacts, coordination
  polyhedra, structural units, structural blocks, rings and topology;
- primary and secondary contact groups, symmetry-orbit grouping and bounded
  representative fragments for periodic objects;
- atoms, two-colour bonds, coordination-polyhedron surfaces, structural blocks
  and topology views built as CRAFT presentation projections;
- profile-aware molecular and reticular views driven by CrIStMa molecular and
  MOF/reticular results;
- document-owned visibility, colour, selection and editing state that never
  changes the underlying scientific identity;
- supercell/range controls, axis views, picking, screenshots and structural-file
  drag-and-drop;
- material-batched VTK rendering with scientific source IDs attached to mesh
  cells for selection;
- an Analysis workspace with configurable report catalogues, tables, snapshots,
  CSV/JSON export and stable links back to structural objects;
- ESD-aware source values: original numeric tokens, standard uncertainties,
  missing/unknown states, units and provenance remain separate from display
  geometry;
- editable BFDH morphology plus CRAFT-specific twins and striation workflows.

If CrIStMa does not provide a scientific result, CRAFT shows that section as
unavailable together with diagnostics. It does not reconstruct the result with
another library. Structure-series mechanics is therefore presentation-only for
now: site matching, motion decomposition and mechanism claims remain disabled
until a stable CrIStMa series contract is available.

## Comparison descriptor definitions

The comparison workspace uses explicit, versioned descriptors rather than a
single opaque “structure similarity” percentage. Thresholds, colours and any
composite ranking are CRAFT workflow heuristics: they are not crystallographic
equivalence tests and do not imply statistical significance.

- **Mo–O distortion index (DI):** mean absolute deviation of all Mo–O bond
  lengths from their mean, divided by that mean;
- **Mo off-centering:** Cartesian distance between Mo and the centroid of all
  ligand vertices in its MoO₆ coordination environment;
- **d₆−d₅:** difference between the sixth and fifth distances after sorting all
  six Mo–O distances; the sixth ligand is never discarded;
- **strong [5+1]:** the reported fraction with d₆−d₅ above the selected
  threshold (default 0.25 Å), while the continuous d₆−d₅ distribution remains
  available;
- **periodic rank:** matrix rank of lattice-translation closure vectors around
  graph cycles (0D/1D/2D/3D), so a single translated tree edge is not
  mislabelled as a chain;
- **comparison colours:** descriptor-specific absolute tolerances; absent
  values are shown as unavailable and never replaced with zero.

## Compare two structures

1. Open or drag one or several CIF files directly into the main window. They
   remain available as separate collapsed roots in the Hierarchy Explorer.
2. Check exactly two structures using the checkbox to the left of each root.
   The tree has one column, no A/B columns, and a third check is not accepted.
3. Press **Compare structures** below the tree. The central view splits into
   equal A/B 3D panes.
4. Move the pointer over a pane to make it active. With **Linked rotation** on,
   rotating the active pane rotates both; turn it off to adjust one projection.
5. Open **Comparison table** for descriptor-specific similarities,
   differences, methods, warnings and 3D focus.
6. Export the table as CSV/JSON or save synchronized A/B PNG images.

## Editable BFDH morphology

1. Open a CIF and select the **Morphology** tab. The hierarchy tree and right
   inspector remain visible.
2. The application uses the full space-group operations: rotational parts
   form symmetry-equivalent `{hkl}` families, while centring translations,
   screw axes and glide planes determine systematic absences.
3. The table reports `d(hkl)`, first allowed reflection order, effective
   spacing, the original BFDH distance, current editable distance, area and
   surface fraction. `rho` is relative and dimensionless; it is not an
   absolute particle size.
4. Edit **Current rho** to rebuild the shape, disable a family with its
   checkbox, or add a signed `(hkl)` family. Complementary polar faces remain
   separate unless an actual symmetry operation relates them.
5. Save manual work to a separate `.morphology.json` sidecar or export CSV and
   PNG. The source CIF is never changed.

BFDH is a geometric morphology prediction, not a thermodynamic equilibrium
shape. DSC measurements do not provide the orientation-dependent surface
energies required for a Wulff construction. A future Wulff mode can reuse this
editor when calculated `gamma(hkl)` values become available.

## macOS installer

Build the Raman-style installer on macOS with:

```bash
zsh scripts/build_macos_pkg.command
```

It produces `dist/CRAFT_macOS_<version>.pkg`, installs
`CRAFT.app` in `/Applications`, and reuses the shared Python 3.11/3.12
environment at `~/Library/Application Support/Sci/env`.

## Run

The launcher creates or reuses the shared per-user Sci Python environment:

```bash
cd Craft
./run_craft.command
```

Without a file argument the application opens an empty session and waits for
Open or drag-and-drop. A structural file can also be passed explicitly:

```bash
./run_craft.command /path/to/structure.cif
```

Opening structural files and XPFF containers is progressive: the atom model becomes interactive
as soon as parsing finishes, while bonds, coordination polyhedra, structural
units and topology are calculated in a background worker and installed stage by
stage. Reopening an unchanged structure reuses the persistent structural cache.

CRAFT depends directly on the independently installable `cristma` package. The
shared Sci environment may install that dependency, but CRAFT does not import
or communicate with Sci. CIF, RES/INS, POSCAR, PDB and XYZ input all cross the
same CrIStMa boundary; CRAFT contains no format-specific structural parser.

## Repository structure

```text
CRAFT/
├── craft/          application Python package
├── assets/         source icons
├── installer/      Windows installer definition
├── scripts/        release and macOS package builders
├── toolkit/        shared Sci environment helpers
├── pyproject.toml
├── run_craft.command
├── run_craft.bat
└── run_craft_silent.vbs
```

The source package is `craft` directly under the repository root. There is no
`src/` compatibility layer. Generated wheels, installers and build workspaces
are release artifacts and are excluded from Git.

## Product roadmap

1. **Presentation parity:** finish picking, labels, visibility controls and
   export without creating a second scientific model.
2. **Hierarchy workbench:** edit presentation state for CrIStMa objects using
   stable IDs, including bounded fragments of chains, layers and frameworks.
3. **Transparent comparison and reports:** expose descriptor definitions,
   provenance, diagnostics and links from every table or figure to the objects
   it represents.
4. **Structure series:** consume a future immutable CrIStMa series result;
   CRAFT will present, compare and animate it without performing site matching
   or motion analysis itself.
5. **CRAFT-specific morphology:** continue the BFDH, twins and striation
   workflows as application features built on CrIStMa structure/symmetry data.
