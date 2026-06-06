"""
Smart Eco-Monitor — FastAPI Backend
Run: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
from collections import deque
from typing import Optional
import json

MAX_READINGS = 10_000

app = FastAPI(title="Smart Eco-Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

readings: deque[dict] = deque(maxlen=MAX_READINGS)
latest: dict = {}
clients: list[WebSocket] = []


class SensorData(BaseModel):
    temp: float
    hum: float
    aqi: float
    co: float
    smoke: float
    device_id: Optional[str] = "ESP32"


# ── Dashboard HTML ────────────────────────────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Eco-Monitor</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f1117; color: #e2e8f0; min-height: 100vh; }
  header { padding: 1.2rem 2rem; border-bottom: 1px solid #1e2535; display: flex; align-items: center; justify-content: space-between; }
  header h1 { font-size: 1.1rem; font-weight: 600; color: #fff; }
  .badge { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94a3b8;
           background: #1e2535; border-radius: 20px; padding: 4px 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #475569; }
  .dot.live { background: #22c55e; animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* ── waiting state ── */
  #waiting { display: flex; flex-direction: column; align-items: center; justify-content: center;
             min-height: 70vh; gap: 16px; text-align: center; padding: 2rem; }
  .waiting-icon { font-size: 3rem; opacity: .4; }
  #waiting h2 { font-size: 1.2rem; color: #94a3b8; font-weight: 500; }
  #waiting p  { font-size: .9rem; color: #475569; max-width: 340px; line-height: 1.6; }
  .steps { list-style: none; margin-top: 1rem; display: flex; flex-direction: column; gap: 8px; }
  .steps li { background: #1e2535; border-radius: 8px; padding: 8px 16px;
              font-size: 13px; color: #64748b; display: flex; align-items: center; gap: 10px; }
  .steps li span { background: #334155; border-radius: 50%; width: 22px; height: 22px;
                   display: flex; align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0; }

  /* ── dashboard ── */
  #dashboard { display: none; padding: 1.5rem 2rem; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 12px; margin-bottom: 1.5rem; }
  .card { background: #1e2535; border-radius: 12px; padding: 1rem 1.2rem; }
  .card-label { font-size: 11px; color: #64748b; margin-bottom: 4px; }
  .card-val { font-size: 26px; font-weight: 600; color: #f8fafc; line-height: 1; }
  .card-unit { font-size: 11px; color: #475569; margin-top: 3px; }
  .bar { height: 3px; background: #0f1117; border-radius: 2px; margin-top: 8px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 2px; transition: width .6s ease; }
  .charts { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 1.5rem; }
  .chart-box { background: #1e2535; border-radius: 12px; padding: 14px; }
  .chart-title { font-size: 12px; color: #64748b; margin-bottom: 10px; }
  .alert { background: #3b0f0f; border: 1px solid #7f1d1d; border-radius: 8px;
           padding: 10px 16px; font-size: 13px; color: #fca5a5;
           display: none; align-items: center; gap: 8px; margin-bottom: 1rem; }
  .alert.show { display: flex; }
  .log-wrap { background: #1e2535; border-radius: 12px; padding: 12px 14px;
              font-family: monospace; font-size: 12px; color: #475569; max-height: 90px; overflow-y: auto; }
  .log-line.ok  { color: #22c55e; }
  .log-line.err { color: #f87171; }
</style>
</head>
<body>
<header>
  <h1>🌿 Smart Eco-Monitor</h1>
  <div class="badge"><span class="dot" id="dot"></span><span id="status-txt">جاري الاتصال…</span></div>
</header>

<!-- Waiting state -->
<div id="waiting">
  <div class="waiting-icon">📡</div>
  <h2>في انتظار بيانات السينسر</h2>
  <p>السيرفر يعمل بشكل صحيح، لكن لم يصل أي قراءة من ESP32 بعد.</p>
  <ul class="steps">
    <li><span>1</span>افتح الكود في Arduino IDE</li>
    <li><span>2</span>أدخل اسم الواي فاي وكلمة السر عبر Serial Monitor</li>
    <li><span>3</span>تأكد أن ESP32 متصل بالإنترنت</li>
    <li><span>4</span>ستظهر البيانات هنا تلقائياً</li>
  </ul>
</div>

<!-- Dashboard (hidden until first reading) -->
<div id="dashboard">
  <div class="alert" id="alert-box">⚠️ <span id="alert-msg"></span></div>
  <div class="cards">
    <div class="card">
      <div class="card-label">🌡 الحرارة</div>
      <div class="card-val" id="v-temp">--</div>
      <div class="card-unit">°C</div>
      <div class="bar"><div class="bar-fill" id="b-temp" style="background:#ef4444;width:0%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">💧 الرطوبة</div>
      <div class="card-val" id="v-hum">--</div>
      <div class="card-unit">%</div>
      <div class="bar"><div class="bar-fill" id="b-hum" style="background:#3b82f6;width:0%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">💨 جودة الهواء</div>
      <div class="card-val" id="v-aqi">--</div>
      <div class="card-unit">AQI</div>
      <div class="bar"><div class="bar-fill" id="b-aqi" style="background:#22c55e;width:0%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">☁️ أول أكسيد الكربون</div>
      <div class="card-val" id="v-co">--</div>
      <div class="card-unit">ppm</div>
      <div class="bar"><div class="bar-fill" id="b-co" style="background:#f59e0b;width:0%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">🔥 الدخان</div>
      <div class="card-val" id="v-smoke">--</div>
      <div class="card-unit">ppm</div>
      <div class="bar"><div class="bar-fill" id="b-smoke" style="background:#a855f7;width:0%"></div></div>
    </div>
  </div>

  <div class="charts">
    <div class="chart-box">
      <div class="chart-title">الحرارة والرطوبة</div>
      <div style="position:relative;height:140px"><canvas id="chart-th"></canvas></div>
    </div>
    <div class="chart-box">
      <div class="chart-title">جودة الهواء</div>
      <div style="position:relative;height:140px"><canvas id="chart-aq"></canvas></div>
    </div>
  </div>

  <div class="log-wrap" id="log"></div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<script>
const BASE = location.origin;
let chartTH, chartAQ, hasData = false;

function setStatus(live) {
  document.getElementById('dot').className = 'dot' + (live ? ' live' : '');
  document.getElementById('status-txt').textContent = live ? 'متصل — بيانات مباشرة' : 'غير متصل';
}

function showDashboard() {
  if (hasData) return;
  hasData = true;
  document.getElementById('waiting').style.display   = 'none';
  document.getElementById('dashboard').style.display = 'block';
  initCharts();
}

function log(msg, cls='') {
  const el = document.getElementById('log');
  const d  = document.createElement('div');
  d.className = 'log-line ' + cls;
  d.textContent = new Date().toLocaleTimeString('ar') + '  ' + msg;
  el.prepend(d);
  while (el.children.length > 20) el.removeChild(el.lastChild);
}

function setCard(id, val, max) {
  document.getElementById('v-'+id).textContent = typeof val === 'number' ? val.toFixed(1) : '--';
  document.getElementById('b-'+id).style.width = Math.min(100,(val/max)*100).toFixed(1)+'%';
}

function checkAlerts(d) {
  const msgs = [];
  if (d.aqi   > 150) msgs.push('جودة الهواء سيئة (AQI ' + d.aqi.toFixed(0) + ')');
  if (d.co    > 35)  msgs.push('CO مرتفع (' + d.co.toFixed(0) + ' ppm)');
  if (d.smoke > 100) msgs.push('دخان مرتفع (' + d.smoke.toFixed(0) + ' ppm)');
  if (d.temp  > 40)  msgs.push('حرارة مرتفعة (' + d.temp.toFixed(1) + '°C)');
  const box = document.getElementById('alert-box');
  if (msgs.length) { box.classList.add('show'); document.getElementById('alert-msg').textContent = msgs.join(' · '); }
  else { box.classList.remove('show'); }
}

function applyReading(d) {
  showDashboard();
  setCard('temp',  d.temp,  60);
  setCard('hum',   d.hum,   100);
  setCard('aqi',   d.aqi,   500);
  setCard('co',    d.co,    1000);
  setCard('smoke', d.smoke, 1000);
  checkAlerts(d);
  log('T:'+d.temp.toFixed(1)+' H:'+d.hum.toFixed(1)+' AQI:'+d.aqi.toFixed(0), 'ok');
}

function initCharts() {
  const cfg = (datasets) => ({
    type:'line', data:{ labels:[], datasets },
    options:{ responsive:true, maintainAspectRatio:false, animation:false,
      plugins:{ legend:{display:false} },
      scales:{ x:{ ticks:{font:{size:10},maxTicksLimit:6,color:'#475569'}, grid:{color:'rgba(255,255,255,.05)'}},
               y:{ ticks:{font:{size:10},color:'#475569'}, grid:{color:'rgba(255,255,255,.05)'}} }}
  });
  chartTH = new Chart(document.getElementById('chart-th'), cfg([
    {label:'Temp', data:[], borderColor:'#ef4444', borderWidth:1.5, pointRadius:0, tension:.3, fill:false},
    {label:'Hum',  data:[], borderColor:'#3b82f6', borderWidth:1.5, pointRadius:0, tension:.3, fill:false, borderDash:[4,3]},
  ]));
  chartAQ = new Chart(document.getElementById('chart-aq'), cfg([
    {label:'AQI',   data:[], borderColor:'#22c55e', borderWidth:1.5, pointRadius:0, tension:.3, fill:false},
    {label:'CO',    data:[], borderColor:'#f59e0b', borderWidth:1.5, pointRadius:0, tension:.3, fill:false, borderDash:[4,3]},
    {label:'Smoke', data:[], borderColor:'#a855f7', borderWidth:1.5, pointRadius:0, tension:.3, fill:false, borderDash:[2,4]},
  ]));
}

function pushChart(rows) {
  if (!chartTH) return;
  const labels = rows.map(r => r.time ? r.time.slice(0,5) : '');
  chartTH.data.labels = labels;
  chartTH.data.datasets[0].data = rows.map(r=>r.temp);
  chartTH.data.datasets[1].data = rows.map(r=>r.hum);
  chartTH.update('none');
  chartAQ.data.labels = labels;
  chartAQ.data.datasets[0].data = rows.map(r=>r.aqi);
  chartAQ.data.datasets[1].data = rows.map(r=>r.co);
  chartAQ.data.datasets[2].data = rows.map(r=>r.smoke);
  chartAQ.update('none');
}

async function fetchLatest() {
  try {
    const [lr, hr] = await Promise.all([
      fetch(BASE+'/data/latest'), fetch(BASE+'/data/history?limit=30')
    ]);
    const latest  = await lr.json();
    const history = await hr.json();
    if (!latest.error) {
      setStatus(true);
      applyReading(latest);
      if (Array.isArray(history) && history.length) pushChart(history.slice(-30));
    } else {
      setStatus(false);
      log('لا توجد بيانات بعد — ESP32 لم يتصل', 'err');
    }
  } catch(e) {
    setStatus(false);
    log('خطأ في الاتصال بالسيرفر', 'err');
  }
}

function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(proto + '://' + location.host + '/ws');
  ws.onopen  = () => setStatus(true);
  ws.onmessage = e => { try { applyReading(JSON.parse(e.data)); } catch(_){} };
  ws.onclose = () => { setStatus(false); setTimeout(connectWS, 4000); };
}

fetchLatest();
connectWS();
setInterval(fetchLatest, 10000);
</script>
</body>
</html>"""


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    """Serve the dashboard HTML."""
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api")
def api_info():
    """JSON info about the API."""
    return {
        "service": "Smart Eco-Monitor API",
        "status": "running",
        "total_readings": len(readings),
        "sensor_connected": len(readings) > 0,
    }


@app.post("/data")
async def receive_data(data: SensorData):
    global latest
    now = datetime.now()
    row = {
        "date":  now.strftime("%Y-%m-%d"),
        "time":  now.strftime("%H:%M:%S"),
        "temp":  round(data.temp,  2),
        "hum":   round(data.hum,   2),
        "aqi":   round(data.aqi,   2),
        "co":    round(data.co,    2),
        "smoke": round(data.smoke, 2),
    }
    readings.append(row)
    latest = {**row, "device": data.device_id, "ts": now.isoformat()}

    msg  = json.dumps(latest)
    dead = []
    for ws in list(clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)

    return {"status": "ok", "received": row}


@app.get("/data/latest")
def get_latest():
    return latest if latest else {"error": "no data yet"}


@app.get("/data/history")
def get_history(limit: int = 200):
    return list(readings)[-limit:]


@app.get("/data/stats")
def get_stats():
    if not readings:
        return {"sensor_connected": False}
    cols = ["temp", "hum", "aqi", "co", "smoke"]
    stats: dict = {"sensor_connected": True}
    for col in cols:
        values = [r[col] for r in readings if col in r]
        if not values:
            continue
        stats[col] = {
            "min":  round(min(values), 2),
            "max":  round(max(values), 2),
            "avg":  round(sum(values) / len(values), 2),
            "last": round(values[-1], 2),
        }
    stats["total_readings"] = len(readings)
    return stats


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    clients.append(ws)
    try:
        if latest:
            await ws.send_text(json.dumps(latest))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in clients:
            clients.remove(ws)


@app.get("/health")
def health():
    return {
        "status": "running",
        "sensor_connected": len(readings) > 0,
        "connected_clients": len(clients),
        "total_readings": len(readings),
    }


@app.delete("/data")
def clear_data():
    global latest
    readings.clear()
    latest = {}
    return {"status": "cleared"}
