"""Parse a FortiClient XML export and render a strongSwan swanctl config.

Pure standard library, no side effects. Shared by the unprivileged UI/CLI and
the root helper (the helper re-validates everything it receives).
"""
import re
import xml.etree.ElementTree as ET

DH_GROUPS = {
    1: "modp768", 2: "modp1024", 5: "modp1536", 14: "modp2048", 15: "modp3072",
    16: "modp4096", 17: "modp6144", 18: "modp8192", 19: "ecp256", 20: "ecp384",
    21: "ecp521", 28: "ecp256bp", 29: "ecp384bp", 30: "ecp512bp",
    31: "curve25519", 32: "curve448",
}
ENC = {"AES128": "aes128", "AES192": "aes192", "AES256": "aes256",
       "3DES": "3des", "AES128GCM": "aes128gcm16", "AES256GCM": "aes256gcm16"}
HASH = {"SHA1": "sha1", "SHA256": "sha256", "SHA384": "sha384",
        "SHA512": "sha512", "MD5": "md5"}

AUTH_MODES = {
    "eap": "EAP login (try first)",
    "psk+eap": "PSK, then EAP (alternative)",
}

_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-:]{0,251}[A-Za-z0-9])?$")
_ID_RE = re.compile(r"^[A-Za-z0-9._@+\-\\]{1,128}$")
_PROP_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+){1,3}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]{1,32}$")
_TS_RE = re.compile(r"^[0-9a-fA-F:.]+/\d{1,3}$")


class ConfigError(ValueError):
    pass


def _txt(node, path, default=""):
    el = node.find(path)
    return (el.text or "").strip() if el is not None and el.text else default


def _proposals(node, dh_names):
    out = []
    for p in node.findall("proposals/proposal"):
        raw = (p.text or "").strip()
        try:
            enc, hsh = [x.strip().upper() for x in raw.split("|")]
            e, h = ENC[enc], HASH[hsh]
        except (ValueError, KeyError):
            raise ConfigError(f"Unsupported proposal '{raw}' in config")
        if e.endswith("gcm16"):
            base = e
        else:
            base = f"{e}-{h}"
        out.append(base + "".join("-" + d for d in dh_names[:1]) if dh_names else base)
    return out


def _dh(text):
    names = []
    for part in re.split(r"[;,\s]+", text or ""):
        if not part:
            continue
        try:
            names.append(DH_GROUPS[int(part)])
        except (ValueError, KeyError):
            raise ConfigError(f"Unsupported Diffie-Hellman group '{part}'")
    return names


def parse_forticlient(xml_text):
    """Return a list of profile dicts, one per IPsec connection in the export."""
    try:
        root = ET.fromstring(xml_text.encode() if isinstance(xml_text, str) else xml_text)
    except ET.ParseError as e:
        raise ConfigError(f"Not a valid FortiClient XML export: {e}")
    if root.tag != "forticlient_configuration":
        raise ConfigError("This is not a FortiClient configuration export.")
    conns = root.findall("vpn/ipsecvpn/connections/connection")
    if not conns:
        raise ConfigError("No IPsec VPN connection found in this file.")
    profiles = []
    for c in conns:
        ike = c.find("ike_settings")
        ips = c.find("ipsec_settings")
        if ike is None or ips is None:
            continue
        warnings = []
        version = int(_txt(ike, "version", "1") or 1)
        if version != 2:
            raise ConfigError("This connection uses IKEv1, which this app does not support (IKEv2 only).")
        method = _txt(ike, "authentication_method")
        if method.lower() != "preshared key":
            warnings.append(f"Authentication method '{method}' is not supported; only Preshared Key is. ")
        ike_dh = _dh(_txt(ike, "dhgroup"))
        esp_dh = _dh(_txt(ips, "dhgroup")) if _txt(ips, "pfs", "1") == "1" else []
        ike_props = _proposals(ike, ike_dh)
        esp_props = _proposals(ips, esp_dh)
        if not ike_props or not esp_props:
            raise ConfigError("Config has no IKE/ESP proposals.")
        networks = []
        for n in ips.findall("remote_networks/network"):
            addr, mask = _txt(n, "addr"), _txt(n, "mask")
            if ":" in addr:
                continue  # IPv6 is blocked in this config (block_ipv6=1)
            try:
                bits = sum(bin(int(o)).count("1") for o in mask.split("."))
            except ValueError:
                bits = 0
            networks.append(f"{addr}/{bits}")
        if not networks:
            networks = ["0.0.0.0/0"]
        tcp_port = int(_txt(ike, "tcp_port", "0") or 0)
        if tcp_port:
            warnings.append(f"The config lists TCP port {tcp_port} as a fallback transport; "
                            "strongSwan cannot use it, so UDP 500/4500 must be reachable.")
        if _txt(ike, "xauth/enabled", "0") != "1":
            warnings.append("This config has no username/password (xauth) step; EAP login will not be used.")
        profiles.append({
            "name": _txt(c, "name", "VPN"),
            "server": _txt(ike, "server"),
            "ike_proposals": ike_props,
            "esp_proposals": esp_props,
            "ike_lifetime": int(_txt(ike, "key_life", "86400") or 86400),
            "esp_lifetime": int(_txt(ips, "key_life_seconds", "43200") or 43200),
            "dpd": _txt(ike, "dpd", "1") == "1",
            "dpd_interval": int(_txt(ike, "dpd_retry_interval", "5") or 5),
            "mode_config": _txt(ike, "mode_config", "1") == "1",
            "remote_ts": networks,
            "use_eap": _txt(ike, "xauth/enabled", "0") == "1",
            "ike_fragmentation": _txt(ike, "enable_ike_fragmentation", "0") == "1",
            "warnings": warnings,
        })
    if not profiles:
        raise ConfigError("No usable IPsec connection found.")
    return profiles


MANUAL_ENC = {"aes128": "AES-128", "aes256": "AES-256", "both": "AES-128 and AES-256"}
MANUAL_HASH = {"sha256": "SHA-256", "sha1": "SHA-1", "both": "SHA-256 and SHA-1"}
MANUAL_DH = {"ecp521": "Group 21 (ECP-521)", "ecp384": "Group 20 (ECP-384)", "ecp256": "Group 19 (ECP-256)",
             "modp2048": "Group 14 (MODP-2048)", "modp1536": "Group 5 (MODP-1536)", "modp1024": "Group 2 (MODP-1024)"}


def manual_profile(name, server, enc="aes128", hsh="sha256", dh="ecp521", networks="0.0.0.0/0"):
    """Build a profile without a FortiClient export (same shape parse_forticlient returns).

    enc/hsh may be 'both'. The DH group is used for IKE and for ESP (PFS), as FortiClient does.
    """
    name = (name or "").strip()
    server = (server or "").strip()
    if not name:
        raise ConfigError("Give the connection a name.")
    if not server:
        raise ConfigError("Enter the gateway address.")
    if enc not in MANUAL_ENC or hsh not in MANUAL_HASH or dh not in MANUAL_DH:
        raise ConfigError("Unknown encryption, hash or Diffie-Hellman choice.")
    encs = ["aes128", "aes256"] if enc == "both" else [enc]
    hashes = ["sha256", "sha1"] if hsh == "both" else [hsh]
    props = [f"{e}-{h}-{dh}" for e in encs for h in hashes]
    nets = [x for x in re.split(r"[,\s;]+", networks or "") if x] or ["0.0.0.0/0"]
    nets = [n if "/" in n else n + "/32" for n in nets]
    profile = {
        "name": name, "server": server, "ike_proposals": props, "esp_proposals": list(props),
        "ike_lifetime": 86400, "esp_lifetime": 43200, "dpd": True, "dpd_interval": 5, "mode_config": True,
        "remote_ts": nets, "use_eap": True, "ike_fragmentation": False, "warnings": [],
        "manual": {"enc": enc, "hash": hsh, "dh": dh},
    }
    if not _NAME_RE.match(conn_name(profile)):
        raise ConfigError("Invalid connection name.")
    validate(profile, "user", "eap")          # checks server, proposals and networks
    return profile


def conn_name(profile):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", profile.get("name", "vpn")).strip("-").lower()[:24] or "vpn"
    return "vpn-" + slug


def validate(profile, username, auth_mode, local_id=""):
    if not _HOST_RE.match(profile.get("server", "")):
        raise ConfigError("Invalid server address.")
    if not _ID_RE.match(username or ""):
        raise ConfigError("Username may only contain letters, digits and . _ @ + - \\")
    if local_id and not _ID_RE.match(local_id):
        raise ConfigError("Peer ID may only contain letters, digits and . _ @ + - \\")
    if auth_mode not in AUTH_MODES:
        raise ConfigError("Unknown authentication mode.")
    for key in ("ike_proposals", "esp_proposals"):
        props = profile.get(key) or []
        if not props or not all(_PROP_RE.match(p) for p in props):
            raise ConfigError(f"Invalid {key}.")
    if not all(_TS_RE.match(t) for t in profile.get("remote_ts") or []):
        raise ConfigError("Invalid remote network.")
    if not _NAME_RE.match(conn_name(profile)):
        raise ConfigError("Invalid connection name.")
    for key in ("ike_lifetime", "esp_lifetime", "dpd_interval"):
        v = profile.get(key)
        if not isinstance(v, int) or not 1 <= v <= 10 * 86400:
            raise ConfigError(f"Invalid {key}.")


def with_routes(profile, text):
    """Return a copy of profile whose remote networks are the CIDRs in text ('' = keep config's routes)."""
    nets = [x for x in re.split(r"[,\s;]+", text or "") if x]
    if not nets:
        return profile
    nets = [n if "/" in n else n + "/32" for n in nets]
    if not all(_TS_RE.match(n) and ":" not in n for n in nets):
        raise ConfigError("Routes must be IPv4 networks like 10.0.0.0/8 or 192.168.10.0/24.")
    return dict(profile, remote_ts=nets)


def _hex(s):
    return "0x" + s.encode("utf-8").hex()


def render_swanctl(profile, username, password, psk, auth_mode="eap", local_id=""):
    """Return swanctl.conf text. Secrets are written as hex so no quoting/injection issues."""
    validate(profile, username, auth_mode, local_id)
    if not password or not psk:
        raise ConfigError("Password and pre-shared key are required.")
    name = conn_name(profile)
    ike = ", ".join(profile["ike_proposals"])
    esp = ", ".join(profile["esp_proposals"])
    ts = ", ".join(profile["remote_ts"])
    frag = "yes" if profile.get("ike_fragmentation") else "accept"
    dpd = f"    dpd_delay = {profile['dpd_interval']}s\n" if profile.get("dpd") else ""
    vips = "    vips = 0.0.0.0\n" if profile.get("mode_config", True) else ""
    # The FortiGate picks the dial-up tunnel by the peer ID (FortiClient's "Local ID"; without one, the user name).
    # Without an explicit id strongSwan would send the laptop's own IP address, which the gateway ignores.
    ident = local_id or username
    if auth_mode == "psk+eap":
        local = (f"    local-1 {{\n      auth = psk\n      id = {ident}\n    }}\n"
                 f"    local-2 {{\n      auth = eap-mschapv2\n      id = {ident}\n      eap_id = {username}\n    }}\n")
    else:
        local = f"    local {{\n      auth = eap-mschapv2\n      id = {ident}\n      eap_id = {username}\n    }}\n"
    return f"""# Generated by IPSec VPN - Design By Rashid - do not edit, removed on disconnect.
connections {{
  {name} {{
    version = 2
    remote_addrs = {profile['server']}
    proposals = {ike}
    encap = yes
    fragmentation = {frag}
{dpd}{vips}    reauth_time = 0
    rekey_time = {profile['ike_lifetime']}s
    over_time = 1h
{local}    remote {{
      auth = psk
    }}
    children {{
      {name} {{
        remote_ts = {ts}
        esp_proposals = {esp}
        rekey_time = {profile['esp_lifetime']}s
        start_action = none
        dpd_action = clear
      }}
    }}
  }}
}}

secrets {{
  ike-{name} {{
    secret = {_hex(psk)}
  }}
  eap-{name} {{
    id = {username}
    secret = {_hex(password)}
  }}
}}
"""
