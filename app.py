"""
app.py  —  ESP32 Energy Monitor
  • UDP listener  → stores history in SQLite
  • REST API      → /api/summary, /api/download
  • Serves        → dashboard.html  (same folder as this file)

Run:
    python app.py
Open:
    http://<server-ip>:5000
"""

from flask import Flask, jsonify, send_from_directory, request, Response
import socket, json, threading, time, sqlite3, os, csv, io, datetime

# ── Resolve paths relative to THIS file, not the CWD ──────────────
BASE_DIR = os.path.dirname(os.path.realpath(__file__))   # realpath resolves symlinks too
DB_PATH  = os.path.join(BASE_DIR, "energy.db")

app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "static"))


# ─────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS devices (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            name      TEXT UNIQUE NOT NULL,
            ip        TEXT,
            last_seen TEXT
        );

        CREATE TABLE IF NOT EXISTS meter_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id   INTEGER NOT NULL REFERENCES devices(id),
            meter_id    INTEGER NOT NULL,
            status      TEXT,
            freq        REAL,
            volt        REAL,
            curr        REAL,
            pf          REAL,
            kw          REAL,
            kva         REAL,
            recorded_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_history_device_date
            ON meter_history(device_id, recorded_at);

        CREATE VIEW IF NOT EXISTS v_meters_latest AS
            SELECT h.*
            FROM meter_history h
            INNER JOIN (
                SELECT device_id, meter_id, MAX(recorded_at) AS max_ts
                FROM meter_history
                GROUP BY device_id, meter_id
            ) latest
            ON  h.device_id   = latest.device_id
            AND h.meter_id    = latest.meter_id
            AND h.recorded_at = latest.max_ts;
    """)
    con.commit()
    con.close()
    print(f"[DB] Using database: {DB_PATH}")


def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def upsert_device(name: str, ip: str) -> int:
    con = get_db()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    con.execute(
        "INSERT INTO devices(name, ip, last_seen) VALUES(?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET ip=excluded.ip, last_seen=excluded.last_seen",
        (name, ip, now)
    )
    con.commit()
    row = con.execute("SELECT id FROM devices WHERE name=?", (name,)).fetchone()
    con.close()
    return row["id"]


def insert_meters(device_id: int, meters: list):
    """
    Record a new snapshot of meter readings in the history table.
    """
    con = get_db()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for m in meters:
        con.execute("""
            INSERT INTO meter_history(
                device_id, meter_id, status, freq, volt, curr, pf, kw, kva, recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?)
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


def calculate_shift_summaries(con, date_from, date_to, selected_shift=None, device_id=None):
    """
    Calculate shift-wise energy consumption for the given date range.
    Uses a continuous stream of data to ensure accurate delta accumulation.
    """
    # 1. Expand range slightly to get the 'previous' reading for the start of the period
    start_dt = (datetime.datetime.strptime(date_from, "%Y-%m-%d") - datetime.timedelta(days=1)).strftime("%Y-%m-%d 23:00:00")
    end_dt = f"{date_to} 23:59:59"

    query = "SELECT device_id, meter_id, kw, recorded_at FROM meter_history WHERE recorded_at BETWEEN ? AND ?"
    params = [start_dt, end_dt]
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    query += " ORDER BY device_id, meter_id, recorded_at"

    rows = con.execute(query, params).fetchall()

    consumption = {'A': 0.0, 'B': 0.0, 'C': 0.0}
    prev_kw = {}

    for row in rows:
        key = (row['device_id'], row['meter_id'])
        curr_kw = row['kw']
        curr_ts = row['recorded_at']
        curr_date, curr_time = curr_ts.split(' ')

        # 2. Identify Shift Category
        if '06:00:00' <= curr_time <= '13:59:59':
            s_key = 'A'
        elif '14:00:00' <= curr_time <= '21:59:59':
            s_key = 'B'
        else:
            s_key = 'C'

        # 3. Accumulate Delta if reading is within the requested calendar dates
        if key in prev_kw and prev_kw[key] is not None and curr_kw is not None:
            if curr_kw >= prev_kw[key]:
                # Normal operation: meter is incrementing
                delta = curr_kw - prev_kw[key]
            else:
                # Rollover or Manual Reset detected (curr < prev)
                # We treat the current value as the consumption since the reset
                delta = curr_kw

            if delta > 0 and date_from <= curr_date <= date_to:
                consumption[s_key] += delta

        prev_kw[key] = curr_kw

    # Prepare result: return only the selected shift or all three
    if selected_shift and selected_shift in consumption:
        result = {selected_shift: round(consumption[selected_shift], 2)}
    else:
        result = {k: round(v, 2) for k, v in consumption.items()}

    result['Total'] = round(sum(v for k, v in result.items() if k in ('A', 'B', 'C')), 2)
    return result


# ─────────────────────────────────────────────────────────────────
# UDP LISTENER
# ─────────────────────────────────────────────────────────────────

def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 6503))
    print("[UDP] Listening on port 6503 ...")

    while True:
        try:
            data, addr  = sock.recvfrom(65535)
            parsed      = json.loads(data.decode("utf-8").strip())
            device_name = parsed.get("device", "Unknown")
            meters      = parsed.get("meters", [])
            sender_ip   = addr[0]

            device_id = upsert_device(device_name, sender_ip)
            insert_meters(device_id, meters)

            online = sum(1 for m in meters if m.get("status") == "OK")
            print(f"[UDP] {time.strftime('%H:%M:%S')}  {device_name} ({sender_ip})"
                  f"  meters={len(meters)}  online={online}")

        except json.JSONDecodeError as e:
            print(f"[UDP] JSON error: {e}")
        except Exception as e:
            print(f"[UDP] Error: {e}")


# ─────────────────────────────────────────────────────────────────
# REST API
# ─────────────────────────────────────────────────────────────────

@app.route("/api/shift-summary")
def api_shift_summary():
    """
    Calculate shift-wise energy consumption using delta accumulation.
    Accepts optional date_from/date_to and shift parameters.
    """
    date_from     = request.args.get("date_from", time.strftime("%Y-%m-%d"))
    date_to       = request.args.get("date_to", date_from)
    selected_shift = request.args.get("shift", "").upper()
    device_id     = request.args.get("device_id", type=int)

    if selected_shift and selected_shift not in ('A', 'B', 'C'):
        return jsonify({"error": "shift must be A, B, or C"}), 400

    con = get_db()
    result = calculate_shift_summaries(con, date_from, date_to, selected_shift, device_id)
    con.close()
    return jsonify(result)


@app.route("/api/summary")
def api_summary():
    """Latest snapshot — polled by the dashboard every 3 s."""
    con = get_db()
    devices = con.execute("SELECT * FROM devices ORDER BY name").fetchall()
    result  = []
    for d in devices:
        meters = con.execute(
            "SELECT * FROM v_meters_latest WHERE device_id=? ORDER BY meter_id",
            (d["id"],)
        ).fetchall()
        total_kw = round(sum((m["kw"] or 0) for m in meters), 2)
        result.append({
            **dict(d),
            "meters": [dict(m) for m in meters],
            "total_kw": total_kw
        })
    con.close()
    return jsonify(result)


@app.route("/api/download")
def api_download():
    """
    ?date_from=YYYY-MM-DD  (required)
    ?date_to=YYYY-MM-DD    (required)
    ?device_id=<int>       (optional)
    ?meter_id=<int>        (optional)
    → returns CSV attachment
    """
    date_from = request.args.get("date_from", "")
    date_to   = request.args.get("date_to",   "")
    device_id = request.args.get("device_id", type=int)
    meter_id  = request.args.get("meter_id",  type=int)
    shift     = request.args.get("shift", "").upper()

    if not date_from or not date_to:
        return jsonify({"error": "date_from and date_to required (YYYY-MM-DD)"}), 400

    if shift and shift not in ('A', 'B', 'C'):
        return jsonify({"error": "shift must be A, B, or C"}), 400

    dt_from = f"{date_from} 00:00:00"
    dt_to   = f"{date_to} 23:59:59"

    sql    = """
        SELECT d.name AS device, h.device_id, h.meter_id, h.status,
               h.freq, h.volt, h.curr, h.pf, h.kw, h.kva, h.recorded_at
        FROM   meter_history h
        JOIN   devices d ON d.id = h.device_id
        WHERE  h.recorded_at BETWEEN ? AND ?
    """
    params = [dt_from, dt_to]

    if shift:
        if shift == 'A':
            sql += " AND strftime('%H:%M:%S', h.recorded_at) BETWEEN '06:00:00' AND '13:59:59'"
        elif shift == 'B':
            sql += " AND strftime('%H:%M:%S', h.recorded_at) BETWEEN '14:00:00' AND '21:59:59'"
        elif shift == 'C':
            sql += " AND (strftime('%H:%M:%S', h.recorded_at) >= '22:00:00' OR strftime('%H:%M:%S', h.recorded_at) <= '05:59:59')"

    if device_id is not None:
        sql += " AND h.device_id = ?";  params.append(device_id)
    if meter_id is not None:
        sql += " AND h.meter_id  = ?";  params.append(meter_id)

    sql += " ORDER BY d.name, h.meter_id, h.recorded_at"

    print(f"[API] Download SQL: {sql}")
    print(f"[API] Download Params: {params}")

    con  = get_db()
    cur  = con.cursor()
    cur.execute(sql, params)
    rows = cur.fetchall()

    print(f"[API] Download Rows fetched: {len(rows)}")

    # Calculate shift summaries for the date range
    shift_summaries = calculate_shift_summaries(con, date_from, date_to, shift, device_id)
    con.close()

    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["Device", "Meter ID", "Status",
                "Frequency (Hz)", "Voltage (V)", "Current (A)",
                "Power Factor", "Active Power (kW)", "Apparent Power (kVA)",
                "Recorded At"])
    for r in rows:
        w.writerow([r["device"], r["meter_id"], r["status"],
                    r["freq"],   r["volt"],     r["curr"],
                    r["pf"],     r["kw"],        r["kva"],
                    r["recorded_at"]])

    # Add summary section
    w.writerow([])
    w.writerow(["SUMMARY"])
    w.writerow(["Shift", "Energy Consumption (kWh)"])
    for shift, consumption in shift_summaries.items():
        w.writerow([f"Shift {shift}", consumption])

    fname = f"energy_{date_from}_to_{date_to}.csv"
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


# ─────────────────────────────────────────────────────────────────
# SERVE DASHBOARD  (dashboard.html must sit next to app.py)
# ─────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    html_path = os.path.join(BASE_DIR, "dashboard.html")
    if not os.path.exists(html_path):
        return (
            "<h2 style='font-family:monospace;color:red'>dashboard.html not found</h2>"
            f"<p>Expected at: <code>{html_path}</code></p>"
            "<p>Make sure dashboard.html is in the same folder as app.py</p>"
        ), 404
    return send_from_directory(BASE_DIR, "dashboard.html")


# Health-check — quick way to confirm Flask is alive
@app.route("/api/ping")
def ping():
    return jsonify({"status": "ok", "time": time.strftime("%Y-%m-%d %H:%M:%S"), "db": DB_PATH})


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[APP] Base directory : {BASE_DIR}")
    print(f"[APP] Dashboard HTML : {os.path.join(BASE_DIR, 'dashboard.html')}")

    init_db()

    t = threading.Thread(target=udp_listener, daemon=True)
    t.start()

    print("[APP] Flask starting on http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)