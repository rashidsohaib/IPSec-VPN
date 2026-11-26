#!/usr/bin/env python3
"""IKE reachability probe (no root, no extra packages).

Sends a harmless IKEv2 IKE_SA_INIT request to a gateway on UDP 500 and UDP 4500 from a random source port
and reports whether ANY reply comes back. A reply (even an error such as NO_PROPOSAL_CHOSEN) proves the
network path and the gateway's IKE service work; silence means a firewall/NAT or the gateway drops it.

    python3 ike_probe.py 103.253.125.4
    python3 ike_probe.py GATEWAY --src-port 500     # needs root and the VPN service stopped
"""
import argparse
import os
import socket
import struct
import sys

NOTIFY = {1: "UNSUPPORTED_CRITICAL_PAYLOAD", 4: "INVALID_IKE_SPI", 5: "INVALID_MAJOR_VERSION", 7: "INVALID_SYNTAX",
          14: "NO_PROPOSAL_CHOSEN", 17: "INVALID_KE_PAYLOAD", 24: "AUTHENTICATION_FAILED",
          43: "TEMPORARY_FAILURE", 16404: "COOKIE"}


def transform(last, ttype, tid, keylen=None):
    attr = struct.pack("!HH", 0x800E, keylen) if keylen else b""
    return struct.pack("!BBHBBH", 0 if last else 3, 0, 8 + len(attr), ttype, 0, tid) + attr


def build_init():
    ispi = os.urandom(8)
    transforms = (transform(False, 1, 12, 128) +      # ENCR AES-CBC-128
                  transform(False, 2, 5) +            # PRF HMAC-SHA2-256
                  transform(False, 3, 12) +           # INTEG HMAC-SHA2-256-128
                  transform(False, 4, 14) +           # DH modp2048
                  transform(True, 4, 21))             # DH ecp521
    proposal = struct.pack("!BBHBBBB", 0, 0, 8 + len(transforms), 1, 1, 0, 5) + transforms
    sa = struct.pack("!BBH", 34, 0, 4 + len(proposal)) + proposal
    key = bytes([os.urandom(1)[0] & 0x7F]) + os.urandom(255)
    ke = struct.pack("!BBHHH", 40, 0, 4 + 4 + len(key), 14, 0) + key
    nonce = struct.pack("!BBH", 0, 0, 4 + 32) + os.urandom(32)
    body = sa + ke + nonce
    header = struct.pack("!8s8sBBBBII", ispi, b"\0" * 8, 33, 0x20, 34, 0x08, 0, 28 + len(body))
    return ispi, header + body


def parse(reply, ispi):
    if len(reply) < 28 or reply[:8] != ispi:
        return None
    nxt, ver, exch, flags = reply[16], reply[17], reply[18], reply[19]
    if exch != 34 or not flags & 0x20:
        return None
    if nxt == 41 and len(reply) >= 36:
        code = struct.unpack("!H", reply[34:36])[0]
        return "error reply: " + NOTIFY.get(code, f"notify {code}")
    if nxt == 33:
        return "normal IKE_SA_INIT response (gateway accepted a proposal)"
    return f"IKE response (next payload {nxt})"


def probe(host, port, src_port, tries, wait):
    ispi, pkt = build_init()
    if port == 4500:
        pkt = b"\0\0\0\0" + pkt                      # non-ESP marker for NAT-T port
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(wait)
    try:
        s.bind(("", src_port))
    except OSError as e:
        return None, f"could not use source port {src_port}: {e}"
    for _ in range(tries):
        s.sendto(pkt, (host, port))
        try:
            data, _addr = s.recvfrom(4096)
        except socket.timeout:
            continue
        if port == 4500 and data[:4] == b"\0\0\0\0":
            data = data[4:]
        res = parse(data, ispi)
        if res:
            return True, res
    return False, "no reply"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("--src-port", type=int, default=0, help="local source port (default: random)")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--wait", type=float, default=3.0, help="seconds to wait per try")
    ap.add_argument("--ports", default="500,4500")
    a = ap.parse_args()
    host = socket.gethostbyname(a.host)
    src = "random source port" if not a.src_port else f"source port {a.src_port}"
    print(f"Probing {host} from {src} ({a.tries} tries x {a.wait:g}s per port)\n")
    results = {}
    for port in [int(p) for p in a.ports.split(",")]:
        ok, msg = probe(host, port, a.src_port, a.tries, a.wait)
        results[port] = ok
        print(f"  UDP {port}: {'REPLY' if ok else 'NO REPLY'} - {msg}")
    print()
    if results.get(500):
        print("RESULT: the gateway answers on UDP 500. The network path works from a random source port.\n"
              "        If the VPN client still fails, the firewall probably mishandles traffic whose SOURCE port\n"
              "        is 500 (the VPN client's default). Send me this output.")
    elif results.get(4500):
        print("RESULT: UDP 4500 is answered but UDP 500 is not: something drops port 500 to this server.")
    else:
        print("RESULT: no answer on either port. Packets are dropped before a reply reaches you. Check, in order:\n"
              "  1. Gajshield: an OUTBOUND (LAN -> internet) rule allowing UDP 500 and 4500 to the gateway, with\n"
              "     NAT/masquerade applied to it. 'Opening ports' as an inbound/port-forward rule is not enough.\n"
              "  2. Gajshield: disable any VPN/IPsec pass-through proxy, ALG, IPS or deep inspection for this traffic;\n"
              "     look in its firewall log for drops from your laptop to the gateway address.\n"
              "  3. Gateway side: its administrator can check whether it receives packets from your office's public\n"
              "     IP and whether that address is allowed to reach the VPN service at all.")
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
