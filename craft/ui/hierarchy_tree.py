from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from craft.analysis.hierarchy import HierarchyLevel
from craft.analysis.structure_profile import ResolvedProfile
from craft.analysis.structural_motifs import RING_SCOPE_LABELS
from craft.analysis.inorganic_classification import RING_OPENING_WARNING
from craft.core.collection import StructureCollection
from craft.core.document import StructureDocument
from craft.core.site_orbits import (
    bond_families,
    connector_orbits,
    hierarchy_object_orbits,
    polyhedron_orbits,
)
from craft.knowledge.resolve import resolve_interpretation
from craft.ui.organic_views import organic_view_descriptors
from craft.presentation.crystal_layers import (
    component_key, component_polyhedron_key, polyhedra_key, ring_unit_key,
    cation_centres_key, coordination_group_label, ring_candidate_label,
)


Payload = tuple[str, str, object]


class HierarchyTree(QTreeWidget):
    """Collection-aware hierarchy browser with independent A/B/compare state."""

    active_requested = Signal(str)
    visual_slot_requested = Signal(str, str)
    compare_toggled = Signal(str, bool)
    visibility_changed = Signal(str, str, object, bool)
    object_selected = Signal(str, str, object)
    SearchTextRole = int(Qt.ItemDataRole.UserRole) + 20
    PreviousCheckStateRole = int(Qt.ItemDataRole.UserRole) + 21
    TableCategoryRole = int(Qt.ItemDataRole.UserRole) + 22
    TableDetailRole = int(Qt.ItemDataRole.UserRole) + 23
    ScopeVariantRole = int(Qt.ItemDataRole.UserRole) + 24
    DefaultScopeLabelRole = int(Qt.ItemDataRole.UserRole) + 25
    TableTransparentRole = int(Qt.ItemDataRole.UserRole) + 26

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._collection: StructureCollection | None = None
        self._updating = False
        self._root_buttons: list[QToolButton] = []
        self._root_labels: list[QLabel] = []
        self.setColumnCount(1)
        self.setHeaderLabels(("Structures",))
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.currentItemChanged.connect(self._current_item_changed)
        self.itemChanged.connect(self._item_changed)

    def set_collection(self, collection: StructureCollection) -> None:
        self._collection = collection
        self._updating = True
        try:
            self.clear()
            self._root_buttons.clear()
            self._root_labels.clear()
            for document_id in collection.order:
                document = collection.documents[document_id]
                item = self._document_root(document)
                self.addTopLevelItem(item)
                self._install_root_widget(item, document)
            for document in collection.documents.values():
                self.sync_crystal_layers(document)
            def remember(item):
                item.setHidden(bool(item.data(0, self.TableDetailRole)))
                if item.data(0, Qt.ItemDataRole.CheckStateRole) is not None:
                    item.setData(0, self.PreviousCheckStateRole, item.checkState(0).value)
                for index in range(item.childCount()):
                    remember(item.child(index))
            for index in range(self.topLevelItemCount()):
                remember(self.topLevelItem(index))
            self.collapseAll()
        finally:
            self._updating = False

    def _document_root(self, document: StructureDocument) -> QTreeWidgetItem:
        root = QTreeWidgetItem([""])
        root.setData(0, Qt.ItemDataRole.UserRole, (document.id, "structure", document.id))
        root.setData(0, self.SearchTextRole, self._document_name(document))
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
        root.setSizeHint(0, QSize(0, 28))

        profile = document.profile_decision
        if profile is not None and profile.resolved is not ResolvedProfile.INORGANIC:
            if hasattr(document.structure, "atomic_view"):
                root.addChild(self._native_crystallography_branch(document))
            chemistry = self._group(document.id, "category", "Crystal chemistry", object_id="molecular_unit", table_category="molecular_unit")
            root.addChild(chemistry)
            label = "Organic" if profile.resolved is ResolvedProfile.MOLECULAR else "Metal-organic"
            domain = self._group(document.id, "category", label, object_id="molecular_unit", table_category="molecular_unit")
            if profile.basis == "composition":
                domain.setToolTip(0, "Candidate domain based on composition; this does not establish a MOF.")
            chemistry.addChild(domain)
            for descriptor in organic_view_descriptors(document):
                label = (
                    f"{descriptor.label} ({descriptor.object_count})"
                    if descriptor.object_count is not None
                    else f"{descriptor.label} — calculating…"
                )
                item = self._group(
                    document.id,
                    "category",
                    label,
                    object_id=descriptor.kind.value,
                    table_category=descriptor.kind.value,
                )
                if not descriptor.ready:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                domain.addChild(item)
            if document.scientific.polyhedra is not None:
                self._add_native_inorganic_children(root, document, chemistry_parent=chemistry)
            self._add_report_branch(root, document)
            return root

        if hasattr(document.structure, "atomic_view"):
            self._add_native_inorganic_children(root, document)
            self._add_report_branch(root, document)
            return root

        cell = self._leaf(document.id, "cell", "cell", "Unit Cell")
        root.addChild(cell)

        contact_rows = tuple(
            getattr(getattr(document, "contact_presentation", None), "rows", ())
        )
        bond_count = len(bond_families(document))
        polyhedron_count = len(polyhedron_orbits(document))
        unit_count = len(
            hierarchy_object_orbits(document, document.hierarchy.structural_units)
        )
        block_count = len(
            hierarchy_object_orbits(document, document.hierarchy.blocks)
        )
        connector_count = len(connector_orbits(document))
        topology_count = (
            len(document.inorganic_topology.families)
            + len(document.inorganic_topology.cation_families)
            if document.inorganic_topology is not None
            else 0
        )
        stage_order = {
            "parsed": 0,
            "bonds": 1,
            "polyhedra": 2,
            "units": 3,
            "topology": 4,
        }
        current_stage = stage_order.get(document.analysis_stage, 4)
        required_stage = {
            "atoms": 0,
            "bonds": 1,
            "contacts": 1,
            "polyhedra": 2,
            "units": 3,
            "interpretations": 3,
            "blocks": 3,
            "connectors": 3,
            "topology": 4,
        }
        for kind, label in (
            ("atoms", f"Atoms ({len(document.legacy_projection.asymmetric_sites)})"),
            (
                "contacts" if contact_rows else "bonds",
                f"Contacts ({len(contact_rows)})" if contact_rows else f"Bonds ({bond_count})",
            ),
            ("polyhedra", f"Polyhedra ({polyhedron_count})"),
            ("units", f"Structural Blocks ({unit_count})"),
            ("interpretations", f"Interpretation ({len(document.hierarchy.structural_domains)})"),
            ("blocks", f"Mechanical Blocks ({block_count})"),
            ("connectors", f"Shared sites / pivot candidates ({connector_count})"),
            ("topology", f"Topology ({topology_count})"),
        ):
            ready = current_stage >= required_stage[kind]
            item = self._group(
                document.id,
                "category",
                label if ready else f"{label.split(' (', 1)[0]} — calculating…",
                object_id=kind,
            )
            if not ready:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            root.addChild(item)
            if kind == "contacts" and ready:
                item.setFlags(
                    item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsAutoTristate
                )
                for classification, title in (
                    ("primary", "Primary"),
                    ("secondary", "Secondary"),
                ):
                    count = sum(
                        getattr(row.classification, "value", row.classification)
                        == classification
                        for row in contact_rows
                    )
                    child = self._group(
                        document.id,
                        "category",
                        f"{title} ({count})",
                        object_id=f"{classification}_contacts",
                    )
                    child.setData(
                        0,
                        Qt.ItemDataRole.UserRole,
                        self._payload(
                            document.id,
                            "contact_group",
                            classification,
                        ),
                    )
                    child.setFlags(
                        child.flags() | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    orbit_ids = {
                        row.contact_orbit_id
                        for row in contact_rows
                        if getattr(row.classification, "value", row.classification)
                        == classification
                    }
                    visible_count = len(
                        orbit_ids - document.visual.hidden_contact_orbit_ids
                    )
                    state = (
                        Qt.CheckState.Unchecked
                        if visible_count == 0
                        else Qt.CheckState.Checked
                        if visible_count == len(orbit_ids)
                        else Qt.CheckState.PartiallyChecked
                    )
                    child.setCheckState(0, state)
                    item.addChild(child)
            if kind == "units" and ready:
                self._add_structural_block_children(item, document)
        self._add_report_branch(root, document)
        return root

    @staticmethod
    def _document_name(document: StructureDocument) -> str:
        if hasattr(document.structure, "atomic_view"):
            return document.structure.name
        return document.display_name

    def _native_crystallography_branch(self, document) -> QTreeWidgetItem:
        view = document.inorganic_presentation()
        crystal_data = self._group(document.id, "category", "Crystallography", object_id="atoms", table_category="atoms")
        crystal_data.setToolTip(0, "Independent atomic positions and contact orbits supplied by CrIStMa. Symmetry copies share one editable row.")
        crystal_data.addChild(self._leaf(document.id, "cell", "cell", "Unit Cell"))
        crystal_data.addChild(self._group(
            document.id, "category", f"Atoms ({len(view.atom_orbits)})", object_id="atoms", table_category="atoms"
        ))
        primary_bonds = tuple(row for row in view.contact_orbits if row.classification == "primary")
        bonds = self._group(
            document.id,
            "category",
            f"Bonds ({len(primary_bonds)})",
            object_id="bonds",
            table_category="bonds",
        )
        crystal_data.addChild(bonds)
        secondary = sum(row.classification == "secondary" for row in view.contact_orbits)
        crystal_data.addChild(self._group(
            document.id, "category", f"Secondary contacts ({secondary})", object_id="secondary_contacts",
            table_category="secondary_contacts",
        ))
        return crystal_data

    def _add_native_inorganic_children(
        self,
        root: QTreeWidgetItem,
        document: StructureDocument,
        *,
        chemistry_parent: QTreeWidgetItem | None = None,
    ) -> None:
        view = document.inorganic_presentation()
        if chemistry_parent is None:
            root.addChild(self._native_crystallography_branch(document))
        if not document.structure.sites:
            unavailable = self._group(
                document.id, "category", "Classification unavailable · no atom coordinates", object_id="atoms",
            )
            unavailable.setToolTip(0, "The source contains unit-cell data but no atom coordinates. Structural classification cannot run.")
            unavailable.setFlags(unavailable.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            root.addChild(unavailable)
            return
        domain = chemistry_parent
        if domain is None:
            domain = self._group(document.id, "category", "Crystal chemistry", object_id="polyhedra")
            root.addChild(domain)
        anions = self._group(document.id, "category", "Anion subsystem", object_id="polyhedra")
        domain.addChild(anions)
        classes = view.compound_classes or (None,)
        for compound_class in classes:
            label = compound_class.label if compound_class is not None else "Class not assigned"
            if compound_class is not None and compound_class.status == "conditional":
                label += " · conditional"
            if len(classes) == 1:
                branch = anions
                branch.setText(0, f"Anion subsystem · {label}")
            else:
                branch = self._group(document.id, "category", label, object_id="polyhedra")
                anions.addChild(branch)
            if compound_class is not None:
                branch.setToolTip(0, "\n".join((
                    *(line for e in compound_class.environments for line in e.evidence),
                    *compound_class.warnings,
                    f"Classification reference: {compound_class.reference}",
                )))
            else:
                slot = document.scientific.inorganic_classification
                branch.setToolTip(0, "No supported oxygen-group signature from the CrIStMa reference matches the selected model."
                                  if slot is not None else "Structural classification is pending.")
            if compound_class is not None and compound_class.subsystem is not None:
                self._add_native_subtypes(branch, document, compound_class)
            elif compound_class is not None:
                # Class browsing must retain its exact native scope even when
                # this family has no polymerization descriptor yet.
                for row in view.polyhedron_orbits:
                    if row.polyhedron_orbit_id in compound_class.polyhedron_orbit_ids:
                        branch.addChild(self._native_polyhedron_detail(document, row))
        if view.cation_groups:
            cation_branch = self._crystal_layer_item(document, cation_centres_key(document.scientific.inorganic_classification.result),
                                                    'Cation subsystem')
            domain.addChild(cation_branch)
            environments = self._group(document.id, "category", "Coordination environments", object_id="polyhedra")
            cation_branch.addChild(environments)
            listed_shells = set()
            for group in view.cation_groups:
                branch = self._group(document.id, "category", group.label, object_id="polyhedra")
                branch.setToolTip(0, '\n'.join(group.warnings))
                cation_branch.addChild(branch)
                if group.subsystem is not None:
                    self._add_native_subtypes(branch, document, group)
                else:
                    warning = self._group(document.id, "category", "Connectivity unresolved · CrIStMa sharing required", object_id="polyhedra")
                    warning.setToolTip(0, '\n'.join(group.warnings))
                    branch.addChild(warning)
                members = group.polyhedron_orbit_ids
                from craft.presentation.coordination_rows import group_polyhedron_rows
                for row in group_polyhedron_rows(document,group,view):
                    if row.polyhedron_orbit_id in members:
                        # A shell is shared by graph criteria. Its explicitly
                        # nested boundary alternatives remain below this one
                        # core environment, rather than duplicating it per graph.
                        if row.coordination_boundary_key or row.source_shell_id in listed_shells:
                            continue
                        listed_shells.add(row.source_shell_id)
                        child = self._native_polyhedron_detail(document, row)
                        child.setText(0, f"{row.label} · {row.geometry_label}")
                        child.setToolTip(0, "Selected coordination environment; formal charge and void geometry are not inferred.")
                        environment = next(e for e in group.environments if e.shell_orbit_id == row.source_shell_id)
                        attachment = environment.anion_attachment
                        if attachment is not None and attachment.status == 'observed':
                            description = ', '.join((*attachment.anion_families,
                                                     *(f'{rank}D' for rank in attachment.anion_ranks)))
                            linked = self._group(document.id,'category',f'Linked anion units · {description}',object_id='polyhedra')
                            linked.setToolTip(0,'Observed sharing through inner-shell ligands. Dimensionality describes the anion subsystem; cavity/channel location is not inferred.')
                            for anion in view.polyhedron_orbits:
                                if anion.source_site_id in attachment.anion_site_ids:
                                    linked.addChild(self._native_polyhedron_detail(document,anion))
                            child.addChild(linked)
                        if environment.coordination_boundaries:
                            partitions = ', '.join('+'.join(map(str,b.coordination_partition)) for b in environment.coordination_boundaries)
                            child.setText(0,child.text(0) + f' · extended: {partitions}')
                        for boundary in environment.coordination_boundaries:
                            partition = '+'.join(map(str,boundary.coordination_partition))
                            outer = self._crystal_layer_item(document,boundary.key,
                                f'Extended CN {partition} ({boundary.coordination_number})')
                            outer.setToolTip(0, '\n'.join((
                                f'Inner contacts: {boundary.inner_distance_range[0]:.4f}–{boundary.inner_distance_range[1]:.4f} Å.',
                                f'Additional contacts: {boundary.outer_distance_range[0]:.4f}–{boundary.outer_distance_range[1]:.4f} Å.',
                                'Larger nested boundary supplied by CrIStMa; retained separately from the selected inner shell.',
                                'Its face-sharing topology is shown in the corresponding boundary-specific branch.',
                            )))
                            labels = {s.id:s.label for s in document.structure.sites}
                            for site,count in boundary.added_ligand_site_counts:
                                outer.addChild(self._leaf(document.id,'atom',site,f'{labels[site]} × {count} · additional'))
                            child.addChild(outer)
                        environments.addChild(child)
        whole = self._group(document.id, "category", "Whole structure", object_id="polyhedra")
        whole.setToolTip(0, "Complete host representation. Objects appear once per native orbit, independently of the compound classes above.")
        domain.addChild(whole)
        self._add_native_host_children(whole, document, view)
        whole.addChild(self._group(
            document.id,
            "category",
            f"Topology ({len(view.topology_families)})",
            object_id="topology",
            table_category="topology",
        ))
        self._compact_chemistry(domain, anions, view)

    def _compact_chemistry(self, domain, anions, view):
        """One hierarchy model: objects in the tree, constituents in the table."""
        if len(view.compound_classes) > 1:
            classes = anions.takeChildren()
            for branch in classes:
                for item in branch.takeChildren():
                    item.setText(0, branch.text(0).split(' · ')[0] + ' · ' + item.text(0))
                    anions.addChild(item)

        def details_only(item):
            item.setData(0, self.TableDetailRole, True)
            for i in range(item.childCount()):
                details_only(item.child(i))

        def summary(item):
            item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.DontShowIndicator)
            for i in range(item.childCount()):
                details_only(item.child(i))

        for i in range(anions.childCount()):
            summary(anions.child(i))
        for index in range(domain.childCount()):
            section = domain.child(index)
            if section.text(0) == 'Cation subsystem' and view.cation_groups:
                primary = view.cation_groups[0]
                section.setData(0, self.DefaultScopeLabelRole, primary.label)
                primary_branch = next((section.child(i) for i in range(section.childCount())
                                       if section.child(i).text(0) == primary.label), None)
                if primary_branch is not None:
                    section.takeChild(section.indexOfChild(primary_branch))
                    objects = primary_branch.takeChildren()
                    for item, assignment in zip(objects, primary.subtypes):
                        if assignment.subtype_id == 'isolated':
                            item.setText(0, item.text(0).replace(
                                'No cation–cation sharing under this criterion', 'Isolated cation centres'))
                    for item in objects:
                        section.addChild(item)
                        for i in range(item.childCount()):
                            child = item.child(i)
                            payload = child.data(0, Qt.ItemDataRole.UserRole)
                            if payload and payload[1] == 'crystal_layer' and '/cn:' in str(payload[2]):
                                child.setData(0, self.TableTransparentRole, True)
                            elif child.text(0).startswith('Ring candidates (') and child.childCount():
                                child.setData(0, self.ScopeVariantRole, child.text(0))
                                item.setData(0, self.DefaultScopeLabelRole, 'Polyhedra')
                        summary(item)
                for i in range(section.childCount()):
                    item = section.child(i)
                    if item.data(0, Qt.ItemDataRole.UserRole)[1] == 'category':
                        item.setData(0, self.ScopeVariantRole, item.text(0))
                        details_only(item)
            elif section.text(0) == 'Whole structure':
                for i in range(section.childCount()):
                    summary(section.child(i))

    def _crystal_layer_item(self, document, key, label):
        item = self._leaf(document.id, "crystal_layer", key, label)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        style = document.visual.crystal_layers.get(key)
        item.setCheckState(0, Qt.CheckState.Checked if style is not None and style.visible
                           else Qt.CheckState.Unchecked)
        return item

    def sync_crystal_layers(self, document):
        """Refresh checkboxes after selection without rebuilding/collapsing the tree."""
        from craft.presentation.crystal_layers import layer_options
        from craft.presentation.layer_state import resolved_layer_style

        options = {row.key: row for row in layer_options(document)}
        previous = self._updating
        self._updating = True
        try:
            def visit(item, ancestors=()):
                payload = item.data(0, Qt.ItemDataRole.UserRole)
                if payload and payload[0] == document.id and payload[1] in {"crystal_layer", "crystal_layer_group"}:
                    if payload[1] == "crystal_layer_group":
                        states = [resolved_layer_style(document, key, ancestors, options=options) for key in payload[2]]
                        count = sum(style is not None and style.visible for style in states)
                        state = (Qt.CheckState.Unchecked if count == 0 else
                                 Qt.CheckState.Checked if count == len(states) else Qt.CheckState.PartiallyChecked)
                        item.setCheckState(0, state)
                        item.setData(0, self.PreviousCheckStateRole, state.value)
                        for i in range(item.childCount()):
                            visit(item.child(i), ancestors)
                        return
                    style = resolved_layer_style(document, payload[2], ancestors, options=options)
                    item.setCheckState(0, Qt.CheckState.Checked if style is not None and style.visible
                                       else Qt.CheckState.Unchecked)
                    item.setData(0, self.PreviousCheckStateRole, item.checkState(0).value)
                    ancestors = (str(payload[2]), *ancestors)
                for i in range(item.childCount()):
                    visit(item.child(i), ancestors)
            for i in range(self.topLevelItemCount()):
                visit(self.topLevelItem(i))
        finally:
            self._updating = previous

    @staticmethod
    def layer_ancestors(item):
        keys = []
        item = item.parent()
        while item is not None:
            payload = item.data(0, Qt.ItemDataRole.UserRole)
            if payload and payload[1] == "crystal_layer":
                keys.append(str(payload[2]))
            item = item.parent()
        return tuple(keys)

    def find_object(self, document_id, kind, object_id):
        target = (document_id, kind, object_id)
        current = self.currentItem()
        if current is not None and current.data(0, Qt.ItemDataRole.UserRole) == target:
            return current

        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == target:
                return item
            for index in range(item.childCount()):
                found = visit(item.child(index))
                if found is not None:
                    return found
            return None

        for index in range(self.topLevelItemCount()):
            found = visit(self.topLevelItem(index))
            if found is not None:
                return found
        return None

    def _native_polyhedron_detail(self, document, row, count=None, layer_key=None):
        layer_key = layer_key or row.coordination_boundary_key or None
        label = row.label + (f" · {count} images in this candidate" if count is not None else "")
        item = (self._crystal_layer_item(document, layer_key, label) if layer_key is not None
                else self._leaf(document.id, "polyhedron", row.polyhedron_orbit_id, label))
        atoms = self._group(document.id, "category", "Atoms", object_id="atoms")
        labels = {site.id: site.label for site in document.structure.sites}
        atoms.addChild(self._leaf(document.id, "atom", row.source_site_id,
                                 labels[row.source_site_id] + " · centre"))
        for site_id, multiplicity in row.ligand_site_counts:
            atoms.addChild(self._leaf(document.id, "atom", site_id,
                                     f"{labels[site_id]} × {multiplicity}"))
        item.addChild(atoms)
        return item

    def _add_native_subtypes(self, parent, document, compound_class) -> None:
        ready = compound_class.subsystem is not None
        if not ready:
            pending = self._group(document.id, "category", "Connectivity — calculating…", object_id="polyhedra")
            pending.setFlags(pending.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            parent.addChild(pending)
            return
        labels = {site.id: site.label for site in document.structure.sites}
        view = document.inorganic_presentation()
        from craft.presentation.coordination_rows import group_polyhedron_rows
        rows_by_shell = {row.source_shell_id: row for row in group_polyhedron_rows(document,compound_class,view)}
        units = ({u.unit_orbit_id: u for u in compound_class.subsystem.representation.unit_orbits}
                 if ready else {})
        for assignment in compound_class.subtypes:
            coordination = " + ".join(coordination_group_label(compound_class.family, cn) for cn in assignment.coordination_numbers)
            label = f"{assignment.label} · {assignment.rank}D · {coordination}"
            if assignment.status != "supported":
                label += f" · {assignment.status}"
            item = self._crystal_layer_item(document, component_key(assignment), label)
            item.setToolTip(0, "\n".join((
                *assignment.evidence,
                "Centres: " + ", ".join(labels[key] for key in assignment.centre_site_ids),
                "Graph-cycle sizes count centre images, not independent site orbits: " + str(assignment.ring_sizes),
                f"Native ring search limit: {assignment.ring_search_max_vertices} graph vertices; {assignment.ring_search_status}.",
                *assignment.warnings,
                "The Polyhedra and Structural Blocks branches show the full host representation.",
                f"Subtype reference: {assignment.reference}",
            )))
            parent.addChild(item)
            motifs = self._group(document.id, "category", f"Ring candidates ({len(assignment.ring_motifs)})",
                                 object_id="polyhedra")
            motifs.setToolTip(0, "Bounded graph-cycle candidates. An empty candidate list does not prove absence of openings.\n"
                             + RING_OPENING_WARNING)
            item.addChild(motifs)
            for motif in assignment.ring_motifs:
                composition = " + ".join(f"{count} × {coordination_group_label(compound_class.family, cn)}" for cn, count in motif.coordination_counts)
                motif_item = self._crystal_layer_item(
                    document, motif.ring_orbit_id,
                    f"{ring_candidate_label(compound_class.family, motif)} · {composition}",
                )
                motif_item.setToolTip(0, "\n".join((
                    f"{motif.vertex_count} vertices in the selected native graph cycle.",
                    f"Native ring orbit: {motif.ring_orbit_id}; multiplicity: {motif.multiplicity}.",
                    "Polymerization subtype and graph-cycle candidates are independent descriptors.",
                    "Shortest-return chordless graph-cycle search; the candidate list is not exhaustive.",
                    RING_OPENING_WARNING,
                )))
                motifs.addChild(motif_item)
                orbit_units = {}
                for unit_id, count in motif.unit_image_counts:
                    row = rows_by_shell.get(units[unit_id].source_shell_orbit_id)
                    if row is not None:
                        orbit_units.setdefault(row.polyhedron_orbit_id, []).append((row, unit_id, count))
                for members in orbit_units.values():
                    row = members[0][0]
                    if len(members) > 1:
                        keys = tuple(ring_unit_key(motif.ring_orbit_id, unit_id) for _, unit_id, _ in members)
                        representative = self._native_polyhedron_detail(document, row, sum(count for _, _, count in members))
                        representative.setData(0, Qt.ItemDataRole.UserRole, (document.id, "crystal_layer_group", keys))
                        representative.setFlags(representative.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        representative.setToolTip(0, "One native polyhedron orbit. Color and visibility apply to its images in this candidate; expand Images to edit a particular image.")
                        images = self._group(document.id, "category", f"Images ({len(members)})", object_id="polyhedra")
                        for index, (_, unit_id, count) in enumerate(members, 1):
                            child = self._native_polyhedron_detail(document, row, count, ring_unit_key(motif.ring_orbit_id, unit_id))
                            child.setText(0, f"Image {index} · {count} in candidate")
                            images.addChild(child)
                        representative.addChild(images)
                        motif_item.addChild(representative)
                    else:
                        _, unit_id, count = members[0]
                        motif_item.addChild(self._native_polyhedron_detail(
                            document, row, count, ring_unit_key(motif.ring_orbit_id, unit_id)))
            for cn in assignment.coordination_numbers:
                group_item = self._crystal_layer_item(document, polyhedra_key(assignment, cn), coordination_group_label(compound_class.family, cn))
                for shell_id in dict.fromkeys(assignment.source_shell_ids):
                    row = rows_by_shell.get(shell_id)
                    if row is not None and row.coordination_number == cn:
                        group_item.addChild(self._native_polyhedron_detail(
                            document, row,
                            layer_key=component_polyhedron_key(assignment, row.polyhedron_orbit_id),
                        ))
                item.addChild(group_item)

    def _add_native_host_children(self, parent, document, view) -> None:
        polyhedra = self._group(
            document.id,
            "category",
            f"Polyhedra ({len(view.polyhedron_orbits)})",
            object_id="polyhedra",
        )
        for polyhedron in view.polyhedron_orbits:
            item = self._native_polyhedron_detail(document, polyhedron)
            item.setToolTip(0, f"Native polyhedron orbit; {len(polyhedron.polyhedron_ids)} symmetry copies in the reference cell.")
            polyhedra.addChild(item)
        parent.addChild(polyhedra)
        blocks = self._group(
            document.id,
            "category",
            f"Structural Blocks ({len(view.structural_blocks)})",
            object_id="units",
        )
        for block in view.structural_blocks:
            block_item = self._leaf(document.id, "block", block.block_id, block.label)
            block_rings = tuple(ring for ring in view.rings if ring.parent_block_id == block.block_id)
            if block_rings:
                rings = self._group(
                    document.id,
                    "category",
                    f"Graph cycles ({len(block_rings)})",
                    object_id="rings",
                )
                for ring in block_rings:
                    rings.addChild(self._leaf(
                        document.id, "ring", ring.ring_orbit_id, ring.label
                    ))
                block_item.addChild(rings)
            for row in view.polyhedron_orbits:
                if row.polyhedron_orbit_id in block.polyhedron_orbit_ids:
                    block_item.addChild(self._native_polyhedron_detail(document, row))
            blocks.addChild(block_item)
        parent.addChild(blocks)

    def _add_report_branch(
        self,
        root: QTreeWidgetItem,
        document: StructureDocument,
    ) -> None:
        draft = document.report_draft
        selected = len(draft.selected_table_ids) if draft is not None else 0
        available = len(draft.available_table_ids) if draft is not None else 0
        included = (
            sum(figure.include for figure in draft.figures) if draft is not None else 0
        )
        total = len(draft.figures) if draft is not None else 0
        references = len(draft.references) if draft is not None else 0
        report = self._group(document.id, "category", "Report", object_id="report")
        for section, label in (
            ("tables", f"Tables ({selected}/{available})"),
            ("figures", f"Figures ({included}/{total})"),
            ("text", f"Text ({references})"),
        ):
            item = self._group(
                document.id,
                "report_section",
                label,
                object_id=section,
            )
            report.addChild(item)
        root.addChild(report)

    def _add_structural_block_children(
        self,
        parent: QTreeWidgetItem,
        document: StructureDocument,
    ) -> None:
        """Nest calculated motifs under the structural block that owns them."""
        motifs = getattr(document, "ring_motifs", None)
        ring_orbits = motifs.ring_orbits if motifs is not None else ()
        rings_by_block: dict[str, list[object]] = {}
        for orbit in ring_orbits:
            key = orbit.parent_block_orbit_id or orbit.parent_block_id
            rings_by_block.setdefault(key, []).append(orbit)

        units = {item.id: item for item in document.hierarchy.structural_units}
        for identifiers in hierarchy_object_orbits(
            document, tuple(units.values())
        ):
            unit = units[identifiers[0]]
            block_item = self._group(
                document.id,
                "unit",
                self._unit_name(document, unit),
                object_id=unit.id,
            )
            parent.addChild(block_item)
            native_orbit_id = getattr(unit, "orbit_id", "")
            block_rings = list(rings_by_block.get(native_orbit_id, ()))
            if not native_orbit_id:
                block_rings = [
                    orbit
                    for identifier in identifiers
                    for orbit in rings_by_block.get(identifier, ())
                ]
            if not block_rings:
                continue
            rings_item = self._group(
                document.id,
                "category",
                f"Rings ({len(block_rings)})",
                object_id="rings",
            )
            block_item.addChild(rings_item)
            for scope in ("local", "framework"):
                scoped_rings = [
                    orbit for orbit in block_rings if orbit.scope == scope
                ]
                if not scoped_rings:
                    continue
                scope_item = self._group(
                    document.id,
                    "category",
                    f"{RING_SCOPE_LABELS[scope]} rings ({len(scoped_rings)})",
                    object_id=f"rings:{scope}",
                )
                rings_item.addChild(scope_item)
                for orbit in scoped_rings:
                    label = (
                        f"{orbit.formula} · {orbit.size}-membered "
                        f"· ×{orbit.multiplicity}"
                    )
                    scope_item.addChild(
                        self._leaf(document.id, "ring", orbit.orbit_id, label)
                    )

    @staticmethod
    def _unit_name(document: StructureDocument, unit) -> str:
        hierarchy = document.hierarchy
        direct_assignment = next(
            (item for item in hierarchy.nomenclature if item.domain_id == unit.id),
            None,
        )
        domain = next(
            (
                item
                for item in hierarchy.structural_domains
                if item.polyhedron_ids == unit.polyhedron_ids
            ),
            None,
        )
        if domain is None and direct_assignment is None:
            return unit.classification
        assignment = direct_assignment or next(
            (item for item in hierarchy.nomenclature if item.domain_id == domain.id),  # type: ignore[union-attr]
            None,
        )
        if assignment is None:
            return unit.classification
        if assignment.vocabulary == "borate" and "-membered ring" in unit.classification:
            generic = unit.classification.split(" · ", 1)[0]
            descriptor = assignment.descriptor.replace(
                f"{len(unit.polyhedron_ids)}-membered ",
                "",
                1,
            )
            return f"{generic} · {descriptor}"
        return f"{unit.classification} · {assignment.descriptor}"

    def _install_root_widget(
        self,
        item: QTreeWidgetItem,
        document: StructureDocument,
    ) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(1, 0, 3, 0)
        layout.setSpacing(7)
        button = QToolButton(container)
        button.setObjectName("structureCompareCheck")
        button.setCheckable(True)
        button.setFixedSize(20, 20)
        button.setToolTip("Select structure for comparison")
        button.setStyleSheet(
            "QToolButton { background: #ffffff; border: 1px solid #8da0b5; "
            "border-radius: 4px; color: #ffffff; font-weight: 800; padding: 0; }"
            "QToolButton:checked { background: #2678c8; border-color: #1f68b1; }"
        )
        selected = self._collection is not None and document.id in self._collection.compared_ids
        button.setChecked(selected)
        self._update_check_visual(button, selected)
        button.toggled.connect(
            lambda checked, document_id=document.id, current=button: self._root_toggled(
                document_id,
                current,
                checked,
            )
        )
        layout.addWidget(button)
        label = QLabel(self._document_name(document), container)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(label, 1)
        self.setItemWidget(item, 0, container)
        self._root_buttons.append(button)
        self._root_labels.append(label)

    @staticmethod
    def _update_check_visual(button: QToolButton, checked: bool) -> None:
        button.setText("✓" if checked else "")

    def _root_toggled(
        self,
        document_id: str,
        button: QToolButton,
        checked: bool,
    ) -> None:
        if self._updating:
            self._update_check_visual(button, checked)
            return
        if checked and sum(candidate.isChecked() for candidate in self._root_buttons) > 2:
            self._updating = True
            try:
                button.setChecked(False)
                self._update_check_visual(button, False)
            finally:
                self._updating = False
            return
        self._update_check_visual(button, checked)
        self.compare_toggled.emit(document_id, checked)

    def root_checkbox(self, index: int) -> QToolButton:
        return self._root_buttons[index]

    def root_label(self, index: int) -> QLabel:
        return self._root_labels[index]

    @staticmethod
    def _payload(document_id: str, kind: str, object_id: object) -> Payload:
        return document_id, kind, object_id

    def _group(
        self,
        document_id: str,
        kind: str,
        label: str,
        level: HierarchyLevel | None = None,
        object_id: object | None = None,
        table_category: str | None = None,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        resolved_id: object = level.value if level is not None else object_id if object_id is not None else label
        payload_kind = "level" if level is not None else kind
        item.setData(0, Qt.ItemDataRole.UserRole, self._payload(document_id, payload_kind, resolved_id))
        if table_category is not None:
            item.setData(0, self.TableCategoryRole, table_category)
        return item

    def _leaf(
        self,
        document_id: str,
        kind: str,
        object_id: object,
        label: str,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, self._payload(document_id, kind, object_id))
        return item

    def _current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        _previous: QTreeWidgetItem | None,
    ) -> None:
        if current is None:
            return
        payload = current.data(0, Qt.ItemDataRole.UserRole)
        if not payload:
            return
        document_id, kind, object_id = payload
        self.active_requested.emit(document_id)
        self.object_selected.emit(document_id, kind, object_id)

    def _item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._updating or column != 0:
            return
        payload = item.data(0, Qt.ItemDataRole.UserRole)
        if not payload or payload[1] not in {"contact_group", "crystal_layer", "crystal_layer_group"}:
            return
        current = item.checkState(0).value
        if item.data(0, self.PreviousCheckStateRole) == current:
            return
        self._updating = True
        try:
            item.setData(0, self.PreviousCheckStateRole, current)
        finally:
            self._updating = False
        document_id, kind, classification = payload
        self.visibility_changed.emit(
            document_id,
            kind,
            classification,
            item.checkState(0) == Qt.CheckState.Checked,
        )
