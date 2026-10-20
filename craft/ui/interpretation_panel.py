from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from craft.knowledge.matching import PresetProposal
from craft.knowledge.resolve import ResolvedInterpretation


class InterpretationPanel(QWidget):
    apply_requested = Signal(str)
    dismiss_requested = Signal(str)
    remove_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._preset_id: str | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("INTERPRETATION", self)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.status_label = QLabel("Automatic interpretation", self)
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        self.apply_button = QPushButton("Apply", self)
        self.dismiss_button = QPushButton("Dismiss", self)
        self.remove_button = QPushButton("Restore automatic", self)
        actions.addWidget(self.apply_button)
        actions.addWidget(self.dismiss_button)
        actions.addWidget(self.remove_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.why_button = QToolButton(self)
        self.why_button.setText("Why this was identified")
        self.why_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.why_button.setCheckable(True)
        self.why_button.setArrowType(Qt.ArrowType.RightArrow)
        layout.addWidget(self.why_button)
        self.details_label = QLabel("", self)
        self.details_label.setWordWrap(True)
        self.details_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.details_label.hide()
        layout.addWidget(self.details_label)
        layout.addStretch(1)

        self.apply_button.clicked.connect(self._apply)
        self.dismiss_button.clicked.connect(self._dismiss)
        self.remove_button.clicked.connect(self.remove_requested)
        self.why_button.toggled.connect(self._toggle_details)
        self.set_automatic()

    def _toggle_details(self, expanded: bool) -> None:
        self.why_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.details_label.setVisible(expanded)

    def _apply(self) -> None:
        if self._preset_id is not None:
            self.apply_requested.emit(self._preset_id)

    def _dismiss(self) -> None:
        if self._preset_id is not None:
            self.dismiss_requested.emit(self._preset_id)

    def _proposal_actions(self, visible: bool) -> None:
        self.apply_button.setVisible(visible)
        self.dismiss_button.setVisible(visible)

    def _set_details(self, text: str) -> None:
        self.details_label.setText(text)
        self.why_button.setVisible(bool(text))
        if not text:
            self.why_button.setChecked(False)
            self.details_label.hide()

    def set_automatic(self) -> None:
        self._preset_id = None
        self.status_label.setText("Automatic interpretation")
        self._set_details("")
        self._proposal_actions(False)
        self.remove_button.hide()

    def set_proposal(self, proposal: PresetProposal) -> None:
        self._preset_id = proposal.preset_id
        self.status_label.setText(
            f"Recognized motif: {proposal.name}\nConfidence: high"
        )
        self._set_details(proposal.evidence.summary)
        self._proposal_actions(True)
        self.remove_button.hide()

    def set_no_reliable_suggestion(self) -> None:
        self._preset_id = None
        self.status_label.setText("The motif could not be identified reliably.")
        self._set_details("")
        self._proposal_actions(False)
        self.remove_button.hide()

    def set_resolved(self, resolved: ResolvedInterpretation) -> None:
        self._preset_id = resolved.preset_id
        self.status_label.setText(
            f"{resolved.name}\nSource: {resolved.provenance}"
        )
        self._set_details(
            f"Vocabulary: {resolved.vocabulary}\n"
            f"Polyhedra: {len(resolved.member_polyhedron_ids)}"
        )
        self._proposal_actions(False)
        self.remove_button.setVisible(resolved.provenance != "automatic")


__all__ = ["InterpretationPanel"]
