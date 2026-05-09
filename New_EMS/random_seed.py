import socket
import json
import random
import time
from datetime import datetime, timedelta

# ================= UDP =================

UDP_IP = "192.168.29.139"
UDP_PORT = 6504

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# ================= PLANTS =================

plants = {

    "Automotive": {

        "incomer": 2,

        "meters": [1, 3, 4, 5, 6, 7, 8]
    },

    "IG Plant": {

        "incomer": 2,

        "meters": [1, 3, 4, 5, 6, 7]
    }
}

# ================= INITIAL KWH =================

kwh_values = {}

for plant_name, config in plants.items():

    for meter_id in config["meters"]:

        kwh_values[f"{plant_name}_{meter_id}"] = round(
            random.uniform(1000, 5000),
            2
        )

# ================= RANDOM FLOAT =================

def rand_float(start, end):

    return round(random.uniform(start, end), 2)

def build_incomer(meter_id):
    incomer = {
        "id": meter_id,
        "status": "OK",
        "freq": rand_float(49.8, 50.2),
        "volt": rand_float(410, 440),
        "curr": rand_float(100, 350),
        "pf": rand_float(0.85, 0.99),
        "kw": rand_float(50, 250),
        "kva": rand_float(60, 300)
    }

    incomer["line_voltage"] = rand_float(220, 250)
    incomer["line_to_line_voltage"] = rand_float(410, 440)
    incomer["avg_voltage"] = rand_float(225, 245)
    incomer["voltage_unbalance"] = rand_float(0.1, 2.5)
    incomer["line_current"] = rand_float(100, 350)
    incomer["current_l1"] = rand_float(95, 340)
    incomer["current_l2"] = rand_float(95, 340)
    incomer["current_l3"] = rand_float(95, 340)
    incomer["avg_current"] = round(
        (incomer["current_l1"] + incomer["current_l2"] + incomer["current_l3"]) / 3,
        2
    )
    incomer["neutral_line_current"] = rand_float(1, 30)
    incomer["kw_l1"] = rand_float(15, 95)
    incomer["kw_l2"] = rand_float(15, 95)
    incomer["kw_l3"] = rand_float(15, 95)
    incomer["kw_total"] = round(
        incomer["kw_l1"] + incomer["kw_l2"] + incomer["kw_l3"],
        2
    )
    incomer["kva_l1"] = rand_float(20, 110)
    incomer["kva_l2"] = rand_float(20, 110)
    incomer["kva_l3"] = rand_float(20, 110)
    incomer["kva_total"] = round(
        incomer["kva_l1"] + incomer["kva_l2"] + incomer["kva_l3"],
        2
    )
    incomer["kva_max_demand"] = round(
        max(incomer["kva_total"], rand_float(210, 340)),
        2
    )
    return incomer


def send_snapshot(snapshot_dt):
    ts = snapshot_dt.strftime("%Y-%m-%d %H:%M:%S")

    for plant_name, config in plants.items():
        meters_data = []

        incomer = build_incomer(config["incomer"])
        incomer["timestamp"] = ts
        meters_data.append(incomer)

        for meter_id in config["meters"]:
            key = f"{plant_name}_{meter_id}"
            kwh_values[key] += random.uniform(0.2, 2.5)
            meters_data.append({
                "id": meter_id,
                "status": "OK",
                "kwh": round(kwh_values[key], 2),
                "timestamp": ts
            })

        payload = {
            "device": plant_name,
            "timestamp": ts,
            "meters": meters_data
        }

        json_data = json.dumps(payload)
        sock.sendto(json_data.encode(), (UDP_IP, UDP_PORT))
        print("\nSent Data:")
        print(json_data)
        print("-" * 80)


def backfill_past_3_days(step_minutes=30):
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=3)
    cursor = start_dt
    while cursor <= end_dt:
        send_snapshot(cursor)
        cursor += timedelta(minutes=step_minutes)


# ================= MAIN LOOP =================

print("Backfilling past 3 days data...")
backfill_past_3_days(step_minutes=30)
print("Backfill complete. Starting live stream...")

while True:
    send_snapshot(datetime.now())
    time.sleep(20)
