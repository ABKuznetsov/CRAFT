"""Edit the position of a drawing copy along the crystal axes."""

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout,
)


def ask_layer_offset(parent, label, initial):
    dialog = QDialog(parent)
    dialog.setWindowTitle("Move display copy")
    layout = QVBoxLayout(dialog)
    caption = QLabel(label)
    caption.setWordWrap(True)
    layout.addWidget(caption)
    layout.addWidget(QLabel("Move along the crystal axes. 1 = one unit cell."))
    form = QFormLayout()
    controls = []
    for axis, value in zip("abc", initial):
        control = QDoubleSpinBox()
        control.setObjectName(f"layer_shift_{axis}")
        control.setRange(-1000., 1000.)
        control.setDecimals(3)
        control.setSingleStep(.25)
        control.setValue(value)
        form.addRow(f"Along {axis}", control)
        controls.append(control)
    layout.addLayout(form)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    reset = buttons.addButton("Reset", QDialogButtonBox.ButtonRole.ResetRole)

    def reset_values():
        for control in controls:
            control.setValue(0.)

    reset.clicked.connect(reset_values)
    layout.addWidget(buttons)
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    result = tuple(control.value() for control in controls) if accepted else None
    dialog.deleteLater()
    return result
