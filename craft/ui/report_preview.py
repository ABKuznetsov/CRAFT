"""Compact, stable-ID preview of composed report content."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QTextBrowser, QVBoxLayout, QWidget

from craft.analysis.reporting import (
    ReportDraft,
    numbered_figures,
    numbered_tables,
    resolve_reference,
)


class ReportPreview(QWidget):
    target_requested = Signal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._activate)
        self.list.setMaximumHeight(120)
        layout.addWidget(self.list)
        self.content = QTextBrowser()
        self.content.setOpenExternalLinks(False)
        layout.addWidget(self.content, 1)

    def set_draft(self, draft: ReportDraft, report=None) -> None:
        from craft.analysis.reporting.automatic import render_report_html
        self.content.setHtml(render_report_html(draft, report))
        self.list.clear()
        for numbered in numbered_tables(draft):
            self._add(
                f"Table {numbered.number} — {numbered.target_id}",
                "table",
                numbered.target_id,
            )
        figures = {figure.id: figure for figure in draft.figures}
        for numbered in numbered_figures(draft):
            figure = figures[numbered.target_id]
            self._add(
                f"Figure {numbered.number} — {figure.title}",
                "figure",
                figure.id,
            )
        for reference in draft.references:
            resolved = resolve_reference(draft, reference)
            if resolved.resolved:
                continue
            item = self._add(
                f"{resolved.label} — {reference.target_id}",
                reference.kind,
                reference.target_id,
            )
            item.setForeground(QBrush(QColor("#c94242")))
            item.setToolTip(resolved.message)

    def _add(self, label: str, kind: str, target_id: str) -> QListWidgetItem:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, (kind, target_id))
        self.list.addItem(item)
        return item

    def _activate(self, item: QListWidgetItem) -> None:
        payload = item.data(Qt.ItemDataRole.UserRole)
        if payload:
            self.target_requested.emit(str(payload[0]), str(payload[1]))

    def labels(self) -> tuple[str, ...]:
        return tuple(self.list.item(index).text() for index in range(self.list.count()))
