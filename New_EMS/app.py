from flask import Flask, render_template, request, jsonify
import socket
import threading
import sqlite3
import json
from datetime import datetime

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
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ================= LOAD JSON =================

with open("meter_map.json", "r") as f:
    meter_map = json.load(f)

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
                    kwh
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (

                    plant,
                    meter.get("id"),
                    meter_name,
                    meter_type,
                    meter.get("status"),

                    meter.get("freq"),
                    meter.get("volt"),
                    meter.get("curr"),
                    meter.get("pf"),
                    meter.get("kw"),
                    meter.get("kva"),
                    meter.get("kwh")
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
            "name": data["name"]
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
        # Get the latest entry for each meter in the plant
        query = """
        SELECT * FROM meter_data 
        WHERE id IN (SELECT MAX(id) FROM meter_data WHERE plant=? GROUP BY meter_id)
        ORDER BY meter_name ASC
        """
        params = [plant]
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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)