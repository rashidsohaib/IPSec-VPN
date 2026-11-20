import json, os, sys, tempfile, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ipsec_vpn import core, helper, webui, forti
from tests.test_all import FAKE

OUT = sys.argv[1]
d = tempfile.mkdtemp()
sw = os.path.join(d, "swanctl"); open(sw, "w").write(FAKE); os.chmod(sw, 0o755)
os.environ["FAKE_LOG"] = os.path.join(d, "log")
os.environ["XDG_CONFIG_HOME"] = os.path.join(d, "cfg")
vici = os.path.join(d, "vici"); open(vici, "w").close()
kw = dict(swanctl=sw, conf_dir=os.path.join(d, "conf"), state_dir=os.path.join(d, "run"), vici=vici)
core.STATE_FILE = os.path.join(d, "run", "state.json")
orig_status = core.status
core.status = lambda **a: orig_status(state_file=core.STATE_FILE, local_ips={"10.212.134.7"})
def fake_helper(req, **_):
    try: return helper.handle(req, **kw)
    except (helper.HelperError, forti.ConfigError) as e: return {"ok": False, "error": str(e)}
core.run_helper = fake_helper

srv = webui.Server(("127.0.0.1", 0), None)
st = webui.State()
srv.RequestHandlerClass = webui.make_handler(st, lambda: srv.server_address[1])
threading.Thread(target=srv.serve_forever, daemon=True).start()
port = srv.server_address[1]
url = f"http://127.0.0.1:{port}/?t={st.token}"

import urllib.request, urllib.error
def code(u, headers=None):
    try: return urllib.request.urlopen(urllib.request.Request(u, headers=headers or {})).status
    except urllib.error.HTTPError as e: return e.code
assert code(f"http://127.0.0.1:{port}/") == 403, "no token must be refused"
assert code(f"http://127.0.0.1:{port}/api/state") == 403
assert code(f"http://127.0.0.1:{port}/api/state", {"X-Token": st.token, "Host": "evil.com"}) == 403, "bad Host (DNS rebinding)"
print("auth checks ok")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 640, "height": 900}, device_scale_factor=1)
    errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(url)
    pg.set_input_files("#file", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "sample-forticlient.conf"))
    pg.wait_for_selector("#conncard:not(.hide)")
    pg.screenshot(path=f"{OUT}/1-imported.png")
    # bad credentials path first: wrong username chars
    pg.fill("#user", "rashid"); pg.fill("#pw", "secret pw"); pg.fill("#psk", "the-psk")
    pg.check("#remember")
    pg.click("#go")
    pg.wait_for_selector("#onview:not(.hide)", timeout=10000)
    assert pg.inner_text("#vip") == "10.212.134.7", pg.inner_text("#vip")
    assert pg.inner_text("#pill") == "Connected"
    pg.screenshot(path=f"{OUT}/2-connected.png")
    print("connected ok; saved secrets file perms:", oct(os.stat(os.path.join(d, "cfg/ipsec-vpn/secrets.json")).st_mode & 0o777))
    # disconnect (fake status keeps vip, but state file flips to not connected)
    pg.click("#disc")
    pg.wait_for_selector("#offview:not(.hide)", timeout=10000)
    assert pg.input_value("#user") == "rashid"
    assert pg.get_attribute("#pw", "placeholder") == "Saved"
    pg.screenshot(path=f"{OUT}/3-disconnected.png")
    # failure path
    os.environ["FAKE_FAIL"] = "received AUTHENTICATION_FAILED notify error"
    pg.click("#go")
    pg.wait_for_selector("#err:not(.hide)", timeout=10000)
    print("error shown:", pg.inner_text("#err").splitlines()[0])
    pg.screenshot(path=f"{OUT}/4-error.png")
    # dark mode + bad import
    pg.emulate_media(color_scheme="dark"); pg.screenshot(path=f"{OUT}/5-dark.png")
    pg.evaluate("""fetch('/api/import',{method:'POST',headers:{'X-Token':TOKEN},body:JSON.stringify({xml:'<x/>'})}).then(r=>r.json()).then(j=>window.__imp=j)""")
    pg.wait_for_function("window.__imp"); assert pg.evaluate("window.__imp.ok") is False
    assert not errs, errs
    b.close()
print("UI e2e passed")
