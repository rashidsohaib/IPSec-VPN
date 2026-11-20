import argparse
import getpass
import sys

from . import core, forti


def _need_profile():
    p = core.load_profile()
    if not p:
        sys.exit("No profile imported yet. Run: ipsec-vpn import <your FortiClient export>.conf")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ipsec-vpn", description="IPsec VPN client for FortiClient configs")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("ui", help="open the app in your browser (default)")
    i = sub.add_parser("import", help="import a FortiClient .conf export")
    i.add_argument("file")
    sub.add_parser("show", help="show the imported profile")
    c = sub.add_parser("connect", help="connect from the terminal")
    c.add_argument("--mode", choices=list(forti.AUTH_MODES), default=None)
    sub.add_parser("disconnect")
    sub.add_parser("status")
    a = ap.parse_args(argv)

    if a.cmd in (None, "ui"):
        from . import webui
        return webui.run()
    if a.cmd == "import":
        try:
            profiles = forti.parse_forticlient(open(a.file, encoding="utf-8-sig").read())
        except (OSError, forti.ConfigError) as e:
            sys.exit(str(e))
        core.save_profile(profiles[0])
        print(f"Imported '{profiles[0]['name']}' -> {profiles[0]['server']}")
        for w in profiles[0]["warnings"]:
            print("note:", w)
        return 0
    if a.cmd == "show":
        p = _need_profile()
        for k, v in p.items():
            print(f"{k}: {v}")
        return 0
    if a.cmd == "status":
        st = core.status()
        print("Connected to %s (VPN IP %s)" % (st.get("server"), st.get("vip")) if st.get("connected")
              else "Not connected" + (f" - {st['note']}" if st.get("note") else ""))
        return 0 if st.get("connected") else 1
    p = _need_profile()
    if a.cmd == "disconnect":
        r = core.disconnect(p)
        print("Disconnected." if r.get("ok") else r.get("error"))
        return 0 if r.get("ok") else 1
    if a.cmd == "connect":
        s = core.load_settings()
        sec = core.load_secrets()
        user = s.get("username") or input("Username: ").strip()
        pw = sec.get("password") or getpass.getpass("Password: ")
        psk = sec.get("psk") or getpass.getpass("Pre-shared key: ")
        try:
            r = core.connect(p, user, pw, psk, a.mode or s.get("auth_mode", "eap"))
        except forti.ConfigError as e:
            sys.exit(str(e))
        if r.get("ok"):
            print("Connected. VPN IP:", r["state"].get("vip") or "unknown")
            return 0
        print(r.get("error"))
        return 1
