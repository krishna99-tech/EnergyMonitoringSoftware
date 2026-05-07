"""
FastAPI version of the Energy Monitoring backend.

This file is a non-breaking parallel app to `app.py` (Flask).
You can run this side-by-side and switch once verified.
"""

from fastapi import FastAPI, HTTPException, Query, APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import socket
import json
import threading
import time
import sqlite3
import os
import csv
import io
import datetime
from typing import Optional


# Paths
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
DB_PATH = os.path.join(BASE_DIR, "energy.db")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    t = threading.Thread(target=udp_listener, daemon=True)
    t.start()
    print("[APP] FastAPI startup complete")
    yield


app = FastAPI(title="Energy Monitoring API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


def ok(data=None, meta=None):
    return {"success": True, "data": data, "meta": meta or {}, "error": None}


def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(
        """
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
            kwh_total   REAL,
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
    """
    )

    cols = [r[1] for r in cur.execute("PRAGMA table_info(meter_history)").fetchall()]
    if "kwh_total" not in cols:
        cur.execute("ALTER TABLE meter_history ADD COLUMN kwh_total REAL")
        cur.execute("UPDATE meter_history SET kwh_total = kw WHERE kwh_total IS NULL")

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
        (name, ip, now),
    )
    con.commit()
    row = con.execute("SELECT id FROM devices WHERE name=?", (name,)).fetchone()
    con.close()
    return row["id"]


def insert_meters(device_id: int, meters: list):
    con = get_db()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for m in meters:
        con.execute(
            """
            INSERT INTO meter_history(
                device_id, meter_id, status, freq, volt, curr, pf, kw, kwh_total, kva, recorded_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        """,
            (
                device_id,
                m.get("id"),
                m.get("status"),
                m.get("freq"),
                m.get("volt"),
                m.get("curr"),
                m.get("pf"),
                m.get("kw"),
                m.get("kwh_total", m.get("kw")),
                m.get("kva"),
                now,
            ),
        )
    con.commit()
    con.close()


def calculate_shift_summaries(
    con, date_from: str, date_to: str, selected_shift: Optional[str] = None, device_id: Optional[int] = None
):
    start_dt = (
        datetime.datetime.strptime(date_from, "%Y-%m-%d") - datetime.timedelta(days=1)
    ).strftime("%Y-%m-%d 23:00:00")
    end_dt = f"{date_to} 23:59:59"

    query = """
        SELECT device_id, meter_id, COALESCE(kwh_total, kw) AS energy_total, recorded_at
        FROM meter_history
        WHERE recorded_at BETWEEN ? AND ?
    """
    params = [start_dt, end_dt]
    if device_id:
        query += " AND device_id = ?"
        params.append(device_id)
    query += " ORDER BY device_id, meter_id, recorded_at"

    rows = con.execute(query, params).fetchall()

    shift_consumption_kwh = {"A": 0.0, "B": 0.0, "C": 0.0}
    prev_energy_reading = {}

    for row in rows:
        key = (row["device_id"], row["meter_id"])
        current_energy_reading = row["energy_total"]
        curr_date, curr_time = row["recorded_at"].split(" ")

        if "06:00:00" <= curr_time <= "13:59:59":
            s_key = "A"
        elif "14:00:00" <= curr_time <= "21:59:59":
            s_key = "B"
        else:
            s_key = "C"

        if key in prev_energy_reading and prev_energy_reading[key] is not None and current_energy_reading is not None:
            if current_energy_reading >= prev_energy_reading[key]:
                delta_kwh = current_energy_reading - prev_energy_reading[key]
            else:
                delta_kwh = current_energy_reading

            if delta_kwh > 0 and date_from <= curr_date <= date_to:
                shift_consumption_kwh[s_key] += delta_kwh

        prev_energy_reading[key] = current_energy_reading

    if selected_shift and selected_shift in shift_consumption_kwh:
        result = {selected_shift: round(shift_consumption_kwh[selected_shift], 2)}
    else:
        result = {k: round(v, 2) for k, v in shift_consumption_kwh.items()}

    result["Total"] = round(sum(v for k, v in result.items() if k in ("A", "B", "C")), 2)
    return result


def build_summary_rows(con):
    devices = con.execute("SELECT * FROM devices ORDER BY name").fetchall()
    result = []
    for d in devices:
        meters = con.execute(
            "SELECT * FROM v_meters_latest WHERE device_id=? ORDER BY meter_id",
            (d["id"],),
        ).fetchall()
        total_active_power_kw = round(sum((m["kw"] or 0) for m in meters), 2)
        result.append(
            {
                **dict(d),
                "meters": [dict(m) for m in meters],
                "total_kw": total_active_power_kw,
            }
        )
    return result


def udp_listener():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 6503))
    print("[UDP] Listening on port 6503 ...")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
            parsed = json.loads(data.decode("utf-8").strip())
            device_name = parsed.get("device", "Unknown")
            meters = parsed.get("meters", [])
            sender_ip = addr[0]

            device_id = upsert_device(device_name, sender_ip)
            insert_meters(device_id, meters)

            online = sum(1 for m in meters if m.get("status") == "OK")
            print(
                f"[UDP] {time.strftime('%H:%M:%S')}  {device_name} ({sender_ip})"
                f"  meters={len(meters)}  online={online}"
            )
        except json.JSONDecodeError as e:
            print(f"[UDP] JSON error: {e}")
        except Exception as e:
            print(f"[UDP] Error: {e}")


@app.get("/")
def dashboard():
    html_path = os.path.join(BASE_DIR, "dashboard.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail=f"dashboard.html not found at {html_path}")
    return FileResponse(html_path)


@app.get("/api/ping")
def ping():
    return {"status": "ok", "time": time.strftime("%Y-%m-%d %H:%M:%S"), "db": DB_PATH}


@app.get("/api/summary")
def api_summary():
    con = get_db()
    result = build_summary_rows(con)
    con.close()
    return JSONResponse(result)


@app.get("/api/stream")
def api_stream():
    def event_stream():
        last_payload = None
        while True:
            try:
                con = get_db()
                rows = build_summary_rows(con)
                con.close()
                payload = json.dumps(rows, separators=(",", ":"))
                if payload != last_payload:
                    yield f"data: {payload}\n\n"
                    last_payload = payload
                else:
                    yield ": keepalive\n\n"
            except Exception as e:
                err = json.dumps({"error": str(e)})
                yield f"event: error\ndata: {err}\n\n"
            time.sleep(1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/shift-summary")
def api_shift_summary(
    date_from: str = Query(default_factory=lambda: time.strftime("%Y-%m-%d")),
    date_to: Optional[str] = None,
    shift: str = "",
    device_id: Optional[int] = None,
):
    date_to = date_to or date_from
    selected_shift = (shift or "").upper()

    if selected_shift and selected_shift not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="shift must be A, B, or C")

    con = get_db()
    result = calculate_shift_summaries(con, date_from, date_to, selected_shift, device_id)
    con.close()
    return JSONResponse(result)


@app.get("/api/download")
def api_download(
    date_from: str = "",
    date_to: str = "",
    device_id: Optional[int] = None,
    meter_id: Optional[int] = None,
    shift: str = "",
):
    if not date_from or not date_to:
        raise HTTPException(status_code=400, detail="date_from and date_to required (YYYY-MM-DD)")

    shift = (shift or "").upper()
    if shift and shift not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="shift must be A, B, or C")

    dt_from = f"{date_from} 00:00:00"
    dt_to = f"{date_to} 23:59:59"

    sql = """
        SELECT d.name AS device, h.device_id, h.meter_id, h.status,
               h.freq, h.volt, h.curr, h.pf, h.kw, h.kva, h.recorded_at
        FROM   meter_history h
        JOIN   devices d ON d.id = h.device_id
        WHERE  h.recorded_at BETWEEN ? AND ?
    """
    params = [dt_from, dt_to]

    if shift:
        if shift == "A":
            sql += " AND strftime('%H:%M:%S', h.recorded_at) BETWEEN '06:00:00' AND '13:59:59'"
        elif shift == "B":
            sql += " AND strftime('%H:%M:%S', h.recorded_at) BETWEEN '14:00:00' AND '21:59:59'"
        elif shift == "C":
            sql += " AND (strftime('%H:%M:%S', h.recorded_at) >= '22:00:00' OR strftime('%H:%M:%S', h.recorded_at) <= '05:59:59')"

    if device_id is not None:
        sql += " AND h.device_id = ?"
        params.append(device_id)
    if meter_id is not None:
        sql += " AND h.meter_id = ?"
        params.append(meter_id)

    sql += " ORDER BY d.name, h.meter_id, h.recorded_at"

    con = get_db()
    rows = con.execute(sql, params).fetchall()
    shift_summaries = calculate_shift_summaries(con, date_from, date_to, shift, device_id)
    con.close()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "Device",
            "Meter ID",
            "Status",
            "Frequency (Hz)",
            "Voltage (V)",
            "Current (A)",
            "Power Factor",
            "Active Power (kW)",
            "Apparent Power (kVA)",
            "Recorded At",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r["device"],
                r["meter_id"],
                r["status"],
                r["freq"],
                r["volt"],
                r["curr"],
                r["pf"],
                r["kw"],
                r["kva"],
                r["recorded_at"],
            ]
        )

    w.writerow([])
    w.writerow(["SUMMARY"])
    w.writerow(["Shift", "Energy Consumption (kWh)"])
    for sh, consumption in shift_summaries.items():
        w.writerow([f"Shift {sh}", consumption])

    fname = f"energy_{date_from}_to_{date_to}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ----------------------------- v1 API Routers ----------------------------- #
v1_health = APIRouter(prefix="/api/v1/health", tags=["v1-health"])
v1_devices = APIRouter(prefix="/api/v1/devices", tags=["v1-devices"])
v1_shifts = APIRouter(prefix="/api/v1/shifts", tags=["v1-shifts"])
v1_reports = APIRouter(prefix="/api/v1/reports", tags=["v1-reports"])
v1_stream = APIRouter(prefix="/api/v1/stream", tags=["v1-stream"])


@v1_health.get("/ping")
def v1_ping():
    return ok({"status": "ok", "time": time.strftime("%Y-%m-%d %H:%M:%S"), "db": DB_PATH})


@v1_devices.get("")
def v1_list_devices():
    con = get_db()
    rows = build_summary_rows(con)
    con.close()
    return ok(rows, {"count": len(rows)})


@v1_devices.get("/{device_id}")
def v1_get_device(device_id: int):
    con = get_db()
    rows = build_summary_rows(con)
    con.close()
    dev = next((d for d in rows if d["id"] == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(dev)


@v1_devices.get("/{device_id}/summary")
def v1_device_summary(device_id: int):
    con = get_db()
    rows = build_summary_rows(con)
    con.close()
    dev = next((d for d in rows if d["id"] == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(
        {
            "device_id": dev["id"],
            "device_name": dev["name"],
            "total_meters": len(dev.get("meters", [])),
            "online_meters": sum(1 for m in dev.get("meters", []) if m.get("status") == "OK"),
            "total_active_power_kw": dev.get("total_kw", 0),
            "last_seen": dev.get("last_seen"),
        }
    )


@v1_devices.get("/{device_id}/meters/latest")
def v1_device_meters_latest(device_id: int):
    con = get_db()
    rows = build_summary_rows(con)
    con.close()
    dev = next((d for d in rows if d["id"] == device_id), None)
    if not dev:
        raise HTTPException(status_code=404, detail="device not found")
    return ok(dev.get("meters", []), {"count": len(dev.get("meters", []))})


@v1_shifts.get("/summary")
def v1_shift_summary(
    date_from: str = Query(default_factory=lambda: time.strftime("%Y-%m-%d")),
    date_to: Optional[str] = None,
    shift: str = "",
    device_id: Optional[int] = None,
):
    date_to = date_to or date_from
    selected_shift = (shift or "").upper()
    if selected_shift and selected_shift not in ("A", "B", "C"):
        raise HTTPException(status_code=400, detail="shift must be A, B, or C")
    con = get_db()
    result = calculate_shift_summaries(con, date_from, date_to, selected_shift, device_id)
    con.close()
    return ok(
        {
            "date_from": date_from,
            "date_to": date_to,
            "device_id": device_id,
            "shift": selected_shift or None,
            "consumption_kwh": result,
        }
    )


@v1_reports.get("/csv")
def v1_download_csv(
    date_from: str,
    date_to: str,
    device_id: Optional[int] = None,
    meter_id: Optional[int] = None,
    shift: str = "",
):
    # Reuse existing CSV endpoint behavior
    return api_download(date_from, date_to, device_id, meter_id, shift)


@v1_stream.get("")
def v1_stream_summary():
    # Reuse existing SSE endpoint behavior
    return api_stream()


app.include_router(v1_health)
app.include_router(v1_devices)
app.include_router(v1_shifts)
app.include_router(v1_reports)
app.include_router(v1_stream)


if __name__ == "__main__":
    import uvicorn

    print(f"[APP] Base directory : {BASE_DIR}")
    print(f"[APP] Dashboard HTML : {os.path.join(BASE_DIR, 'dashboard.html')}")
    print("[APP] FastAPI starting on http://0.0.0.0:5000")
    uvicorn.run("app_fastapi:app", host="0.0.0.0", port=5000, reload=False)
