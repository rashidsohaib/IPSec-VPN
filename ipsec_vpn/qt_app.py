"""Native desktop client: main window + system-tray icon (StatusNotifier / XEmbed via Qt)."""
import html
import os
import shutil
import sys
import threading

from PyQt5 import QtCore, QtGui, QtNetwork, QtWidgets
from PyQt5.QtCore import Qt

from . import __version__, core, forti, sysetup, theme

APP_NAME = "IPSec VPN - Design By Rashid"
WINDOW_TITLE = "IPSec VPN - Design By Rashid"
COLORS = {"off": "#7a828c", "busy": "#e0a100", "on": "#1f9d63"}
STATE_TEXT = {"off": "Disconnected", "busy": "Working…", "on": "Connected"}


def make_pixmap(state, size=64):
    pm = QtGui.QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.scale(size / 64.0, size / 64.0)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor(COLORS[state]))
    p.drawEllipse(2, 2, 60, 60)
    shield = QtGui.QPainterPath()
    shield.moveTo(32, 11)
    shield.lineTo(49, 17)
    shield.lineTo(49, 31)
    shield.cubicTo(49, 43, 41, 50, 32, 54)
    shield.cubicTo(23, 50, 15, 43, 15, 31)
    shield.lineTo(15, 17)
    shield.closeSubpath()
    p.setBrush(QtGui.QColor("white"))
    p.drawPath(shield)
    pen = QtGui.QPen(QtGui.QColor(COLORS[state]), 5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if state == "on":
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(24, 32), QtCore.QPointF(30, 38), QtCore.QPointF(41, 25)]))
    elif state == "off":
        p.drawLine(24, 32, 40, 32)
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(COLORS["busy"]))
        for x in (23, 32, 41):
            p.drawEllipse(QtCore.QPointF(x, 32), 3, 3)
    p.end()
    return pm


def icons():
    return {s: QtGui.QIcon(make_pixmap(s)) for s in COLORS}


FONT_BUMP_PX = 2


def bump_font(app, px):
    """Make the whole UI `px` pixels larger than the system default (DPI-aware)."""
    f = app.font()
    if f.pixelSize() > 0:
        f.setPixelSize(f.pixelSize() + px)
    else:
        scr = app.primaryScreen()
        dpi = (scr.logicalDotsPerInch() if scr else 96) or 96
        f.setPointSizeF(f.pointSizeF() + px * 72.0 / dpi)
    app.setFont(f)


def appimage_path():
    return os.environ.get("APPIMAGE") or ""


class Banner(QtWidgets.QLabel):
    """Message strip that is only visible while it has text."""

    def __init__(self, kind):
        super().__init__()
        self.setObjectName(kind)
        self.setWordWrap(True)
        self.setVisible(False)

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))


def _card(title):
    """A flat white card with a small caps title; returns (frame, layout to add content to)."""
    frame = QtWidgets.QFrame()
    frame.setObjectName("card")
    lay = QtWidgets.QVBoxLayout(frame)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
    t = QtWidgets.QLabel(title.upper())
    t.setObjectName("cardtitle")
    f = t.font()
    f.setPointSizeF(max(6.0, f.pointSizeF() - 1.5))
    t.setFont(f)
    lay.addWidget(t)
    return frame, lay


def _field_label(text):
    lbl = QtWidgets.QLabel(text)
    lbl.setObjectName("fieldlabel")
    return lbl



class ProfileDialog(QtWidgets.QDialog):
    """Add (or edit) a connection by hand instead of importing a FortiClient export."""

    def __init__(self, parent=None, profile=None, username=""):
        super().__init__(parent)
        self.setWindowTitle("Add connection")
        self.setMinimumWidth(480)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        title = QtWidgets.QLabel("Add connection manually")
        f = title.font()
        f.setPointSize(f.pointSize() + 3)
        f.setBold(True)
        title.setFont(f)
        lay.addWidget(title)
        hint = QtWidgets.QLabel("Enter the gateway and your sign-in details. The encryption defaults match a typical "
                                "FortiGate IPsec tunnel for FortiClient (IKEv2, group 21); change them only if your "
                                "administrator says so.")
        hint.setObjectName("fieldlabel")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        form = QtWidgets.QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        lay.addLayout(form)
        self.name = QtWidgets.QLineEdit()
        self.name.setPlaceholderText("Office VPN")
        self.server = QtWidgets.QLineEdit()
        self.server.setPlaceholderText("vpn.example.com or 203.0.113.10")
        self.nets = QtWidgets.QLineEdit()
        self.nets.setPlaceholderText("Empty = everything; or 10.0.0.0/8, 192.168.50.0/24")
        self.user = QtWidgets.QLineEdit()
        self.user.setPlaceholderText("Your VPN user name")
        self.user.setText(username)
        self.pw = QtWidgets.QLineEdit()
        self.pw.setEchoMode(QtWidgets.QLineEdit.Password)
        self.psk = QtWidgets.QLineEdit()
        self.psk.setEchoMode(QtWidgets.QLineEdit.Password)
        self.enc = self._combo(forti.MANUAL_ENC)
        self.hash = self._combo(forti.MANUAL_HASH)
        self.dh = self._combo(forti.MANUAL_DH)
        for label, w in (("Name", self.name), ("Gateway", self.server), ("User name", self.user),
                         ("Password", self.pw), ("Pre-shared key", self.psk), ("Networks", self.nets),
                         ("Encryption", self.enc), ("Integrity", self.hash), ("DH group", self.dh)):
            form.addRow(_field_label(label), w)
        self.err = Banner("err")
        lay.addWidget(self.err)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        self.ok = QtWidgets.QPushButton("Save connection")
        self.ok.setObjectName("primary")
        self.ok.setDefault(True)
        for b in (cancel, self.ok):
            b.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self._save)
        row.addWidget(cancel)
        row.addWidget(self.ok)
        lay.addLayout(row)
        self.result_profile = None
        m = (profile or {}).get("manual")
        if m:
            self.setWindowTitle("Edit connection")
            self.name.setText(profile["name"])
            self.server.setText(profile["server"])
            ts = profile.get("remote_ts") or []
            self.nets.setText("" if ts == ["0.0.0.0/0"] else ", ".join(ts))
            for box, key in ((self.enc, "enc"), (self.hash, "hash"), (self.dh, "dh")):
                box.setCurrentIndex(max(0, box.findData(m.get(key))))

    @staticmethod
    def _combo(options):
        box = QtWidgets.QComboBox()
        for k, v in options.items():
            box.addItem(v, k)
        return box

    def _save(self):
        try:
            self.result_profile = forti.manual_profile(
                self.name.text(), self.server.text(), self.enc.currentData(), self.hash.currentData(),
                self.dh.currentData(), self.nets.text())
            if self.user.text().strip():
                forti.validate(self.result_profile, self.user.text().strip(), "eap")
        except forti.ConfigError as e:
            self.err.setText(str(e))
            self.result_profile = None
            return
        self.accept()

    def credentials(self):
        return self.user.text().strip(), self.pw.text(), self.psk.text()


class MainWindow(QtWidgets.QWidget):
    job_done = QtCore.pyqtSignal(str, object)
    problems_ready = QtCore.pyqtSignal(object)

    def __init__(self, start_hidden=False):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.icons = icons()
        self.setWindowIcon(self.icons["off"])
        self.setMinimumWidth(540)
        self.resize(580, 800)
        self.setAcceptDrops(True)
        self.profile = core.load_profile()
        self.state = "off"
        self.busy = False
        self.expect_drop = False
        self.was_connected = False
        self.problems = []
        self.quitting = False
        self._build_ui()
        self._build_tray()
        self.job_done.connect(self._on_job_done)
        self.problems_ready.connect(self._on_problems)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self._load_settings()
        self._render_profile()
        self.recheck_system()
        self.refresh()
        if not start_hidden or not self.tray_ok:
            self.show_window()

    # ---------- UI ----------
    def _build_ui(self):
        self.setObjectName("root")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 14)
        outer.setSpacing(12)
        inner = QtWidgets.QWidget()
        inner.setObjectName("body")
        root = QtWidgets.QVBoxLayout(inner)      # scrollable body: nothing clips on small screens
        root.setContentsMargins(1, 1, 9, 1)
        root.setSpacing(12)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setWidget(inner)
        self.body = inner

        # hero: big status tile that tints with the connection state
        self.hero = QtWidgets.QFrame()
        self.hero.setObjectName("hero")
        self.hero.setProperty("state", "off")
        head = QtWidgets.QHBoxLayout(self.hero)
        head.setContentsMargins(16, 14, 16, 14)
        head.setSpacing(14)
        self.dot = QtWidgets.QLabel()
        self.dot.setFixedSize(48, 48)
        self.status_lbl = QtWidgets.QLabel()
        self.status_lbl.setObjectName("status")
        f = self.status_lbl.font()
        f.setPointSize(f.pointSize() + 5)
        self.status_lbl.setFont(f)
        self.sub_lbl = QtWidgets.QLabel()
        self.sub_lbl.setObjectName("substatus")
        self.sub_lbl.setWordWrap(True)
        col = QtWidgets.QVBoxLayout()
        col.setSpacing(1)
        col.addWidget(self.status_lbl)
        col.addWidget(self.sub_lbl)
        head.addWidget(self.dot)
        head.addLayout(col, 1)
        outer.addWidget(self.hero)

        self.setup_box, sb = _card("System setup")
        self.setup_lbl = QtWidgets.QLabel()
        self.setup_lbl.setWordWrap(True)
        self.setup_btn = QtWidgets.QPushButton("Set up system components…")
        self.setup_btn.setCursor(Qt.PointingHandCursor)
        self.setup_btn.clicked.connect(self.run_setup)
        sb.addWidget(self.setup_lbl)
        sb.addWidget(self.setup_btn)
        root.addWidget(self.setup_box)

        cfg, cl = _card("Configuration")
        self.prof_lbl = QtWidgets.QLabel()
        self.prof_lbl.setObjectName("profile")
        self.prof_lbl.setWordWrap(True)
        self.prof_lbl.setTextFormat(Qt.RichText)
        self.warn_lbl = Banner("warn")
        self.imp_btn = QtWidgets.QPushButton("Import FortiClient config…")
        self.imp_btn.setCursor(Qt.PointingHandCursor)
        self.imp_btn.clicked.connect(self.pick_config)
        self.add_btn = QtWidgets.QPushButton("Add manually…")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.add_manually)
        btns = QtWidgets.QHBoxLayout()
        btns.setSpacing(8)
        btns.addWidget(self.imp_btn, 1)
        btns.addWidget(self.add_btn, 1)
        cl.addWidget(self.prof_lbl)
        cl.addWidget(self.warn_lbl)
        cl.addLayout(btns)
        root.addWidget(cfg)

        self.form_box, fv = _card("Sign in")
        fl = QtWidgets.QFormLayout()
        fl.setHorizontalSpacing(14)
        fl.setVerticalSpacing(10)
        fl.setFieldGrowthPolicy(QtWidgets.QFormLayout.ExpandingFieldsGrow)
        fv.addLayout(fl)
        self.user = QtWidgets.QLineEdit()
        self.pw = QtWidgets.QLineEdit()
        self.pw.setEchoMode(QtWidgets.QLineEdit.Password)
        self.psk = QtWidgets.QLineEdit()
        self.psk.setEchoMode(QtWidgets.QLineEdit.Password)
        self.mode = QtWidgets.QComboBox()
        for k, v in forti.AUTH_MODES.items():
            self.mode.addItem(v, k)
        self.route = QtWidgets.QComboBox()
        self.route.addItem("Everything", "all")
        self.route.addItem("Only these networks", "custom")
        self.routes = QtWidgets.QLineEdit()
        self.routes.setPlaceholderText("10.0.0.0/8, 192.168.50.0/24")
        self.route.currentIndexChanged.connect(lambda: self.routes.setEnabled(self.route.currentData() == "custom"))
        self.peer = QtWidgets.QLineEdit()
        self.peer.setPlaceholderText("Same as username")
        self.peer.setToolTip("The ID your FortiGate expects (FortiClient's \u201cLocal ID\u201d). Leave empty to use the username.")
        self.remember = QtWidgets.QCheckBox("Remember password and key")
        for label, w in (("Username", self.user), ("Password", self.pw), ("Pre-shared key", self.psk),
                         ("Authentication", self.mode), ("Peer ID", self.peer), ("Route", self.route), ("Networks", self.routes)):
            fl.addRow(_field_label(label), w)
        self.strict = QtWidgets.QCheckBox("Strict firewall mode (random local ports)")
        self.strict.setToolTip("Use random local UDP ports instead of 500/4500. Try this when the gateway never "
                               "replies from behind a strict firewall.")
        fv.addSpacing(2)
        fv.addWidget(self.strict)
        fv.addWidget(self.remember)
        for w in (self.strict, self.remember, self.mode, self.route):
            w.setCursor(Qt.PointingHandCursor)
        root.addWidget(self.form_box)

        self.err = Banner("err")
        self.err.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.err)
        root.addStretch(1)
        outer.addWidget(self.scroll, 1)

        self.go = QtWidgets.QPushButton("Connect")
        self.go.setObjectName("primary")
        self.go.setCursor(Qt.PointingHandCursor)
        self.go.setMinimumHeight(46)
        self.go.setDefault(True)
        self.go.clicked.connect(self.toggle_connection)
        outer.addWidget(self.go)

        opts = QtWidgets.QHBoxLayout()
        self.autostart = QtWidgets.QCheckBox("Start at login (in tray)")
        self.autostart.toggled.connect(self.set_autostart)
        self.menu_btn = QtWidgets.QPushButton("Add to app menu")
        self.menu_btn.setObjectName("link")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.clicked.connect(self.add_to_menu)
        opts.addWidget(self.autostart, 1)
        opts.addWidget(self.menu_btn)
        outer.addLayout(opts)

        self.log_btn = QtWidgets.QPushButton("Show technical log")
        self.log_btn.setObjectName("link")
        self.log_btn.setCursor(Qt.PointingHandCursor)
        self.log_btn.setCheckable(True)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(90)
        self.log.hide()
        self.log_btn.toggled.connect(lambda on: (self.log.setVisible(on),
                                                 self.log_btn.setText("Hide technical log" if on else "Show technical log")))
        outer.addWidget(self.log_btn, 0, Qt.AlignLeft)
        outer.addWidget(self.log)
        self.autostart.setEnabled(bool(appimage_path()))
        self.menu_btn.setEnabled(bool(appimage_path()))
        self.autostart.setChecked(os.path.exists(self._autostart_file()))
        self._migrate_legacy_desktop_files()

    def _build_tray(self):
        self.tray_ok = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
        self.tray = QtWidgets.QSystemTrayIcon(self.icons["off"], self)
        m = QtWidgets.QMenu()
        self.act_status = m.addAction("Disconnected")
        self.act_status.setEnabled(False)
        m.addSeparator()
        self.act_show = m.addAction("Show window")
        self.act_show.triggered.connect(self.toggle_window)
        self.act_conn = m.addAction("Connect")
        self.act_conn.triggered.connect(self.toggle_connection_from_tray)
        m.addSeparator()
        m.addAction("Quit").triggered.connect(self.quit_app)
        self.tray_menu = m
        self.tray.setContextMenu(m)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    # ---------- window <-> tray ----------
    def show_window(self):
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show_window()

    def _tray_activated(self, reason):
        if reason in (QtWidgets.QSystemTrayIcon.Trigger, QtWidgets.QSystemTrayIcon.DoubleClick):
            self.toggle_window()

    def closeEvent(self, e):
        if self.quitting or not (self.tray_ok and self.tray.isVisible()):
            e.accept()
            QtWidgets.QApplication.quit()
            return
        e.ignore()
        self.hide()
        if not getattr(self, "_told", False):
            self._told = True
            self.notify("Still running", "IPSec VPN - Design By Rashid is in the system tray. Click the icon to open it.")

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.WindowStateChange and self.isMinimized() and self.tray_ok and self.tray.isVisible():
            QtCore.QTimer.singleShot(0, self.hide)
        super().changeEvent(e)

    def quit_app(self):
        if self.state == "on":
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle("Quit IPSec VPN - Design By Rashid")
            box.setText("The VPN is connected. Disconnect before quitting?")
            d = box.addButton("Disconnect and quit", QtWidgets.QMessageBox.AcceptRole)
            k = box.addButton("Quit, stay connected", QtWidgets.QMessageBox.DestructiveRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            box.exec_()
            if box.clickedButton() is d:
                self.expect_drop = True
                core.disconnect(self.profile)
            elif box.clickedButton() is not k:
                return
        self.quitting = True
        self.tray.hide()
        QtWidgets.QApplication.quit()

    def notify(self, title, msg, warn=False):
        if self.tray_ok:
            self.tray.showMessage(title, msg, QtWidgets.QSystemTrayIcon.Warning if warn
                                  else QtWidgets.QSystemTrayIcon.Information, 5000)

    # drag & drop a .conf onto the window
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.import_config(u.toLocalFile())
                break

    # ---------- settings / profile ----------
    def _load_settings(self):
        s = core.load_settings()
        self.user.setText(s.get("username") or "")
        self.mode.setCurrentIndex(max(0, self.mode.findData(s.get("auth_mode") or "eap")))
        self.routes.setText(s.get("routes") or "")
        self.route.setCurrentIndex(1 if s.get("routes") else 0)
        self.routes.setEnabled(bool(s.get("routes")))
        self.strict.setChecked(bool(s.get("random_ports")))
        self.peer.setText(s.get("local_id") or "")
        self.remember.setChecked(bool(s.get("remember")))
        self._update_saved_placeholders()

    def _update_saved_placeholders(self):
        saved = bool(core.load_secrets())
        self.pw.setPlaceholderText("Saved" if saved else "")
        self.psk.setPlaceholderText("Saved" if saved else "")

    def _render_profile(self):
        p = self.profile
        if not p:
            self.prof_lbl.setText("No connection yet. Import your <b>FortiClient .conf export</b> "
                                  "(or drop it on this window), or add the connection by hand.")
            self.warn_lbl.setText("")
            self.imp_btn.setText("Import FortiClient config…")
            self.add_btn.setText("Add manually…")
        else:
            self.prof_lbl.setText(
                f"<b>{html.escape(p['name'])}</b><br>Server: {html.escape(p['server'])}<br>IKEv2 · {p['ike_proposals'][0]} (+{len(p['ike_proposals']) - 1})"
                f"<br>Lifetimes: IKE {p['ike_lifetime'] // 3600} h · ESP {p['esp_lifetime'] // 3600} h")
            self.warn_lbl.setText("\n".join(p.get("warnings") or []))
            self.imp_btn.setText("Import a different config…")
            self.add_btn.setText("Edit connection…" if p.get("manual") else "Add manually…")
        self.form_box.setEnabled(bool(p))
        self.go.setEnabled(bool(p) and not self.busy and not self.problems)

    def pick_config(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose FortiClient config", os.path.expanduser("~"),
            "FortiClient config (*.conf *.xml);;All files (*)")
        if path:
            self.import_config(path)

    def add_manually(self):
        dlg = ProfileDialog(self, self.profile if (self.profile or {}).get("manual") else None,
                            username=self.user.text().strip())
        if dlg.exec_() == QtWidgets.QDialog.Accepted and dlg.result_profile:
            self.err.setText("")
            self.profile = dlg.result_profile
            core.save_profile(self.profile)
            user, pw, psk = dlg.credentials()      # fill the Sign in form; "Remember" decides what is kept
            if user:
                self.user.setText(user)
            if pw:
                self.pw.setText(pw)
            if psk:
                self.psk.setText(psk)
            self._render_profile()

    def import_config(self, path):
        try:
            with open(path, encoding="utf-8-sig") as f:
                profiles = forti.parse_forticlient(f.read())
        except (OSError, forti.ConfigError, UnicodeDecodeError) as e:
            self.err.setText(f"Could not import: {e}")
            return
        self.err.setText("")
        self.profile = profiles[0]
        core.save_profile(self.profile)
        self._render_profile()

    # ---------- system setup ----------
    def recheck_system(self):
        threading.Thread(target=lambda: self.problems_ready.emit(sysetup.check()), daemon=True).start()

    def _on_problems(self, problems):
        self.problems = problems
        self.setup_box.setVisible(bool(problems))
        if problems:
            self.setup_lbl.setText("Before the first connection this computer needs: " + "; ".join(problems)
                                   + ".\nThis installs strongSwan and a small helper, and asks for your "
                                     "administrator password once.")
        self._render_profile()
        self._update_actions()

    def run_setup(self):
        app = appimage_path()
        cmd = [app] if app else [sys.executable, "-m", "ipsec_vpn.app"]
        if app and ".mount_" not in os.environ.get("APPDIR", ""):
            # launched without FUSE (extract-and-run): root must do the same
            cmd = ["env", "APPIMAGE_EXTRACT_AND_RUN=1"] + cmd
        self.setup_btn.setEnabled(False)
        self.log.appendPlainText("Starting system setup…")  # log stays collapsed unless the user opens it
        proc = QtCore.QProcess(self)
        proc.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self.log.appendPlainText(bytes(proc.readAllStandardOutput()).decode(errors="replace").rstrip()))

        def finished(code, _status):
            self.setup_btn.setEnabled(True)
            if code == 0:
                self.log.appendPlainText("Setup finished.")
                self.err.setText("")
            else:
                manual = f"sudo '{app or 'ipsec-vpn'}' --system-setup"
                self.err.setText("Setup did not complete (administrator permission was denied or unavailable).\n"
                                 f"You can run it in a terminal instead:\n{manual}")
            self.recheck_system()
        proc.finished.connect(finished)
        proc.start("pkexec", cmd + ["--system-setup"])
        self._setup_proc = proc

    # ---------- connection ----------
    def refresh(self):
        st = core.status()
        on = bool(st.get("connected"))
        if self.was_connected and not on and not self.expect_drop and not self.busy:
            self.notify("VPN connection lost", st.get("note") or "The tunnel to the gateway went down.", warn=True)
        if not on:
            self.expect_drop = False
        self.was_connected = on
        self._st = st
        self._apply_state("busy" if self.busy else "on" if on else "off", st)

    def _apply_state(self, state, st=None):
        st = st or getattr(self, "_st", {})
        self.state = state
        self.dot.setPixmap(make_pixmap(state, 48))
        self.hero.setProperty("state", state)
        theme.repolish(self.hero)
        self.hero.style().polish(self.status_lbl)
        self.status_lbl.setText(STATE_TEXT[state])
        if state == "on":
            self.sub_lbl.setText(f"VPN address {st.get('vip') or 'unknown'} · server {st.get('server', '')}")
        else:
            self.sub_lbl.setText(st.get("note") or "")
        self.sub_lbl.setVisible(bool(self.sub_lbl.text()))
        self.tray.setIcon(self.icons[state])
        self.setWindowIcon(self.icons[state])
        self.tray.setToolTip(f"{APP_NAME} — {STATE_TEXT[state]}")
        self.act_status.setText(STATE_TEXT[state] + (f" ({st.get('vip')})" if state == "on" and st.get("vip") else ""))
        self._update_actions()

    def _update_actions(self):
        on = self.state == "on"
        ready = bool(self.profile) and not self.problems and not self.busy
        self.go.setText("Disconnect" if on else "Connect")
        self.go.setProperty("danger", on)
        theme.repolish(self.go)
        self.go.setEnabled(ready or (on and not self.busy))
        self.form_box.setEnabled(bool(self.profile) and not on and not self.busy)
        self.act_conn.setText("Disconnect" if on else "Connect")
        self.act_conn.setEnabled(ready or (on and not self.busy))

    def _inputs(self):
        s = core.load_settings()
        sec = core.load_secrets()
        user = self.user.text().strip()
        pw = self.pw.text() or sec.get("password", "")
        psk = self.psk.text() or sec.get("psk", "")
        mode = self.mode.currentData()
        routes = self.routes.text().strip() if self.route.currentData() == "custom" else ""
        return user, pw, psk, mode, routes, s

    def toggle_connection(self):
        if self.state == "on":
            return self.disconnect()
        user, pw, psk, mode, routes, _ = self._inputs()
        if not pw or not psk:
            self.err.setText("Enter the password and the pre-shared key.")
            return
        self.connect_with(user, pw, psk, mode, routes, remember=self.remember.isChecked())

    def toggle_connection_from_tray(self):
        if self.state == "on":
            return self.disconnect()
        user, pw, psk, mode, routes, s = self._inputs()
        if user and pw and psk:
            self.connect_with(user, pw, psk, mode, routes, remember=bool(s.get("remember")))
        else:
            self.show_window()
            self.err.setText("Enter your credentials once (tick “Remember” to connect from the tray in one click).")

    def connect_with(self, user, pw, psk, mode, routes, remember):
        try:
            prof = forti.with_routes(self.profile, routes)
            forti.validate(prof, user, mode)
        except forti.ConfigError as e:
            self.err.setText(str(e))
            return
        strict = self.strict.isChecked()
        local_id = self.peer.text().strip()
        core.save_settings({"username": user, "auth_mode": mode, "remember": remember, "routes": routes,
                            "random_ports": strict, "local_id": local_id})
        if remember:
            core.save_secrets(pw, psk)
        else:
            core.clear_secrets()
        self.pw.clear()
        self.psk.clear()
        self._update_saved_placeholders()
        self.err.setText("")
        self._run_job("connect", lambda: core.connect(prof, user, pw, psk, mode, random_ports=strict,
                                                         local_id=local_id))

    def disconnect(self):
        self.expect_drop = True
        self._run_job("disconnect", lambda: core.disconnect(self.profile))

    def _run_job(self, kind, fn):
        if self.busy:
            return
        self.busy = True
        self._apply_state("busy")

        def work():
            try:
                r = fn()
            except Exception as e:  # keep the UI alive whatever happens
                r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            self.job_done.emit(kind, r)
        threading.Thread(target=work, daemon=True).start()

    def _on_job_done(self, kind, r):
        self.busy = False
        if r.get("log"):
            self.log.appendPlainText(r["log"])
        if r.get("ok"):
            if kind == "connect":
                vip = (r.get("state") or {}).get("vip")
                self.notify("VPN connected", f"VPN address {vip}" if vip else "Tunnel established.")
            else:
                self.notify("VPN disconnected", "The tunnel is closed.")
        else:
            msg = r.get("error", "Failed")
            self.err.setText(msg)
            self.log.appendPlainText(msg)
            self.notify("VPN " + kind + " failed", msg.splitlines()[0], warn=True)
            if kind == "disconnect":
                self.expect_drop = False
        self.refresh()

    # ---------- desktop integration ----------
    @staticmethod
    def _autostart_file():
        return os.path.expanduser("~/.config/autostart/ipsec-vpn.desktop")

    def _migrate_legacy_desktop_files(self):
        """Replace launcher entries written by earlier versions (old name) with current ones."""
        home = os.path.expanduser("~")
        old_auto = os.path.join(home, ".config/autostart/diadem-vpn.desktop")
        old_menu = os.path.join(home, ".local/share/applications/diadem-vpn.desktop")
        old_icon = os.path.join(home, ".local/share/icons/hicolor/256x256/apps/diadem-vpn.png")
        if os.path.exists(old_auto):
            os.remove(old_auto)
            if appimage_path():
                self.autostart.setChecked(True)
        for p in (old_menu, old_icon):
            if os.path.exists(p):
                os.remove(p)
                if p is old_menu and appimage_path():
                    self.add_to_menu(announce=False)

    def set_autostart(self, on):
        path = self._autostart_file()
        if on and appimage_path():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec=\"{appimage_path()}\" --minimized\n"
                        "Icon=ipsec-vpn\nX-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(path):
            os.remove(path)

    def add_to_menu(self, announce=True):
        app = appimage_path()
        if not app:
            return
        icon_dir = os.path.expanduser("~/.local/share/icons/hicolor/256x256/apps")
        os.makedirs(icon_dir, exist_ok=True)
        make_pixmap("on", 256).save(os.path.join(icon_dir, "ipsec-vpn.png"))
        apps = os.path.expanduser("~/.local/share/applications")
        os.makedirs(apps, exist_ok=True)
        with open(os.path.join(apps, "ipsec-vpn.desktop"), "w") as f:
            f.write(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nComment=IPsec VPN client\n"
                    f"Exec=\"{app}\"\nIcon=ipsec-vpn\nCategories=Network;\nTerminal=false\n")
        if announce:
            self.notify("Added to menu", "IPSec VPN - Design By Rashid now appears in your application menu.")


def _single_instance(name):
    """Return (server, None) if we are the first instance, else (None, True) after asking the first to show."""
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return None, True
    QtNetwork.QLocalServer.removeServer(name)
    srv = QtNetwork.QLocalServer()
    srv.listen(name)
    return srv, False


def main(argv):
    hidden = "--minimized" in argv
    smoke = argv[argv.index("--smoke") + 1] if "--smoke" in argv else None
    app = QtWidgets.QApplication([APP_NAME] + [a for a in argv if a not in ("--minimized",)])
    app.setApplicationName("ipsec-vpn")
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("ipsec-vpn")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    bump_font(app, FONT_BUMP_PX)
    theme.apply_theme(app)
    srv, already = _single_instance(f"ipsec-vpn-{os.getuid()}")
    if already and not smoke:
        return 0
    win = MainWindow(start_hidden=hidden)
    if srv:
        srv.newConnection.connect(lambda: (srv.nextPendingConnection(), win.show_window()))
    if smoke:
        def snap():
            win.grab().save(smoke)
            print("SMOKE OK tray_available=%s version=%s" % (win.tray_ok, __version__))
            app.quit()
        QtCore.QTimer.singleShot(1500, snap)
    return app.exec_()
