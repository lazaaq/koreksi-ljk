"""Lapisan kompatibilitas Qt.

Build utama memakai PySide6 (Qt 6: Windows 10/11, macOS 11+). Build "legacy"
memakai PySide2 (Qt 5.15: Windows 7/8/8.1, macOS 10.13–10.15). Semua modul
aplikasi mengimpor Qt dari sini, bukan langsung dari PySide6/PySide2.
"""
from __future__ import annotations

import os

_force = os.environ.get("KOREKSI_LJK_QT", "").lower()  # "pyside2" untuk menguji jalur legacy

if _force != "pyside2":
    try:
        from PySide6 import QtCore, QtGui, QtWidgets  # noqa: F401
        QT6 = True
    except ImportError:  # pragma: no cover - tergantung paket terpasang
        _force = "pyside2"
if _force == "pyside2":
    from PySide2 import QtCore, QtGui, QtWidgets  # noqa: F401
    QT6 = False

QT_API = "PySide6" if QT6 else "PySide2"
QT_VERSION = QtCore.qVersion()

Qt = QtCore.Qt
QRectF, QPointF, QThread, Signal = QtCore.QRectF, QtCore.QPointF, QtCore.QThread, QtCore.Signal
QSettings, QStandardPaths = QtCore.QSettings, QtCore.QStandardPaths

QImage, QPixmap, QPen, QColor = QtGui.QImage, QtGui.QPixmap, QtGui.QPen, QtGui.QColor
QBrush, QPainter, QFont, QPalette = QtGui.QBrush, QtGui.QPainter, QtGui.QFont, QtGui.QPalette

_W = QtWidgets
(QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
 QPushButton, QLabel, QListWidget, QListWidgetItem, QLineEdit, QPlainTextEdit, QComboBox, QSpinBox,
 QDoubleSpinBox, QFileDialog, QMessageBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
 QGraphicsPixmapItem, QDialog, QDialogButtonBox, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
 QCheckBox, QSplitter, QAbstractItemView, QScrollArea, QFrame, QTextBrowser, QAbstractButton, QTabBar,
 QAbstractSpinBox) = (
    _W.QApplication, _W.QMainWindow, _W.QTabWidget, _W.QWidget, _W.QVBoxLayout, _W.QHBoxLayout, _W.QGridLayout,
    _W.QFormLayout, _W.QPushButton, _W.QLabel, _W.QListWidget, _W.QListWidgetItem, _W.QLineEdit, _W.QPlainTextEdit,
    _W.QComboBox, _W.QSpinBox, _W.QDoubleSpinBox, _W.QFileDialog, _W.QMessageBox, _W.QGraphicsView,
    _W.QGraphicsScene, _W.QGraphicsRectItem, _W.QGraphicsPixmapItem, _W.QDialog, _W.QDialogButtonBox,
    _W.QProgressBar, _W.QTableWidget, _W.QTableWidgetItem, _W.QHeaderView, _W.QCheckBox, _W.QSplitter,
    _W.QAbstractItemView, _W.QScrollArea, _W.QFrame, _W.QTextBrowser, _W.QAbstractButton, _W.QTabBar,
    _W.QAbstractSpinBox)


def exec_(obj):
    """dialog.exec() di Qt 6, dialog.exec_() di PySide2."""
    fn = getattr(obj, "exec", None) or getattr(obj, "exec_")
    return fn()


def event_pos(e) -> "QPointF":
    """Posisi mouse dalam widget (QPointF) untuk Qt 5 & 6."""
    if hasattr(e, "position"):
        return e.position()
    return e.localPos()


def set_form_row_visible(form, field, visible: bool):
    """QFormLayout.setRowVisible baru ada di Qt 6.4 — sediakan cadangan untuk Qt lama."""
    if hasattr(form, "setRowVisible"):
        form.setRowVisible(field, visible)
        return
    field.setVisible(visible)
    lab = form.labelForField(field)
    if lab is not None:
        lab.setVisible(visible)


def prepare_app_attributes():
    """Harus dipanggil SEBELUM QApplication dibuat. Qt 5 perlu ini agar tajam di layar HiDPI/Retina
    dan skala Windows 125–200%; Qt 6 sudah otomatis."""
    if not QT6:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
