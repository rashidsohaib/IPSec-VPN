PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPSec VPN - Design By Rashid</title>
<style>
:root{--bg:#f4f5f7;--card:#fff;--ink:#16191d;--mute:#5d6672;--line:#dde1e6;--acc:#1f5fd6;--accink:#fff;--ok:#16794c;--okbg:#e2f4ea;--bad:#b3261e;--badbg:#fbe9e7;--warn:#8a5a00;--warnbg:#fff3d6}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1f24;--ink:#e8eaed;--mute:#9aa3ae;--line:#2c323a;--acc:#5b92f0;--accink:#0b1220;--ok:#5fd09a;--okbg:#10291d;--bad:#ff8a80;--badbg:#341715;--warn:#f2c46b;--warnbg:#33290f}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:560px;margin:0 auto;padding:24px 16px 48px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
h1{font-size:20px;margin:0}
h2{font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--mute);margin:0 0 12px}
.pill{padding:4px 12px;border-radius:99px;font-size:13px;font-weight:600;background:var(--line);color:var(--mute)}
.pill.on{background:var(--okbg);color:var(--ok)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:14px}
label{display:block;font-size:13px;color:var(--mute);margin:12px 0 4px}
input[type=text],input[type=password],select{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font:inherit}
input:focus,select:focus,button:focus-visible{outline:2px solid var(--acc);outline-offset:1px}
.chk{display:flex;gap:8px;align-items:center;margin-top:14px;font-size:14px;color:var(--ink)}
button{font:inherit;font-weight:600;border:0;border-radius:8px;padding:11px 16px;cursor:pointer;background:var(--acc);color:var(--accink);width:100%;margin-top:16px}
button.sec{background:transparent;color:var(--acc);border:1px solid var(--line);margin-top:8px}
button:disabled{opacity:.55;cursor:default}
.drop{border:2px dashed var(--line);border-radius:10px;padding:18px;text-align:center;color:var(--mute);cursor:pointer}
.drop.hover{border-color:var(--acc);color:var(--ink)}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:0;font-size:14px}
dt{color:var(--mute)}dd{margin:0;word-break:break-word}
.note{background:var(--warnbg);color:var(--warn);border-radius:8px;padding:9px 12px;font-size:13px;margin-top:10px}
.err{background:var(--badbg);color:var(--bad);border-radius:8px;padding:10px 12px;font-size:14px;margin-top:12px;white-space:pre-wrap}
.big{font-size:28px;font-weight:700;margin:4px 0}
.hide{display:none}
details{margin-top:10px;font-size:13px;color:var(--mute)}pre{white-space:pre-wrap;font-size:12px;max-height:180px;overflow:auto}
</style></head><body><main>
<header><h1>IPSec VPN - Design By Rashid</h1><span id="pill" class="pill">Disconnected</span></header>

<section class="card" id="cfgcard">
 <h2>1 · Configuration</h2>
 <div id="summary" class="hide"></div>
 <div class="drop" id="drop" tabindex="0" role="button">Drop your FortiClient <b>.conf</b> export here, or click to choose it</div>
 <input type="file" id="file" class="hide" accept=".conf,.xml,text/xml">
 <div id="imperr" class="err hide"></div>
</section>

<section class="card hide" id="conncard">
 <h2>2 · Connect</h2>
 <div id="onview" class="hide">
  <div class="big" id="vip">—</div>
  <div style="color:var(--mute)" id="onsub"></div>
  <button id="disc">Disconnect</button>
 </div>
 <form id="offview" autocomplete="off">
  <label for="user">Username</label><input type="text" id="user" autocomplete="username" required>
  <label for="pw">Password</label><input type="password" id="pw" autocomplete="current-password">
  <label for="psk">Pre-shared key</label><input type="password" id="psk" autocomplete="off">
  <label for="mode">Authentication mode</label><select id="mode"></select>
  <label for="route">Traffic through the VPN</label>
  <select id="route"><option value="all">Everything (as in the Windows config)</option><option value="custom">Only these networks (split tunnel)</option></select>
  <div id="routebox" class="hide"><label for="routes">Networks, comma-separated</label><input type="text" id="routes" placeholder="10.0.0.0/8, 192.168.50.0/24"></div>
  <label class="chk"><input type="checkbox" id="strict"> Strict firewall mode (random local ports)</label>
  <label class="chk"><input type="checkbox" id="remember"> Remember password and key on this computer</label>
  <button type="submit" id="go">Connect</button>
  <button type="button" class="sec hide" id="forget">Forget saved credentials</button>
 </form>
 <div id="err" class="err hide"></div>
 <details id="logbox" class="hide"><summary>Technical log</summary><pre id="log"></pre></details>
</section>
</main>
<script>
const TOKEN="__TOKEN__";
const $=id=>document.getElementById(id);
async function api(path,body){
  const r=await fetch(path,{method:body?"POST":"GET",headers:{"X-Token":TOKEN,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
  return r.json();
}
function show(el,on){el.classList.toggle("hide",!on)}
function fmtSecs(s){return s%3600===0?(s/3600)+" h":s%60===0?(s/60)+" min":s+" s"}
function renderSummary(p){
  const box=$("summary");box.textContent="";
  const dl=document.createElement("dl");
  [["Name",p.name],["Server",p.server],["IKE","IKEv2 · "+p.ike_proposals.join(" / ")],["ESP",p.esp_proposals.join(" / ")],
   ["Lifetimes","IKE "+fmtSecs(p.ike_lifetime)+" · ESP "+fmtSecs(p.esp_lifetime)],["Routes",p.remote_ts.join(", ")+" (via VPN)"],
   ["Address","Assigned by server (mode config)"],["Keep-alive",p.dpd?"Dead-peer detection every "+p.dpd_interval+" s":"Off"]
  ].forEach(([k,v])=>{const a=document.createElement("dt");a.textContent=k;const b=document.createElement("dd");b.textContent=v;dl.append(a,b)});
  box.append(dl);
  (p.warnings||[]).forEach(w=>{const n=document.createElement("div");n.className="note";n.textContent=w;box.append(n)});
  show(box,true);
  $("drop").textContent="Import a different config";$("drop").style.marginTop="12px";
}
let initialised=false;
async function refresh(){
  const s=await api("/api/state");
  if(s.profile){renderSummary(s.profile);show($("conncard"),true)}
  if(!initialised){
    initialised=true;
    $("user").value=s.settings.username||"";
    $("remember").checked=!!s.settings.remember;
    const m=$("mode");
    Object.entries(s.auth_modes).forEach(([k,v])=>{const o=document.createElement("option");o.value=k;o.textContent=v;m.append(o)});
    m.value=s.settings.auth_mode||"eap";
    $("strict").checked=!!s.settings.random_ports;
    $("routes").value=s.settings.routes||"";$("route").value=s.settings.routes?"custom":"all";show($("routebox"),!!s.settings.routes);
  }
  $("pw").placeholder=$("psk").placeholder=s.has_secrets?"Saved":"";
  show($("forget"),s.has_secrets);
  const on=s.status.connected,busy=s.job.busy;
  $("pill").textContent=busy?s.job.msg:on?"Connected":"Disconnected";
  $("pill").classList.toggle("on",on&&!busy);
  show($("onview"),on);show($("offview"),!on);
  if(on){$("vip").textContent=s.status.vip||"Connected";
    $("onsub").textContent="VPN address · server "+s.status.server+" · since "+new Date(s.status.since*1000).toLocaleTimeString()}
  $("go").disabled=busy;$("disc").disabled=busy;
  const msg=(!busy&&s.job.ok===false&&s.job.msg)||(!on&&s.status.note)||"";
  $("err").textContent=msg;show($("err"),!!msg);
  $("log").textContent=s.job.log||"";show($("logbox"),!!s.job.log);
}
async function doImport(file){
  const xml=await file.text();
  const r=await api("/api/import",{xml});
  $("imperr").textContent=r.error||"";show($("imperr"),!r.ok);
  if(r.ok)refresh();
}
$("drop").onclick=()=>$("file").click();
$("drop").onkeydown=e=>{if(e.key==="Enter"||e.key===" ")$("file").click()};
$("file").onchange=e=>e.target.files[0]&&doImport(e.target.files[0]);
["dragover","dragenter"].forEach(t=>$("drop").addEventListener(t,e=>{e.preventDefault();$("drop").classList.add("hover")}));
["dragleave","drop"].forEach(t=>$("drop").addEventListener(t,e=>{e.preventDefault();$("drop").classList.remove("hover")}));
$("drop").addEventListener("drop",e=>e.dataTransfer.files[0]&&doImport(e.dataTransfer.files[0]));
$("offview").onsubmit=async e=>{
  e.preventDefault();
  const r=await api("/api/connect",{username:$("user").value,password:$("pw").value,psk:$("psk").value,auth_mode:$("mode").value,routes:$("route").value==="custom"?$("routes").value:"",strict:$("strict").checked,remember:$("remember").checked});
  if(!r.ok){$("err").textContent=r.error;show($("err"),true)}else{$("pw").value="";$("psk").value=""}
  refresh();
};
$("route").onchange=()=>show($("routebox"),$("route").value==="custom");
$("disc").onclick=async()=>{await api("/api/disconnect",{});refresh()};
$("forget").onclick=async()=>{await api("/api/forget",{});$("pw").placeholder=$("psk").placeholder="";refresh()};
refresh();setInterval(refresh,1500);
</script></body></html>
"""
