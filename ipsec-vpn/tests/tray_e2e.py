"""Tray integration test: mock StatusNotifierWatcher + Notifications on a private session bus."""
import asyncio, os, sys, tempfile, threading, time
sys.path.insert(0, "/tmp/dbusnext")
from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next import Variant, BusType, DBusError

notes = []
items = []

class Notif(ServiceInterface):
    def __init__(self): super().__init__("org.freedesktop.Notifications")
    @method()
    def Notify(self, app: "s", rid: "u", icon: "s", summary: "s", body: "s", actions: "as", hints: "a{sv}", timeout: "i") -> "u":
        notes.append((summary, body)); return len(notes)
    @method()
    def GetCapabilities(self) -> "as": return ["body"]
    @method()
    def GetServerInformation(self) -> "ssss": return ["mock", "t", "1", "1.2"]
    @method()
    def CloseNotification(self, i: "u"): pass

result = {}
async def server_side(ready):
    bus = await MessageBus(bus_type=BusType.SESSION).connect()
    bus.export("/org/freedesktop/Notifications", Notif())
    await bus.request_name("org.freedesktop.Notifications")
    ready.set()
    return bus

def dbus_thread(win_ref, ready):
    async def run():
        bus = await server_side(ready)
        for _ in range(80):
            await asyncio.sleep(0.25)
            r = await bus.call(__import__("dbus_next").Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus", interface="org.freedesktop.DBus", member="ListNames"))
            names = [n for n in r.body[0] if n.startswith("org.kde.StatusNotifierItem")]
            if names and win_ref: items[:] = names; break
        result["items"] = list(items)
        win = win_ref[0]
        svc, _, path = items[0].partition("/")
        path = "/" + path if path else "/StatusNotifierItem"
        intro = await bus.introspect(svc, path)
        proxy = bus.get_proxy_object(svc, path, intro)
        sni = proxy.get_interface("org.kde.StatusNotifierItem")
        result["title"] = await sni.get_title()
        result["status"] = await sni.get_status()
        menu_path = await sni.get_menu()
        # menu layout
        mi = await bus.introspect(svc, menu_path)
        mp = bus.get_proxy_object(svc, menu_path, mi).get_interface("com.canonical.dbusmenu")
        rev, layout = await mp.call_get_layout(0, -1, [])
        labels = []
        def walk(n):
            _id, props, kids = n
            if "label" in props: labels.append(props["label"].value)
            for k in kids: walk(k.value if hasattr(k, "value") else k)
        walk(layout)
        result["menu"] = labels
        # left click toggles window
        before = win.isVisible()
        await sni.call_activate(0, 0); await asyncio.sleep(0.6)
        result["vis"] = (before, win.isVisible())
        await sni.call_activate(0, 0); await asyncio.sleep(0.6)
        result["vis2"] = win.isVisible()
        # closing the window hides to tray + notifies
        win.show_window(); await asyncio.sleep(0.4)
        win.close(); await asyncio.sleep(0.8)
        result["after_close"] = (win.isVisible(), win.quitting)
        result["notes"] = list(notes)
        win._apply_state("on", {"vip": "10.9.8.7", "server": "x"}); await asyncio.sleep(0.5)
        result["tip"] = win.tray.toolTip()
        QtCore.QMetaObject.invokeMethod(app, "quit", QtCore.Qt.QueuedConnection)
    asyncio.run(run())

os.environ.setdefault("XDG_CONFIG_HOME", tempfile.mkdtemp())
from PyQt5 import QtWidgets, QtCore
from ipsec_vpn import qt_app
ready = threading.Event(); win_ref = []
th = threading.Thread(target=dbus_thread, args=(win_ref, ready), daemon=True); th.start()
ready.wait(10)
app = QtWidgets.QApplication(["t"]); app.setQuitOnLastWindowClosed(False)
win = qt_app.MainWindow(start_hidden=True); win_ref.append(win)
print("tray_ok:", win.tray_ok)
QtCore.QTimer.singleShot(40000, app.quit)
app.exec_()
for k, v in result.items(): print(k, "=", v)
assert win.tray_ok and result.get("items"), "tray did not register with the watcher"
assert result["vis"] == (False, True) and result["vis2"] is False, result["vis"]
assert {"Show window", "Connect", "Quit"} <= set(result["menu"]), result["menu"]
assert result["after_close"][0] is False and not result["after_close"][1]
assert any("tray" in b.lower() for _, b in result["notes"]), result["notes"]
assert "Connected" in result["tip"]
print("TRAY E2E PASSED")
