import json, os, stat, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ipsec_vpn import forti, helper, core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL = os.path.join(ROOT, "examples", "sample-forticlient.conf")

FAKE = """#!/bin/bash
echo "$@" >> "$FAKE_LOG"
case "$1" in
  --initiate) if [ -n "$FAKE_FAIL" ]; then echo "$FAKE_FAIL" >&2; exit 1; fi; echo "initiate completed successfully";;
  --list-sas) echo "vpn-example-ipsec: #1, ESTABLISHED, IKEv2"; echo "  local  'x' @ 192.168.1.5[4500] [10.212.134.7]";;
  --load-all) if [ "$2" = "--clear" ] && [ -n "$FAKE_NOCLEAR" ]; then exit 1; fi;;
esac
exit 0
"""

class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.sw = os.path.join(self.d, "swanctl")
        open(self.sw, "w").write(FAKE); os.chmod(self.sw, 0o755)
        self.log = os.path.join(self.d, "log"); os.environ["FAKE_LOG"] = self.log
        os.environ.pop("FAKE_FAIL", None); os.environ.pop("FAKE_NOCLEAR", None)
        self.conf = os.path.join(self.d, "conf.d"); self.state = os.path.join(self.d, "run")
        self.vici = os.path.join(self.d, "vici"); open(self.vici, "w").close()
        self.profile = forti.parse_forticlient(open(REAL).read())[0]
        self.kw = dict(swanctl=self.sw, conf_dir=self.conf, state_dir=self.state, vici=self.vici)
    def req(self, **o):
        r = {"action": "connect", "profile": self.profile, "username": "rashid", "password": "p@ss\"w{o}rd\\",
             "psk": "sec ret'", "auth_mode": "eap"}; r.update(o); return r

class TestParse(Base):
    def test_real_file(self):
        p = self.profile
        self.assertEqual(p["server"], "vpn.example.com")
        self.assertEqual(p["ike_proposals"], ["aes128-sha256-ecp521", "aes256-sha256-ecp521"])
        self.assertEqual(p["esp_proposals"], p["ike_proposals"])
        self.assertEqual((p["ike_lifetime"], p["esp_lifetime"]), (86400, 43200))
        self.assertEqual(p["remote_ts"], ["0.0.0.0/0"])
        self.assertTrue(any("5500" in w for w in p["warnings"]))
    def test_rejects_non_forticlient(self):
        with self.assertRaises(forti.ConfigError): forti.parse_forticlient("<a/>")
        with self.assertRaises(forti.ConfigError): forti.parse_forticlient("garbage")
    def test_ikev1_rejected(self):
        x = open(REAL).read().replace("<ike_settings>\n                        <version>2</version>", "<ike_settings>\n                        <version>1</version>")
        with self.assertRaises(forti.ConfigError): forti.parse_forticlient(x)

class TestRender(Base):
    def test_secrets_hex_and_no_injection(self):
        t = forti.render_swanctl(self.profile, "rashid", 'a"}\nevil{', "k", "eap")
        self.assertNotIn("evil", t)
        self.assertIn("0x" + 'a"}\nevil{'.encode().hex(), t)
        self.assertIn("auth = eap-mschapv2", t); self.assertNotIn("local-1", t)
    def test_multiauth(self):
        t = forti.render_swanctl(self.profile, "rashid", "p", "k", "psk+eap")
        self.assertIn("local-1", t); self.assertIn("local-2", t)
    def test_bad_username_and_server(self):
        for u in ["a b", 'x"', "x\n{", ""]:
            with self.assertRaises(forti.ConfigError): forti.render_swanctl(self.profile, u, "p", "k")
        bad = dict(self.profile, server="1.2.3.4; rm -rf /")
        with self.assertRaises(forti.ConfigError): forti.render_swanctl(bad, "u", "p", "k")
        bad = dict(self.profile, ike_proposals=["aes128 } evil"])
        with self.assertRaises(forti.ConfigError): forti.render_swanctl(bad, "u", "p", "k")

class TestRoutes(Base):
    def test_with_routes(self):
        self.assertEqual(forti.with_routes(self.profile, "")["remote_ts"], ["0.0.0.0/0"])
        r = forti.with_routes(self.profile, "10.0.0.0/8, 192.168.50.0/24 172.16.1.5")
        self.assertEqual(r["remote_ts"], ["10.0.0.0/8", "192.168.50.0/24", "172.16.1.5/32"])
        self.assertIn("remote_ts = 10.0.0.0/8, 192.168.50.0/24", forti.render_swanctl(r, "u", "p", "k"))
        for bad in ["evil", "10.0.0.0/8; x", "fe80::/10"]:
            with self.assertRaises(forti.ConfigError): forti.with_routes(self.profile, bad)

class TestSetup(Base):
    def test_install_and_run_helper(self):
        import subprocess
        from ipsec_vpn import sysetup
        lib = os.path.join(self.d, "lib"); sud = os.path.join(self.d, "sudoers.d", "ipsec-vpn")
        sysetup.install("rashid", lib=lib, sudoers=sud, do_apt=False, log=lambda m: None)
        self.assertEqual(stat.S_IMODE(os.stat(sud).st_mode), 0o440)
        self.assertIn("rashid ALL=(root) NOPASSWD: " + os.path.join(lib, "ipsec-vpn-helper"), open(sud).read())
        self.assertEqual(sysetup.installed_version(lib), sysetup.__version__)
        # the installed copy must run on its own (isolated mode, flat package) and refuse bad input
        r = subprocess.run([os.path.join(lib, "ipsec-vpn-helper")], input='{"action":"nope"}', capture_output=True, text=True)
        self.assertEqual(json.loads(r.stdout), {"ok": False, "error": "Unknown action."}, r.stderr)
    def test_rejects_bad_user(self):
        from ipsec_vpn import sysetup
        for u in ["", "root", "a b", "x;rm", "Bob\n"]:
            with self.assertRaises(SystemExit): sysetup.install(u, lib="/nonexistent", sudoers="/nonexistent/x", do_apt=False, log=print)

class TestMigration(Base):
    def test_legacy_files_removed_on_setup(self):
        from ipsec_vpn import sysetup
        old_dir = os.path.join(self.d, "old-lib"); os.makedirs(old_dir); open(os.path.join(old_dir, "x"), "w").close()
        old_file = os.path.join(self.d, "old-sudoers"); open(old_file, "w").close()
        sysetup.install("rashid", lib=os.path.join(self.d, "lib2"), sudoers=os.path.join(self.d, "s2", "ipsec-vpn"),
                        do_apt=False, log=lambda m: None, legacy=[old_dir, old_file, os.path.join(self.d, "absent")])
        self.assertFalse(os.path.exists(old_dir)); self.assertFalse(os.path.exists(old_file))
    def test_settings_folder_migrates(self):
        base = os.path.join(self.d, "xdg"); old = os.path.join(base, "diadem-vpn"); os.makedirs(old)
        with open(os.path.join(old, "profile.json"), "w") as f: f.write('{"name": "kept"}')
        os.chmod(os.path.join(old, "profile.json"), 0o600)
        os.environ["XDG_CONFIG_HOME"] = base
        try:
            self.assertEqual(core.load_profile(), {"name": "kept"})
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(base, "ipsec-vpn", "profile.json")).st_mode), 0o600)
        finally:
            os.environ.pop("XDG_CONFIG_HOME", None)

class TestHelper(Base):
    def test_connect_flow(self):
        r = helper.handle(self.req(), **self.kw)
        self.assertTrue(r["ok"]); self.assertEqual(r["state"]["vip"], "10.212.134.7")
        calls = open(self.log).read()
        self.assertIn("--load-all --clear", calls); self.assertIn("--initiate --ike vpn-example-ipsec --child vpn-example-ipsec", calls)
        # credentials are not left on disk after success
        self.assertFalse(os.path.exists(os.path.join(self.conf, helper.CONF_FILE)))
        self.assertTrue(json.load(open(os.path.join(self.state, "state.json")))["connected"])
    def test_conf_written_0600(self):
        p = helper.write_conf("x", self.conf)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)
    def test_failure_cleans_up_and_explains(self):
        os.environ["FAKE_FAIL"] = "received AUTHENTICATION_FAILED notify error"
        with self.assertRaises(helper.HelperError) as c: helper.handle(self.req(), **self.kw)
        self.assertIn("rejected the login", str(c.exception))
        self.assertFalse(os.path.exists(os.path.join(self.conf, helper.CONF_FILE)))
        self.assertFalse(json.load(open(os.path.join(self.state, "state.json")))["connected"])
    def test_timeout_message(self):
        os.environ["FAKE_FAIL"] = "giving up after 5 retransmits"
        with self.assertRaises(helper.HelperError) as c: helper.handle(self.req(), **self.kw)
        self.assertIn("UDP 500/4500", str(c.exception))
    def test_no_reply_from_gateway_is_explained_and_log_is_cleaned(self):
        os.environ["FAKE_FAIL"] = ("[IKE] retransmit 3 of request with message ID 0\\n"
                                   "plugin 'aes': failed to load - aes_plugin_create not found\\n"
                                   "initiate failed: CHILD_SA 'x' not established after 30000ms")
        os.environ["FAKE_FAIL"] = os.environ["FAKE_FAIL"].replace("\\n", "\n")
        with self.assertRaises(helper.HelperError) as c: helper.handle(self.req(), **self.kw)
        msg = str(c.exception)
        self.assertIn("No reply from the gateway", msg); self.assertNotIn("plugin 'aes'", msg)
        self.assertIn("not established after", msg)
    def test_load_all_without_clear_fallback(self):
        os.environ["FAKE_NOCLEAR"] = "1"
        self.assertTrue(helper.handle(self.req(), **self.kw)["ok"])
    def test_disconnect(self):
        helper.handle(self.req(), **self.kw)
        r = helper.handle({"action": "disconnect", "profile": self.profile}, **self.kw)
        self.assertTrue(r["ok"])
        self.assertIn("--terminate --ike vpn-example-ipsec", open(self.log).read())
        self.assertFalse(json.load(open(os.path.join(self.state, "state.json")))["connected"])
    def test_helper_validates_input(self):
        with self.assertRaises(forti.ConfigError): helper.handle(self.req(username="a b"), **self.kw)
        with self.assertRaises(helper.HelperError): helper.handle({"action": "rm -rf"}, **self.kw)
    def test_missing_swanctl(self):
        kw = dict(self.kw, swanctl="/nonexistent/swanctl")
        with self.assertRaises(helper.HelperError): helper.handle(self.req(), **kw)

class TestStatus(Base):
    def test_status(self):
        os.makedirs(self.state); f = os.path.join(self.state, "state.json")
        json.dump({"connected": True, "vip": "10.0.0.9", "server": "s", "since": 1}, open(f, "w"))
        self.assertTrue(core.status(f, local_ips={"10.0.0.9"})["connected"])
        self.assertFalse(core.status(f, local_ips={"1.1.1.1"})["connected"])  # dropped tunnel
        self.assertFalse(core.status(os.path.join(self.d, "none"))["connected"])

if __name__ == "__main__":
    unittest.main(verbosity=1)
