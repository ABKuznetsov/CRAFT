from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
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


Payload = tuple[str, str, object]


class HierarchyTree(QTreeWidget):
    """Collection-aware hierarchy browser with independent A/B/compare state."""

    active_requested = Signal(str)
    visual_slot_requested = Signal(str, str)
    compare_toggled = Signal(str, bool)
    visibility_changed = Signal(str, str, object, bool)
    object_selected = Signal(str, str, object)
    SearchTextRole = int(Qt.ItemDataRole.UserRole) + 20

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
            self.collapseAll()
            QTimer.singleShot(0, self.collapseAll)
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
                )
                if not descriptor.ready:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                root.addChild(item)
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

    def _add_native_inorganic_children(
        self,
        root: QTreeWidgetItem,
        document: StructureDocument,
    ) -> None:
        view = document.inorganic_presentation()
        root.addChild(self._leaf(document.id, "cell", "cell", "Unit Cell"))
        root.addChild(self._group(
            document.id, "category", f"Atoms ({len(view.atom_orbits)})", object_id="atoms"
        ))
        primary_bonds = {
            row.pair_label
            for row in view.contact_orbits
            if row.classification == "primary"
        }
        bonds = self._group(
            document.id,
            "category",
            f"Bonds ({len(primary_bonds)})",
            object_id="bonds",
        )
        root.addChild(bonds)
        root.addChild(self._group(
            document.id,
            "category",
            f"Polyhedra ({len(view.polyhedron_orbits)})",
            object_id="polyhedra",
        ))
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
                    f"Rings ({len(block_rings)})",
                    object_id="rings",
                )
                for ring in block_rings:
                    rings.addChild(self._leaf(
                        document.id, "ring", ring.ring_orbit_id, ring.label
                    ))
                block_item.addChild(rings)
            blocks.addChild(block_item)
        root.addChild(blocks)
        root.addChild(self._group(
            document.id, "category", "Mechanical Blocks (0)", object_id="blocks"
        ))
        root.addChild(self._group(
            document.id,
            "category",
            f"Topology ({len(view.topology_families)})",
            object_id="topology",
        ))

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
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        resolved_id: object = level.value if level is not None else object_id if object_id is not None else label
        payload_kind = "level" if level is not None else kind
        item.setData(0, Qt.ItemDataRole.UserRole, self._payload(document_id, payload_kind, resolved_id))
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
        if not payload or payload[1] != "contact_group":
            return
        document_id, kind, classification = payload
        self.visibility_changed.emit(
            document_id,
            kind,
            classification,
            item.checkState(0) == Qt.CheckState.Checked,
        )
