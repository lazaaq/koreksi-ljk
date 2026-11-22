"""Tema terang Koreksi LJK: dominan putih, aksen biru, teks 14 px."""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

# Warna (selaras dengan skala Tailwind agar konsisten & kontras memenuhi WCAG AA)
WHITE = "#FFFFFF"
SURFACE = "#F8FAFC"      # latar panel halus
BORDER = "#E2E8F0"
BORDER_STRONG = "#CBD5E1"
TEXT = "#0F172A"
MUTED = "#64748B"
PRIMARY = "#2563EB"
PRIMARY_HOVER = "#1D4ED8"
PRIMARY_SOFT = "#EFF6FF"
SUCCESS = "#16A34A"
SUCCESS_SOFT = "#F0FDF4"
WARNING = "#D97706"
WARNING_SOFT = "#FFFBEB"
DANGER = "#DC2626"
DANGER_SOFT = "#FEF2F2"
PURPLE = "#9333EA"

QSS = f"""
QMainWindow, QDialog, QMessageBox {{ background: {WHITE}; }}
QWidget {{ font-size: 14px; color: {TEXT}; }}
QWidget#Page, QWidget#Header, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {WHITE}; }}
QScrollArea {{ border: none; }}

/* ---------- teks ---------- */
QLabel[role="appTitle"] {{ font-size: 20px; font-weight: 700; }}
QLabel[role="appSub"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="pageTitle"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="pageSub"] {{ color: {MUTED}; font-size: 14px; }}
QLabel[role="cardTitle"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="label"] {{ font-weight: 600; color: #334155; }}
QLabel[role="hint"] {{ color: {MUTED}; font-size: 13px; }}
QLabel[role="bigScore"] {{ font-size: 40px; font-weight: 800; color: {PRIMARY}; }}
QLabel[role="info"] {{ background: {PRIMARY_SOFT}; border: 1px solid #BFDBFE; border-radius: 10px; padding: 12px 14px; color: #1E3A8A; }}
QLabel[role="warn"] {{ background: {WARNING_SOFT}; border: 1px solid #FDE68A; border-radius: 10px; padding: 10px 14px; color: #92400E; }}
QLabel[role="ok"] {{ background: {SUCCESS_SOFT}; border: 1px solid #BBF7D0; border-radius: 10px; padding: 10px 14px; color: #166534; }}
QLabel[role="error"] {{ background: {DANGER_SOFT}; border: 1px solid #FECACA; border-radius: 10px; padding: 10px 14px; color: #991B1B; }}
QLabel[role="chipOk"] {{ background: {SUCCESS_SOFT}; color: #166534; border-radius: 12px; padding: 4px 12px; font-weight: 600; }}
QLabel[role="chipBad"] {{ background: {DANGER_SOFT}; color: #991B1B; border-radius: 12px; padding: 4px 12px; font-weight: 600; }}
QLabel[role="chipWarn"] {{ background: {WARNING_SOFT}; color: #92400E; border-radius: 12px; padding: 4px 12px; font-weight: 600; }}
QLabel[role="chip"] {{ background: #F1F5F9; color: #334155; border-radius: 12px; padding: 4px 12px; font-weight: 600; }}

/* ---------- kartu ---------- */
QFrame#Card {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#Divider {{ background: {BORDER}; max-height: 1px; min-height: 1px; border: none; }}

/* ---------- tombol ---------- */
QPushButton {{
    background: {WHITE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 8px 16px; min-height: 22px; font-weight: 600;
}}
QPushButton:hover {{ background: {SURFACE}; border-color: #94A3B8; }}
QPushButton:pressed {{ background: #F1F5F9; }}
QPushButton:focus {{ outline: none; border: 2px solid #93C5FD; padding: 7px 15px; }}
QPushButton:disabled {{ color: #94A3B8; background: {SURFACE}; border-color: {BORDER}; }}
QPushButton[kind="primary"] {{ background: {PRIMARY}; color: white; border: 1px solid {PRIMARY}; }}
QPushButton[kind="primary"]:hover {{ background: {PRIMARY_HOVER}; border-color: {PRIMARY_HOVER}; }}
QPushButton[kind="primary"]:focus {{ border: 2px solid #93C5FD; }}
QPushButton[kind="primary"]:disabled {{ background: #BFDBFE; border-color: #BFDBFE; color: white; }}
QPushButton[kind="danger"] {{ color: {DANGER}; border-color: #FECACA; }}
QPushButton[kind="danger"]:hover {{ background: {DANGER_SOFT}; border-color: #FCA5A5; }}
QPushButton[kind="ghost"] {{ border: none; background: transparent; color: {PRIMARY}; padding: 8px 10px; }}
QPushButton[kind="ghost"]:hover {{ background: {PRIMARY_SOFT}; }}
QPushButton[size="lg"] {{ font-size: 16px; padding: 12px 28px; border-radius: 10px; }}
QPushButton[kind="primary"][size="lg"]:focus {{ padding: 11px 27px; }}

/* ---------- input ---------- */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {WHITE}; border: 1px solid {BORDER_STRONG}; border-radius: 8px; padding: 7px 10px;
    min-height: 22px; selection-background-color: #BFDBFE; selection-color: {TEXT};
}}
QPlainTextEdit {{ padding: 8px 10px; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ subcontrol-origin: border; width: 0px; border: none; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 2px solid {PRIMARY}; padding: 6px 9px; }}
QPlainTextEdit:focus {{ padding: 7px 9px; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ background: {SURFACE}; color: #94A3B8; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox QAbstractItemView {{ border: 1px solid {BORDER}; border-radius: 8px; padding: 4px; background: {WHITE};
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; outline: none; }}

/* ---------- tab utama ---------- */
QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER}; background: {WHITE}; top: -1px; }}
QTabWidget::tab-bar {{ left: 24px; }}
QTabBar {{ background: {WHITE}; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; font-size: 15px; font-weight: 600;
    padding: 12px 18px; margin-right: 8px; border: none; border-bottom: 3px solid transparent;
}}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 3px solid {PRIMARY}; }}
QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

/* ---------- daftar & tabel ---------- */
QListWidget {{ background: {WHITE}; border: 1px solid {BORDER}; border-radius: 10px; padding: 4px; outline: none; }}
QListWidget::item {{ padding: 10px 10px; border-radius: 6px; margin: 1px 0; }}
QListWidget::item:hover {{ background: {SURFACE}; }}
QListWidget::item:selected {{ background: {PRIMARY_SOFT}; color: {PRIMARY_HOVER}; font-weight: 600; }}
QTableWidget {{
    background: {WHITE}; border: 1px solid {BORDER}; border-radius: 10px; gridline-color: transparent;
    alternate-background-color: #FBFCFE; selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; outline: none;
}}
QTableWidget::item {{ padding: 4px 10px; border-bottom: 1px solid #F1F5F9; }}
QTableWidget::item:selected {{ background: {PRIMARY_SOFT}; color: {TEXT}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {MUTED}; font-size: 13px; font-weight: 600;
    padding: 10px 10px; border: none; border-bottom: 1px solid {BORDER};
}}
QTableCornerButton::section {{ background: {SURFACE}; border: none; }}

/* ---------- lain-lain ---------- */
QProgressBar {{ background: #F1F5F9; border: none; border-radius: 6px; height: 10px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 6px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {BORDER_STRONG}; border-radius: 5px; background: {WHITE}; }}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
QGraphicsView {{ border: 1px solid {BORDER}; border-radius: 10px; background: #F1F5F9; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #CBD5E1; border-radius: 4px; min-height: 32px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #CBD5E1; border-radius: 4px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: {TEXT}; color: white; border: none; padding: 6px 8px; border-radius: 6px; }}
QMessageBox QLabel {{ font-size: 14px; }}
"""


CHEVRON = """<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'>
<path d='M2.5 4.5 L6 8 L9.5 4.5' fill='none' stroke='#64748B' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/></svg>"""


def _asset(name: str, content: str) -> str:
    import tempfile
    from pathlib import Path
    d = Path(tempfile.gettempdir()) / "koreksi-ljk-theme"
    d.mkdir(exist_ok=True)
    f = d / name
    if not f.exists() or f.read_text() != content:
        f.write_text(content)
    return f.as_posix()


def apply(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in [(QPalette.Window, WHITE), (QPalette.Base, WHITE), (QPalette.AlternateBase, "#FBFCFE"),
                      (QPalette.Text, TEXT), (QPalette.WindowText, TEXT), (QPalette.Button, WHITE),
                      (QPalette.ButtonText, TEXT), (QPalette.Highlight, PRIMARY), (QPalette.HighlightedText, "#FFFFFF"),
                      (QPalette.ToolTipBase, TEXT), (QPalette.ToolTipText, "#FFFFFF"), (QPalette.PlaceholderText, "#94A3B8")]:
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    f = QFont(".AppleSystemUIFont" if sys.platform == "darwin" else ("Segoe UI" if sys.platform == "win32" else app.font().family()))
    f.setPixelSize(14)
    app.setFont(f)
    chevron = _asset("chevron-down.svg", CHEVRON)
    app.setStyleSheet(QSS + f"QComboBox::down-arrow {{ image: url({chevron}); width: 12px; height: 12px; }}")


# ----------------------------------------------------------------------------- helper
def set_role(w: QWidget, role: str):
    w.setProperty("role", role)
    w.style().unpolish(w); w.style().polish(w)


def label(text: str = "", role: str | None = None, wrap=False) -> QLabel:
    l = QLabel(text)
    if role:
        l.setProperty("role", role)
    l.setWordWrap(wrap)
    return l


def button(text: str, kind: str | None = None, size: str | None = None, slot=None) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    if size:
        b.setProperty("size", size)
    from PySide6.QtCore import Qt
    b.setCursor(Qt.PointingHandCursor)
    if slot:
        b.clicked.connect(slot)
    return b


class Card(QFrame):
    """Kartu putih berbingkai tipis dengan judul & keterangan opsional."""

    def __init__(self, title: str | None = None, subtitle: str | None = None, step: int | None = None):
        super().__init__()
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(20, 18, 20, 20)
        self.lay.setSpacing(10)
        if title:
            head = QHBoxLayout(); head.setSpacing(10)
            if step is not None:
                n = QLabel(str(step))
                n.setFixedSize(26, 26)
                from PySide6.QtCore import Qt
                n.setAlignment(Qt.AlignCenter)
                n.setStyleSheet(f"background:{PRIMARY_SOFT};color:{PRIMARY};border-radius:13px;font-weight:700;font-size:13px;")
                head.addWidget(n)
            head.addWidget(label(title, "cardTitle"))
            head.addStretch()
            self.lay.addLayout(head)
        if subtitle:
            self.lay.addWidget(label(subtitle, "hint", wrap=True))


def page_header(title: str, subtitle: str) -> QWidget:
    w = QWidget(); l = QVBoxLayout(w); l.setContentsMargins(0, 0, 0, 4); l.setSpacing(4)
    l.addWidget(label(title, "pageTitle")); l.addWidget(label(subtitle, "pageSub", wrap=True))
    return w


def clickable(root: QWidget):
    """Kursor tangan untuk semua elemen yang bisa diklik di bawah root."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QListWidget, QTabBar, QTableWidget, QHeaderView,
                                   QTabWidget)
    for w in [root] + root.findChildren(QWidget):
        if isinstance(w, (QAbstractButton, QComboBox, QTabBar)):
            w.setCursor(Qt.PointingHandCursor)
            if isinstance(w, QComboBox):
                w.view().viewport().setCursor(Qt.PointingHandCursor)
        elif isinstance(w, (QListWidget, QTableWidget)):
            w.viewport().setCursor(Qt.PointingHandCursor)
        elif isinstance(w, QHeaderView) and w.sectionsClickable():
            w.setCursor(Qt.PointingHandCursor)
