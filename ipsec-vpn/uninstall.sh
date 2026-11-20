#!/bin/bash
# Removes IPSec VPN - Design By Rashid. strongSwan packages are left alone unless you pass --purge-strongswan.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo:  sudo ./uninstall.sh" >&2; exit 1; }
for H in /usr/local/lib/ipsec-vpn/ipsec-vpn-helper /usr/local/lib/diadem-vpn/diadem-helper; do   # current + pre-rename
    [ -x "$H" ] && "$H" <<< '{"action":"disconnect","profile":null}' >/dev/null 2>&1 || true
done
rm -f /etc/swanctl/conf.d/ipsec-vpn.conf /etc/sudoers.d/ipsec-vpn \
      /usr/local/bin/ipsec-vpn /usr/share/applications/ipsec-vpn.desktop
rm -rf /usr/local/lib/ipsec-vpn /run/ipsec-vpn
# files from the pre-rename install (harmless if absent)
rm -f /etc/swanctl/conf.d/diadem-vpn.conf /etc/sudoers.d/diadem-vpn /usr/local/bin/diadem-vpn \
      /usr/share/applications/diadem-vpn.desktop
rm -rf /usr/local/lib/diadem-vpn /run/diadem-vpn
if [ "${1:-}" = "--purge-strongswan" ]; then
    apt-get purge -y strongswan strongswan-swanctl charon-systemd libcharon-extauth-plugins libstrongswan-standard-plugins
    apt-get autoremove -y --purge
fi
echo "Removed. Your saved profile is in ~/.config/ipsec-vpn (delete it if you want)."
