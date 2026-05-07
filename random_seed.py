"""
simulate_esp32.py
─────────────────
Simulates 3 ESP32 devices, each sending 18 energy meter readings
over UDP to the Flask server (app.py).

Usage:
    python simulate_esp32.py

Config:
    Change SERVER_IP / SERVER_PORT / INTERVAL below as needed.
"""

import socket
import json
import time
import random
import threading

# ── CONFIG ────────────────────────────────────────────────────────
SERVER_IP   = "127.0.0.1"   # Change to your Flask server IP if remote
SERVER_PORT = 6503
INTERVAL    = 50              # seconds between each device transmission
NUM_METERS  = 18
ENERGY_STEP = 1.0             # fixed increment per send for online meters (kWh)
FIXED_PROFILE_MODE = True     # True => deterministic meter currents/PF (stable totals)
TRANSIENT_FAIL_RATE = 0.0     # 0.0 disables random temporary OFFLINE events
# ──────────────────────────────────────────────────────────────────

DEVICES = [
    "ESP32-BLOCK-A",
    "ESP32-BLOCK-B",
    "ESP32-BLOCK-C",
]

# Meters that are permanently offline per device (simulate real failures)
OFFLINE_METERS = {
    "ESP32-BLOCK-A": [],           # all online
    "ESP32-BLOCK-B": [5, 11],      # meters 5 and 11 offline
    "ESP32-BLOCK-C": [3, 14, 17],  # meters 3, 14, 17 offline
}

# Persistent cumulative energy per device/meter
# Key: (device_name, meter_id), Value: cumulative kWh
ENERGY_TOTALS = {}

# Deterministic base profiles for each meter (1..18).
# Used when FIXED_PROFILE_MODE=True so active power stays predictable.
METER_BASE = {
    1:  {"curr": 10.91, "pf": 0.894},
    2:  {"curr": 1.13,  "pf": 0.941},
    3:  {"curr": 3.98,  "pf": 0.810},
    4:  {"curr": 18.01, "pf": 0.816},
    5:  {"curr": 14.26, "pf": 0.880},
    6:  {"curr": 8.72,  "pf": 0.776},
    7:  {"curr": 7.53,  "pf": 0.934},
    8:  {"curr": 16.01, "pf": 0.764},
    9:  {"curr": 11.05, "pf": 0.951},
    10: {"curr": 15.20, "pf": 0.908},
    11: {"curr": 12.56, "pf": 0.782},
    12: {"curr": 18.71, "pf": 0.977},
    13: {"curr": 9.45,  "pf": 0.901},
    14: {"curr": 6.84,  "pf": 0.863},
    15: {"curr": 4.77,  "pf": 0.918},
    16: {"curr": 13.28, "pf": 0.846},
    17: {"curr": 2.95,  "pf": 0.889},
    18: {"curr": 17.03, "pf": 0.932},
}


def random_meter(meter_id: int, device_name: str) -> dict:
    """Generate one meter's data. Returns OFFLINE for configured meters."""

    offline_list = OFFLINE_METERS.get(device_name, [])

    transient_fail = random.random() < TRANSIENT_FAIL_RATE

    if meter_id in offline_list or transient_fail:
        return {"id": meter_id, "status": "OFFLINE"}

    if FIXED_PROFILE_MODE:
        base = METER_BASE.get(meter_id, {"curr": 8.0, "pf": 0.9})
        # Tiny bounded jitter keeps values "live" while staying near baseline.
        freq = round(50.0 + random.uniform(-0.25, 0.25), 2)
        volt = round(225.0 + random.uniform(-5.0, 5.0), 2)
        curr = round(base["curr"] + random.uniform(-0.20, 0.20), 2)
        pf = round(min(1.0, max(0.75, base["pf"] + random.uniform(-0.01, 0.01))), 3)
    else:
        freq = round(random.uniform(49.5, 50.5), 2)
        volt = round(random.uniform(215.0, 235.0), 2)
        curr = round(random.uniform(1.0, 20.0), 2)
        pf   = round(random.uniform(0.75, 1.00), 3)
    kw   = round(volt * curr * pf / 1000, 3)
    kva  = round(volt * curr / 1000, 3)
    key = (device_name, meter_id)
    prev_total = ENERGY_TOTALS.get(key, 0.0)
    kwh_total = round(prev_total + ENERGY_STEP, 3)
    ENERGY_TOTALS[key] = kwh_total

    return {
        "id":     meter_id,
        "status": "OK",
        "freq":   freq,
        "volt":   volt,
        "curr":   curr,
        "pf":     pf,
        "kw":     kw,
        "kwh_total": kwh_total,
        "kva":    kva,
    }


def build_payload(device_name: str) -> dict:
    """Build full JSON payload for one ESP32 device."""
    return {
        "device": device_name,
        "meters": [random_meter(i + 1, device_name) for i in range(NUM_METERS)],
    }


def send_udp(payload: dict, sock: socket.socket):
    """Serialize and send one UDP packet."""
    message = json.dumps(payload).encode("utf-8")
    sock.sendto(message, (SERVER_IP, SERVER_PORT))


def device_loop(device_name: str):
    """Thread loop: send data for one device every INTERVAL seconds."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[{device_name}] Starting → sending to {SERVER_IP}:{SERVER_PORT} every {INTERVAL}s")

    while True:
        payload = build_payload(device_name)
        send_udp(payload, sock)

        online  = sum(1 for m in payload["meters"] if m["status"] == "OK")
        offline = NUM_METERS - online
        total_kw = sum(m.get("kw", 0) for m in payload["meters"])
        total_kwh = sum(m.get("kwh_total", 0) for m in payload["meters"])

        print(
            f"  [{time.strftime('%H:%M:%S')}] {device_name} "
            f"| online={online}  offline={offline} "
            f"| total kW={total_kw:.2f}  total kWh={total_kwh:.2f}"
        )

        time.sleep(INTERVAL)


def main():
    print("=" * 55)
    print("  ESP32 Energy Monitor — UDP Simulator")
    print(f"  Target : {SERVER_IP}:{SERVER_PORT}")
    print(f"  Devices: {len(DEVICES)}  |  Meters/device: {NUM_METERS}")
    print(f"  Interval: {INTERVAL}s per device")
    print("=" * 55)

    threads = []
    for name in DEVICES:
        t = threading.Thread(target=device_loop, args=(name,), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(0.4)   # stagger startup slightly

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nSimulator stopped.")


if __name__ == "__main__":
    main()
