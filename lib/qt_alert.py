"""
Qt message box helpers for Qt applications.
"""
from typing import Optional

from PySide6.QtWidgets import QWidget, QMessageBox


def qt_alert(
    parent: Optional[QWidget],
    title: str,
    message: str,
    kind: str = "info",
):
    """Show a Qt message box. kind: info, warning, error, askokcancel, askyesno, askyesnocancel."""
    if kind == "askokcancel":
        result = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result == QMessageBox.StandardButton.Ok
    if kind == "askyesno":
        result = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes
    if kind == "askyesnocancel":
        result = QMessageBox.question(
            parent,
            title,
            message,
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return result
    if kind == "error":
        QMessageBox.critical(parent, title, message)
        return None
    if kind == "warning":
        QMessageBox.warning(parent, title, message)
        return None
    QMessageBox.information(parent, title, message)
    return None
