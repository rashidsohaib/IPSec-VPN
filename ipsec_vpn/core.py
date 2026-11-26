"""Unprivileged side: profile storage, helper invocation, status."""
import json
import os
import shutil
import subprocess

from . import forti

HELPER = "/usr/local/lib/ipsec-vpn/ipsec-vpn-helper"
STATE_FILE = "/run/ipsec-vpn/state.json"


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    d = os.path.join(base, "ipsec-vpn")
    old = os.path.join(base, "diadem-vpn")  # folder used by earlier versions
    if not os.path.isdir(d) and os.path.isdir(old):
        shutil.copytree(old, d)
        os.chmod(d, 0o700)
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _read(name):
    try:
        with open(os.path.join(config_dir(), name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write(name, data):
    path = os.path.join(config_dir(), name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def load_profile():
    return _read("profile.json")


def save_profile(profile):
    _write("profile.json", profile)


def load_settings():
    return _read("settings.json") or {"username": "", "auth_mode": "eap", "remember": False, "routes": "", "random_ports": False, "local_id": ""}


def save_settings(s):
    _write("settings.json", {k: s.get(k) for k in ("username", "auth_mode", "remember", "routes", "random_ports", "local_id")})


def load_secrets():
    return _read("secrets.json") or {}


def save_secrets(password, psk):
    _write("secrets.json", {"password": password, "psk": psk})


def clear_secrets():
    try:
        os.remove(os.path.join(config_dir(), "secrets.json"))
    except FileNotFoundError:
        pass


def run_helper(req, helper=None, use_sudo=True, timeout=120):
    cmd = ([] if os.geteuid() == 0 or not use_sudo else ["sudo", "-n"]) + [helper or HELPER]
    try:
        r = subprocess.run(cmd, input=json.dumps(req), capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "error": "Helper not installed. Run install.sh first."}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "The helper timed out."}
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        if "password is required" in r.stderr or "a terminal is required" in r.stderr:
            return {"ok": False, "error": "sudo needs a password for the helper. Re-run install.sh."}
        return {"ok": False, "error": (r.stderr or "Helper returned no output.").strip()[:400]}


def _local_ips():
    try:
        out = subprocess.run(["ip", "-o", "-4", "addr"], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return set()
    return {part.split("/")[0] for line in out.splitlines() for part in line.split() if "/" in part}


def status(state_file=STATE_FILE, local_ips=None):
    try:
        with open(state_file) as f:
            st = json.load(f)
    except (OSError, ValueError):
        return {"connected": False}
    if not st.get("connected"):
        return {"connected": False}
    vip = st.get("vip")
    if vip and vip not in (local_ips if local_ips is not None else _local_ips()):
        return {"connected": False, "note": "Tunnel dropped (gateway or network went away)."}
    return st


def connect(profile, username, password, psk, auth_mode, random_ports=False, local_id="", **kw):
    forti.validate(profile, username, auth_mode, local_id)
    return run_helper({"action": "connect", "profile": profile, "username": username,
                       "password": password, "psk": psk, "auth_mode": auth_mode,
                       "random_ports": bool(random_ports), "local_id": local_id or ""}, **kw)


def disconnect(profile, **kw):
    return run_helper({"action": "disconnect", "profile": profile}, **kw)
