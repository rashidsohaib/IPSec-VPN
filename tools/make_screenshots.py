"""Render README screenshots from the real UI with fictional data (offscreen, no VPN needed).

Run with a Python that has PyQt5:  python3 tools/make_screenshots.py docs/screenshots
"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_SCALE_FACTOR", "2")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
from PyQt5 import QtCore, QtGui, QtWidgets
from ipsec_vpn import core, qt_app, sysetup, forti

OUT = sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots"
os.makedirs(OUT, exist_ok=True)
STATE = {"connected": False}
core.status = lambda **_: dict(STATE)
app = QtWidgets.QApplication(["shots"])
app.setStyle("Fusion")
qt_app.bump_font(app, qt_app.FONT_BUMP_PX)
from ipsec_vpn import theme
MODE = os.environ.get("IPSEC_VPN_THEME", "light")
theme.apply_theme(app, MODE)
SUFFIX = "" if MODE == "light" else "-dark"

def wait(ms=500):
    loop = QtCore.QEventLoop(); QtCore.QTimer.singleShot(ms, loop.quit); loop.exec_()

def window(problems, profile=True):
    sysetup.check = lambda *a, **k: problems
    if not profile:
        try: os.remove(os.path.join(core.config_dir(), "profile.json"))
        except FileNotFoundError: pass
    w = qt_app.MainWindow(start_hidden=True)
    w.timer.stop()
    if profile:
        w.import_config(os.path.join(ROOT, "examples", "sample-forticlient.conf"))
    w.show(); wait(600)
    return w

def shot(w, name):
    w.scroll.setFixedHeight(w.body.sizeHint().height() + 4)   # show the whole form, no scrolling
    w.adjustSize(); wait(300)
    w.resize(w.width(), w.sizeHint().height()); wait(300)
    w.grab().save(os.path.join(OUT, name.replace(".png", SUFFIX + ".png"))); print("saved", name)

# 1. first run: system setup banner
w = window(["strongSwan is not installed", "the VPN helper is not installed"], profile=False)
shot(w, "01-first-run.png"); w.deleteLater()

# 2. ready to connect
w = window([])
w.user.setText("jdoe"); w.pw.setText("example-password"); w.psk.setText("example-psk")
w.route.setCurrentIndex(1); w.routes.setText("10.0.0.0/8")
shot(w, "02-ready.png"); w.deleteLater()

# 3. connected (+ tray menu)
STATE.update({"connected": True, "vip": "10.20.30.40", "server": "vpn.example.com", "since": 0})
w = window([])
w.user.setText("jdoe"); w.route.setCurrentIndex(1); w.routes.setText("10.0.0.0/8")
w.refresh(); wait(300)
shot(w, "03-connected.png")
m = w.tray_menu; m.popup(QtCore.QPoint(0, 0)); wait(300)
m.grab().save(os.path.join(OUT, "04-tray-menu.png")); print("saved 04-tray-menu.png"); m.hide(); w.deleteLater()

# 4. helpful error
STATE.clear(); STATE["connected"] = False
w = window([])
w.user.setText("jdoe"); w.pw.setText("example-password"); w.psk.setText("example-psk")
from ipsec_vpn import helper
w.err.setText(helper.explain("initiate failed: CHILD_SA not established after 30000ms"))
shot(w, "05-error.png"); w.deleteLater()

# 4b. add a connection by hand
w = window([], profile=False)
d = qt_app.ProfileDialog(w); d.name.setText("Office VPN"); d.server.setText("vpn.example.com"); d.nets.setText("10.0.0.0/8")
d.show(); wait(500); d.resize(d.width(), d.sizeHint().height()); wait(300)
d.grab().save(os.path.join(OUT, "07-add-connection" + SUFFIX + ".png")); print("saved 07-add-connection.png")
d.close(); w.deleteLater()

# 5. tray icon states
S = 96; pad = 24; label_h = 40
img = QtGui.QPixmap(3 * (S + pad) + pad, S + pad * 2 + label_h); img.fill(QtGui.QColor("#f4f6f9" if MODE == "light" else "#13161b"))
p = QtGui.QPainter(img); p.setPen(QtGui.QColor("#1a1f26" if MODE == "light" else "#e7eaee")); f = p.font(); f.setPixelSize(16); p.setFont(f)
for i, (st, label) in enumerate((("off", "Disconnected"), ("busy", "Working"), ("on", "Connected"))):
    x = pad + i * (S + pad)
    p.drawPixmap(x, pad, qt_app.make_pixmap(st, S))
    p.drawText(QtCore.QRect(x - 10, pad + S + 6, S + 20, label_h), QtCore.Qt.AlignHCenter | QtCore.Qt.AlignTop, label)
p.end(); img.save(os.path.join(OUT, "06-tray-icons.png")); print("saved 06-tray-icons.png")
