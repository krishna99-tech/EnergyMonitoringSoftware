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


def random_meter(meter_id: int, device_name: str) -> dict:
    """Generate one meter's data. Returns OFFLINE for configured meters."""

    offline_list = OFFLINE_METERS.get(device_name, [])

    # Random transient failure: 5% chance any meter goes offline
    transient_fail = random.random() < 0.05

    if meter_id in offline_list or transient_fail:
        return {"id": meter_id, "status": "OFFLINE"}

    freq = round(random.uniform(49.5, 50.5), 2)
    volt = round(random.uniform(215.0, 235.0), 2)
    curr = round(random.uniform(1.0, 20.0), 2)
    pf   = round(random.uniform(0.75, 1.00), 3)
    kw   = round(volt * curr * pf / 1000, 3)
    kva  = round(volt * curr / 1000, 3)

    return {
        "id":     meter_id,
        "status": "OK",
        "freq":   freq,
        "volt":   volt,
        "curr":   curr,
        "pf":     pf,
        "kw":     kw,
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

        print(
            f"  [{time.strftime('%H:%M:%S')}] {device_name} "
            f"| online={online}  offline={offline} "
            f"| total kW={total_kw:.2f}"
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