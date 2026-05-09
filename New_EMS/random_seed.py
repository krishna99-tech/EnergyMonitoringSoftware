import socket
import json
import random
import time

# ================= UDP =================

UDP_IP = "192.168.0.179"
UDP_PORT = 6503

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

# ================= MAIN LOOP =================

while True:

    for plant_name, config in plants.items():

        meters_data = []

        # ================= INCOMER =================

        incomer = {

            "id": config["incomer"],

            "status": "OK",

            "freq": rand_float(49.8, 50.2),

            "volt": rand_float(410, 440),

            "curr": rand_float(100, 350),

            "pf": rand_float(0.85, 0.99),

            "kw": rand_float(50, 250),

            "kva": rand_float(60, 300)
        }

        meters_data.append(incomer)

        # ================= SUB METERS =================

        for meter_id in config["meters"]:

            key = f"{plant_name}_{meter_id}"

            # Increment KWH slowly
            increment = random.uniform(0.2, 2.5)

            kwh_values[key] += increment

            sub_meter = {

                "id": meter_id,

                "status": "OK",

                "kwh": round(kwh_values[key], 2)
            }

            meters_data.append(sub_meter)

        # ================= JSON =================

        payload = {

            "device": plant_name,

            "meters": meters_data
        }

        json_data = json.dumps(payload)

        # ================= SEND =================

        sock.sendto(
            json_data.encode(),
            (UDP_IP, UDP_PORT)
        )

        print("\nSent Data:")
        print(json_data)

        print("-" * 80)

    time.sleep(3)