"""Minimal org.kde.StatusNotifierWatcher built on Qt D-Bus (so Qt clients treat it like Plasma's)."""
import sys
from PyQt5 import QtCore, QtDBus
XML = """<interface name="org.kde.StatusNotifierWatcher">
  <method name="RegisterStatusNotifierItem"><arg direction="in" type="s" name="service"/></method>
  <method name="RegisterStatusNotifierHost"><arg direction="in" type="s" name="service"/></method>
  <property name="RegisteredStatusNotifierItems" type="as" access="read"/>
  <property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
  <property name="ProtocolVersion" type="i" access="read"/>
  <signal name="StatusNotifierItemRegistered"><arg type="s"/></signal>
  <signal name="StatusNotifierHostRegistered"/>
</interface>"""

class Adaptor(QtDBus.QDBusAbstractAdaptor):
    QtCore.Q_CLASSINFO("D-Bus Interface", "org.kde.StatusNotifierWatcher")
    QtCore.Q_CLASSINFO("D-Bus Introspection", XML)
    StatusNotifierItemRegistered = QtCore.pyqtSignal(str)
    StatusNotifierHostRegistered = QtCore.pyqtSignal()
    def __init__(self, parent):
        super().__init__(parent); self._items = []
    @QtCore.pyqtProperty(bool)
    def IsStatusNotifierHostRegistered(self): return True
    @QtCore.pyqtProperty(int)
    def ProtocolVersion(self): return 0
    @QtCore.pyqtProperty("QStringList")
    def RegisteredStatusNotifierItems(self): return self._items
    @QtCore.pyqtSlot(str)
    def RegisterStatusNotifierItem(self, s):
        self._items.append(s); self.StatusNotifierItemRegistered.emit(s)
        print("REGISTERED", s, flush=True)
    @QtCore.pyqtSlot(str)
    def RegisterStatusNotifierHost(self, s): pass

app = QtCore.QCoreApplication(sys.argv)
obj = QtCore.QObject(); ad = Adaptor(obj)
bus = QtDBus.QDBusConnection.sessionBus()
assert bus.registerService("org.kde.StatusNotifierWatcher")
assert bus.registerObject("/StatusNotifierWatcher", obj)
print("WATCHER UP", flush=True)
QtCore.QTimer.singleShot(int(sys.argv[1]) * 1000 if len(sys.argv) > 1 else 60000, app.quit)
app.exec_()
