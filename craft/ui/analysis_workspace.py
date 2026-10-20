from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from craft.analysis.reporting import (
    Availability,
    REPORT_PRESETS,
    TABLE_DEFINITIONS,
    StructureReport,
    ReportDraft,
    ReportRecommendation,
    recommend_report_content,
    report_preset,
)
from craft.ui.report_table_model import ReportTableModel
from craft.ui.report_preview import ReportPreview


class AnalysisWorkspace(QWidget):
    object_refs_selected = Signal(tuple)
    export_csv_requested = Signal(str)
    export_json_requested = Signal()
    export_html_requested = Signal()
    export_docx_requested = Signal()
    draft_changed = Signal(object)
    snapshot_requested = Signal()
    standard_overview_requested = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.report: StructureReport | None = None
        self.draft: ReportDraft | None = None
        self.recommendation: ReportRecommendation | None = None
        self._updating_selection = False
        self.table_definitions = TABLE_DEFINITIONS
        self._models: dict[str, ReportTableModel] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        self.sections = QTabWidget()
        self.sections.tabBar().hide()
        splitter = QSplitter()
        root.addWidget(splitter, 1)

        catalogue_panel = QFrame()
        catalogue_layout = QVBoxLayout(catalogue_panel)
        title = QLabel("REPORT CONTENTS")
        title.setObjectName("eyebrow")
        catalogue_layout.addWidget(title)
        self.preset_combo = QComboBox()
        for preset in REPORT_PRESETS:
            self.preset_combo.addItem(preset.title, preset.id)
        self.preset_combo.currentIndexChanged.connect(self._preset_changed)
        catalogue_layout.addWidget(self.preset_combo)
        selection_row = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_none_button = QPushButton("Select none")
        self.recommended_button = QPushButton("Use recommended set")
        selection_row.addWidget(self.select_all_button)
        selection_row.addWidget(self.select_none_button)
        selection_row.addWidget(self.recommended_button)
        catalogue_layout.addLayout(selection_row)
        self.recommendation_label = QLabel("No recommendation prepared")
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        catalogue_layout.addWidget(self.recommendation_label)
        self.catalogue = QTreeWidget()
        self.catalogue.setHeaderLabels(("Content", "State"))
        self.catalogue.setColumnWidth(0, 245)
        self.catalogue.currentItemChanged.connect(self._catalogue_changed)
        self.catalogue.itemChanged.connect(self._selection_changed)
        catalogue_layout.addWidget(self.catalogue, 1)
        self.unavailable_check = QCheckBox("Show unavailable sections")
        self.unavailable_check.toggled.connect(self._refresh_availability)
        catalogue_layout.addWidget(self.unavailable_check)
        splitter.addWidget(catalogue_panel)

        centre = QFrame()
        centre_layout = QVBoxLayout(centre)
        self.table_title = QLabel("Select a report table")
        self.table_title.setObjectName("selectedTitle")
        centre_layout.addWidget(self.table_title)
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False)
        self.table_view.clicked.connect(self._row_selected)
        centre_layout.addWidget(self.table_view, 1)
        self.sections.addTab(centre, "Tables")
        splitter.addWidget(self.sections)

        properties = QFrame()
        properties_layout = QVBoxLayout(properties)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.availability_label = QLabel("—")
        self.method_label = QLabel("—")
        self.method_label.setWordWrap(True)
        self.warning_label = QLabel("—")
        self.warning_label.setWordWrap(True)
        form.addRow("Availability", self.availability_label)
        form.addRow("Method", self.method_label)
        form.addRow("Warnings", self.warning_label)
        properties_layout.addLayout(form)
        self.csv_button = QPushButton("Export current table as CSV…")
        self.json_button = QPushButton("Export report as JSON…")
        self.csv_button.clicked.connect(self._request_csv)
        self.json_button.clicked.connect(self.export_json_requested)
        self.properties_button = QToolButton()
        self.properties_button.setText("Method and warnings")
        self.properties_button.setCheckable(True)
        self.properties_button.toggled.connect(properties.setVisible)
        properties.hide()
        table_actions = QHBoxLayout()
        table_actions.addWidget(self.properties_button)
        table_actions.addStretch()
        table_actions.addWidget(self.csv_button)
        centre_layout.insertLayout(1, table_actions)
        centre_layout.insertWidget(2, properties)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes((350, 1000))
        self.select_all_button.clicked.connect(self._select_all)
        self.select_none_button.clicked.connect(self._select_none)
        self.recommended_button.clicked.connect(self._apply_recommendation)
        self.recommended_button.setEnabled(False)

        figures_page = QWidget()
        figures_layout = QVBoxLayout(figures_page)
        figure_actions = QHBoxLayout()
        self.snapshot_button = QPushButton("Add view to report")
        self.atom_overview_button = QPushButton("Standard overview · atom labels")
        self.polyhedron_overview_button = QPushButton(
            "Standard overview · polyhedron labels"
        )
        self.figure_up_button = QPushButton("Move up")
        self.figure_down_button = QPushButton("Move down")
        self.figure_remove_button = QPushButton("Remove")
        for button in (
            self.snapshot_button,
            self.atom_overview_button,
            self.polyhedron_overview_button,
            self.figure_up_button,
            self.figure_down_button,
            self.figure_remove_button,
        ):
            figure_actions.addWidget(button)
        figures_layout.addLayout(figure_actions)
        self.figure_table = QTableWidget(0, 6)
        self.figure_table.setHorizontalHeaderLabels(
            ("Include", "Title", "Caption", "Kind", "State", "Description")
        )
        self.figure_table.horizontalHeader().setStretchLastSection(True)
        self.figure_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.figure_table.itemChanged.connect(self._figure_changed)
        figures_layout.addWidget(self.figure_table)
        self.sections.addTab(figures_page, "Figures")

        self.preview = ReportPreview()
        self.preview.list.hide()
        self.preview.target_requested.connect(self._preview_target_requested)
        preview_page = QWidget()
        preview_layout = QVBoxLayout(preview_page)
        self.html_button = QPushButton("Export HTML…")
        self.html_button.clicked.connect(self.export_html_requested)
        self.docx_button = QPushButton("Export Word (.docx)…")
        self.docx_button.clicked.connect(self.export_docx_requested)
        preview_layout.addWidget(self.preview, 1)
        self.sections.addTab(preview_page, "Preview")
        export_actions = QHBoxLayout()
        export_actions.addStretch()
        export_actions.addWidget(self.json_button)
        export_actions.addWidget(self.html_button)
        export_actions.addWidget(self.docx_button)
        root.insertLayout(0, export_actions)
        self.snapshot_button.clicked.connect(self.snapshot_requested)
        self.atom_overview_button.clicked.connect(
            lambda: self.standard_overview_requested.emit("atom-orbits")
        )
        self.polyhedron_overview_button.clicked.connect(
            lambda: self.standard_overview_requested.emit("polyhedron-orbits")
        )
        self.figure_up_button.clicked.connect(lambda: self._move_figure(-1))
        self.figure_down_button.clicked.connect(lambda: self._move_figure(1))
        self.figure_remove_button.clicked.connect(self._remove_figure)
        self.clear_report()

    def _clear_table_models(self) -> None:
        self.table_view.setModel(None)
        for model in self._models.values():
            model.deleteLater()
        self._models.clear()

    def _set_report_actions_enabled(self, enabled: bool) -> None:
        for button in (self.json_button, self.html_button, self.docx_button, self.snapshot_button,
                       self.atom_overview_button, self.polyhedron_overview_button,
                       self.select_all_button, self.select_none_button):
            button.setEnabled(enabled)

    def clear_report(self) -> None:
        """Drop document-owned report content before a new document or analysis."""
        self.report = None
        self.draft = None
        self.recommendation = None
        self._clear_table_models()
        self.catalogue.clear()
        self._section_items = {}
        self.figure_table.setRowCount(0)
        self.preview.list.clear()
        self.preview.content.clear()
        for label in (self.table_title, self.availability_label, self.method_label, self.warning_label):
            label.clear()
        self.recommendation_label.setText("No recommendation prepared")
        self.recommendation_label.setToolTip("")
        self.recommended_button.setEnabled(False)
        self.csv_button.setEnabled(False)
        self._set_report_actions_enabled(False)

    def set_report(
        self,
        report: StructureReport,
        draft: ReportDraft | None = None,
    ) -> None:
        self.report = report
        available = tuple(
            table_id
            for table_id, table in report.tables.items()
            if table.availability is Availability.AVAILABLE
        )
        self.draft = draft or ReportDraft(
            structure_fingerprint="",
            available_table_ids=available,
        )
        self.recommendation = None
        self.recommended_button.setEnabled(False)
        self.recommendation_label.setText("No recommendation prepared")
        self.recommendation_label.setToolTip("")
        self._clear_table_models()
        self._set_report_actions_enabled(True)
        self._updating_selection = True
        self.catalogue.clear()
        self._section_items = {}
        for section, title in (("preview", "Description / document"), ("tables", "Tables"), ("figures", "Figures")):
            item = QTreeWidgetItem((title, ""))
            item.setData(0, Qt.ItemDataRole.UserRole, "@" + section)
            self.catalogue.addTopLevelItem(item)
            self._section_items[section] = item
        groups: dict[str, QTreeWidgetItem] = {}
        first_available: QTreeWidgetItem | None = None
        for definition in TABLE_DEFINITIONS:
            group = groups.get(definition.group)
            if group is None:
                group = QTreeWidgetItem((definition.group, ""))
                groups[definition.group] = group
                self._section_items["tables"].addChild(group)
            table = report.tables.get(definition.id)
            available = table is not None and table.availability is Availability.AVAILABLE and bool(table.rows)
            state = "Available" if available else "No data"
            item = QTreeWidgetItem((definition.title, state))
            item.setToolTip(0, definition.title)
            item.setData(0, Qt.ItemDataRole.UserRole, definition.id)
            item.setCheckState(
                0, Qt.CheckState.Checked if definition.id in self.draft.selected_table_ids else Qt.CheckState.Unchecked,
            )
            if available:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                item.setFlags(item.flags() & ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable))
                item.setToolTip(0, table.unavailable_reason if table is not None else "No data available")
            group.addChild(item)
            if available and first_available is None:
                first_available = item
        self.catalogue.expandAll()
        self._updating_selection = False
        if first_available is not None:
            self.catalogue.setCurrentItem(first_available)
        self._refresh_figures()
        self.preview.set_draft(self.draft, self.report)
        self._refresh_availability()
        self.select_section("preview")

    def _refresh_availability(self) -> None:
        if self.report is None:
            return
        show_all = self.unavailable_check.isChecked()
        self.catalogue.setColumnHidden(1, not show_all)
        selected = self.draft.selected_table_ids if self.draft is not None else ()
        for item in self._table_items():
            table_id = item.data(0, Qt.ItemDataRole.UserRole)
            table = self.report.tables.get(table_id)
            available = table is not None and table.availability is Availability.AVAILABLE and bool(table.rows)
            item.setHidden(not (show_all or available or table_id in selected))
        tables = self._section_items.get("tables")
        if tables is not None:
            for index in range(tables.childCount()):
                group = tables.child(index)
                group.setHidden(all(group.child(i).isHidden() for i in range(group.childCount())))

    def select_section(self, section: str) -> None:
        mapping = {"tables": 0, "figures": 1, "text": 2, "preview": 2}
        if section in mapping:
            self.sections.setCurrentIndex(mapping[section])
            item = self._section_items.get("preview" if section == "text" else section)
            if item is not None and self.catalogue.currentItem() is not item:
                self.catalogue.setCurrentItem(item)

    def _refresh_figures(self) -> None:
        self.figure_table.blockSignals(True)
        self.figure_table.setRowCount(0)
        if self.draft is not None:
            for row, figure in enumerate(self.draft.figures):
                self.figure_table.insertRow(row)
                include = QTableWidgetItem()
                include.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
                )
                include.setCheckState(
                    Qt.CheckState.Checked if figure.include else Qt.CheckState.Unchecked
                )
                include.setData(Qt.ItemDataRole.UserRole, figure.id)
                self.figure_table.setItem(row, 0, include)
                self.figure_table.setItem(row, 1, QTableWidgetItem(figure.title))
                self.figure_table.setItem(row, 2, QTableWidgetItem(figure.caption))
                kind = QTableWidgetItem(figure.kind.value)
                kind.setFlags(kind.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.figure_table.setItem(row, 3, kind)
                state = QTableWidgetItem("Stale" if figure.stale else "Ready")
                state.setFlags(state.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.figure_table.setItem(row, 4, state)
                self.figure_table.setItem(row, 5, QTableWidgetItem(figure.description))
        self.figure_table.blockSignals(False)

    def _figure_changed(self, item: QTableWidgetItem) -> None:
        if self.draft is None or not (0 <= item.row() < len(self.draft.figures)):
            return
        figure = self.draft.figures[item.row()]
        updated = replace(
            figure,
            include=self.figure_table.item(item.row(), 0).checkState()
            == Qt.CheckState.Checked,
            title=self.figure_table.item(item.row(), 1).text(),
            caption=self.figure_table.item(item.row(), 2).text(),
            description=self.figure_table.item(item.row(), 5).text(),
        )
        self.draft = self.draft.with_figure(updated)
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def _selected_figure_row(self) -> int:
        return self.figure_table.currentRow()

    def _move_figure(self, delta: int) -> None:
        if self.draft is None:
            return
        row = self._selected_figure_row()
        if not (0 <= row < len(self.draft.figures)):
            return
        figure_id = self.draft.figures[row].id
        destination = max(0, min(row + delta, len(self.draft.figures) - 1))
        self.draft = self.draft.move_figure(figure_id, destination)
        self._refresh_figures()
        self.figure_table.setCurrentCell(destination, 1)
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def _remove_figure(self) -> None:
        if self.draft is None:
            return
        row = self._selected_figure_row()
        if not (0 <= row < len(self.draft.figures)):
            return
        self.draft = self.draft.without_figure(self.draft.figures[row].id)
        self._refresh_figures()
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def _preview_target_requested(self, kind: str, target_id: str) -> None:
        if kind == "table":
            for item in self._table_items():
                if item.data(0, Qt.ItemDataRole.UserRole) == target_id:
                    self.sections.setCurrentIndex(0)
                    self.catalogue.setCurrentItem(item)
                    return
        if kind.startswith("figure") and self.draft is not None:
            for row, figure in enumerate(self.draft.figures):
                if figure.id == target_id:
                    self.sections.setCurrentIndex(1)
                    self.figure_table.setCurrentCell(row, 1)
                    return

    def catalogue_table_ids(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(0, Qt.ItemDataRole.UserRole))
            for item in self._table_items()
        )

    def _table_items(self):
        table_ids = {definition.id for definition in self.table_definitions}
        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) in table_ids:
                yield item
            for index in range(item.childCount()):
                yield from visit(item.child(index))
        for index in range(self.catalogue.topLevelItemCount()):
            yield from visit(self.catalogue.topLevelItem(index))

    def _catalogue_changed(self, current, _previous) -> None:
        if current is None or self.report is None:
            return
        table_id = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(table_id, str) and table_id.startswith("@"):
            self.select_section(table_id[1:])
            return
        if not table_id or table_id not in self.report.tables:
            return
        table = self.report.tables[table_id]
        self.sections.setCurrentIndex(0)
        model = self._models.get(table_id)
        if model is None:
            display_table = self.draft.publication_table(table) if self.draft is not None else table
            model = ReportTableModel(display_table, self)
            self._models[table_id] = model
            model.dataChanged.connect(
                lambda _first, _last, roles, key=table_id, source=model:
                    self._publication_rows_changed(key, source, roles)
            )
        self.table_view.setModel(model)
        self.table_view.resizeColumnsToContents()
        self.table_title.setText(table.title)
        self.availability_label.setText(table.availability.value)
        self.method_label.setText(table.method or table.unavailable_reason or "Source CIF")
        self.warning_label.setText("\n".join(w.message for w in table.warnings) or "None")
        self.csv_button.setEnabled(table.availability is Availability.AVAILABLE)

    def _publication_rows_changed(self, table_id, model, roles) -> None:
        if (self.draft is None or self.report is None or self._models.get(table_id) is not model
                or roles and Qt.ItemDataRole.CheckStateRole not in roles):
            return
        defaults = {row.id: row.include_in_publication for row in self.report.tables[table_id].rows}
        overrides = dict(dict(self.draft.table_row_inclusion).get(table_id, ()))
        for row in model.rows:
            if row.include_in_publication == defaults[row.id]:
                overrides.pop(row.id, None)
            else:
                overrides[row.id] = row.include_in_publication
        self.draft = self.draft.with_table_rows(table_id, tuple(overrides.items()))
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def _row_selected(self, index) -> None:
        model = self.table_view.model()
        if isinstance(model, ReportTableModel) and index.isValid():
            self.object_refs_selected.emit(model.rows[index.row()].object_refs)

    def _request_csv(self) -> None:
        current = self.catalogue.currentItem()
        if current is not None:
            table_id = current.data(0, Qt.ItemDataRole.UserRole)
            if table_id:
                self.export_csv_requested.emit(table_id)

    def _preset_changed(self, _index: int) -> None:
        preset_id = self.preset_combo.currentData()
        if not preset_id:
            return
        self._set_selected_ids(report_preset(str(preset_id)).table_ids)

    def _selection_changed(self, _item, _column: int) -> None:
        if self._updating_selection or self.draft is None:
            return
        self.draft = self.draft.with_tables(self.selected_table_ids())
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def _set_selected_ids(self, selected_ids) -> None:
        if self.draft is None:
            return
        selected_ids = tuple(dict.fromkeys(key for key in selected_ids if key in self.draft.available_table_ids))
        selected = set(selected_ids)
        self._updating_selection = True
        try:
            for item in self._table_items():
                table_id = str(item.data(0, Qt.ItemDataRole.UserRole))
                if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked
                        if table_id in selected
                        else Qt.CheckState.Unchecked,
                    )
        finally:
            self._updating_selection = False
        self.draft = self.draft.with_tables(selected_ids)
        self.preview.set_draft(self.draft, self.report)
        self.draft_changed.emit(self.draft)

    def set_table_selected(self, table_id: str, selected: bool) -> None:
        for item in self._table_items():
            if item.data(0, Qt.ItemDataRole.UserRole) == table_id:
                if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    item.setCheckState(
                        0,
                        Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked,
                    )
                return

    def _select_all(self) -> None:
        if self.draft is not None:
            self._set_selected_ids(self.draft.available_table_ids)

    def _select_none(self) -> None:
        self._set_selected_ids(())

    def build_recommendation(self, **capabilities: bool) -> ReportRecommendation:
        if self.report is None:
            raise ValueError("A structure report is required before recommendation.")
        return recommend_report_content(self.report, **capabilities)

    def set_recommendation(self, recommendation: ReportRecommendation) -> None:
        self.recommendation = recommendation
        self.recommendation_label.setText(
            f"Recommended: {len(recommendation.table_ids)} tables, "
            f"{len(recommendation.figure_requests)} figures."
        )
        self.recommendation_label.setToolTip("\n".join(recommendation.reasons))
        self.recommended_button.setEnabled(True)

    def _apply_recommendation(self) -> None:
        if self.recommendation is not None:
            self._set_selected_ids(self.recommendation.table_ids)
            if self.draft is not None:
                self.draft = replace(self.draft, recommendation_applied=True)
                self.draft_changed.emit(self.draft)
            standard = next(
                (
                    request
                    for request in self.recommendation.figure_requests
                    if request.kind.value == "standard-overview"
                ),
                None,
            )
            if standard is not None:
                self.standard_overview_requested.emit(standard.label_mode.value)

    def selected_table_ids(self) -> tuple[str, ...]:
        selected: list[str] = []
        for item in self._table_items():
            if item.checkState(0) is Qt.CheckState.Checked:
                selected.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        if self.draft is None:
            return tuple(selected)
        represented = set(self.catalogue_table_ids())
        retained = tuple(key for key in self.draft.selected_table_ids if key in selected or key not in represented)
        return (*retained, *(key for key in selected if key not in retained))
