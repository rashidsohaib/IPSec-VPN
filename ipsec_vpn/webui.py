"""Local web UI. Binds 127.0.0.1 only, random port, per-run token required on every API call."""
import http.server
import json
import secrets
import os
import socketserver
import threading
import time
import webbrowser

from . import core, forti
from .page import PAGE

MAX_BODY = 200_000
IDLE_EXIT = 150  # seconds without a poll (background tabs are throttled to ~1/min)


class State:
    token = secrets.token_urlsafe(24)
    job = {"busy": False, "msg": "", "ok": None, "log": ""}
    lock = threading.Lock()
    last_seen = None


def make_handler(state, port_getter):
    class H(http.server.BaseHTTPRequestHandler):
        server_version = "IPSecVPN"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else (
                json.dumps(body) if ctype == "application/json" else body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            return self.headers.get("Host", "") in (f"127.0.0.1:{port_getter()}", f"localhost:{port_getter()}")

        def _authed(self):
            return self._host_ok() and secrets.compare_digest(
                self.headers.get("X-Token", ""), state.token)

        def do_GET(self):
            path, _, q = self.path.partition("?")
            if path == "/" and self._host_ok() and secrets.compare_digest(
                    q.replace("t=", "", 1), state.token):
                return self._send(200, PAGE.replace("__TOKEN__", state.token), "text/html")
            if not self._authed():
                return self._send(403, {"error": "forbidden"})
            if path == "/api/state":
                state.last_seen = time.time()
                p = core.load_profile()
                s = core.load_settings()
                sec = core.load_secrets()
                return self._send(200, {
                    "profile": p, "settings": s, "has_secrets": bool(sec),
                    "status": core.status(), "job": state.job,
                    "auth_modes": forti.AUTH_MODES})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._authed():
                return self._send(403, {"error": "forbidden"})
            n = int(self.headers.get("Content-Length", 0) or 0)
            if n > MAX_BODY:
                return self._send(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            path = self.path
            if path == "/api/import":
                try:
                    profiles = forti.parse_forticlient(body.get("xml", ""))
                except forti.ConfigError as e:
                    return self._send(200, {"ok": False, "error": str(e)})
                core.save_profile(profiles[0])
                return self._send(200, {"ok": True, "profile": profiles[0]})
            if path == "/api/connect":
                return self._connect(body)
            if path == "/api/disconnect":
                return self._disconnect()
            if path == "/api/forget":
                core.clear_secrets()
                return self._send(200, {"ok": True})
            self._send(404, {"error": "not found"})

        def _start_job(self, msg, fn):
            with state.lock:
                if state.job["busy"]:
                    return self._send(200, {"ok": False, "error": "Another action is in progress."})
                state.job = {"busy": True, "msg": msg, "ok": None, "log": ""}

            def run():
                try:
                    r = fn()
                except Exception as e:
                    r = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                state.job = {"busy": False, "ok": bool(r.get("ok")),
                             "msg": "" if r.get("ok") else r.get("error", "Failed"),
                             "log": r.get("log", "")}
            threading.Thread(target=run, daemon=True).start()
            self._send(200, {"ok": True})

        def _connect(self, b):
            p = core.load_profile()
            if not p:
                return self._send(200, {"ok": False, "error": "Import a config first."})
            sec = core.load_secrets()
            user = (b.get("username") or "").strip()
            pw = b.get("password") or sec.get("password", "")
            psk = b.get("psk") or sec.get("psk", "")
            mode = b.get("auth_mode", "eap")
            routes = (b.get("routes") or "").strip()
            strict = bool(b.get("strict"))
            try:
                p = forti.with_routes(p, routes)
                forti.validate(p, user, mode)
            except forti.ConfigError as e:
                return self._send(200, {"ok": False, "error": str(e)})
            if not pw or not psk:
                return self._send(200, {"ok": False, "error": "Password and pre-shared key are required."})
            core.save_settings({"username": user, "auth_mode": mode, "remember": bool(b.get("remember")), "routes": routes,
                                "random_ports": strict})
            if b.get("remember"):
                core.save_secrets(pw, psk)
            else:
                core.clear_secrets()
            self._start_job("Connecting...", lambda: core.connect(p, user, pw, psk, mode, random_ports=strict))

        def _disconnect(self):
            p = core.load_profile()
            if not p:
                return self._send(200, {"ok": False, "error": "No profile."})
            self._start_job("Disconnecting...", lambda: core.disconnect(p))
    return H


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def run(open_browser=True):
    state = State()
    srv = Server(("127.0.0.1", 0), None)
    srv.RequestHandlerClass = make_handler(state, lambda: srv.server_address[1])
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={state.token}"
    print("IPSec VPN - Design By Rashid is running at", url, "\nPress Ctrl+C to quit.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    def watchdog():  # quit shortly after the browser tab is closed
        while True:
            time.sleep(10)
            if state.last_seen and time.time() - state.last_seen > IDLE_EXIT:
                print("Browser closed, exiting.")
                os._exit(0)
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
