from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from craft.core.chemistry import site_colour
from craft.analysis.structural_motifs import (
    RING_SCOPE_COLORS,
    RING_SCOPE_LABELS,
)
from craft.core.site_orbits import (
    bond_families,
    connector_orbits,
    hierarchy_object_orbits,
    polyhedron_orbits,
    site_orbit_key,
    site_orbits,
)
from craft.analysis.reporting import resolve_reference


_SUBSCRIPT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_UNIT_COLORS = ("#2878b5", "#7b4ab8", "#008f7a", "#c05b2b", "#9a6b00")
_BLOCK_COLORS = ("#335c81", "#795548", "#536d3b", "#7a4d7b", "#8a6d1d")


class SitesPanel(QWidget):
    """One context-sensitive object table controlled by the hierarchy tree."""

    state_changed = Signal()
    report_draft_changed = Signal(object)
    organic_object_activated = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._document = None
        self._updating = False
        self._color_mode = "automatic"
        self._comparison_locked = False
        self._category = "atoms"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.topology_status = QLabel()
        self.topology_status.setWordWrap(True)
        self.topology_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.topology_status.hide()
        layout.addWidget(self.topology_status)
        self.stack = QStackedWidget()
        self.atom_table = self._table(("Site", "Color", "Visible"))
        self.bond_table = self._table(("Bond", "Gradient", "Visible"))
        self.contact_table = self._table(
            ("Type", "Interaction", "Distance, Å", "Color", "Visible")
        )
        self.polyhedron_table = self._table(("Polyhedron", "Color", "Visible"))
        self.unit_table = self._table(("Structural block", "Color", "Visible"))
        self.ring_table = self._table(
            ("Ring", "Type", "Parent block", "Color", "Visible")
        )
        self.block_table = self._table(("Mechanical block", "Color", "Visible"))
        self.interpretation_table = self._table(("Domain", "Interpretation"))
        self.connector_table = self._table(("Shared site", "Connection"))
        self.topology_table = self._table(
            ("Network", "Type", "Direction / plane", "Connections", "Visible")
        )
        self.organic_table = self._table(("Object", "Type", "Details", "Visible"))
        self.report_tables_table = self._table(("Table", "Availability", "Include"))
        self.report_figures_table = self._table(("Figure", "Kind", "State", "Include"))
        self.report_text_table = self._table(("Reference", "Target", "State"))
        self.tables = {
            "atoms": self.atom_table,
            "bonds": self.bond_table,
            "primary_contacts": self.contact_table,
            "secondary_contacts": self.contact_table,
            "polyhedra": self.polyhedron_table,
            "units": self.unit_table,
            "rings": self.ring_table,
            "interpretations": self.interpretation_table,
            "blocks": self.block_table,
            "connectors": self.connector_table,
            "topology": self.topology_table,
            "molecular_unit": self.organic_table,
            "molecular_rings": self.organic_table,
            "coordination_fragment": self.organic_table,
            "covalent_bonds": self.organic_table,
            "coordination_bonds": self.organic_table,
            "contacts": self.organic_table,
            "nodes_sbus": self.organic_table,
            "linkers": self.organic_table,
            "periodic_network": self.organic_table,
            "crystal_packing": self.organic_table,
            "report_tables": self.report_tables_table,
            "report_figures": self.report_figures_table,
            "report_text": self.report_text_table,
        }
        for table in dict.fromkeys(self.tables.values()):
            self.stack.addWidget(table)
        layout.addWidget(self.stack)
        self.atom_table.itemChanged.connect(self._atom_changed)
        self.bond_table.itemChanged.connect(self._bond_changed)
        self.contact_table.itemChanged.connect(self._contact_changed)
        self.contact_table.cellDoubleClicked.connect(self._contact_color_clicked)
        self.polyhedron_table.itemChanged.connect(self._polyhedron_changed)
        self.unit_table.itemChanged.connect(self._unit_changed)
        self.ring_table.itemChanged.connect(self._ring_changed)
        self.block_table.itemChanged.connect(self._block_changed)
        self.topology_table.itemChanged.connect(self._topology_changed)
        for table, callback in (
            (self.atom_table, self._atom_color_clicked),
            (self.polyhedron_table, self._polyhedron_color_clicked),
            (self.unit_table, self._unit_color_clicked),
            (self.block_table, self._block_color_clicked),
            (self.ring_table, self._ring_color_clicked),
        ):
            table.cellDoubleClicked.connect(callback)
        self.organic_table.cellDoubleClicked.connect(self._organic_double_clicked)
        self.organic_table.itemChanged.connect(self._organic_changed)
        self.report_tables_table.itemChanged.connect(self._report_tables_changed)
        self.report_figures_table.itemChanged.connect(self._report_figures_changed)
        self.set_category("atoms")

    @staticmethod
    def _table(headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        return table

    @staticmethod
    def _check_item(checked: bool) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        return item

    @staticmethod
    def _color_item(color: str, key: str) -> QTableWidgetItem:
        item = QTableWidgetItem("■")
        item.setData(Qt.ItemDataRole.UserRole, key)
        item.setForeground(QColor(color))
        item.setToolTip("Double-click to change color")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        return item

    @staticmethod
    def _name_item(text: str, key: object) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, key)
        return item

    def set_category(self, category: str) -> None:
        native = self._document is not None and hasattr(
            self._document.structure, "atomic_view"
        )
        table = (
            self.contact_table
            if native and category in {"bonds", "contacts"}
            else self.tables.get(category)
        )
        if table is not None:
            self._category = category
            if table is self.organic_table:
                self._fill_organic_table(category)
            elif table is self.contact_table:
                self._fill_contacts(
                    "primary_contacts" if native and category == "bonds" else category
                )
            self.stack.setCurrentWidget(table)
        self._update_topology_status_visibility()

    def current_table(self) -> QTableWidget:
        return self.stack.currentWidget()  # type: ignore[return-value]

    def select_object(self, kind: str, object_id: object) -> bool:
        """Show and select the symmetry-orbit row containing a scene object."""
        if self._document is None:
            return False
        native = hasattr(self._document.structure, "atomic_view")
        category = {
            "atom": "atoms",
            "bond": "bonds",
            "polyhedron": "polyhedra",
            "unit": "units",
            "ring": "rings",
            "block": "units" if native else "blocks",
        }.get(str(kind))
        if category is None:
            return False
        table = self.contact_table if native and category == "bonds" else self.tables[category]
        target = object_id
        if kind == "bond" and isinstance(object_id, str) and not native:
            presentation = getattr(self._document, "contact_presentation", None)
            row = next(
                (
                    item for item in getattr(presentation, "rows", ())
                    if item.contact_orbit_id == object_id
                ),
                None,
            )
            if row is None:
                return False
            category = f"{getattr(row.classification, 'value', row.classification)}_contacts"
            table = self.tables[category]
            self._fill_contacts(category)
        if kind == "atom" and not native:
            try:
                target = site_orbit_key(
                    self._document.legacy_projection.sites[int(object_id)].label
                )
            except (IndexError, TypeError, ValueError):
                return False
        elif kind == "polyhedron" and not native:
            polyhedron = next(
                (
                    item
                    for item in self._document.hierarchy.polyhedra
                    if item.id == str(object_id)
                ),
                None,
            )
            if polyhedron is None:
                return False
            target = polyhedron.polyhedron_orbit_id or polyhedron.id
        for row in range(table.rowCount()):
            key = self._key(table, row)
            matches = key == target
            if (
                (native and kind == "bond") or kind in {"unit", "block"}
            ) and isinstance(key, tuple):
                matches = str(object_id) in key
            if not matches:
                continue
            self.set_category(category)
            table.setCurrentCell(row, 0)
            table.selectRow(row)
            table.scrollToItem(table.item(row, 0))
            return True
        return False

    def set_document(self, document) -> None:
        self._document = document
        self._updating = True
        try:
            for table in self.tables.values():
                table.setRowCount(0)
            if document is None:
                return
            if hasattr(document.structure, "atomic_view"):
                self._fill_native_inorganic_tables()
                if self._category in {
                    "molecular_unit", "coordination_fragment", "molecular_rings",
                    "contacts", "nodes_sbus", "linkers",
                    "periodic_network", "crystal_packing",
                }:
                    self._fill_organic_table(self._category)
                self._fill_report_tables()
                self._fill_report_figures()
                self._fill_report_text()
                self._update_color_availability()
                self._update_topology_status_visibility()
                return
            self._fill_atoms()
            self._fill_bonds()
            if self._category in {"primary_contacts", "secondary_contacts"}:
                self._fill_contacts(self._category)
            self._fill_polyhedra()
            self._fill_units()
            self._fill_rings()
            self._fill_blocks()
            self._fill_read_only_tables()
            self._fill_report_tables()
            self._fill_report_figures()
            self._fill_report_text()
            if self._category in {
                "molecular_unit", "coordination_fragment", "covalent_bonds",
                "coordination_bonds", "contacts", "nodes_sbus", "linkers",
                "periodic_network", "crystal_packing",
            }:
                self._fill_organic_table(self._category)
            self._update_color_availability()
            self._update_topology_status_visibility()
        finally:
            self._updating = False

    def _fill_native_inorganic_tables(self) -> None:
        view = self._document.inorganic_presentation()
        for row, atom in enumerate(view.atom_orbits):
            self.atom_table.insertRow(row)
            self.atom_table.setItem(
                row, 0, self._name_item(atom.label, atom.source_site_id)
            )
            color = self._document.visual.atom_orbit_colors.get(
                atom.source_site_id, atom.default_color
            )
            self.atom_table.setItem(
                row, 1, self._color_item(color, atom.source_site_id)
            )
            self.atom_table.setItem(row, 2, self._check_item(
                atom.source_site_id not in self._document.visual.hidden_atom_orbit_ids
            ))
        contact_category = self._category if self._category in {
            "contacts", "primary_contacts", "secondary_contacts"
        } else "primary_contacts" if self._category == "bonds" else "contacts"
        self._fill_contacts(contact_category)
        for row, polyhedron in enumerate(view.polyhedron_orbits):
            self.polyhedron_table.insertRow(row)
            identifier = polyhedron.polyhedron_orbit_id
            self.polyhedron_table.setItem(
                row, 0, self._name_item(polyhedron.label, identifier)
            )
            color = self._document.visual.polyhedron_orbit_colors.get(
                identifier, polyhedron.default_color
            )
            self.polyhedron_table.setItem(row, 1, self._color_item(color, identifier))
            self.polyhedron_table.setItem(row, 2, self._check_item(
                identifier not in self._document.visual.hidden_polyhedron_orbit_ids
            ))
        for row, block in enumerate(view.structural_blocks):
            self.unit_table.insertRow(row)
            self.unit_table.setItem(row, 0, self._name_item(block.label, block.block_id))
            color = self._document.visual.block_colors.get(
                block.block_id, _UNIT_COLORS[row % len(_UNIT_COLORS)]
            )
            self.unit_table.setItem(row, 1, self._color_item(color, block.block_id))
            self.unit_table.setItem(row, 2, self._check_item(
                block.block_id in self._document.visual.shown_block_ids
            ))
        for row, ring in enumerate(view.rings):
            self.ring_table.insertRow(row)
            self.ring_table.setItem(
                row, 0, self._name_item(ring.label, ring.ring_orbit_id)
            )
            self.ring_table.setItem(row, 1, QTableWidgetItem(ring.scope.replace("_", " ")))
            self.ring_table.setItem(row, 2, QTableWidgetItem(ring.parent_block_id))
            color = self._document.visual.ring_scope_colors.get(ring.scope, "#1f78b4")
            self.ring_table.setItem(row, 3, self._color_item(color, ring.scope))
            self.ring_table.setItem(row, 4, self._check_item(
                ring.ring_orbit_id in self._document.visual.shown_ring_ids
            ))
        for row, topology in enumerate(view.topology_families):
            self.topology_table.insertRow(row)
            self.topology_table.setItem(
                row, 0, self._name_item(topology.label, topology.topology_id)
            )
            self.topology_table.setItem(row, 1, QTableWidgetItem(f"{topology.rank}D"))
            self.topology_table.setItem(row, 2, QTableWidgetItem("—"))
            self.topology_table.setItem(row, 3, QTableWidgetItem("native component"))
            self.topology_table.setItem(row, 4, self._check_item(
                topology.topology_id not in self._document.visual.hidden_topology_family_ids
            ))

    def _fill_report_tables(self) -> None:
        table = self.report_tables_table
        draft = getattr(self._document, "report_draft", None)
        if draft is None:
            return
        selected = set(draft.selected_table_ids)
        for row, table_id in enumerate(draft.available_table_ids):
            table.insertRow(row)
            table.setItem(row, 0, self._name_item(table_id, table_id))
            table.setItem(row, 1, QTableWidgetItem("Available"))
            table.setItem(row, 2, self._check_item(table_id in selected))

    def _fill_report_figures(self) -> None:
        table = self.report_figures_table
        draft = getattr(self._document, "report_draft", None)
        if draft is None:
            return
        for row, figure in enumerate(draft.figures):
            table.insertRow(row)
            table.setItem(row, 0, self._name_item(figure.title, figure.id))
            table.setItem(row, 1, QTableWidgetItem(figure.kind.value))
            table.setItem(row, 2, QTableWidgetItem("Stale" if figure.stale else "Ready"))
            table.setItem(row, 3, self._check_item(figure.include))

    def _fill_report_text(self) -> None:
        table = self.report_text_table
        draft = getattr(self._document, "report_draft", None)
        if draft is None:
            return
        for row, reference in enumerate(draft.references):
            resolved = resolve_reference(draft, reference)
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(resolved.label))
            table.setItem(row, 1, QTableWidgetItem(reference.target_id))
            table.setItem(row, 2, QTableWidgetItem("Ready" if resolved.resolved else resolved.message))

    def _report_tables_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 2 or self._document is None:
            return
        draft = self._document.report_draft
        if draft is None:
            return
        selected = tuple(
            table_id
            for row, table_id in enumerate(draft.available_table_ids)
            if self.report_tables_table.item(row, 2).checkState() == Qt.CheckState.Checked
        )
        self._document.report_draft = draft.with_tables(selected)
        self.report_draft_changed.emit(self._document.report_draft)

    def _report_figures_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 3 or self._document is None:
            return
        draft = self._document.report_draft
        if draft is None or not (0 <= item.row() < len(draft.figures)):
            return
        figure = draft.figures[item.row()]
        updated = replace(
            figure,
            include=item.checkState() == Qt.CheckState.Checked,
        )
        self._document.report_draft = draft.with_figure(updated)
        self.report_draft_changed.emit(self._document.report_draft)

    def _fill_organic_table(self, category: str) -> None:
        table = self.organic_table
        was_blocked = table.blockSignals(True)
        table.setRowCount(0)
        native = self._document.organic_presentation()
        if getattr(self._document.scientific.molecular, "result", None) is not None:
            rows: list[tuple[str, str, str]] = []
            if category == "molecular_unit":
                rows.extend(
                    (
                        item.orbit_id,
                        "molecule" if item.periodic_rank == 0 else f"{item.periodic_rank}D component",
                        f"{len(item.independent_site_ids)} independent sites · ×{item.multiplicity}",
                    )
                    for item in native.components
                )
            elif category == "molecular_rings":
                rows.extend(
                    (
                        item.orbit_id,
                        "molecular ring",
                        f"{len(item.atom_refs)} atoms · ×{item.multiplicity}",
                    )
                    for item in native.rings
                )
            elif category == "contacts":
                rows.extend(
                    (
                        item.orbit_id,
                        "intermolecular contact",
                        f"{item.representative_distance:.3f} Å · ×{item.multiplicity}",
                    )
                    for item in native.contacts
                )
            elif category in {"coordination_fragment", "nodes_sbus"}:
                rows.extend(
                    (
                        item.orbit_id,
                        "SBU",
                        f"{len(item.node_orbit_ids)} node orbit(s) · ×{item.multiplicity}",
                    )
                    for item in native.sbus
                )
                if not rows:
                    rows.extend(
                        (
                            item.orbit_id,
                            "coordination node",
                            f"{item.center_site_id} · ×{item.multiplicity}",
                        )
                        for item in native.nodes
                    )
            elif category == "linkers":
                rows.extend(
                    (
                        item.orbit_id,
                        str(getattr(item.role, "value", item.role)).replace("_", " "),
                        f"connectivity {item.attachment_count} · ×{item.multiplicity}",
                    )
                    for item in native.linkers
                )
            elif category == "periodic_network":
                rows.extend(
                    (
                        item.orbit_id,
                        "net edge",
                        f"{item.first_vertex_orbit_id} → {item.second_vertex_orbit_id} · ×{item.multiplicity}",
                    )
                    for item in native.net_edges
                )
            elif category == "crystal_packing":
                rows.extend(
                    (
                        item.orbit_id,
                        "packing connection",
                        f"{item.first_component_orbit_id} → {item.second_component_orbit_id} · ×{item.multiplicity}",
                    )
                    for item in native.packing_connections
                )
                if not rows:
                    rows.append(("packing", "crystal packing", "no connection orbits"))
            for row, values in enumerate(rows):
                table.insertRow(row)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if column == 0:
                        item.setData(Qt.ItemDataRole.UserRole, value)
                    table.setItem(row, column, item)
                table.setItem(row, 3, self._check_item(True))
            table.blockSignals(was_blocked)
            return

        table.blockSignals(was_blocked)

    def _organic_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 3 or item.checkState() != Qt.CheckState.Checked:
            return
        self._organic_activate_row(item.row())

    def _organic_double_clicked(self, row: int, _column: int) -> None:
        self._organic_activate_row(row)

    def _organic_activate_row(self, row: int) -> None:
        if self._document is None or not (0 <= row < self.organic_table.rowCount()):
            return
        item = self.organic_table.item(row, 0)
        if item is None:
            return
        identifier = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self.organic_object_activated.emit(self._category, str(identifier))

    def _update_topology_status_visibility(self) -> None:
        is_contacts = self.stack.currentWidget() is self.contact_table
        presentation = getattr(self._document, "contact_presentation", None)
        if is_contacts and presentation is not None:
            raw_status = getattr(presentation, "scientific_status", "")
            status = str(getattr(raw_status, "value", raw_status)).lower()
            diagnostics = tuple(getattr(presentation, "diagnostics", ()))
            if status in {"ambiguous", "incomplete"} or diagnostics:
                messages = [
                    str(getattr(item, "message", item)) for item in diagnostics
                ]
                self.topology_status.setText(
                    " ".join((status.capitalize() + ".", *messages)).strip()
                )
                self.topology_status.show()
                return
        report = getattr(self._document, "inorganic_topology", None)
        is_topology = self.stack.currentWidget() is self.topology_table
        unavailable = report is not None and not report.interpretable
        if unavailable:
            self.topology_status.setText(
                " ".join(report.warnings) or "Topology could not be evaluated."
            )
        else:
            self.topology_status.clear()
        self.topology_status.setVisible(is_topology and unavailable)

    def set_color_mode(self, mode: str) -> None:
        self._color_mode = str(mode).strip().lower().replace(" ", "_")
        self._update_color_availability()

    def set_comparison_locked(self, locked: bool) -> None:
        self._comparison_locked = bool(locked)
        self._update_color_availability()

    def _update_color_availability(self) -> None:
        editable = {
            "atoms": True,
            "polyhedra": self._color_mode in {"automatic", "element"},
            "units": True,
            "blocks": self._color_mode != "automatic",
        }
        for category, table in (
            ("atoms", self.atom_table),
            ("polyhedra", self.polyhedron_table),
            ("units", self.unit_table),
            ("blocks", self.block_table),
        ):
            enabled = editable[category] and not self._comparison_locked
            for row in range(table.rowCount()):
                item = table.item(row, 1)
                if item is None:
                    continue
                flags = item.flags()
                item.setFlags(
                    flags | Qt.ItemFlag.ItemIsEnabled
                    if enabled
                    else flags & ~Qt.ItemFlag.ItemIsEnabled
                )
                item.setToolTip(
                    "Double-click to change color"
                    if enabled
                    else "Color is controlled by the active coloring mode"
                )

    def _fill_atoms(self) -> None:
        document = self._document
        orbits = site_orbits(document.legacy_projection)
        for row, site in enumerate(document.legacy_projection.asymmetric_sites):
            key = site_orbit_key(site.label)
            indices = orbits.get(key, ())
            self.atom_table.insertRow(row)
            self.atom_table.setItem(row, 0, self._name_item(site.label, key))
            color = document.visual.atom_orbit_colors.get(key, site_colour(site))
            self.atom_table.setItem(row, 1, self._color_item(color, key))
            visible = not any(index in document.visual.hidden_atom_indices for index in indices)
            self.atom_table.setItem(row, 2, self._check_item(visible))

    def _bond_families(self) -> list[tuple[str, str]]:
        return list(bond_families(self._document))

    def _fill_bonds(self) -> None:
        for row, pair in enumerate(self._bond_families()):
            self.bond_table.insertRow(row)
            self.bond_table.setItem(row, 0, self._name_item("—".join(pair), pair))
            gradient = QTableWidgetItem("■  →  ■")
            gradient.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.bond_table.setItem(row, 1, gradient)
            visible = pair not in self._document.visual.hidden_bond_families
            self.bond_table.setItem(row, 2, self._check_item(visible))

    def _fill_contacts(self, category: str) -> None:
        table = self.contact_table
        was_blocked = table.blockSignals(True)
        table.setRowCount(0)
        classification = category.removesuffix("_contacts")
        if hasattr(self._document.structure, "atomic_view"):
            rows = self._document.inorganic_presentation().contact_orbits
            if category != "contacts":
                rows = tuple(row for row in rows if row.classification == classification)
            grouped: dict[str, list[object]] = {}
            for contact in rows:
                grouped.setdefault(contact.pair_label or contact.label, []).append(contact)
            for index, (pair_label, contacts) in enumerate(grouped.items()):
                table.insertRow(index)
                identifiers = tuple(contact.contact_orbit_id for contact in contacts)
                table.setItem(index, 0, self._name_item(pair_label, identifiers))
                layers = sorted({
                    contact.interaction_layer.replace("_", " ")
                    for contact in contacts
                })
                table.setItem(index, 1, QTableWidgetItem(", ".join(layers)))
                distance_min = min(contact.distance_min for contact in contacts)
                distance_max = max(contact.distance_max for contact in contacts)
                distance = (
                    f"{distance_min:.3f}"
                    if abs(distance_max - distance_min) < 1e-9
                    else f"{distance_min:.3f}–{distance_max:.3f}"
                )
                table.setItem(index, 2, QTableWidgetItem(distance))
                color = self._document.visual.contact_orbit_colors.get(identifiers[0], "#7f8791")
                table.setItem(index, 3, self._color_item(color, identifiers))
                table.setItem(index, 4, self._check_item(
                    all(
                        identifier not in self._document.visual.hidden_contact_orbit_ids
                        for identifier in identifiers
                    )
                ))
            table.blockSignals(was_blocked)
            return
        presentation = getattr(self._document, "contact_presentation", None)
        rows = (
            row for row in getattr(presentation, "rows", ())
            if getattr(row.classification, "value", row.classification) == classification
        )
        for index, contact in enumerate(rows):
            table.insertRow(index)
            identifier = contact.contact_orbit_id
            contact_type = getattr(contact.interaction_type, "value", contact.interaction_type)
            interaction = getattr(contact.interaction_layer, "value", contact.interaction_layer)
            table.setItem(index, 0, self._name_item(str(contact_type), identifier))
            table.setItem(index, 1, QTableWidgetItem(str(interaction).replace("_", " ")))
            distance = (
                f"{contact.distance_min:.3f}"
                if abs(contact.distance_max - contact.distance_min) < 1e-9
                else f"{contact.distance_min:.3f}–{contact.distance_max:.3f}"
            )
            table.setItem(index, 2, QTableWidgetItem(distance))
            color = self._document.visual.contact_orbit_colors.get(identifier, "#7f8791")
            table.setItem(index, 3, self._color_item(color, identifier))
            table.setItem(index, 4, self._check_item(
                identifier not in self._document.visual.hidden_contact_orbit_ids
            ))
        table.blockSignals(was_blocked)

    def _fill_polyhedra(self) -> None:
        document = self._document
        first_by_key = {}
        for polyhedron in document.hierarchy.polyhedra:
            key = polyhedron.polyhedron_orbit_id or polyhedron.id
            first_by_key.setdefault(key, polyhedron)
        for row, (key, ids) in enumerate(polyhedron_orbits(document).items()):
            polyhedron = first_by_key[key]
            site = document.legacy_projection.sites[polyhedron.center_index]
            coordination = str(polyhedron.coordination_number).translate(_SUBSCRIPT)
            formula = (
                f"{site_orbit_key(site.label)}"
                f"{polyhedron.ligand_element}{coordination}"
            )
            self.polyhedron_table.insertRow(row)
            self.polyhedron_table.setItem(row, 0, self._name_item(formula, key))
            color = document.visual.polyhedron_orbit_colors.get(key, site_colour(site))
            self.polyhedron_table.setItem(row, 1, self._color_item(color, key))
            visible = not any(identifier in document.visual.hidden_polyhedron_ids for identifier in ids)
            self.polyhedron_table.setItem(row, 2, self._check_item(visible))

    def _fill_units(self) -> None:
        units = {item.id: item for item in self._document.hierarchy.structural_units}
        for row, identifiers in enumerate(
            hierarchy_object_orbits(self._document, tuple(units.values()))
        ):
            unit = units[identifiers[0]]
            self.unit_table.insertRow(row)
            self.unit_table.setItem(
                row, 0, self._name_item(self._aggregate_name(unit), identifiers)
            )
            color = self._document.visual.unit_colors.get(
                identifiers[0], _UNIT_COLORS[row % len(_UNIT_COLORS)]
            )
            self.unit_table.setItem(row, 1, self._color_item(color, identifiers))
            self.unit_table.setItem(
                row,
                2,
                self._check_item(
                    all(
                        identifier in self._document.visual.shown_unit_ids
                        for identifier in identifiers
                    )
                ),
            )

    def _fill_rings(self) -> None:
        motifs = getattr(self._document, "ring_motifs", None)
        if motifs is None:
            return
        units = {
            item.id: item for item in self._document.hierarchy.structural_units
        }
        units_by_orbit = {
            item.orbit_id: item
            for item in self._document.hierarchy.structural_units
            if getattr(item, "orbit_id", "")
        }
        for row, orbit in enumerate(motifs.ring_orbits):
            parent = units_by_orbit.get(
                orbit.parent_block_orbit_id
            ) or units.get(orbit.parent_block_id)
            parent_name = (
                self._aggregate_name(parent)
                if parent is not None
                else orbit.parent_block_id
            )
            size = str(orbit.size).translate(_SUBSCRIPT)
            label = f"{orbit.formula} ring · {size}-membered · ×{orbit.multiplicity}"
            self.ring_table.insertRow(row)
            self.ring_table.setItem(
                row, 0, self._name_item(label, orbit.orbit_id)
            )
            scope_label = RING_SCOPE_LABELS.get(orbit.scope, orbit.scope.title())
            self.ring_table.setItem(row, 1, QTableWidgetItem(scope_label))
            self.ring_table.setItem(row, 2, QTableWidgetItem(parent_name))
            color = self._document.visual.ring_scope_colors.get(
                orbit.scope, RING_SCOPE_COLORS.get(orbit.scope, "#1f78b4")
            )
            self.ring_table.setItem(row, 3, self._color_item(color, orbit.scope))
            self.ring_table.setItem(
                row,
                4,
                self._check_item(
                    orbit.orbit_id in self._document.visual.shown_ring_ids
                ),
            )

    def _fill_blocks(self) -> None:
        blocks = {item.id: item for item in self._document.hierarchy.blocks}
        for row, identifiers in enumerate(
            hierarchy_object_orbits(self._document, tuple(blocks.values()))
        ):
            block = blocks[identifiers[0]]
            self.block_table.insertRow(row)
            self.block_table.setItem(
                row, 0, self._name_item(self._aggregate_name(block), identifiers)
            )
            color = self._document.visual.block_colors.get(
                identifiers[0], _BLOCK_COLORS[row % len(_BLOCK_COLORS)]
            )
            self.block_table.setItem(row, 1, self._color_item(color, identifiers))
            self.block_table.setItem(
                row,
                2,
                self._check_item(
                    all(
                        identifier in self._document.visual.shown_block_ids
                        for identifier in identifiers
                    )
                ),
            )

    def _aggregate_name(self, item) -> str:
        polyhedra = {
            polyhedron.id: polyhedron
            for polyhedron in self._document.hierarchy.polyhedra
        }
        labels = tuple(
            dict.fromkeys(
                site_orbit_key(
                    self._document.legacy_projection.sites[
                        polyhedra[identifier].center_index
                    ].label
                )
                for identifier in item.polyhedron_ids
                if identifier in polyhedra
            )
        )
        return (
            f"{item.classification} · {'/'.join(labels)}"
            if labels
            else item.classification
        )

    def _fill_read_only_tables(self) -> None:
        for row, domain in enumerate(self._document.hierarchy.structural_domains):
            self.interpretation_table.insertRow(row)
            self.interpretation_table.setItem(row, 0, QTableWidgetItem(domain.id))
            self.interpretation_table.setItem(row, 1, QTableWidgetItem(domain.classification))
        connectors = {
            connector.id: connector for connector in self._document.hierarchy.connectors
        }
        for row, identifiers in enumerate(connector_orbits(self._document)):
            connector = connectors[identifiers[0]]
            labels = tuple(
                dict.fromkeys(
                    site_orbit_key(self._document.legacy_projection.sites[index].label)
                    for index in connector.ligand_indices
                )
            )
            self.connector_table.insertRow(row)
            self.connector_table.setItem(
                row,
                0,
                QTableWidgetItem("/".join(labels) if labels else connector.id),
            )
            self.connector_table.setItem(row, 1, QTableWidgetItem(connector.kind))
        report = self._document.inorganic_topology
        if report is None:
            return
        families = (*report.families, *report.cation_families)
        for row, family in enumerate(families):
            self.topology_table.insertRow(row)
            name = "/".join(family.building_units) or family.id
            if family.representation == "cation":
                name += " · cation network"
            self.topology_table.setItem(row, 0, self._name_item(name, family.id))
            self.topology_table.setItem(row, 1, QTableWidgetItem(family.classification))
            self.topology_table.setItem(
                row, 2, QTableWidgetItem(self._topology_orientation(family))
            )
            connections = " · ".join(
                f"{kind}: {count}" for kind, count in family.connection_counts
            )
            if family.distance_range is not None:
                minimum, maximum = family.distance_range
                distance = (
                    f"d: {minimum:.2f} Å"
                    if abs(maximum - minimum) < 0.005
                    else f"d: {minimum:.2f}–{maximum:.2f} Å"
                )
                connections = " · ".join(filter(None, (connections, distance)))
            self.topology_table.setItem(row, 3, QTableWidgetItem(connections or "—"))
            self.topology_table.setItem(
                row,
                4,
                self._check_item(
                    family.id not in self._document.visual.hidden_topology_family_ids
                ),
            )

    @staticmethod
    def _topology_orientation(family) -> str:
        if family.periodic_rank == 0:
            return "finite"
        if family.periodic_rank == 3:
            return "3D"
        if family.periodic_rank == 2 and family.plane_normal is not None:
            return "(" + " ".join(str(value) for value in family.plane_normal) + ")"
        if family.directions:
            return " · ".join(
                "[" + " ".join(str(value) for value in direction) + "]"
                for direction in family.directions
            )
        return "—"

    @staticmethod
    def _key(table: QTableWidget, row: int):
        return table.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def _atom_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 2:
            return
        key = self._key(self.atom_table, item.row())
        visible = item.checkState() == Qt.CheckState.Checked
        if hasattr(self._document.structure, "atomic_view"):
            hidden = self._document.visual.hidden_atom_orbit_ids
            hidden.discard(key) if visible else hidden.add(key)
            self.state_changed.emit()
            return
        hidden = self._document.visual.hidden_atom_indices
        for index in site_orbits(self._document.legacy_projection).get(key, ()):
            if visible:
                hidden.discard(index)
                for values in self._document.visual.unit_auto_hidden_atoms.values():
                    values.discard(index)
            else:
                hidden.add(index)
        self.state_changed.emit()

    def _bond_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 2:
            return
        pair = self._key(self.bond_table, item.row())
        hidden = self._document.visual.hidden_bond_families
        hidden.discard(pair) if item.checkState() == Qt.CheckState.Checked else hidden.add(pair)
        self.state_changed.emit()

    def _contact_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 4:
            return
        key = self._key(self.contact_table, item.row())
        identifiers = key if isinstance(key, tuple) else (str(key),)
        hidden = self._document.visual.hidden_contact_orbit_ids
        for identifier in identifiers:
            hidden.discard(identifier) if item.checkState() == Qt.CheckState.Checked else hidden.add(identifier)
        self.state_changed.emit()

    def _polyhedron_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 2:
            return
        key = self._key(self.polyhedron_table, item.row())
        visible = item.checkState() == Qt.CheckState.Checked
        if hasattr(self._document.structure, "atomic_view"):
            hidden = self._document.visual.hidden_polyhedron_orbit_ids
            hidden.discard(key) if visible else hidden.add(key)
            self.state_changed.emit()
            return
        hidden = self._document.visual.hidden_polyhedron_ids
        for identifier in polyhedron_orbits(self._document).get(key, ()):
            if visible:
                hidden.discard(identifier)
                for values in self._document.visual.unit_auto_hidden_polyhedra.values():
                    values.discard(identifier)
            else:
                hidden.add(identifier)
        self.state_changed.emit()

    def _sync_constituent_visibility_checks(self) -> None:
        """Reflect block-driven visibility changes without rebuilding the tables."""
        document = self._document
        if document is None:
            return
        atom_orbits = site_orbits(document.legacy_projection)
        polyhedron_groups = polyhedron_orbits(document)
        previous = self._updating
        self._updating = True
        try:
            for row in range(self.atom_table.rowCount()):
                item = self.atom_table.item(row, 2)
                if item is None:
                    continue
                indices = atom_orbits.get(self._key(self.atom_table, row), ())
                visible = not any(
                    index in document.visual.hidden_atom_indices
                    for index in indices
                )
                item.setCheckState(
                    Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
                )
            for row in range(self.polyhedron_table.rowCount()):
                item = self.polyhedron_table.item(row, 2)
                if item is None:
                    continue
                identifiers = polyhedron_groups.get(
                    self._key(self.polyhedron_table, row), ()
                )
                visible = not any(
                    identifier in document.visual.hidden_polyhedron_ids
                    for identifier in identifiers
                )
                item.setCheckState(
                    Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked
                )
        finally:
            self._updating = previous

    def _unit_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 2:
            return
        identifiers = self._key(self.unit_table, item.row())
        if hasattr(self._document.structure, "atomic_view"):
            shown = self._document.visual.shown_block_ids
            block = self._document.inorganic_presentation().block(str(identifiers))
            if item.checkState() == Qt.CheckState.Checked:
                shown.add(str(identifiers))
                self._document.visual.block_auto_hidden_atom_ids[block.block_id] = (
                    block.internal_atom_ids
                )
                self._document.visual.block_auto_hidden_polyhedron_orbit_ids[
                    block.block_id
                ] = frozenset(block.polyhedron_orbit_ids)
            else:
                shown.discard(str(identifiers))
                self._document.visual.block_auto_hidden_atom_ids.pop(block.block_id, None)
                self._document.visual.block_auto_hidden_polyhedron_orbit_ids.pop(
                    block.block_id, None
                )
            self.state_changed.emit()
            return
        visual = self._document.visual
        shown = visual.shown_unit_ids
        units = {unit.id: unit for unit in self._document.hierarchy.structural_units}
        connector_atoms = {
            index
            for connector in self._document.hierarchy.connectors
            for index in connector.ligand_indices
        }
        checked = item.checkState() == Qt.CheckState.Checked
        for identifier in identifiers:
            unit = units.get(identifier)
            if checked:
                shown.add(identifier)
                if unit is None:
                    continue
                internal_atoms = set(unit.atom_indices) - connector_atoms
                already_auto_hidden_atoms = (
                    set().union(*visual.unit_auto_hidden_atoms.values())
                    if visual.unit_auto_hidden_atoms
                    else set()
                )
                already_auto_hidden_polyhedra = (
                    set().union(*visual.unit_auto_hidden_polyhedra.values())
                    if visual.unit_auto_hidden_polyhedra
                    else set()
                )
                newly_hidden_atoms = internal_atoms & (
                    (set(range(len(self._document.legacy_projection.sites)))
                     - visual.hidden_atom_indices)
                    | already_auto_hidden_atoms
                )
                newly_hidden_polyhedra = set(unit.polyhedron_ids) & (
                    (set(unit.polyhedron_ids) - visual.hidden_polyhedron_ids)
                    | already_auto_hidden_polyhedra
                )
                visual.unit_auto_hidden_atoms[identifier] = newly_hidden_atoms
                visual.unit_auto_hidden_polyhedra[identifier] = newly_hidden_polyhedra
                visual.hidden_atom_indices.update(newly_hidden_atoms)
                visual.hidden_polyhedron_ids.update(newly_hidden_polyhedra)
            else:
                shown.discard(identifier)
                atoms = visual.unit_auto_hidden_atoms.pop(identifier, set())
                polyhedra = visual.unit_auto_hidden_polyhedra.pop(identifier, set())
                still_hidden_atoms = set().union(
                    *visual.unit_auto_hidden_atoms.values()
                ) if visual.unit_auto_hidden_atoms else set()
                still_hidden_polyhedra = set().union(
                    *visual.unit_auto_hidden_polyhedra.values()
                ) if visual.unit_auto_hidden_polyhedra else set()
                visual.hidden_atom_indices.difference_update(atoms - still_hidden_atoms)
                visual.hidden_polyhedron_ids.difference_update(
                    polyhedra - still_hidden_polyhedra
                )
        self._sync_constituent_visibility_checks()
        self.state_changed.emit()

    def _ring_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 4:
            return
        identifier = str(self._key(self.ring_table, item.row()))
        shown = self._document.visual.shown_ring_ids
        if item.checkState() == Qt.CheckState.Checked:
            shown.add(identifier)
        else:
            shown.discard(identifier)
        self.state_changed.emit()

    def set_ring_scope_color(self, scope: str, color: str) -> None:
        self._set_color("ring_scope_colors", scope, color)

    def _block_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 2:
            return
        identifiers = self._key(self.block_table, item.row())
        shown = self._document.visual.shown_block_ids
        for identifier in identifiers:
            shown.add(identifier) if item.checkState() == Qt.CheckState.Checked else shown.discard(identifier)
        self.state_changed.emit()

    def _topology_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or self._document is None or item.column() != 4:
            return
        identifier = self._key(self.topology_table, item.row())
        hidden = self._document.visual.hidden_topology_family_ids
        if item.checkState() == Qt.CheckState.Checked:
            hidden.discard(identifier)
        else:
            hidden.add(identifier)
        self.state_changed.emit()

    def set_atom_color(self, key: str, color: str) -> None:
        self._set_color("atom_orbit_colors", key, color)

    def set_polyhedron_color(self, key: str, color: str) -> None:
        self._set_color("polyhedron_orbit_colors", key, color)

    def set_unit_color(self, identifiers: tuple[str, ...], color: str) -> None:
        self._set_color("unit_colors", identifiers, color)

    def set_block_color(self, identifiers: tuple[str, ...], color: str) -> None:
        self._set_color("block_colors", identifiers, color)

    def _set_color(self, attribute: str, key, color: str) -> None:
        if self._document is None:
            return
        identifiers = key if isinstance(key, tuple) else (key,)
        for identifier in identifiers:
            getattr(self._document.visual, attribute)[identifier] = QColor(color).name()
        self.set_document(self._document)
        self.state_changed.emit()

    def _choose_color(self, table: QTableWidget, row: int, column: int, attribute: str) -> None:
        if column != 1 or self._document is None:
            return
        if not table.item(row, column).flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        key = self._key(table, row)
        color = QColorDialog.getColor(table.item(row, 1).foreground().color(), self, "Object color")
        if color.isValid():
            self._set_color(attribute, key, color.name())

    def _atom_color_clicked(self, row: int, column: int) -> None:
        self._choose_color(self.atom_table, row, column, "atom_orbit_colors")

    def _contact_color_clicked(self, row: int, column: int) -> None:
        if column != 3 or self._document is None:
            return
        item = self.contact_table.item(row, column)
        if item is None:
            return
        color = QColorDialog.getColor(item.foreground().color(), self, "Contact color")
        if color.isValid():
            key = self._key(self.contact_table, row)
            identifiers = key if isinstance(key, tuple) else (key,)
            for identifier in identifiers:
                self._document.visual.contact_orbit_colors[identifier] = color.name()
            self.set_document(self._document)
            self.state_changed.emit()

    def _polyhedron_color_clicked(self, row: int, column: int) -> None:
        self._choose_color(self.polyhedron_table, row, column, "polyhedron_orbit_colors")

    def _unit_color_clicked(self, row: int, column: int) -> None:
        self._choose_color(self.unit_table, row, column, "unit_colors")

    def _ring_color_clicked(self, row: int, column: int) -> None:
        if column != 3 or self._document is None:
            return
        item = self.ring_table.item(row, column)
        if item is None:
            return
        scope = str(item.data(Qt.ItemDataRole.UserRole))
        color = QColorDialog.getColor(
            item.foreground().color(), self, "Ring type color"
        )
        if color.isValid():
            self.set_ring_scope_color(scope, color.name())

    def _block_color_clicked(self, row: int, column: int) -> None:
        self._choose_color(self.block_table, row, column, "block_colors")
