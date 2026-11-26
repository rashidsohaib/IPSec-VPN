"""Flat, modern look for the Qt UI: light and dark palettes, one stylesheet, no external assets."""
import os
import tempfile
from string import Template

from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import Qt

LIGHT = dict(bg="#f4f6f9", card="#ffffff", border="#e2e6ec", text="#1a1f26", muted="#667180",
             field="#f1f3f7", field_hover="#e9edf3", accent="#2f6df6", accent_hover="#2559d6",
             accent_press="#1d4cb8", accent_soft="#e8efff", off="#7a828c", off_bg="#eceff3",
             busy="#c98a00", busy_bg="#fff4d6", on="#18915b", on_bg="#def5ea",
             danger="#d03b3b", danger_hover="#b83030", danger_soft="#fde8e8",
             warn="#946200", warn_soft="#fff3d6", disabled_bg="#dfe3ea", disabled_text="#a0a8b4",
             scroll="#c9d0da", log_bg="#f1f3f7")
DARK = dict(bg="#13161b", card="#1c2026", border="#2a3039", text="#e7eaee", muted="#93a0ae",
            field="#14171c", field_hover="#191d23", accent="#4b8bff", accent_hover="#639aff",
            accent_press="#3a78e8", accent_soft="#1f2c46", off="#8a94a0", off_bg="#232830",
            busy="#e3a91a", busy_bg="#3a3015", on="#2fbf84", on_bg="#14352a",
            danger="#ef5f5f", danger_hover="#f47878", danger_soft="#3b1e1f",
            warn="#e3b04a", warn_soft="#3a3015", disabled_bg="#252a32", disabled_text="#68727e",
            scroll="#39414c", log_bg="#14171c")

QSS = Template("""
* { outline: 0; }
QWidget#root { background: $bg; }
QWidget { color: $text; }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }
QWidget#body { background: transparent; }
QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 4px 6px; }

/* cards */
QFrame#card { background: $card; border: 1px solid $border; border-radius: 12px; }
QFrame#card QLabel { background: transparent; }
QLabel#cardtitle { color: $muted; font-weight: 600; letter-spacing: 1px; }
QLabel#fieldlabel { color: $muted; }
QLabel#profile { color: $text; }

/* hero */
QFrame#hero { border: 1px solid $border; border-radius: 14px; background: $off_bg; }
QFrame#hero[state="on"] { background: $on_bg; border-color: $on; }
QFrame#hero[state="busy"] { background: $busy_bg; border-color: $busy; }
QFrame#hero QLabel { background: transparent; }
QLabel#status { font-weight: 700; }
QFrame#hero[state="on"] QLabel#status { color: $on; }
QFrame#hero[state="busy"] QLabel#status { color: $busy; }
QLabel#substatus { color: $muted; }

/* banners */
QLabel#err { background: $danger_soft; color: $danger; border-radius: 10px; padding: 10px 12px; }
QFrame#card QLabel#warn, QLabel#warn { background: $warn_soft; color: $warn; border-radius: 10px; padding: 8px 10px; }

/* inputs */
QLineEdit, QComboBox { background: $field; border: 1px solid transparent; border-radius: 8px;
    padding: 7px 10px; min-height: 22px; selection-background-color: $accent; selection-color: white; }
QLineEdit:hover, QComboBox:hover { background: $field_hover; }
QLineEdit:focus, QComboBox:focus, QComboBox:on { border: 1px solid $accent; background: $card; }
QLineEdit:disabled, QComboBox:disabled { color: $disabled_text; background: $field; }
QComboBox::drop-down { border: none; width: 30px; }
QComboBox::down-arrow { image: url($chevron); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $card; border: 1px solid $border; border-radius: 8px; padding: 4px;
    selection-background-color: $accent_soft; selection-color: $text; outline: 0; }

/* check boxes */
QCheckBox { spacing: 10px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1.5px solid $muted; background: transparent; }
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background: $accent; border-color: $accent; image: url($check); }
QCheckBox:disabled { color: $disabled_text; }

/* buttons */
QPushButton { background: $accent_soft; color: $accent; border: none; border-radius: 9px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: $field_hover; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { background: $disabled_bg; color: $disabled_text; }
QPushButton#primary { background: $accent; color: white; border-radius: 11px; padding: 11px 16px; font-weight: 700; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:pressed { background: $accent_press; }
QPushButton#primary[danger="true"] { background: $danger; }
QPushButton#primary[danger="true"]:hover { background: $danger_hover; }
QPushButton#primary:disabled { background: $disabled_bg; color: $disabled_text; }
QPushButton#link { background: transparent; color: $muted; padding: 4px 6px; font-weight: 500; }
QPushButton#link:hover { color: $accent; background: transparent; }
QPushButton#link:checked { color: $accent; }

/* log */
QPlainTextEdit { background: $log_bg; border: 1px solid $border; border-radius: 10px; padding: 6px;
    font-family: monospace; selection-background-color: $accent; selection-color: white; }

/* scroll bars */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $scroll; border-radius: 3px; min-height: 30px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: $muted; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* menus and dialogs follow the theme */
QMenu { background: $card; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 22px; border-radius: 6px; }
QMenu::item:selected { background: $accent_soft; color: $text; }
QMenu::item:disabled { color: $muted; }
QMenu::separator { height: 1px; background: $border; margin: 5px 8px; }
QDialog, QMessageBox { background: $card; }
""")

_assets = None


def _asset_dir():
    global _assets
    if _assets is None:
        _assets = tempfile.mkdtemp(prefix="ipsec-vpn-theme-")
    return _assets


def _glyph(name, color, kind, size=48):
    """Draw a small chevron / check mark PNG and return its path (QSS can only reference image files)."""
    path = os.path.join(_asset_dir(), f"{name}-{color.lstrip('#')}.png")
    if not os.path.exists(path):
        pm = QtGui.QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(QtGui.QColor(color), size * 0.11, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        s = size / 48.0
        pts = ([(12, 19), (24, 31), (36, 19)] if kind == "chevron" else [(12, 25), (21, 34), (36, 15)])
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(x * s, y * s) for x, y in pts]))
        p.end()
        pm.save(path)
    return path.replace("\\", "/")


def detect(app=None):
    """'light' or 'dark': IPSEC_VPN_THEME wins, otherwise the system palette decides."""
    forced = os.environ.get("IPSEC_VPN_THEME", "").lower()
    if forced in ("light", "dark"):
        return forced
    pal = (app.palette() if app else QtGui.QGuiApplication.palette())
    return "dark" if pal.color(QtGui.QPalette.Window).lightness() < 128 else "light"


def apply_theme(app, mode=None):
    mode = mode or detect(app)
    c = LIGHT if mode == "light" else DARK
    pal = QtGui.QPalette()
    for role, key in ((QtGui.QPalette.Window, "bg"), (QtGui.QPalette.Base, "field"), (QtGui.QPalette.AlternateBase, "card"),
                      (QtGui.QPalette.Button, "card"), (QtGui.QPalette.ToolTipBase, "card")):
        pal.setColor(role, QtGui.QColor(c[key]))
    for role in (QtGui.QPalette.WindowText, QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.ToolTipText):
        pal.setColor(role, QtGui.QColor(c["text"]))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(c["accent"]))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("white"))
    pal.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor(c["muted"]))
    for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
        pal.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor(c["disabled_text"]))
    app.setPalette(pal)
    app.setStyleSheet(QSS.substitute(c, chevron=_glyph("chev", c["muted"], "chevron"),
                                     check=_glyph("check", "#ffffff", "check")))
    return mode


def repolish(w):
    """Re-evaluate the stylesheet after a dynamic property (state, danger) changed."""
    w.style().unpolish(w)
    w.style().polish(w)
