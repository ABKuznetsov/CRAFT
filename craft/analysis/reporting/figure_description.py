"""Describe captured native subjects; does not classify or calculate geometry."""
from craft.analysis.reporting.composer import FigureNarrative
from craft.presentation.crystal_layers import component_key, coordination_group_label, layer_options


def _coordination(family, counts):
    return " + ".join(f"{count} × {coordination_group_label(family, cn)}" for cn, count in counts)


def describe_view(document, manifest):
    if manifest.scene_kind.startswith("organic:"):
        mode = manifest.scene_kind.split(":", 1)[1]
        title, text, tables = {
            "single_molecule": ("Molecular fragment", "The selected molecular fragment and its atomic connectivity are shown.", ("molecular_components", "bond_lengths")),
            "ring": ("Molecular ring", "A molecular ring is highlighted in the selected fragment.", ("molecular_rings", "bond_lengths")),
            "sbu": ("Coordination block", "The selected coordination block and its composition are shown.", ("coordination_nodes", "sbus")),
            "linker": ("Linker", "The selected linker and its atomic connectivity are shown.", ("linkers", "bond_lengths")),
            "net": ("Periodic net", "The selected representation of the periodic net is shown.", ("reticular_net",)),
            "packing": ("Crystal packing", "The crystal packing of molecular fragments is shown.", ("molecular_components", "packing_interactions")),
            "contacts": ("Intermolecular contacts", "The selected intermolecular contacts are shown.", ("intermolecular_contacts",)),
        }[mode]
        refs = tuple(ref for ref in manifest.visible_object_refs if not ref.startswith("contact-orbit:"))
        return title, title + ".", FigureNarrative("molecule" if mode == "single_molecule" else mode,
            refs, (text,), ("crystal_data", "refinement", *tables))
    visible = set(manifest.visible_object_refs)
    layer_refs = tuple(ref for ref in manifest.visible_object_refs if ref.startswith("crystal-layer:"))
    selected = tuple(ref for ref in manifest.selected_object_refs if ref in visible)
    previous = getattr(document, "report_draft", None)
    earlier = set(previous.figures[-1].manifest.visible_object_refs) if previous is not None and previous.figures else set()
    fresh = tuple(ref for ref in layer_refs if ref not in earlier)
    # A previous tree selection can remain while a checkbox adds another layer.
    # Describe that newly visible subject before reusing the old selection.
    subjects = (fresh if previous is not None and fresh else selected) or fresh or layer_refs
    classification = getattr(getattr(document.scientific, "inorganic_classification", None), "result", None)
    groups = (*classification.groups, *classification.cation_groups) if classification is not None else ()
    options = {row.key: row for row in layer_options(document)} if classification is not None else {}
    assignments = {component_key(a): (group, a) for group in groups for a in group.subtypes}
    rings = {m.ring_orbit_id: (group, a, m) for group in groups for a in group.subtypes for m in a.ring_motifs}
    statements, diagnostics, tables, roles, labels = [], [], ["crystal_data", "refinement"], [], []
    view = document.inorganic_presentation() if classification is not None else None
    for ref in subjects:
        kind, identifier = ref.split(":", 1)
        option = options.get(identifier) if kind == "crystal-layer" else None
        if identifier in rings:
            group, assignment, ring = rings[identifier]
            composition = _coordination(group.family, ring.coordination_counts)
            labels.append(f"Cyclic motif with {ring.centre_count} centres")
            statements.append(f"Coordination polyhedra ({composition}) form a graph cycle with {ring.centre_count} centres.")
            if ring.opening_status != "confirmed":
                statements.append("A geometric opening in this motif has not been confirmed; the selection is based on graph connectivity.")
            if assignment.status != "supported":
                statements.append("The connectivity description is conditional on the selected average structural model.")
            roles.append("ring")
            tables.extend(("inorganic_classification", "coordination", "connectivity"))
        elif identifier in assignments:
            group, assignment = assignments[identifier]
            labels.append({0: "Finite group", 1: "One-dimensional subsystem", 2: "Layer subsystem", 3: "Three-dimensional framework"}[assignment.rank])
            units = " + ".join(coordination_group_label(group.family, cn) for cn in assignment.coordination_numbers)
            topology = {0: "a finite group", 1: "a connected one-dimensional periodic subsystem",
                        2: "a connected two-dimensional periodic subsystem", 3: "a three-dimensional framework"}[assignment.rank]
            statements.append(f"Coordination groups {units} form {topology} in the selected connectivity graph.")
            if group.family == "cation":
                statements.append(f"Cation centres are grouped using the selected criterion: {group.label}.")
            if assignment.status != "supported":
                statements.append("The result is conditional on the selected average structural model.")
            roles.append("component")
            tables.extend(("inorganic_classification", "coordination", "connectivity"))
        elif option is not None and option.boundary_key:
            boundary = next(b for group in groups for environment in group.environments
                            for b in environment.coordination_boundaries if b.key == option.boundary_key)
            labels.append(option.label)
            partition = "+".join(map(str, boundary.coordination_partition))
            statements.append(f"The extended coordination environment {option.label} is shown. "
                              f"Coordination number: {boundary.coordination_number}; shell partition: {partition}.")
            statements.append("Outer neighbours belong to the explicitly selected alternative shell.")
            if boundary.conditional:
                statements.append("The environment is conditional on the selected average structural model.")
            roles.append("polyhedra")
            tables.extend(("coordination", "bond_lengths"))
        elif option is not None and option.kind == "coordination_set":
            labels.append("Cation coordination")
            statements.append("The selected coordination environments of cation sites are shown. Coordination alone does not establish positions in channels or cavities.")
            roles.append("cation")
            tables.extend(("coordination", "bond_lengths", "polyhedra"))
        elif option is not None and option.kind == "atom" or kind == "atom-orbit":
            site = option.site_id if option is not None else identifier
            atom = next((row for row in view.atom_orbits if row.source_site_id == site), None) if view is not None else None
            label = f"{atom.label} ({atom.composition_label})" if atom is not None else site
            labels.append(label)
            statements.append(f"The independent atomic site {label} and its displayed symmetry copies are highlighted.")
            roles.append("atom")
            tables.append("atomic_sites")
        elif option is not None and option.kind == "polyhedra" or kind == "polyhedron-orbit":
            members = set(option.polyhedron_orbit_ids) if option is not None else {identifier}
            rows = tuple(row for row in view.polyhedron_orbits if row.polyhedron_orbit_id in members) if view is not None else ()
            label = option.label if option is not None else ", ".join(row.label for row in rows)
            labels.append(label)
            statements.append(f"Coordination polyhedra are highlighted: {label}.")
            if rows:
                statements.append("Coordination numbers: " + ", ".join(f"{row.label}: {row.coordination_number}" for row in rows) + ".")
            roles.append("polyhedra")
            tables.extend(("coordination", "polyhedra", "bond_lengths"))
        else:
            labels.append(option.label if option is not None else "Selected structure objects")
            statements.append("The selected objects of the structural model are shown; their display settings are saved with the figure.")
            roles.append("detail")
    if not statements:
        name = document.display_name
        labels = [f"Structure overview of {name}"]
        statements = [f"Overview of the crystal structure {name}."]
        roles = ["overview"]
        subjects = tuple(manifest.visible_object_refs)
        tables.extend(("atomic_sites", "bond_lengths"))
        # Classification describes the model; no cavity, charge or mineral
        # species is inferred from a formula or the drawing.
        if classification is not None:
            for group in classification.groups:
                label = {"borate": "Borates", "silicate": "Silicates", "sulfate": "Sulfates", "phosphate": "Phosphates"}.get(group.family, group.label)
                statements.append(f"Compound class in the selected model: {label}"
                                  + (" (conditional assignment)." if group.status != "supported" else "."))
            if classification.groups:
                tables.append("inorganic_classification")
    title = "; ".join(dict.fromkeys(labels))
    role = roles[0] if len(set(roles)) == 1 else "detail"
    narrative = FigureNarrative(role, tuple(subjects), tuple(dict.fromkeys(statements)),
                                tuple(dict.fromkeys(tables)), tuple(diagnostics))
    caption = title + "."
    return title, caption, narrative
