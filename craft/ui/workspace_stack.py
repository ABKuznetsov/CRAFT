"""Workspace sizing follows the visible page rather than hidden editors."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QStackedWidget


class WorkspaceStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda _index: self.updateGeometry())

    def minimumSizeHint(self):
        page = self.currentWidget()
        if page is None:
            return super().minimumSizeHint()
        margins = self.contentsMargins()
        return page.minimumSizeHint().expandedTo(page.minimumSize()) + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom(),
        )

    def sizeHint(self):
        page = self.currentWidget()
        if page is None:
            return super().sizeHint()
        margins = self.contentsMargins()
        return page.sizeHint().expandedTo(page.minimumSize()) + QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom(),
        )
