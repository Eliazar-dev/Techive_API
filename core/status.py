"""Public status page (/) and health endpoint (/api/health/). Exposes no secrets or versions."""
import time

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

STARTED = time.time()  # per process: on serverless hosts this resets on a cold start


def health(request):
    t0 = time.perf_counter()
    try:
        with connection.cursor() as c:
            c.execute('SELECT 1')
        db = 'connected'
    except Exception:
        db = 'error'
    resp = JsonResponse({
        'status': 'ok' if db == 'connected' else 'degraded',
        'database': db,
        'uptime_seconds': int(time.time() - STARTED),
        'latency_ms': round((time.perf_counter() - t0) * 1000, 1),
        'server_time': timezone.now().isoformat(),
        'environment': 'development' if settings.DEBUG else 'production',
    }, status=200 if db == 'connected' else 503)
    resp['Cache-Control'] = 'no-store'
    return resp


def status_page(request):
    resp = HttpResponse(PAGE)
    resp['Cache-Control'] = 'no-store'
    return resp


PAGE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex"><title>Techive API · Status</title>
<style>
:root{--bg:#0a0a0b;--card:#141416;--line:#26262b;--txt:#f4f4f5;--mute:#8b8b95;--ok:#22c55e;--bad:#ef4444;--warn:#f59e0b;--g:linear-gradient(90deg,#06c3ff,#7c5cff 60%,#a855f7)}
*{box-sizing:border-box;margin:0}
body{min-height:100vh;background:var(--bg);color:var(--txt);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;display:grid;place-items:center;padding:24px;overflow-x:hidden}
.glow{position:fixed;inset:0;pointer-events:none;background:radial-gradient(40rem 30rem at 85% -10%,#a855f733,transparent),radial-gradient(36rem 28rem at -10% 110%,#06c3ff26,transparent)}
main{position:relative;width:100%;max-width:760px;animation:rise .7s ease both}
@keyframes rise{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:22px;gap:12px;flex-wrap:wrap}
.brand{font-weight:800;font-size:22px;letter-spacing:-.02em}.brand b{background:var(--g);-webkit-background-clip:text;background-clip:text;color:transparent}
.env{font-size:12px;letter-spacing:.15em;text-transform:uppercase;color:var(--mute);border:1px solid var(--line);padding:4px 12px;border-radius:99px}
.hero{background:var(--card);border:1px solid var(--line);border-radius:24px;padding:34px;position:relative;overflow:hidden}
.hero:before{content:"";position:absolute;inset:0 0 auto 0;height:3px;background:var(--g)}
.state{display:flex;align-items:center;gap:18px}
.dot{position:relative;width:22px;height:22px;border-radius:50%;background:var(--ok);flex:none;transition:background .3s}
.dot:before,.dot:after{content:"";position:absolute;inset:0;border-radius:50%;background:inherit;animation:ping 2s ease-out infinite}.dot:after{animation-delay:1s}
@keyframes ping{0%{transform:scale(1);opacity:.6}100%{transform:scale(3);opacity:0}}
h1{font-size:clamp(26px,5vw,38px);font-weight:800;letter-spacing:-.02em;line-height:1.1}
.sub{color:var(--mute);margin-top:4px;font-size:15px}
.beat{margin:26px 0 6px;height:54px;width:100%}
.beat path{fill:none;stroke:var(--ok);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:420;stroke-dashoffset:420;animation:draw 2.4s linear infinite;filter:drop-shadow(0 0 6px var(--ok))}
@keyframes draw{to{stroke-dashoffset:-420}}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-top:18px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;transition:transform .2s,border-color .2s}
.tile:hover{transform:translateY(-3px);border-color:#3a3a42}
.k{font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--mute)}
.v{font-size:26px;font-weight:800;margin-top:6px;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.v small{font-size:13px;color:var(--mute);font-weight:500;margin-left:4px}
.bars{display:flex;align-items:flex-end;gap:3px;height:30px;margin-top:10px}
.bars i{flex:none;width:6px;background:var(--g);border-radius:2px;min-height:3px;opacity:.85;transition:height .4s}
.foot{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-top:18px;color:var(--mute);font-size:14px}
button{font:inherit;color:#fff;background:var(--g);border:0;border-radius:99px;padding:10px 20px;font-weight:600;cursor:pointer;display:inline-flex;gap:8px;align-items:center;transition:transform .15s,filter .2s}
button:hover{filter:brightness(1.1)}button:active{transform:scale(.95)}
button svg{width:16px;height:16px}button.spin svg{animation:rot .7s linear}
@keyframes rot{to{transform:rotate(360deg)}}
.ring{display:inline-flex;align-items:center;gap:8px}
.ring svg{width:20px;height:20px;transform:rotate(-90deg)}.ring circle{fill:none;stroke-width:3}
.ring .bg{stroke:var(--line)}.ring .fg{stroke:#7c5cff;stroke-linecap:round;stroke-dasharray:50.3;stroke-dashoffset:0;transition:stroke-dashoffset 1s linear}
.bad .dot{background:var(--bad)}.bad .beat path{stroke:var(--bad);filter:drop-shadow(0 0 6px var(--bad))}
.warn .dot{background:var(--warn)}.warn .beat path{stroke:var(--warn);filter:drop-shadow(0 0 6px var(--warn))}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}.beat path{stroke-dasharray:none}}
</style></head>
<body><div class="glow"></div>
<main id="app">
 <header><div class="brand">Techive <b>API</b></div><span class="env" id="env">—</span></header>
 <section class="hero">
  <div class="state"><span class="dot"></span>
   <div><h1 id="title">Checking…</h1><p class="sub" id="sub">Contacting the server</p></div></div>
  <svg class="beat" viewBox="0 0 400 54" preserveAspectRatio="none" aria-hidden="true"><path d="M0 27H110l12-20 16 40 14-34 10 14h238"/></svg>
 </section>
 <section class="grid">
  <div class="tile"><div class="k">Uptime</div><div class="v" id="up">—</div></div>
  <div class="tile"><div class="k">API connection</div><div class="v" id="db">—</div></div>
  <div class="tile"><div class="k">Response time</div><div class="v" id="lat">—<small>ms</small></div><div class="bars" id="bars"></div></div>
  <div class="tile"><div class="k">Server time</div><div class="v" id="clock" style="font-size:22px">—</div></div>
 </section>
 <div class="foot">
  <span class="ring"><svg viewBox="0 0 20 20"><circle class="bg" cx="10" cy="10" r="8"/><circle class="fg" id="fg" cx="10" cy="10" r="8"/></svg><span id="next">Refreshing every 5s</span></span>
  <button id="btn"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/></svg>Refresh now</button>
 </div>
</main>
<script>
(()=>{
 const $=id=>document.getElementById(id),EVERY=5,hist=[];
 let up=null,upAt=0,left=EVERY,timer,busy=false,skew=0;
 const pad=n=>String(n).padStart(2,'0');
 const fmt=s=>{const d=Math.floor(s/86400),h=Math.floor(s%86400/3600),m=Math.floor(s%3600/60);return (d?d+'d ':'')+pad(h)+':'+pad(m)+':'+pad(Math.floor(s%60))};
 function paint(state,title,sub){const a=$('app');a.className=state;$('title').textContent=title;$('sub').textContent=sub}
 async function check(){
  if(busy)return;busy=true;$('btn').classList.add('spin');
  const t0=performance.now();
  try{
   const r=await fetch('/api/health/',{cache:'no-store'});const j=await r.json();
   const rtt=Math.round(performance.now()-t0);
   up=j.uptime_seconds;upAt=performance.now();skew=new Date(j.server_time)-Date.now();
   $('env').textContent=j.environment;
   $('db').textContent=j.database==='connected'?'Connected':'Error';
   $('lat').innerHTML=rtt+'<small>ms</small>';
   hist.push(rtt);if(hist.length>24)hist.shift();
   const max=Math.max(...hist,50);$('bars').innerHTML=hist.map(v=>'<i style="height:'+Math.max(10,v/max*100)+'%"></i>').join('');
   j.status==='ok'?paint('','API is running','All systems operational'):paint('warn','Degraded','The API is up but the database is not responding');
  }catch(e){paint('bad','Unreachable','Cannot reach the API. Retrying…');$('db').textContent='Offline';up=null}
  busy=false;$('btn').classList.remove('spin');left=EVERY;tick(true);
 }
 function tick(force){
  if(up!==null)$('up').textContent=fmt(up+(performance.now()-upAt)/1000);
  $('clock').textContent=new Date(Date.now()+skew).toLocaleTimeString([], {hour12:false});
  if(!force)left=Math.max(0,left-1);
  $('next').textContent=left?'Refreshing in '+left+'s':'Refreshing…';
  $('fg').style.strokeDashoffset=50.3*(1-left/EVERY);
 }
 setInterval(()=>{tick();if(left===0)check()},1000);
 setInterval(()=>{if(up!==null)$('up').textContent=fmt(up+(performance.now()-upAt)/1000)},250);
 $('btn').onclick=check;check();
})();
</script></body></html>"""
