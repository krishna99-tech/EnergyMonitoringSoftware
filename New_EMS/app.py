from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import socket
import threading
import sqlite3
import json
from datetime import datetime, timedelta
import time

app = Flask(__name__)

DB_NAME = "meters.db"

# ================= DATABASE =================

def init_db():

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS meter_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        plant TEXT,
        meter_id INTEGER,
        meter_name TEXT,
        meter_type TEXT,
        status TEXT,
        freq REAL,
        volt REAL,
        curr REAL,
        pf REAL,
        kw REAL,
        kva REAL,
        kwh REAL,
        line_voltage REAL,
        line_to_line_voltage REAL,
        avg_voltage REAL,
        voltage_unbalance REAL,
        line_current REAL,
        current_l1 REAL,
        current_l2 REAL,
        current_l3 REAL,
        avg_current REAL,
        neutral_line_current REAL,
        kw_l1 REAL,
        kw_l2 REAL,
        kw_l3 REAL,
        kw_total REAL,
        kva_l1 REAL,
        kva_l2 REAL,
        kva_l3 REAL,
        kva_total REAL,
        kva_max_demand REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Backward-compatible migration for existing databases.
    cur.execute("PRAGMA table_info(meter_data)")
    existing_columns = {row[1] for row in cur.fetchall()}
    required_columns = [
        ("line_voltage", "REAL"),
        ("line_to_line_voltage", "REAL"),
        ("avg_voltage", "REAL"),
        ("voltage_unbalance", "REAL"),
        ("line_current", "REAL"),
        ("current_l1", "REAL"),
        ("current_l2", "REAL"),
        ("current_l3", "REAL"),
        ("avg_current", "REAL"),
        ("neutral_line_current", "REAL"),
        ("kw_l1", "REAL"),
        ("kw_l2", "REAL"),
        ("kw_l3", "REAL"),
        ("kw_total", "REAL"),
        ("kva_l1", "REAL"),
        ("kva_l2", "REAL"),
        ("kva_l3", "REAL"),
        ("kva_total", "REAL"),
        ("kva_max_demand", "REAL"),
    ]
    for col_name, col_type in required_columns:
        if col_name not in existing_columns:
            cur.execute(f"ALTER TABLE meter_data ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()

init_db()

# ================= LOAD JSON =================

with open("meter_map.json", "r") as f:
    meter_map = json.load(f)


def normalize_historical_data():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    submeter_null_cols = [
        "freq",
        "volt",
        "curr",
        "pf",
        "kw",
        "kva",
        "line_voltage",
        "line_to_line_voltage",
        "avg_voltage",
        "voltage_unbalance",
        "line_current",
        "current_l1",
        "current_l2",
        "current_l3",
        "avg_current",
        "neutral_line_current",
        "kw_l1",
        "kw_l2",
        "kw_l3",
        "kw_total",
        "kva_l1",
        "kva_l2",
        "kva_l3",
        "kva_total",
        "kva_max_demand",
    ]
    null_assignments = ", ".join([f"{col}=NULL" for col in submeter_null_cols])

    for plant, meters in meter_map.items():
        for meter_id, meta in meters.items():
            meter_name = meta.get("name", f"Meter {meter_id}")
            meter_type = meta.get("type", "submeter")

            # Keep historical rows aligned with current meter map identity.
            cur.execute(
                """
                UPDATE meter_data
                SET meter_name=?, meter_type=?
                WHERE plant=? AND meter_id=?
                """,
                [meter_name, meter_type, plant, int(meter_id)]
            )

            if meter_type == "submeter":
                # Submeters are kWh-focused; clear non-kWh electrical columns.
                cur.execute(
                    f"""
                    UPDATE meter_data
                    SET {null_assignments}
                    WHERE plant=? AND meter_id=?
                    """,
                    [plant, int(meter_id)]
                )

    conn.commit()
    conn.close()


normalize_historical_data()

# ================= UDP SERVER =================

UDP_IP = "0.0.0.0"
UDP_PORT = 6503

def udp_server():

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    print(f"UDP Server Listening on {UDP_PORT}")

    while True:

        data, addr = sock.recvfrom(4096)

        try:
            decoded = data.decode()
            print("Received:", decoded)

            payload = json.loads(decoded)

            plant = payload.get("device", "Unknown")

            conn = sqlite3.connect(DB_NAME)
            cur = conn.cursor()

            for meter in payload["meters"]:

                meter_id = str(meter.get("id"))

                config = meter_map.get(plant, {}).get(meter_id, {})

                meter_name = config.get("name", f"Meter {meter_id}")
                meter_type = config.get("type", "submeter")
                is_incomer = meter_type == "incomer"

                # Only incomers should persist full electrical parameters.
                # Submeters are kWh-focused and keep non-kWh fields as NULL.
                freq = meter.get("freq") if is_incomer else None
                volt = meter.get("volt") if is_incomer else None
                curr = meter.get("curr") if is_incomer else None
                pf = meter.get("pf") if is_incomer else None
                kw = meter.get("kw") if is_incomer else None
                kva = meter.get("kva") if is_incomer else None
                kwh = meter.get("kwh")
                line_voltage = meter.get("line_voltage") if is_incomer else None
                line_to_line_voltage = meter.get("line_to_line_voltage") if is_incomer else None
                avg_voltage = meter.get("avg_voltage") if is_incomer else None
                voltage_unbalance = meter.get("voltage_unbalance") if is_incomer else None
                line_current = meter.get("line_current") if is_incomer else None
                current_l1 = meter.get("current_l1") if is_incomer else None
                current_l2 = meter.get("current_l2") if is_incomer else None
                current_l3 = meter.get("current_l3") if is_incomer else None
                avg_current = meter.get("avg_current") if is_incomer else None
                neutral_line_current = meter.get("neutral_line_current") if is_incomer else None
                kw_l1 = meter.get("kw_l1") if is_incomer else None
                kw_l2 = meter.get("kw_l2") if is_incomer else None
                kw_l3 = meter.get("kw_l3") if is_incomer else None
                kw_total = meter.get("kw_total") if is_incomer else None
                kva_l1 = meter.get("kva_l1") if is_incomer else None
                kva_l2 = meter.get("kva_l2") if is_incomer else None
                kva_l3 = meter.get("kva_l3") if is_incomer else None
                kva_total = meter.get("kva_total") if is_incomer else None
                kva_max_demand = meter.get("kva_max_demand") if is_incomer else None

                cur.execute("""
                INSERT INTO meter_data (
                    plant,
                    meter_id,
                    meter_name,
                    meter_type,
                    status,
                    freq,
                    volt,
                    curr,
                    pf,
                    kw,
                    kva,
                    kwh,
                    line_voltage,
                    line_to_line_voltage,
                    avg_voltage,
                    voltage_unbalance,
                    line_current,
                    current_l1,
                    current_l2,
                    current_l3,
                    avg_current,
                    neutral_line_current,
                    kw_l1,
                    kw_l2,
                    kw_l3,
                    kw_total,
                    kva_l1,
                    kva_l2,
                    kva_l3,
                    kva_total,
                    kva_max_demand,
                    timestamp
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (

                    plant,
                    meter.get("id"),
                    meter_name,
                    meter_type,
                    meter.get("status"),
                    freq,
                    volt,
                    curr,
                    pf,
                    kw,
                    kva,
                    kwh,
                    line_voltage,
                    line_to_line_voltage,
                    avg_voltage,
                    voltage_unbalance,
                    line_current,
                    current_l1,
                    current_l2,
                    current_l3,
                    avg_current,
                    neutral_line_current,
                    kw_l1,
                    kw_l2,
                    kw_l3,
                    kw_total,
                    kva_l1,
                    kva_l2,
                    kva_l3,
                    kva_total,
                    kva_max_demand,
                    meter.get("timestamp") or payload.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

            conn.commit()
            conn.close()

        except Exception as e:
            print("Error:", e)

threading.Thread(target=udp_server, daemon=True).start()

# ================= ROUTES =================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/plants")
def plants():

    return jsonify(list(meter_map.keys()))

@app.route("/meters")
def meters():

    plant = request.args.get("plant")

    meters = meter_map.get(plant, {})

    result = []

    for meter_id, data in meters.items():

        result.append({
            "id": meter_id,
            "name": data["name"],
            "type": data.get("type", "submeter")
        })

    return jsonify(result)

@app.route("/latest")
def latest():

    plant = request.args.get("plant")
    meter = request.args.get("meter")

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    if meter == "all":
        meters = meter_map.get(str(plant), {})
        rows = []
        for meter_id, meta in meters.items():
            cur.execute(
                "SELECT * FROM meter_data WHERE plant=? AND meter_id=? ORDER BY timestamp DESC LIMIT 1",
                [str(plant), int(meter_id)]
            )
            row = cur.fetchone()
            if not row:
                continue
            normalized = dict(row)
            normalized["meter_name"] = meta.get("name", normalized.get("meter_name"))
            normalized["meter_type"] = meta.get("type", normalized.get("meter_type"))
            rows.append(normalized)
        rows.sort(key=lambda r: (r.get("meter_name") or ""))
        conn.close()
        return jsonify(rows)
    else:
        query = "SELECT * FROM meter_data WHERE plant=? AND meter_id=? ORDER BY timestamp DESC LIMIT 1"
        try:
            # Ensure we are querying with the correct types (string for plant, int for meter_id)
            params = [str(plant), int(meter)]
        except (ValueError, TypeError):
            # Fallback if meter is not a valid number
            params = [str(plant), str(meter)]

    cur.execute(query, params)

    rows = cur.fetchall()

    conn.close()

    return jsonify([dict(r) for r in rows])


def fetch_latest_rows(plant, meter):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if meter == "all":
        meters = meter_map.get(str(plant), {})
        rows = []
        for meter_id, meta in meters.items():
            cur.execute(
                "SELECT * FROM meter_data WHERE plant=? AND meter_id=? ORDER BY timestamp DESC LIMIT 1",
                [str(plant), int(meter_id)]
            )
            row = cur.fetchone()
            if not row:
                continue
            normalized = dict(row)
            normalized["meter_name"] = meta.get("name", normalized.get("meter_name"))
            normalized["meter_type"] = meta.get("type", normalized.get("meter_type"))
            rows.append(normalized)
        rows.sort(key=lambda r: (r.get("meter_name") or ""))
        conn.close()
        return rows
    else:
        query = "SELECT * FROM meter_data WHERE plant=? AND meter_id=? ORDER BY timestamp DESC LIMIT 1"
        try:
            params = [str(plant), int(meter)]
        except (ValueError, TypeError):
            params = [str(plant), str(meter)]

    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.route("/stream_latest")
def stream_latest():
    plant = request.args.get("plant")
    meter = request.args.get("meter")

    if not plant or not meter:
        return jsonify({"error": "plant and meter are required"}), 400

    @stream_with_context
    def generate():
        last_signature = None
        while True:
            try:
                rows = fetch_latest_rows(plant, meter)
                signature = "|".join(f"{r.get('meter_id')}:{r.get('id')}" for r in rows) if rows else "empty"
                if signature != last_signature:
                    payload = {
                        "plant": plant,
                        "meter": meter,
                        "rows": rows,
                        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    yield f"event: latest\ndata: {json.dumps(payload)}\n\n"
                    last_signature = signature
                else:
                    # Keep-alive event so proxies/browser keep the stream open.
                    yield "event: ping\ndata: {}\n\n"
            except Exception as e:
                err_payload = {"message": str(e)[:180]}
                yield f"event: error\ndata: {json.dumps(err_payload)}\n\n"
            time.sleep(2)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def get_shift_name(dt):
    hour = dt.hour
    if 6 <= hour < 14:
        return "Shift A (06:00-14:00)"
    if 14 <= hour < 22:
        return "Shift B (14:00-22:00)"
    return "Shift C (22:00-06:00)"


def get_shift_start(dt):
    day = dt.date()
    hour = dt.hour
    if 6 <= hour < 14:
        return datetime.combine(day, datetime.min.time()).replace(hour=6)
    if 14 <= hour < 22:
        return datetime.combine(day, datetime.min.time()).replace(hour=14)
    if hour >= 22:
        return datetime.combine(day, datetime.min.time()).replace(hour=22)
    return datetime.combine(day - timedelta(days=1), datetime.min.time()).replace(hour=22)


def get_shift_windows(start_dt, end_dt):
    windows = []
    cursor = get_shift_start(start_dt)
    while cursor < end_dt:
        next_cursor = cursor + timedelta(hours=8)
        if next_cursor > start_dt and cursor < end_dt:
            windows.append((cursor, next_cursor, get_shift_name(cursor)))
        cursor = next_cursor
    return windows


def fetch_latest_kwh_at_or_before(cur, plant, meter_id, dt):
    cur.execute(
        """
        SELECT kwh, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        [plant, meter_id, dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    return cur.fetchone()


def fetch_latest_value_at_or_before(cur, plant, meter_id, dt, column):
    cur.execute(
        f"""
        SELECT {column} AS val, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp <= ? AND {column} IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        [plant, meter_id, dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    return cur.fetchone()


def fetch_kwh_bounds_in_window(cur, plant, meter_id, start_dt, end_dt):
    cur.execute(
        """
        SELECT kwh, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp ASC
        LIMIT 1
        """,
        [plant, meter_id, start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    first_row = cur.fetchone()

    cur.execute(
        """
        SELECT kwh, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        [plant, meter_id, start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    last_row = cur.fetchone()
    return first_row, last_row


def fetch_value_bounds_in_window(cur, plant, meter_id, start_dt, end_dt, column):
    cur.execute(
        f"""
        SELECT {column} AS val, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp >= ? AND timestamp <= ? AND {column} IS NOT NULL
        ORDER BY timestamp ASC
        LIMIT 1
        """,
        [plant, meter_id, start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    first_row = cur.fetchone()

    cur.execute(
        f"""
        SELECT {column} AS val, timestamp
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp >= ? AND timestamp <= ? AND {column} IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        [plant, meter_id, start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    last_row = cur.fetchone()
    return first_row, last_row


def fetch_avg_value_in_window(cur, plant, meter_id, start_dt, end_dt, column):
    cur.execute(
        f"""
        SELECT AVG({column}) AS avg_val
        FROM meter_data
        WHERE plant=? AND meter_id=? AND timestamp >= ? AND timestamp <= ? AND {column} IS NOT NULL
        """,
        [plant, meter_id, start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S")]
    )
    return cur.fetchone()


@app.route("/energy_summary")
def energy_summary():
    plant = request.args.get("plant")
    meter = request.args.get("meter")
    mode = request.args.get("mode", "shiftwise")
    selected_shift = request.args.get("shift", "all")
    from_dt_raw = request.args.get("from_dt")
    to_dt_raw = request.args.get("to_dt")

    if not plant or not meter:
        return jsonify({"error": "plant and meter are required"}), 400

    now = datetime.now()
    if from_dt_raw and to_dt_raw:
        try:
            from_dt = datetime.fromisoformat(from_dt_raw)
            to_dt = datetime.fromisoformat(to_dt_raw)
        except ValueError:
            return jsonify({"error": "Invalid datetime format"}), 400
    else:
        yesterday = now.date() - timedelta(days=1)
        from_dt = datetime.combine(yesterday, datetime.min.time())
        to_dt = datetime.combine(yesterday, datetime.max.time())

    if to_dt <= from_dt:
        return jsonify({"error": "to_dt must be greater than from_dt"}), 400

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    meters = meter_map.get(plant, {})
    meter_config = meters.get(str(meter), {})
    if not meter_config:
        conn.close()
        return jsonify({"error": "Meter not found"}), 404

    meter_type = meter_config.get("type", "submeter")
    value_column = "kwh"
    unit = "kWh"
    metric_name = "Energy Consumption"

    start_row = fetch_latest_value_at_or_before(cur, plant, int(meter), from_dt, value_column)
    end_row = fetch_latest_value_at_or_before(cur, plant, int(meter), to_dt, value_column)

    start_kwh = start_row["val"] if start_row else None
    end_kwh = end_row["val"] if end_row else None
    total_consumption = None
    if start_kwh is not None and end_kwh is not None:
        total_consumption = round(max(0, end_kwh - start_kwh), 2)

    shift_start = get_shift_start(now)
    shift_end = shift_start + timedelta(hours=8)
    shift_start_row = fetch_latest_value_at_or_before(cur, plant, int(meter), shift_start, value_column)
    shift_now_row = fetch_latest_value_at_or_before(cur, plant, int(meter), now, value_column)

    current_shift_start_kwh = shift_start_row["val"] if shift_start_row else None
    current_shift_end_kwh = shift_now_row["val"] if shift_now_row else None
    current_shift_consumption = None
    if current_shift_start_kwh is not None and current_shift_end_kwh is not None:
        current_shift_consumption = round(max(0, current_shift_end_kwh - current_shift_start_kwh), 2)

    bars = []
    if mode == "totalshifts":
        windows = get_shift_windows(from_dt, to_dt)
        for idx, (window_start, window_end, shift_name) in enumerate(windows, start=1):
            w_start_row, w_end_row = fetch_value_bounds_in_window(cur, plant, int(meter), window_start, window_end, value_column)
            if not w_start_row or not w_end_row:
                continue
            cons = round(max(0, w_end_row["val"] - w_start_row["val"]), 2)
            bars.append({
                "label": f"Shift {idx}",
                "shift_name": shift_name,
                "start": window_start.strftime("%Y-%m-%d %H:%M:%S"),
                "end": window_end.strftime("%Y-%m-%d %H:%M:%S"),
                "start_kwh": round(w_start_row["val"], 2),
                "end_kwh": round(w_end_row["val"], 2),
                "consumption": cons
            })
    else:
        windows = get_shift_windows(from_dt, to_dt)
        if selected_shift != "all":
            day_buckets = {}
            for window_start, window_end, shift_name in windows:
                if not shift_name.startswith(selected_shift):
                    continue
                w_start_row, w_end_row = fetch_value_bounds_in_window(cur, plant, int(meter), window_start, window_end, value_column)
                if not w_start_row or not w_end_row:
                    continue
                cons = round(max(0, w_end_row["val"] - w_start_row["val"]), 2)
                day_key = window_start.strftime("%Y-%m-%d")
                day_buckets[day_key] = day_buckets.get(day_key, 0) + cons
            for day_key in sorted(day_buckets.keys()):
                bars.append({
                    "label": day_key,
                    "shift_name": selected_shift,
                    "start": f"{day_key} 00:00:00",
                    "end": f"{day_key} 23:59:59",
                    "start_kwh": None,
                    "end_kwh": None,
                    "consumption": round(day_buckets[day_key], 2)
                })
        else:
            # All Shifts => full-day total per date (sum of A+B+C for each day)
            day_buckets = {}
            for window_start, window_end, _shift_name in windows:
                w_start_row, w_end_row = fetch_value_bounds_in_window(cur, plant, int(meter), window_start, window_end, value_column)
                if not w_start_row or not w_end_row:
                    continue
                cons = round(max(0, w_end_row["val"] - w_start_row["val"]), 2)
                day_key = window_start.strftime("%Y-%m-%d")
                day_buckets[day_key] = day_buckets.get(day_key, 0) + cons

            for day_key in sorted(day_buckets.keys()):
                bars.append({
                    "label": day_key,
                    "shift_name": "All Shifts",
                    "start": f"{day_key} 00:00:00",
                    "end": f"{day_key} 23:59:59",
                    "start_kwh": None,
                    "end_kwh": None,
                    "consumption": round(day_buckets[day_key], 2)
                })

    selected_total_kwh = round(sum((b.get("consumption") or 0) for b in bars), 2)
    # Shift-filtered card values: for specific shift, show aggregated start/end for that shift;
    # for All Shifts, keep range boundary values.
    selected_start_kwh = start_kwh
    selected_end_kwh = end_kwh
    if selected_shift != "all":
        shift_windows = [w for w in get_shift_windows(from_dt, to_dt) if w[2].startswith(selected_shift)]
        if shift_windows:
            first_window = shift_windows[0]
            last_window = shift_windows[-1]
            first_start_row, _ = fetch_value_bounds_in_window(cur, plant, int(meter), first_window[0], first_window[1], value_column)
            _, last_end_row = fetch_value_bounds_in_window(cur, plant, int(meter), last_window[0], last_window[1], value_column)
            selected_start_kwh = first_start_row["val"] if first_start_row else None
            selected_end_kwh = last_end_row["val"] if last_end_row else None

    response = jsonify({
        "meter_id": meter,
        "meter_name": meter_config.get("name"),
        "meter_type": meter_type,
        "value_unit": unit,
        "metric_name": metric_name,
        "mode": mode,
        "selected_shift": selected_shift,
        "from_dt": from_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "to_dt": to_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "yesterday_total_kwh": total_consumption,
        "range_start_kwh": selected_start_kwh,
        "range_end_kwh": selected_end_kwh,
        "current_shift_name": get_shift_name(now),
        "current_shift_start": shift_start.strftime("%Y-%m-%d %H:%M:%S"),
        "current_shift_end": shift_end.strftime("%Y-%m-%d %H:%M:%S"),
        "current_shift_start_kwh": current_shift_start_kwh,
        "current_shift_end_kwh": current_shift_end_kwh,
        "current_shift_consumption_kwh": current_shift_consumption,
        "selected_total_kwh": selected_total_kwh,
        "bars": bars
    })
    conn.close()
    return response


@app.route("/incomer_shift_summary")
def incomer_shift_summary():
    plant = request.args.get("plant")
    meter = request.args.get("meter")
    selected_shift = request.args.get("shift", "all")
    from_dt_raw = request.args.get("from_dt")
    to_dt_raw = request.args.get("to_dt")

    if not plant or not meter or not from_dt_raw or not to_dt_raw:
        return jsonify({"error": "plant, meter, from_dt and to_dt are required"}), 400

    try:
        from_dt = datetime.fromisoformat(from_dt_raw)
        to_dt = datetime.fromisoformat(to_dt_raw)
    except ValueError:
        return jsonify({"error": "Invalid datetime format"}), 400

    if to_dt <= from_dt:
        return jsonify({"error": "to_dt must be greater than from_dt"}), 400

    meters = meter_map.get(plant, {})
    meter_config = meters.get(str(meter), {})
    if not meter_config:
        return jsonify({"error": "Meter not found"}), 404
    if meter_config.get("type") != "incomer":
        return jsonify({"error": "This endpoint is only for incomer meters"}), 400

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    parameter_defs = [
        ("Line Voltage", "line_voltage", "V"),
        ("Line-to-Line Voltage", "line_to_line_voltage", "V"),
        ("Average Voltage", "avg_voltage", "V"),
        ("Voltage Unbalance", "voltage_unbalance", "%"),
        ("Line Current", "line_current", "A"),
        ("Phase-wise Current L1", "current_l1", "A"),
        ("Phase-wise Current L2", "current_l2", "A"),
        ("Phase-wise Current L3", "current_l3", "A"),
        ("Average Current", "avg_current", "A"),
        ("Neutral Line Current", "neutral_line_current", "A"),
        ("Active Power kW L1", "kw_l1", "kW"),
        ("Active Power kW L2", "kw_l2", "kW"),
        ("Active Power kW L3", "kw_l3", "kW"),
        ("Cumulative kW", "kw_total", "kW"),
        ("Apparent Power kVA L1", "kva_l1", "kVA"),
        ("Apparent Power kVA L2", "kva_l2", "kVA"),
        ("Apparent Power kVA L3", "kva_l3", "kVA"),
        ("Cumulative kVA", "kva_total", "kVA"),
        ("Power Factor", "pf", ""),
        ("Frequency", "freq", "Hz"),
        ("kVA Maximum Demand", "kva_max_demand", "kVA"),
    ]

    windows = get_shift_windows(from_dt, to_dt)
    if selected_shift != "all":
        windows = [w for w in windows if w[2].startswith(selected_shift)]

    series = []
    # Add kWh consumption shift series for incomer as well.
    kwh_day_buckets = {}
    for window_start, window_end, _shift_name in windows:
        w_start_row, w_end_row = fetch_value_bounds_in_window(cur, plant, int(meter), window_start, window_end, "kwh")
        if not w_start_row or not w_end_row:
            continue
        cons = round(max(0, w_end_row["val"] - w_start_row["val"]), 2)
        day_key = window_start.strftime("%Y-%m-%d")
        kwh_day_buckets[day_key] = kwh_day_buckets.get(day_key, 0) + cons

    kwh_bars = []
    for day_key in sorted(kwh_day_buckets.keys()):
        kwh_bars.append({
            "label": day_key,
            "value": round(kwh_day_buckets[day_key], 2)
        })
    if kwh_bars:
        series.append({
            "label": "Energy Consumption",
            "unit": "kWh",
            "bars": kwh_bars
        })

    for label, column, unit in parameter_defs:
        day_buckets = {}
        day_counts = {}
        for window_start, window_end, _shift_name in windows:
            avg_row = fetch_avg_value_in_window(cur, plant, int(meter), window_start, window_end, column)
            if not avg_row or avg_row["avg_val"] is None:
                continue
            day_key = window_start.strftime("%Y-%m-%d")
            day_buckets[day_key] = day_buckets.get(day_key, 0.0) + float(avg_row["avg_val"])
            day_counts[day_key] = day_counts.get(day_key, 0) + 1

        bars = []
        for day_key in sorted(day_buckets.keys()):
            avg_val = day_buckets[day_key] / max(day_counts.get(day_key, 1), 1)
            bars.append({
                "label": day_key,
                "value": round(avg_val, 2)
            })

        if bars:
            series.append({
                "label": label,
                "unit": unit,
                "bars": bars
            })

    conn.close()
    return jsonify({
        "meter_id": meter,
        "meter_name": meter_config.get("name"),
        "meter_type": "incomer",
        "selected_shift": selected_shift,
        "from_dt": from_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "to_dt": to_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "series": series
    })

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
