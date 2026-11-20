"""One-time system setup (runs as root via `--system-setup`) and a cheap readiness check.

Installs strongSwan, the root-owned helper, and a sudoers rule that lets *one* user run only that helper.
Used by the AppImage (pkexec <AppImage> --system-setup) and runnable with plain sudo.
"""
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile

from . import __version__

LIB = "/usr/local/lib/ipsec-vpn"
SUDOERS = "/etc/sudoers.d/ipsec-vpn"
APT_PKGS = ["strongswan", "strongswan-swanctl", "charon-systemd", "libcharon-extauth-plugins",
            "libstrongswan-standard-plugins", "python3", "iproute2"]
# Files written by private builds made before the app was renamed; removed on setup so no stale
# sudo rule or helper is left behind. Safe to delete these lines if you never used such a build.
LEGACY = ["/usr/local/lib/diadem-vpn", "/etc/sudoers.d/diadem-vpn", "/usr/local/bin/diadem-vpn",
          "/usr/share/applications/diadem-vpn.desktop", "/etc/swanctl/conf.d/diadem-vpn.conf"]
PKG_FILES = ["__init__.py", "forti.py", "helper.py"]
HELPER_SCRIPT = """#!/usr/bin/python3 -I
import os, sys
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from ipsec_vpn import helper
sys.exit(helper.main())
"""
_USER_RE = re.compile(r"^[a-z_][a-z0-9_.-]{0,31}$")


def have_swanctl():
    return bool(shutil.which("swanctl") or os.path.exists("/usr/sbin/swanctl"))


def installed_version(lib=LIB):
    try:
        with open(os.path.join(lib, "ipsec_vpn", "__init__.py")) as f:
            m = re.search(r'__version__\s*=\s*"([^"]+)"', f.read())
        return m.group(1) if m else None
    except OSError:
        return None


def check(lib=LIB):
    """Return a list of problems; empty means ready to connect."""
    problems = []
    if not have_swanctl():
        problems.append("strongSwan is not installed")
    v = installed_version(lib)
    if v is None:
        problems.append("the VPN helper is not installed")
    elif v != __version__:
        problems.append(f"the VPN helper is out of date ({v} installed, {__version__} needed)")
    else:
        helper = os.path.join(lib, "ipsec-vpn-helper")
        r = subprocess.run(["sudo", "-n", "-l", helper], capture_output=True)
        if r.returncode != 0:
            problems.append("this user is not allowed to run the VPN helper")
    return problems


def target_user():
    uid = os.environ.get("PKEXEC_UID")
    if uid and uid.isdigit():
        return pwd.getpwuid(int(uid)).pw_name
    return os.environ.get("SUDO_USER") or ""


def install(user, lib=LIB, sudoers=SUDOERS, pkg_dir=None, do_apt=True, log=print, legacy=None):
    if not _USER_RE.match(user or "") or user == "root":
        raise SystemExit("Could not determine which user to authorise (run via pkexec or sudo from your account).")
    pkg_dir = pkg_dir or os.path.dirname(os.path.abspath(__file__))
    if do_apt:
        log("==> Installing strongSwan (IKEv2 + EAP support)")
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        if subprocess.run(["apt-get", "update", "-qq"], env=env).returncode != 0:
            log("WARNING: apt-get update reported errors (dead repository?); continuing.")
        if subprocess.run(["apt-get", "install", "-y"] + APT_PKGS, env=env).returncode != 0:
            raise SystemExit("Could not install strongSwan. Fix your apt repositories and try again.")
        subprocess.run(["systemctl", "disable", "--now", "strongswan-starter"], capture_output=True)
        subprocess.run(["systemctl", "enable", "--now", "strongswan"], capture_output=True)
    for p in (LEGACY if legacy is None else legacy):  # leftovers of the pre-rename install
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
        elif os.path.lexists(p):
            os.remove(p)
    log("==> Installing the VPN helper (root-owned)")
    shutil.rmtree(lib, ignore_errors=True)
    os.makedirs(os.path.join(lib, "ipsec_vpn"), mode=0o755)
    for name in PKG_FILES:
        shutil.copyfile(os.path.join(pkg_dir, name), os.path.join(lib, "ipsec_vpn", name))
        os.chmod(os.path.join(lib, "ipsec_vpn", name), 0o644)
    helper = os.path.join(lib, "ipsec-vpn-helper")
    with open(helper, "w") as f:
        f.write(HELPER_SCRIPT)
    os.chmod(helper, 0o755)
    log(f"==> Allowing '{user}' to run only the VPN helper without a password")
    fd, tmp = tempfile.mkstemp()
    try:
        with os.fdopen(fd, "w") as f:
            f.write(f"{user} ALL=(root) NOPASSWD: {helper}\n")
        if shutil.which("visudo") and subprocess.run(["visudo", "-cf", tmp], capture_output=True).returncode != 0:
            raise SystemExit("sudoers validation failed; aborting.")
        os.makedirs(os.path.dirname(sudoers), exist_ok=True)
        shutil.copyfile(tmp, sudoers)
        os.chmod(sudoers, 0o440)
    finally:
        os.unlink(tmp)
    log("==> Done.")


def run_cli():
    if os.geteuid() != 0:
        print("System setup must run as root: sudo <this AppImage> --system-setup", file=sys.stderr)
        return 1
    try:
        install(target_user())
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 1
    return 0
