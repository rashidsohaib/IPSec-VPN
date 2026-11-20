"""Root helper. Runs via `sudo -n /usr/local/lib/ipsec-vpn/ipsec-vpn-helper`.

Reads one JSON request on stdin, prints one JSON response on stdout.
Everything is re-validated here; the caller is not trusted.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    from . import forti
except ImportError:  # run as a script from the install dir
    import forti

CONF_DIR = "/etc/swanctl/conf.d"
CONF_FILE = "ipsec-vpn.conf"
STATE_DIR = "/run/ipsec-vpn"
VICI_SOCKET = "/var/run/charon.vici"
_VIP_RE = re.compile(r"\[(\d{1,3}(?:\.\d{1,3}){3})\]")


class HelperError(Exception):
    pass


def _swanctl(args, swanctl="swanctl", timeout=60):
    try:
        r = subprocess.run([swanctl] + args, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise HelperError("strongSwan is not installed (swanctl not found). Run the installer again.")
    except subprocess.TimeoutExpired:
        raise HelperError("swanctl timed out.")
    return r.returncode, (r.stdout + r.stderr).strip()


def explain(output):
    o = output.lower()
    if "authentication_failed" in o or "eap_failure" in o or "eap authentication failed" in o:
        return ("The gateway rejected the login. Check username, password and pre-shared key; "
                "if those are right, try the other 'Authentication mode'.")
    if "no_proposal_chosen" in o:
        return "The gateway rejected the encryption proposals in the config."
    if ("timeout" in o or "timed out" in o or "giving up after" in o or "not established after" in o
            or "retransmit" in o):
        return ("No reply from the gateway. UDP 500/4500 may be blocked on this network "
                "(the config's TCP 5500 fallback is not supported), or the server address is wrong.")
    if "invalid_ke_payload" in o:
        return "Diffie-Hellman group mismatch with the gateway."
    return None


def clean(output):
    """Drop strongSwan's harmless 'plugin ... failed to load' chatter so real errors are readable."""
    keep = [l for l in output.splitlines()
            if not l.startswith("plugin '") and "plugin requires CAP_" not in l]
    return "\n".join(keep).strip()


def ensure_daemon(swanctl="swanctl", vici=VICI_SOCKET, wait=8):
    if os.path.exists(vici):
        return
    for unit in ("strongswan", "strongswan-swanctl", "charon-systemd"):
        subprocess.run(["systemctl", "start", unit], capture_output=True)
        for _ in range(wait * 2):
            if os.path.exists(vici):
                return
            time.sleep(0.5)
    raise HelperError("The strongSwan service (charon) is not running and could not be started.")


def write_conf(text, conf_dir=CONF_DIR):
    os.makedirs(conf_dir, exist_ok=True)
    path = os.path.join(conf_dir, CONF_FILE)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(path, 0o600)
    return path


def write_state(data, state_dir=STATE_DIR):
    os.makedirs(state_dir, exist_ok=True)
    path = os.path.join(state_dir, "state.json")
    with open(path, "w") as f:
        json.dump(data, f)
    os.chmod(path, 0o644)


def _reload(swanctl):
    rc, out = _swanctl(["--load-all", "--clear"], swanctl)
    if rc != 0:
        rc, out = _swanctl(["--load-all"], swanctl)
    if rc != 0:
        raise HelperError("Could not load the VPN config: " + out)


def do_connect(req, swanctl="swanctl", conf_dir=CONF_DIR, state_dir=STATE_DIR, vici=VICI_SOCKET):
    profile = req["profile"]
    text = forti.render_swanctl(profile, req["username"], req["password"], req["psk"],
                                req.get("auth_mode", "eap"))
    name = forti.conn_name(profile)
    ensure_daemon(swanctl, vici)
    _swanctl(["--terminate", "--ike", name], swanctl)  # clear any stale session
    write_conf(text, conf_dir)
    try:
        _reload(swanctl)
        rc, out = _swanctl(["--initiate", "--ike", name, "--child", name, "--timeout", "30"],
                           swanctl, timeout=60)
    finally:
        pass
    if rc != 0:
        do_disconnect(req, swanctl, conf_dir, state_dir, quiet=True)
        raise HelperError((explain(out) or "Connection failed.") + "\n\n" + clean(out))
    _, sas = _swanctl(["--list-sas", "--ike", name], swanctl)
    m = _VIP_RE.search(sas)
    state = {"connected": True, "name": name, "since": int(time.time()),
             "vip": m.group(1) if m else None, "server": profile["server"]}
    write_state(state, state_dir)
    # Credentials need not stay on disk once the tunnel is up (rekeys use loaded secrets).
    try:
        os.remove(os.path.join(conf_dir, CONF_FILE))
    except FileNotFoundError:
        pass
    return {"ok": True, "state": state, "log": out}


def do_disconnect(req, swanctl="swanctl", conf_dir=CONF_DIR, state_dir=STATE_DIR, vici=None, quiet=False):
    name = forti.conn_name(req["profile"]) if req.get("profile") else None
    out = ""
    if name:
        _, out = _swanctl(["--terminate", "--ike", name], swanctl)
    try:
        os.remove(os.path.join(conf_dir, CONF_FILE))
    except FileNotFoundError:
        pass
    try:
        _reload(swanctl)
    except HelperError:
        if not quiet:
            raise
    write_state({"connected": False}, state_dir)
    return {"ok": True, "log": out}


def handle(req, **kw):
    action = req.get("action")
    if action == "connect":
        return do_connect(req, **kw)
    if action == "disconnect":
        return do_disconnect(req, **kw)
    raise HelperError("Unknown action.")


def main():
    if os.geteuid() != 0:
        print(json.dumps({"ok": False, "error": "helper must run as root"}))
        return 1
    try:
        req = json.loads(sys.stdin.read(65536))
        resp = handle(req)
    except (HelperError, forti.ConfigError) as e:
        resp = {"ok": False, "error": str(e)}
    except Exception as e:  # never leak a traceback with secrets
        resp = {"ok": False, "error": f"Internal error: {type(e).__name__}"}
    print(json.dumps(resp))
    return 0 if resp.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
