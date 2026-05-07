from flask import Flask, jsonify, render_template_string
import socket
import json
import threading
import time
import sqlite3
import os

app = Flask(__name__)

DB_PATH = "energy.db"

# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT UNIQUE NOT NULL,
            last_seen TEXT
        );

        CREATE TABLE IF NOT EXISTS meters (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id  INTEGER NOT NULL REFERENCES devices(id),
            meter_id   INTEGER NOT NULL,
            status     TEXT,
            freq       REAL,
            volt       REAL,
            curr       REAL,
            pf         REAL,
            kw         REAL,
            kva        REAL,
            recorded_at TEXT,
            UNIQUE(device_id, meter_id)
        );
    """)
    con.commit()
    con.close()


def upsert_device(name: str) -> int:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        "INSERT INTO devices(name, last_seen) VALUES(?,?) "
        "ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen",
        (name, now)
    )
    con.commit()
    cur.execute("SELECT id FROM devices WHERE name=?", (name,))
    device_id = cur.fetchone()[0]
    con.close()
    return device_id


def upsert_meters(device_id: int, meters: list):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for m in meters:
        cur.execute("""
            INSERT INTO meters(device_id, meter_id, status, freq, volt, curr, pf, kw, kva, recorded_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(device_id, meter_id) DO UPDATE SET
                status=excluded.status,
                freq=excluded.freq,
                volt=excluded.volt,
                curr=excluded.curr,
                pf=excluded.pf,
                kw=excluded.kw,
                kva=excluded.kva,
                recorded_at=excluded.recorded_at
        """, (
            device_id,
            m.get("id"),
            m.get("status"),
            m.get("freq"),
            m.get("volt"),
            m.get("curr"),
            m.get("pf"),
            m.get("kw"),
            m.get("kva"),
            now
        ))
    con.commit()
    con.close()


# ─────────────────────────────────────────
# UDP LISTENER
# ─────────────────────────────────────────

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", 6503))
    print("✅ UDP Server listening on port 6503...")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            decoded = data.decode("utf-8").strip()
            parsed = json.loads(decoded)

            device_name = parsed.get("device", "Unknown")
            meters = parsed.get("meters", [])

            device_id = upsert_device(device_name)
            upsert_meters(device_id, meters)

            print(f"📡 [{time.strftime('%H:%M:%S')}] {device_name} → {len(meters)} meters from {addr[0]}")

        except json.JSONDecodeError as e:
            print("❌ JSON parse error:", e)
        except Exception as e:
            print("❌ UDP error:", e)


# ─────────────────────────────────────────
# REST API
# ─────────────────────────────────────────

@app.route("/api/devices")
def api_devices():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM devices ORDER BY name").fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/devices/<int:device_id>/meters")
def api_meters(device_id):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM meters WHERE device_id=? ORDER BY meter_id",
        (device_id,)
    ).fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/summary")
def api_summary():
    """Returns all devices with their meters in one shot."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    devices = con.execute("SELECT * FROM devices ORDER BY name").fetchall()
    result = []
    for d in devices:
        meters = con.execute(
            "SELECT * FROM meters WHERE device_id=? ORDER BY meter_id",
            (d["id"],)
        ).fetchall()
        result.append({
            **dict(d),
            "meters": [dict(m) for m in meters]
        })
    con.close()
    return jsonify(result)


# ─────────────────────────────────────────
# DASHBOARD (Single-page, served by Flask)
# ─────────────────────────────────────────

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Energy Monitor</title>
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;500;700&display=swap" rel="stylesheet"/>
<style>
  :root{
    --bg:#060d1a;--panel:#0c1829;--border:#1a3a5c;--accent:#00d4ff;
    --accent2:#ff6b35;--ok:#00ff88;--warn:#ffcc00;--offline:#ff3366;
    --text:#c8e8ff;--dim:#4a7a9b;--card:#0f2035;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--text);font-family:'Exo 2',sans-serif;
       min-height:100vh;overflow-x:hidden}

  /* scanline overlay */
  body::before{content:'';position:fixed;inset:0;
    background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,212,255,.02) 2px,rgba(0,212,255,.02) 4px);
    pointer-events:none;z-index:9999}

  /* HEADER */
  header{display:flex;align-items:center;justify-content:space-between;
    padding:18px 32px;border-bottom:1px solid var(--border);
    background:linear-gradient(90deg,#060d1a,#0c1829)}
  .logo{display:flex;align-items:center;gap:14px}
  .logo svg{width:36px;height:36px;filter:drop-shadow(0 0 8px var(--accent))}
  .logo h1{font-size:1.4rem;font-weight:700;letter-spacing:3px;
    text-transform:uppercase;color:var(--accent);
    text-shadow:0 0 12px rgba(0,212,255,.5)}
  .logo span{font-family:'Share Tech Mono';font-size:.75rem;
    color:var(--dim);letter-spacing:2px}
  #clock{font-family:'Share Tech Mono';font-size:.9rem;color:var(--accent2);
    text-align:right;line-height:1.5}

  /* TABS */
  #tabs{display:flex;gap:0;padding:0 32px;
    background:var(--panel);border-bottom:1px solid var(--border);
    overflow-x:auto}
  .tab{padding:14px 28px;cursor:pointer;font-size:.85rem;
    letter-spacing:2px;text-transform:uppercase;font-weight:500;
    color:var(--dim);border-bottom:2px solid transparent;
    transition:all .2s;white-space:nowrap}
  .tab:hover{color:var(--text)}
  .tab.active{color:var(--accent);border-bottom-color:var(--accent);
    text-shadow:0 0 8px rgba(0,212,255,.4)}
  .tab .dot{display:inline-block;width:7px;height:7px;border-radius:50%;
    background:var(--dim);margin-right:8px;vertical-align:middle}
  .tab.active .dot,.tab.live .dot{background:var(--ok);
    box-shadow:0 0 6px var(--ok);animation:blink 1.5s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}

  /* MAIN */
  main{padding:28px 32px}
  .panel-header{display:flex;align-items:center;justify-content:space-between;
    margin-bottom:24px}
  .panel-header h2{font-size:1.1rem;letter-spacing:3px;text-transform:uppercase;
    font-weight:500;color:var(--accent)}
  .stats-bar{display:flex;gap:20px;flex-wrap:wrap}
  .stat{background:var(--panel);border:1px solid var(--border);
    border-radius:6px;padding:10px 20px;text-align:center;min-width:100px}
  .stat .val{font-family:'Share Tech Mono';font-size:1.4rem;color:var(--accent2)}
  .stat .lbl{font-size:.65rem;letter-spacing:2px;color:var(--dim);text-transform:uppercase}

  /* METER GRID */
  .grid{display:grid;
    grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:16px}
  .card{background:var(--card);border:1px solid var(--border);
    border-radius:10px;padding:18px;position:relative;overflow:hidden;
    transition:border-color .25s,transform .25s}
  .card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px}
  .card.ok::before{background:linear-gradient(90deg,transparent,var(--ok),transparent)}
  .card.offline::before{background:linear-gradient(90deg,transparent,var(--offline),transparent)}
  .card:hover{border-color:var(--accent);transform:translateY(-2px)}
  .card .meter-id{font-family:'Share Tech Mono';font-size:.75rem;
    color:var(--dim);letter-spacing:2px;margin-bottom:8px}
  .card .status{font-size:.8rem;font-weight:700;letter-spacing:2px;
    text-transform:uppercase;margin-bottom:14px}
  .card.ok .status{color:var(--ok)}
  .card.offline .status{color:var(--offline)}
  .row{display:flex;justify-content:space-between;align-items:center;
    padding:5px 0;border-bottom:1px solid rgba(26,58,92,.5)}
  .row:last-child{border-bottom:none}
  .row .lbl{font-size:.72rem;color:var(--dim);letter-spacing:1px}
  .row .val{font-family:'Share Tech Mono';font-size:.82rem;color:var(--text)}
  .row .unit{font-size:.65rem;color:var(--dim);margin-left:3px}
  .no-data{text-align:center;padding:60px 20px;color:var(--dim);
    font-size:.9rem;letter-spacing:2px;text-transform:uppercase}
  .offline-msg{padding:20px 0;color:var(--offline);font-size:.75rem;
    font-family:'Share Tech Mono';text-align:center}

  /* loading */
  #loading{display:flex;align-items:center;justify-content:center;
    min-height:200px;font-family:'Share Tech Mono';color:var(--dim);
    letter-spacing:3px;font-size:.9rem}
  .spinner{width:20px;height:20px;border:2px solid var(--border);
    border-top-color:var(--accent);border-radius:50%;
    animation:spin .8s linear infinite;margin-right:14px}
  @keyframes spin{to{transform:rotate(360deg)}}

  /* last update */
  #lastseen{font-family:'Share Tech Mono';font-size:.7rem;color:var(--dim);
    margin-bottom:20px}
  #lastseen span{color:var(--accent2)}

  @media(max-width:600px){
    header{padding:14px 16px}.panel-header{flex-direction:column;gap:10px;align-items:flex-start}
    main{padding:16px}#tabs{padding:0 8px}.tab{padding:12px 16px}
  }
</style>
</head>
<body>

<header>
  <div class="logo">
    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="20" cy="20" r="18" stroke="#00d4ff" stroke-width="1.5"/>
      <path d="M20 8 L14 22 H20 L16 32 L28 18 H21 Z" fill="#00d4ff"/>
    </svg>
    <div>
      <h1>PowerGrid</h1>
      <span>ESP32 · ENERGY MONITOR</span>
    </div>
  </div>
  <div id="clock">
    <div id="time">--:--:--</div>
    <div style="font-size:.65rem;letter-spacing:2px;color:var(--dim)">LIVE MONITORING</div>
  </div>
</header>

<nav id="tabs"><div id="tab-list"></div></nav>

<main>
  <div class="panel-header">
    <h2 id="panel-title">Select a Device</h2>
    <div class="stats-bar" id="stats-bar"></div>
  </div>
  <div id="lastseen"></div>
  <div id="meter-grid"><div class="no-data">Waiting for devices…</div></div>
</main>

<script>
let allData = [];
let activeDeviceId = null;

// Clock
function updateClock(){
  document.getElementById('time').textContent = new Date().toLocaleTimeString('en-GB');
}
setInterval(updateClock, 1000);
updateClock();

// Format value
function fmt(v, decimals=2){
  if(v===null||v===undefined) return '—';
  return parseFloat(v).toFixed(decimals);
}

function renderTabs(){
  const list = document.getElementById('tab-list');
  list.style.display='flex';
  list.innerHTML = allData.map(d=>`
    <div class="tab ${d.id===activeDeviceId?'active':''} ${isLive(d.last_seen)?'live':''}"
         onclick="selectDevice(${d.id})">
      <span class="dot"></span>${d.name}
    </div>`).join('');
}

function isLive(ts){
  if(!ts) return false;
  const diff = (Date.now() - new Date(ts).getTime())/1000;
  return diff < 15;
}

function selectDevice(id){
  activeDeviceId = id;
  renderTabs();
  renderMeters();
}

function renderMeters(){
  const dev = allData.find(d=>d.id===activeDeviceId);
  if(!dev){ document.getElementById('meter-grid').innerHTML='<div class="no-data">No device selected</div>'; return; }

  document.getElementById('panel-title').textContent = dev.name;
  const ls = dev.last_seen
    ? `Last seen: <span>${dev.last_seen}</span> · ${isLive(dev.last_seen)?'<span style="color:var(--ok)">LIVE</span>':'<span style="color:var(--offline)">OFFLINE</span>'}`
    : '';
  document.getElementById('lastseen').innerHTML = ls;

  const meters = dev.meters || [];
  if(!meters.length){
    document.getElementById('meter-grid').innerHTML='<div class="no-data">No meter data received yet</div>';
    return;
  }

  const ok = meters.filter(m=>m.status==='OK').length;
  const offline = meters.length - ok;
  const totalKw = meters.reduce((s,m)=>s+(m.kw||0),0);
  const totalKva = meters.reduce((s,m)=>s+(m.kva||0),0);

  document.getElementById('stats-bar').innerHTML = `
    <div class="stat"><div class="val">${meters.length}</div><div class="lbl">Total Meters</div></div>
    <div class="stat"><div class="val" style="color:var(--ok)">${ok}</div><div class="lbl">Online</div></div>
    <div class="stat"><div class="val" style="color:var(--offline)">${offline}</div><div class="lbl">Offline</div></div>
    <div class="stat"><div class="val">${totalKw.toFixed(1)}</div><div class="lbl">Total kW</div></div>
    <div class="stat"><div class="val">${totalKva.toFixed(1)}</div><div class="lbl">Total kVA</div></div>
  `;

  document.getElementById('meter-grid').innerHTML = `
    <div class="grid">${meters.map(m=>{
      const isOk = m.status==='OK';
      return `
      <div class="card ${isOk?'ok':'offline'}">
        <div class="meter-id">METER · ${String(m.meter_id).padStart(2,'0')}</div>
        <div class="status">${isOk?'● ONLINE':'✕ OFFLINE'}</div>
        ${isOk?`
          <div class="row"><span class="lbl">Frequency</span><span class="val">${fmt(m.freq)}<span class="unit">Hz</span></span></div>
          <div class="row"><span class="lbl">Voltage</span><span class="val">${fmt(m.volt)}<span class="unit">V</span></span></div>
          <div class="row"><span class="lbl">Current</span><span class="val">${fmt(m.curr)}<span class="unit">A</span></span></div>
          <div class="row"><span class="lbl">Power Factor</span><span class="val">${fmt(m.pf,3)}</span></div>
          <div class="row"><span class="lbl">Active Power</span><span class="val">${fmt(m.kw)}<span class="unit">kW</span></span></div>
          <div class="row"><span class="lbl">Apparent Power</span><span class="val">${fmt(m.kva)}<span class="unit">kVA</span></span></div>
        `:`<div class="offline-msg">// NO DATA RECEIVED //</div>`}
      </div>`}).join('')}
    </div>`;
}

async function fetchData(){
  try{
    const res = await fetch('/api/summary');
    allData = await res.json();
    if(!activeDeviceId && allData.length) activeDeviceId = allData[0].id;
    renderTabs();
    renderMeters();
  } catch(e){ console.error('Fetch error',e); }
}

fetchData();
setInterval(fetchData, 3000);
</script>
</body>
</html>
"""

@app.route("/")
def dashboard():
    return render_template_string(DASHBOARD_HTML)


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    init_db()

    thread = threading.Thread(target=udp_listener, daemon=True)
    thread.start()

    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
