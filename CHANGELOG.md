# Changelog

## 1.5.0
- **Add manually…**: create a connection by hand (name, gateway, networks, encryption, integrity, DH group) instead of
  importing a FortiClient export; **Edit connection…** reopens it.

## 1.4.3
- Fix: the VPN configuration file was written with the wrong content (regression in 1.4.2); added a test.

## 1.4.2
- The IKE ID is now the user name (FortiGates match the dial-up tunnel on it); optional **Peer ID** field.

## 1.4.0
- Flat, modern look with light and dark themes.

## 1.3
- Strict firewall mode (random local UDP ports) for firewalls that mishandle IKE from source port 500.

## 1.2
- Renamed to "IPSec VPN - Design By Rashid", larger UI font, technical log collapsed by default, GitHub README.

## 1.1 and earlier
- Tray icon and notifications, split tunnel, AppImage packaging, FortiClient export import.
