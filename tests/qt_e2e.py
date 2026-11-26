import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
d = tempfile.mkdtemp(); os.environ["XDG_CONFIG_HOME"] = d + "/cfg"
from PyQt5 import QtWidgets, QtCore
from ipsec_vpn import core, helper, forti, qt_app, sysetup
from tests.test_all import FAKE
OUT = sys.argv[1]
sw = d + "/swanctl"; open(sw, "w").write(FAKE); os.chmod(sw, 0o755); os.environ["FAKE_LOG"] = d + "/log"
vici = d + "/vici"; open(vici, "w").close()
kw = dict(swanctl=sw, conf_dir=d + "/conf", state_dir=d + "/run", vici=vici, ports_conf=d + "/ports.conf", restart=lambda: None)
sf = d + "/run/state.json"; orig = core.status
core.status = lambda **a: orig(state_file=sf, local_ips={"10.212.134.7"})
seen = {}
def fake(req, **_):
    seen["req"] = req
    try: return helper.handle(req, **kw)
    except (helper.HelperError, forti.ConfigError) as e: return {"ok": False, "error": str(e)}
core.run_helper = fake
sysetup.check = lambda *a, **k: []          # pretend the system is set up

app = QtWidgets.QApplication(["t"]); app.setStyle("Fusion")
from PyQt5 import QtGui
base_px = QtGui.QFontInfo(app.font()).pixelSize()
qt_app.bump_font(app, qt_app.FONT_BUMP_PX)
new_px = QtGui.QFontInfo(app.font()).pixelSize()
assert abs((new_px - base_px) - 2) <= 1, (base_px, new_px)   # UI font is 2px larger
w = qt_app.MainWindow(start_hidden=True)
assert w.log.isHidden() and not w.log_btn.isChecked() and w.log_btn.text() == "Show technical log"  # collapsed by default
def spin(ms=300):
    l = QtCore.QEventLoop(); QtCore.QTimer.singleShot(ms, l.quit); l.exec_()
w.import_config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "sample-forticlient.conf")); spin(200)
assert w.profile and w.profile["server"] == "vpn.example.com"
# manual profile dialog: validation error, then a saved connection that becomes the active profile
d = qt_app.ProfileDialog(w); d.show(); spin(100)
d.ok.click(); assert d.err.text() and d.result_profile is None, "empty form must be refused"
d.name.setText("Office VPN"); d.server.setText("vpn.example.com"); d.nets.setText("10.0.0.0/8"); d.ok.click()
assert d.result_profile and d.result_profile["remote_ts"] == ["10.0.0.0/8"] and d.result_profile["manual"]["dh"] == "ecp521"
w.profile = d.result_profile; core.save_profile(w.profile); w._render_profile()
assert w.add_btn.text() == "Edit connection…" and "Office VPN" in w.prof_lbl.text()
d2 = qt_app.ProfileDialog(w, w.profile); assert d2.name.text() == "Office VPN" and d2.nets.text() == "10.0.0.0/8"
w.import_config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "sample-forticlient.conf")); spin(200)
assert w.add_btn.text() == "Add manually…"
w.user.setText("rashid"); w.pw.setText("pw"); w.psk.setText("psk")
w.route.setCurrentIndex(1); w.routes.setText("10.0.0.0/8"); w.remember.setChecked(True); w.strict.setChecked(True)
assert w.go.isEnabled() and w.go.text() == "Connect"
w.go.click()
for _ in range(40):
    spin(150)
    if w.state == "on": break
assert w.state == "on", (w.state, w.err.text())
assert seen["req"]["profile"]["remote_ts"] == ["10.0.0.0/8"], "split-tunnel route not passed to helper"
assert seen["req"]["random_ports"] is True and core.load_settings()["random_ports"] is True, "strict mode not passed/saved"
assert w.go.text() == "Disconnect" and w.act_conn.text() == "Disconnect" and "10.212.134.7" in w.sub_lbl.text()
assert "Connected" in w.tray.toolTip()
w.grab().save(OUT + "/qt-connected.png")
w.go.click()
for _ in range(40):
    spin(150)
    if w.state == "off": break
assert w.state == "off" and w.go.text() == "Connect", w.state
assert w.pw.placeholderText() == "Saved"       # remembered credentials
# tray "Connect" with remembered credentials connects in one click
w.act_conn.trigger()
for _ in range(40):
    spin(150)
    if w.state == "on": break
assert w.state == "on", "tray one-click connect failed"
# failure path shows an explanation, state returns to off
w.go.click(); spin(1500)
os.environ["FAKE_FAIL"] = "received AUTHENTICATION_FAILED notify error"
w.go.click()
for _ in range(40):
    spin(150)
    if w.err.text(): break
assert "rejected the login" in w.err.text(), w.err.text()
assert w.log.isHidden(), "log must stay collapsed even after an error"
w.log_btn.click(); assert w.log.isVisibleTo(w) and w.log_btn.text() == "Hide technical log"   # user can expand
w.grab().save(OUT + "/qt-error.png")
print("QT E2E PASSED")
