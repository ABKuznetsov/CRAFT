"""Scrollable display controls with independent, expandable sections."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QScrollArea, QToolButton, QVBoxLayout, QWidget


class InspectorSections(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.addStretch()
        self.setWidget(body)
        self.sections = {}

    def add_section(self, title, content, *, expanded=False):
        toggle = QToolButton()
        toggle.setText(title)
        toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toggle.setCheckable(True)
        toggle.setSizePolicy(content.sizePolicy().horizontalPolicy(), toggle.sizePolicy().verticalPolicy())

        def changed(checked):
            toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            content.setVisible(checked)

        toggle.toggled.connect(changed)
        toggle.setChecked(expanded)
        changed(expanded)
        self._layout.insertWidget(self._layout.count() - 1, toggle)
        self._layout.insertWidget(self._layout.count() - 1, content)
        self.sections[title] = toggle, content

    def reveal(self, title):
        toggle, content = self.sections[title]
        for other, _content in self.sections.values():
            if other is not toggle:
                other.setChecked(False)
        toggle.setChecked(True)
        QTimer.singleShot(0, self, lambda: self.ensureWidgetVisible(toggle))
