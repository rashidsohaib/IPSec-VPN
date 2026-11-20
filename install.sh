#!/bin/bash
# Installs IPSec VPN - Design By Rashid system-wide. Run:  sudo ./install.sh
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo:  sudo ./install.sh" >&2; exit 1; }
TARGET_USER="${SUDO_USER:-}"
[ -n "$TARGET_USER" ] && [ "$TARGET_USER" != root ] || { echo "Run it via sudo from your normal user account." >&2; exit 1; }
SRC="$(cd "$(dirname "$0")" && pwd)"
LIB=/usr/local/lib/ipsec-vpn

echo "==> Installing strongSwan (IKEv2 + EAP support)"
export DEBIAN_FRONTEND=noninteractive
# A dead third-party repo (e.g. Q4OS mirrors) makes "apt-get update" exit non-zero even though the
# Debian lists were refreshed fine, so don't abort on it; the install below is the real test.
apt-get update -qq || echo "WARNING: apt-get update reported errors (see above); continuing with the lists that did load."
apt-get install -y strongswan strongswan-swanctl charon-systemd \
    libcharon-extauth-plugins libstrongswan-standard-plugins python3 iproute2
# The classic starter service would conflict with charon-systemd; the app uses swanctl only.
systemctl disable --now strongswan-starter >/dev/null 2>&1 || true
systemctl enable --now strongswan >/dev/null 2>&1 || true

echo "==> Installing app to $LIB (root-owned, so the sudo helper cannot be tampered with)"
rm -rf "$LIB"
# remove files from the pre-rename install, if any
rm -f /etc/swanctl/conf.d/diadem-vpn.conf /etc/sudoers.d/diadem-vpn /usr/local/bin/diadem-vpn \
      /usr/share/applications/diadem-vpn.desktop
rm -rf /usr/local/lib/diadem-vpn
install -d -m 755 "$LIB/ipsec_vpn"
install -m 644 "$SRC"/ipsec_vpn/*.py "$LIB/ipsec_vpn/"
cat > "$LIB/ipsec-vpn-helper" <<'PY'
#!/usr/bin/python3 -I
import os, sys
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from ipsec_vpn import helper
sys.exit(helper.main())
PY
chmod 755 "$LIB/ipsec-vpn-helper"
chown -R root:root "$LIB"

cat > /usr/local/bin/ipsec-vpn <<'SH'
#!/bin/sh
PYTHONPATH=/usr/local/lib/ipsec-vpn exec python3 -s -m ipsec_vpn "$@"
SH
chmod 755 /usr/local/bin/ipsec-vpn
install -m 644 "$SRC/packaging/ipsec-vpn.desktop" /usr/share/applications/ipsec-vpn.desktop

echo "==> Allowing '$TARGET_USER' to run only the VPN helper without a password"
TMP="$(mktemp)"
echo "$TARGET_USER ALL=(root) NOPASSWD: $LIB/ipsec-vpn-helper" > "$TMP"
if visudo -cf "$TMP" >/dev/null; then
    install -m 440 -o root -g root "$TMP" /etc/sudoers.d/ipsec-vpn
else
    rm -f "$TMP"; echo "sudoers check failed; aborting" >&2; exit 1
fi
rm -f "$TMP"

echo
echo "Installed. Start it from the menu (Network > IPSec VPN - Design By Rashid) or run:  ipsec-vpn"
